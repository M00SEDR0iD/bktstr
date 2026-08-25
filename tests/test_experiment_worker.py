from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

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
    """A process crash must not strand its claimed experiment in the running state."""
    store = ExperimentStore(tmp_path)
    record, _ = store.create_experiment("compare", {"ids": []}, "async", None)
    assert store.claim_next() is not None

    recovered = ExperimentWorker(store, {}).recover_incomplete()

    assert recovered == 1
    assert store.load_experiment(record.experiment_id).status is ExperimentStatus.QUEUED


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
        "details": {},
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


def test_worker_terminalizes_result_persistence_errors_and_keeps_processing(tmp_path):
    """An invalid completed result must fail only its experiment, not strand or stop the worker."""
    store = ExperimentStore(tmp_path)
    bad, _ = store.create_experiment("backtest", {"invalid": True}, "async", None)
    good, _ = store.create_experiment("backtest", {"invalid": False}, "async", None)

    def results(record):
        value = float("nan") if record.request["invalid"] else 1
        return {"metric": value}, {"source": "fixture"}

    worker = ExperimentWorker(store, {"backtest": results})
    failed = worker.run_one()
    completed = worker.run_one()

    assert failed is not None
    assert failed.status is ExperimentStatus.FAILED
    assert failed.error == {
        "code": "result_persistence_failed",
        "message": "Experiment result persistence failed.",
        "details": {},
    }
    assert completed is not None
    assert completed.status is ExperimentStatus.COMPLETED
    assert store.load_experiment(bad.experiment_id).status is ExperimentStatus.FAILED
    assert store.load_experiment(good.experiment_id).status is ExperimentStatus.COMPLETED
