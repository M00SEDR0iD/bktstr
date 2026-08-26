from __future__ import annotations

import json
from pathlib import Path

import pytest

from bktstr.api.schemas import ExperimentEnvelope
from bktstr.services.experiments import (
    ExperimentStateError,
    ExperimentStatus,
    ExperimentStore,
    ExperimentWorker,
    IdempotencyConflictError,
    experiment_root,
)


def test_same_idempotency_key_returns_the_existing_canonical_experiment(tmp_path):
    """Changing duplicate handling must not silently create a second experiment."""
    store = ExperimentStore(tmp_path)

    first, made_first = store.create_experiment("backtest", {"symbol": "NVDA"}, "auto", "client-key")
    second, made_second = store.create_experiment("backtest", {"symbol": "NVDA"}, "auto", "client-key")

    assert made_first is True
    assert made_second is False
    assert second.experiment_id == first.experiment_id


def test_experiment_root_prefers_explicit_storage_then_railway_volume(monkeypatch):
    """Changing storage-root precedence could split Railway experiment history."""
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", "C:/explicit-experiments")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", "C:/railway-volume")
    assert experiment_root() == Path("C:/explicit-experiments")

    monkeypatch.delenv("BKTSTR_EXPERIMENT_DIR")
    assert experiment_root() == Path("C:/railway-volume/bktstr-experiments")


def test_idempotency_key_rejects_a_different_canonical_request(tmp_path):
    """A client-key collision must not make two different research inputs indistinguishable."""
    store = ExperimentStore(tmp_path)
    store.create_experiment("backtest", {"symbol": "NVDA"}, "auto", "client-key")

    with pytest.raises(IdempotencyConflictError):
        store.create_experiment("backtest", {"symbol": "AMD"}, "auto", "client-key")


def test_completed_record_is_immutable_and_writes_canonical_artifacts(tmp_path):
    """Overwriting a finished result would destroy reproducible research evidence."""
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("backtest", {"symbol": "NVDA", "z": 1}, "sync", None)

    completed = store.complete(
        record.experiment_id,
        {"metrics": {"trade_count": 1}},
        {"software": {"bktstr_version": "0.5.0"}},
    )

    assert completed.status is ExperimentStatus.COMPLETED
    artifact_dir = tmp_path / "artifacts" / record.experiment_id
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    generation = artifact_dir / "generations" / manifest["generation"]
    assert json.loads((generation / "request.json").read_text(encoding="utf-8")) == {"symbol": "NVDA", "z": 1}
    assert (generation / "request.json").read_bytes() == b'{"symbol":"NVDA","z":1}'
    assert json.loads((generation / "result.json").read_text(encoding="utf-8")) == {"metrics": {"trade_count": 1}}
    assert json.loads((generation / "provenance.json").read_text(encoding="utf-8")) == {
        "software": {"bktstr_version": "0.5.0"}
    }
    with pytest.raises(ExperimentStateError):
        store.complete(record.experiment_id, {"metrics": {}}, {})


def test_failed_artifact_publish_never_surfaces_an_uncommitted_terminal_generation(
    tmp_path, monkeypatch
):
    """A crash between SQLite commit and publication must recover from SQLite, not lie via files."""
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("backtest", {"symbol": "NVDA"}, "sync", None)
    previous_manifest = json.loads(
        (tmp_path / "artifacts" / record.experiment_id / "manifest.json").read_text("utf-8")
    )

    def interrupted(*_args, **_kwargs):
        raise OSError("simulated publish interruption")

    publish = store._publish_artifact_generation
    monkeypatch.setattr(store, "_publish_artifact_generation", interrupted)
    completed = store.complete(
        record.experiment_id,
        {"metrics": {"trade_count": 1}},
        {"source": "fixture"},
    )

    # SQLite is authoritative and the last manifest is still explicitly nonterminal.
    assert completed.status is ExperimentStatus.COMPLETED
    assert store.load_experiment(record.experiment_id).status is ExperimentStatus.COMPLETED
    assert json.loads(
        (tmp_path / "artifacts" / record.experiment_id / "manifest.json").read_text("utf-8")
    ) == previous_manifest

    monkeypatch.setattr(store, "_publish_artifact_generation", publish)
    assert store.reconcile_artifacts(record.experiment_id) == 1
    manifest = dict(store.load_artifact_manifest(record.experiment_id))
    assert manifest["status"] == "completed"
    generation = tmp_path / "artifacts" / record.experiment_id / "generations" / manifest["generation"]
    assert json.loads((generation / "result.json").read_text("utf-8")) == {"metrics": {"trade_count": 1}}
    assert store.load_experiment(record.experiment_id).status is ExperimentStatus.COMPLETED


