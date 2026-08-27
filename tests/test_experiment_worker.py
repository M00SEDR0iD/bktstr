from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import threading

import pytest
import httpx

from bktstr.services.experiments import (
    ExecutionMode,
    ExecutionNotAvailableError,
    ExecutionPolicy,
    ExperimentStatus,
    ExperimentStore,
    ExperimentWorker,
    submit,
)


def test_auto_runs_bounded_backtest_inline_and_queues_sweep():
    """A policy regression must not make inexpensive research jobs require polling."""
    policy = ExecutionPolicy(sync_max_calendar_days=31)

    assert policy.choose("backtest", ExecutionMode.AUTO, calendar_days=1) is ExecutionMode.SYNC
    assert policy.choose("parameter_sweep", ExecutionMode.AUTO, calendar_days=1) is ExecutionMode.ASYNC


def test_sync_request_outside_policy_raises_stable_error():
    """An oversized inline request must fail explicitly instead of blocking the API worker."""
    with pytest.raises(ExecutionNotAvailableError) as raised:
        ExecutionPolicy(sync_max_calendar_days=31).choose(
            "backtest", ExecutionMode.SYNC, calendar_days=32
        )

    assert raised.value.code == "execution_not_available"


def test_worker_completes_a_queued_record_after_restart(tmp_path):
    """A durable queued experiment must remain executable after its creating process exits."""
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("parameter_sweep", {"grid": {}}, "async", None)

    restarted_store = ExperimentStore(tmp_path)
    worker = ExperimentWorker(
        restarted_store,
        {"parameter_sweep": lambda _: ({"items": []}, {"source": "fixture"})},
    )

    completed = worker.run_one()

    assert completed is not None
    assert completed.status is ExperimentStatus.COMPLETED
    assert list(restarted_store.load_experiment(record.experiment_id).result["items"]) == []  # type: ignore[index]


def test_recover_incomplete_returns_stale_running_work_to_the_queue(tmp_path):
    """Only an expired prior lease may return claimed work to the queue."""
    current = [datetime(2026, 8, 25, tzinfo=timezone.utc)]
    first_store = ExperimentStore(tmp_path)
    second_store = ExperimentStore(tmp_path)
    record, _ = first_store.create_experiment(
        "compare", {"ids": []}, "async", None
    )
    first = ExperimentWorker(
        first_store,
        {},
        owner_id="worker-one",
        lease_duration_seconds=10,
        clock=lambda: current[0],
    )
    second = ExperimentWorker(
        second_store,
        {},
        owner_id="worker-two",
        lease_duration_seconds=10,
        clock=lambda: current[0],
    )

    assert first.recover_incomplete() == 0
    claimed = first_store.claim_next(first.owner_id, now=current[0])
    assert claimed is not None
    assert second.recover_incomplete() == 0
    assert second_store.load_experiment(record.experiment_id).status is ExperimentStatus.RUNNING

    current[0] += timedelta(seconds=11)
    assert second.recover_incomplete() == 1
    assert second_store.load_experiment(record.experiment_id).status is ExperimentStatus.QUEUED


def test_active_worker_lease_excludes_an_overlapping_instance_and_heartbeats(
    tmp_path, monkeypatch
):
    first_store = ExperimentStore(tmp_path)
    second_store = ExperimentStore(tmp_path)
    record, _ = first_store.create_experiment(
        "backtest", {"symbol": "NVDA"}, "async", None
    )
    entered = threading.Event()
    renewed = threading.Event()
    release = threading.Event()
    stop = threading.Event()
    original_renew = first_store.renew_worker_lease

    def observe_renewal(*args, **kwargs):
        renewed.set()
        return original_renew(*args, **kwargs)

    monkeypatch.setattr(first_store, "renew_worker_lease", observe_renewal)

    def execute(_record):
        entered.set()
        assert release.wait(2)
        stop.set()
        return {"ok": True}, {"source": "fixture"}

    first = ExperimentWorker(
        first_store,
        {"backtest": execute},
        poll_interval_seconds=0.01,
        lease_duration_seconds=0.3,
        heartbeat_interval_seconds=0.03,
    )
    second = ExperimentWorker(
        second_store,
        {"backtest": execute},
        lease_duration_seconds=0.3,
        heartbeat_interval_seconds=0.03,
    )
    thread = threading.Thread(target=first.run_forever, args=(stop,))
    thread.start()

    assert entered.wait(2)
    assert renewed.wait(2)
    assert second.run_one() is None
    assert second_store.load_experiment(record.experiment_id).status is ExperimentStatus.RUNNING
    release.set()
    thread.join(3)

    assert not thread.is_alive()
    assert second_store.load_experiment(record.experiment_id).status is ExperimentStatus.COMPLETED
    assert second_store.acquire_worker_lease(
        second.owner_id, lease_duration_seconds=0.3
    )


