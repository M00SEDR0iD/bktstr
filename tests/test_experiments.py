from __future__ import annotations

import json
from pathlib import Path

import pytest

from bktstr.api.schemas import ExperimentEnvelope
from bktstr.services.experiments import (
    ExperimentStateError,
    ExperimentStatus,
    ExperimentStore,
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
    assert json.loads((artifact_dir / "request.json").read_text(encoding="utf-8")) == {"symbol": "NVDA", "z": 1}
    assert (artifact_dir / "request.json").read_bytes() == b'{"symbol":"NVDA","z":1}'
    assert json.loads((artifact_dir / "result.json").read_text(encoding="utf-8")) == {"metrics": {"trade_count": 1}}
    assert json.loads((artifact_dir / "provenance.json").read_text(encoding="utf-8")) == {
        "software": {"bktstr_version": "0.5.0"}
    }
    with pytest.raises(ExperimentStateError):
        store.complete(record.experiment_id, {"metrics": {}}, {})


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