def test_failed_publish_stays_dirty_until_bounded_reconciliation_clears_it(
    tmp_path, monkeypatch
):
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment(
        "backtest", {"symbol": "NVDA"}, "sync", None
    )
    publish = store._publish_artifact_generation
    monkeypatch.setattr(
        store,
        "_publish_artifact_generation",
        lambda _experiment_id: (_ for _ in ()).throw(OSError("interrupted")),
    )
    store.complete(record.experiment_id, {"metrics": {}}, {"source": "fixture"})

    with store._connect() as connection:
        dirty = connection.execute(
            "SELECT artifact_generation, artifact_published_generation "
            "FROM experiments WHERE experiment_id = ?",
            (record.experiment_id,),
        ).fetchone()
    assert dirty["artifact_generation"] != dirty["artifact_published_generation"]

    monkeypatch.setattr(store, "_publish_artifact_generation", publish)
    assert store.reconcile_artifacts(limit=1) == 1
    with store._connect() as connection:
        clean = connection.execute(
            "SELECT artifact_generation, artifact_published_generation "
            "FROM experiments WHERE experiment_id = ?",
            (record.experiment_id,),
        ).fetchone()
    assert clean["artifact_generation"] == clean["artifact_published_generation"]


def test_idle_worker_reconciliation_does_not_validate_every_published_artifact(
    tmp_path, monkeypatch
):
    store = ExperimentStore(tmp_path)
    for ordinal in range(5):
        record, _ = store.create_experiment(
            "backtest", {"ordinal": ordinal}, "sync", None
        )
        store.complete(record.experiment_id, {"ordinal": ordinal}, {"source": "fixture"})

    validated: list[str] = []
    original_validate = store._validated_manifest

    def observe_validation(row):
        validated.append(row["experiment_id"])
        return original_validate(row)

    monkeypatch.setattr(store, "_validated_manifest", observe_validation)
    worker = ExperimentWorker(store, {})

    assert worker.run_one() is None
    assert worker.run_one() is None
    assert validated == []


def test_manifest_publication_cannot_overwrite_a_later_terminal_generation(
    tmp_path, monkeypatch
):
    # Break caught: an older running publication could pass its generation check,
    # pause, and overwrite the completed manifest after the terminal transition.
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment(
        "backtest", {"symbol": "NVDA"}, "async", None
    )
    original_write = store._write_json
    running_manifest_ready = Event()
    allow_running_manifest = Event()
    completed_manifest_published = Event()
    delayed_once = False

    def delay_running_manifest(destination, canonical_json):
        nonlocal delayed_once
        payload = json.loads(canonical_json)
        if (
            destination.name == "manifest.json"
            and payload["status"] == "running"
            and not delayed_once
        ):
            delayed_once = True
            running_manifest_ready.set()
            assert allow_running_manifest.wait(2)
        original_write(destination, canonical_json)
        if destination.name == "manifest.json" and payload["status"] == "completed":
            completed_manifest_published.set()

    monkeypatch.setattr(store, "_write_json", delay_running_manifest)
    with ThreadPoolExecutor(max_workers=2) as executor:
        claim_future = executor.submit(store.claim, record.experiment_id)
        assert running_manifest_ready.wait(2)
        complete_future = executor.submit(
            store.complete,
            record.experiment_id,
            {"metrics": {"trade_count": 1}},
            {"source": "fixture"},
        )
        assert not completed_manifest_published.wait(0.25)
        allow_running_manifest.set()
        assert claim_future.result().status is ExperimentStatus.RUNNING
        assert complete_future.result().status is ExperimentStatus.COMPLETED

    manifest = json.loads(
        (
            tmp_path / "artifacts" / record.experiment_id / "manifest.json"
        ).read_text("utf-8")
    )
    assert manifest["status"] == "completed"
    assert dict(store.load_artifact_manifest(record.experiment_id)) == manifest