def test_terminal_completion_race_does_not_stop_the_worker_loop(tmp_path):
    store = ExperimentStore(tmp_path)
    first, _ = store.create_experiment("backtest", {"ordinal": 1}, "async", None)
    second, _ = store.create_experiment("backtest", {"ordinal": 2}, "async", None)
    stop = threading.Event()

    def execute(record):
        if record.experiment_id == first.experiment_id:
            store.complete(
                record.experiment_id,
                {"ordinal": 1, "winner": "other instance"},
                {"source": "fixture"},
            )
        else:
            stop.set()
        return {"ordinal": record.request["ordinal"]}, {"source": "fixture"}

    thread = threading.Thread(
        target=ExperimentWorker(
            store, {"backtest": execute}, poll_interval_seconds=0.01
        ).run_forever,
        args=(stop,),
    )
    thread.start()
    thread.join(3)

    assert not thread.is_alive()
    assert store.load_experiment(first.experiment_id).status is ExperimentStatus.COMPLETED
    assert store.load_experiment(second.experiment_id).status is ExperimentStatus.COMPLETED


def test_submit_runs_an_auto_bounded_backtest_inline(tmp_path):
    """Changing submit to only queue bounded backtests would degrade normal API calls."""
    store = ExperimentStore(tmp_path)

    record = submit(
        store,
        {"backtest": lambda _: ({"metrics": {"trade_count": 1}}, {"source": "fixture"})},
        "backtest",
        {"symbol": "NVDA"},
        execution=ExecutionMode.AUTO,
        calendar_days=1,
    )

    assert record.status is ExperimentStatus.COMPLETED
    assert record.execution is ExecutionMode.SYNC


def test_worker_persists_provider_failures_with_a_stable_error_code(tmp_path):
    """A provider outage must be queryable research state rather than a lost worker exception."""
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("backtest", {"symbol": "NVDA"}, "async", None)

    def unavailable(_: object):
        raise httpx.ConnectError("provider unavailable")

    failed = ExperimentWorker(store, {"backtest": unavailable}).run_one()

    assert failed is not None
    assert failed.status is ExperimentStatus.FAILED
    assert failed.error == {
        "code": "market_data_http_error",
        "message": "Market-data provider request failed.",
        "details": {
            "stage": "execution",
            "exception_type": "ConnectError",
        },
    }


def test_worker_persists_redacted_unexpected_failure_details(monkeypatch, tmp_path):
    monkeypatch.setenv("BKTSTR_API_KEY", "service-secret")
    monkeypatch.setenv("MASSIVE_API_KEY", "provider-secret")
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("compare", {"candidates": []}, "async")

    def fail(_):
        raise RuntimeError(
            "Bearer service-secret provider-secret "
            "https://provider.example/data?apiKey=provider-secret"
        )

    failed = ExperimentWorker(store, {"compare": fail}).run(record.experiment_id)

    assert failed.error["code"] == "operation_failed"
    assert failed.error["details"] == {
        "stage": "execution",
        "exception_type": "RuntimeError",
    }
    rendered = json.dumps(dict(failed.error), default=dict)
    assert "service-secret" not in rendered
    assert "provider-secret" not in rendered
    assert "apiKey=" not in rendered
    assert "[redacted]" in failed.error["message"]