def test_reconciliation_rebuilds_a_corrupted_existing_generation_from_sqlite(tmp_path):
    # Break caught: a content-addressed directory could exist with corrupted files,
    # causing reconciliation to republish a manifest that can never validate.
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment(
        "backtest", {"symbol": "NVDA"}, "sync", None
    )
    completed = store.complete(
        record.experiment_id,
        {"metrics": {"trade_count": 1}},
        {"source": "fixture"},
    )
    artifact_dir = tmp_path / "artifacts" / completed.experiment_id
    manifest = json.loads((artifact_dir / "manifest.json").read_text("utf-8"))
    result_path = (
        artifact_dir / "generations" / manifest["generation"] / "result.json"
    )
    result_path.write_text('{"metrics":{"trade_count":999}}', encoding="utf-8")

    assert store.reconcile_artifacts(completed.experiment_id) == 1
    assert json.loads(result_path.read_text("utf-8")) == {
        "metrics": {"trade_count": 1}
    }
    assert dict(store.load_artifact_manifest(completed.experiment_id))["generation"] == (
        manifest["generation"]
    )

    result_path.write_text("corrupt", encoding="utf-8")
    reopened = ExperimentStore(tmp_path)
    assert dict(reopened.load_artifact_manifest(completed.experiment_id))["status"] == (
        "completed"
    )
    assert json.loads(result_path.read_text("utf-8")) == {
        "metrics": {"trade_count": 1}
    }


def test_failed_creation_transaction_publishes_no_artifact_generation(tmp_path, monkeypatch):
    """A creation transaction failure cannot leave an artifact a later reader could trust."""
    import sqlite3

    store = ExperimentStore(tmp_path)

    def interrupted(*_args, **_kwargs):
        raise sqlite3.OperationalError("simulated transaction failure")

    monkeypatch.setattr(store, "_set_artifact_generation", interrupted)
    with pytest.raises(sqlite3.OperationalError, match="transaction failure"):
        store.create_experiment("backtest", {"symbol": "NVDA"}, "async", None)

    assert list((tmp_path / "artifacts").iterdir()) == []
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0] == 0


def test_reopened_store_loads_terminal_records_and_rejects_non_finite_json(tmp_path):
    """Persisted records must survive a restart without accepting non-reproducible JSON."""
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("backtest", {"symbol": "NVDA"}, "sync", None)
    store.complete(record.experiment_id, {"metrics": {"trade_count": 1}}, {"source": "fixture"})

    reopened = ExperimentStore(tmp_path)
    loaded = reopened.load_experiment(record.experiment_id)

    assert loaded == store.load_experiment(record.experiment_id)
    with pytest.raises(ValueError, match="non-finite|NaN"):
        reopened.create_experiment("backtest", {"metric": float("nan")}, "auto", None)


def test_claim_next_and_fail_follow_the_experiment_lifecycle(tmp_path):
    """A worker must claim a queued record once and preserve a terminal failure."""
    store = ExperimentStore(tmp_path)
    queued, _ = store.create_experiment("compare", {"ids": ["exp_a", "exp_b"]}, "async", None)

    claimed = store.claim_next()
    failed = store.fail(queued.experiment_id, {"code": "provider_error", "message": "unavailable"})

    assert claimed is not None
    assert claimed.status is ExperimentStatus.RUNNING
    assert failed.status is ExperimentStatus.FAILED
    assert failed.error == {"code": "provider_error", "message": "unavailable"}
    assert store.claim_next() is None
    with pytest.raises(ExperimentStateError):
        store.fail(queued.experiment_id, {"code": "retry"})


def test_api_envelope_projects_immutable_service_records_as_typed_json(tmp_path):
    """Removing API-edge conversion would expose service-only mappings to clients."""
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("backtest", {"symbol": "NVDA"}, "sync", None)
    completed = store.complete(
        record.experiment_id,
        {"metrics": {"trade_count": 1}},
        {"software": {"bktstr_version": "0.5.0"}},
    )

    payload = ExperimentEnvelope.from_record(completed).model_dump(mode="json")

    assert payload["status"] == "completed"
    assert payload["execution"] == "sync"
    assert payload["request"] == {"symbol": "NVDA"}
    assert payload["result"] == {"metrics": {"trade_count": 1}}