@pytest.mark.parametrize(
    ("payload", "secret"),
    [
        ("Authorization: Basic basic-auth-secret", "basic-auth-secret"),
        ("X-API-Key: unconfigured-api-key", "unconfigured-api-key"),
        ("/data?apiKey=relative-query-secret", "relative-query-secret"),
        ("prices?token=short-query-secret", "short-query-secret"),
        ("provider response body: raw-provider-body", "raw-provider-body"),
        ("response_body: short-body-secret", "short-body-secret"),
        ("provider body raw-body-secret", "raw-body-secret"),
        ('{"detail": "private-json-value"}', "private-json-value"),
        (
            "Traceback (most recent call last):\\nBKTSTR_API_KEY=environment-secret",
            "environment-secret",
        ),
        ("Traceback: raw-trace-secret", "raw-trace-secret"),
        ("{'HOME': 'home-directory-secret'}", "home-directory-secret"),
        ("provider rejected sk-proj-unconfigured-secret", "sk-proj-unconfigured-secret"),
    ],
)
def test_worker_persists_redacted_adversarial_unexpected_failure_details(
    tmp_path, payload, secret
):
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("compare", {"candidates": []}, "async")

    def fail(_):
        raise RuntimeError(payload)

    failed = ExperimentWorker(store, {"compare": fail}).run(record.experiment_id)

    assert failed.error["code"] == "operation_failed"
    assert failed.error["message"] == "The experiment operation failed."
    assert failed.error["details"] == {
        "stage": "execution",
        "exception_type": "RuntimeError",
    }
    assert secret not in json.dumps(dict(failed.error), default=dict)


def test_worker_classifies_retryable_provider_failures(tmp_path):
    store = ExperimentStore(tmp_path)
    store.create_experiment("backtest", {"symbol": "NVDA"}, "async")
    request = httpx.Request("GET", "https://provider.example/data")
    response = httpx.Response(429, request=request)

    def rate_limited(_):
        raise httpx.HTTPStatusError(
            "rate limited", request=request, response=response
        )

    failed = ExperimentWorker(store, {"backtest": rate_limited}).run_one()

    assert failed.error == {
        "code": "market_data_http_error",
        "message": "Market-data provider request failed.",
        "details": {
            "stage": "execution",
            "exception_type": "HTTPStatusError",
            "status_code": 429,
            "retryable": True,
        },
    }


def test_reserved_inline_experiment_is_not_claimable_by_the_polling_worker(tmp_path):
    """A polling worker must never steal a just-created inline backtest."""
    store = ExperimentStore(tmp_path)

    reserved, created = store.create_and_claim_experiment(
        "backtest", {"symbol": "NVDA"}, ExecutionMode.SYNC, None
    )

    assert created is True
    assert reserved.status is ExperimentStatus.RUNNING
    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(ExperimentWorker(store, {}).run_one).result() is None


def test_worker_terminalizes_result_persistence_errors_and_keeps_processing(
    tmp_path, monkeypatch
):
    """A persistence error must fail only its experiment, not strand or stop the worker."""
    store = ExperimentStore(tmp_path)
    bad, _ = store.create_experiment("backtest", {"invalid": True}, "async", None)
    good, _ = store.create_experiment("backtest", {"invalid": False}, "async", None)
    original_complete = store.complete

    def persist(experiment_id, *args, **kwargs):
        if experiment_id == bad.experiment_id:
            raise RuntimeError("disk unavailable")
        return original_complete(experiment_id, *args, **kwargs)

    monkeypatch.setattr(store, "complete", persist)

    def results(record):
        return {"metric": int(not record.request["invalid"])}, {"source": "fixture"}

    worker = ExperimentWorker(store, {"backtest": results})
    failed = worker.run_one()
    completed = worker.run_one()

    assert failed is not None
    assert failed.status is ExperimentStatus.FAILED
    assert failed.error == {
        "code": "result_persistence_failed",
        "message": "disk unavailable",
        "details": {
            "stage": "persistence",
            "exception_type": "RuntimeError",
        },
    }
    assert completed is not None
    assert completed.status is ExperimentStatus.COMPLETED
    assert store.load_experiment(bad.experiment_id).status is ExperimentStatus.FAILED
    assert store.load_experiment(good.experiment_id).status is ExperimentStatus.COMPLETED


def test_worker_redacts_sensitive_result_persistence_errors(tmp_path, monkeypatch):
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("backtest", {"symbol": "NVDA"}, "async")

    def persist(*_args, **_kwargs):
        raise RuntimeError(
            "Authorization: Basic persistence-auth-secret "
            "/data?apiKey=persistence-query-secret"
        )

    monkeypatch.setattr(store, "complete", persist)

    failed = ExperimentWorker(
        store, {"backtest": lambda _: ({"metric": 1}, {"source": "fixture"})}
    ).run(record.experiment_id)

    assert failed.error == {
        "code": "result_persistence_failed",
        "message": "Experiment result persistence failed.",
        "details": {
            "stage": "persistence",
            "exception_type": "RuntimeError",
        },
    }
    rendered = json.dumps(dict(failed.error), default=dict)
    assert "persistence-auth-secret" not in rendered
    assert "persistence-query-secret" not in rendered


def test_worker_survives_completed_projection_failure_and_repairs_on_next_iteration(
    tmp_path, monkeypatch
):
    # Break caught: a post-commit manifest failure could make fail() attack an
    # immutable completed row and terminate the polling loop before later work.
    store = ExperimentStore(tmp_path)
    first, _ = store.create_experiment(
        "backtest", {"ordinal": 1}, "async", None
    )
    second, _ = store.create_experiment(
        "backtest", {"ordinal": 2}, "async", None
    )
    original_publish = store._publish_artifact_generation
    interrupted = False

    def interrupt_first_completion(experiment_id):
        nonlocal interrupted
        current = store.load_experiment(experiment_id)
        if (
            experiment_id == first.experiment_id
            and current.status is ExperimentStatus.COMPLETED
            and not interrupted
        ):
            interrupted = True
            raise OSError("simulated completed projection failure")
        original_publish(experiment_id)

    monkeypatch.setattr(
        store, "_publish_artifact_generation", interrupt_first_completion
    )
    stop_event = threading.Event()

    def execute(record):
        if record.experiment_id == second.experiment_id:
            stop_event.set()
        return {"ordinal": record.request["ordinal"]}, {"source": "fixture"}

    worker_thread = threading.Thread(
        target=ExperimentWorker(store, {"backtest": execute}).run_forever,
        args=(stop_event,),
    )
    worker_thread.start()
    worker_thread.join(3)

    assert not worker_thread.is_alive()
    assert store.load_experiment(first.experiment_id).status is ExperimentStatus.COMPLETED
    assert store.load_experiment(second.experiment_id).status is ExperimentStatus.COMPLETED
    assert dict(store.load_artifact_manifest(first.experiment_id))["status"] == "completed"


def test_inline_completion_returns_committed_result_when_projection_fails(
    tmp_path, monkeypatch
):
    # Break caught: a bounded inline request could return an error even though its
    # authoritative result had already committed successfully.
    store = ExperimentStore(tmp_path)
    original_publish = store._publish_artifact_generation

    def interrupt_completion(experiment_id):
        if store.load_experiment(experiment_id).status is ExperimentStatus.COMPLETED:
            raise OSError("simulated inline projection failure")
        original_publish(experiment_id)

    monkeypatch.setattr(store, "_publish_artifact_generation", interrupt_completion)
    record = submit(
        store,
        {"backtest": lambda _: ({"metric": 1}, {"source": "fixture"})},
        "backtest",
        {"symbol": "NVDA"},
        execution=ExecutionMode.SYNC,
        calendar_days=1,
    )

    assert record.status is ExperimentStatus.COMPLETED
    assert record.result == {"metric": 1}
