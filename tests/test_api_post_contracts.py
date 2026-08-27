from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

import bktstr.api.routes as api_routes
import bktstr.services.backtest as backtest_service
from bktstr.api.app import create_app
from bktstr.services.experiments import ExperimentWorker
from research_fixtures import deterministic_research_result


AUTH = {"Authorization": "Bearer test-key"}
BACKTEST_ASYNC_BODY = {
    "strategy": {
        "id": "bktstr.bearish-regime-scalp",
        "version": "1.0.0",
        "parameters": {"stop_pct": 1.0, "target_pct": 3.0},
    },
    "market": {
        "symbol": "NVDA",
        "start": "2026-08-17",
        "end": "2026-08-17",
        "timeframe": "1m",
        "source": "auto",
    },
    "side": "short",
    "entry": "close.cross_below:vwap",
    "regime": None,
    "execution": "async",
    "include_trades": True,
}
SWEEP_BODY = {
    "base": BACKTEST_ASYNC_BODY,
    "grid": {"stop_pct": [1.0]},
    "objective": "profit_factor",
    "execution": "async",
}
COMPARE_BODY = {
    "candidates": [
        {"name": "control", "backtest": BACKTEST_ASYNC_BODY},
        {
            "name": "wide-stop",
            "backtest": {
                **BACKTEST_ASYNC_BODY,
                "strategy": {
                    **BACKTEST_ASYNC_BODY["strategy"],
                    "parameters": {"stop_pct": 2.0, "target_pct": 3.0},
                },
            },
        },
    ],
    "execution": "async",
}
REGIME_BODY = {
    "base": BACKTEST_ASYNC_BODY,
    "labels": [
        {"label": "first-day", "start": "2026-08-17", "end": "2026-08-17"},
        {"label": "second-day", "start": "2026-08-18", "end": "2026-08-18"},
    ],
    "disjoint_periods": True,
    "execution": "async",
}
POST_CASES = (
    ("/api/v1/backtests", BACKTEST_ASYNC_BODY),
    ("/api/v1/parameter-sweeps", SWEEP_BODY),
    ("/api/v1/compare", COMPARE_BODY),
    ("/api/v1/regime-comparison", REGIME_BODY),
)


@contextmanager
def _client(monkeypatch, tmp_path):
    async def deterministic(value):
        return deterministic_research_result(value)

    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))
    monkeypatch.setattr(ExperimentWorker, "run_forever", lambda self, stop_event: None)
    monkeypatch.setattr(backtest_service, "run_backtest", deterministic)
    monkeypatch.setattr(api_routes, "run_backtest", deterministic)
    with TestClient(create_app()) as client:
        yield client


@pytest.mark.parametrize("path,body", POST_CASES)
def test_post_routes_require_authentication_and_reject_invalid_schema(
    monkeypatch, tmp_path, path, body
):
    # Break caught: a POST route could bypass the shared authentication or schema boundary.
    invalid = deepcopy(body)
    invalid["unexpected"] = True
    with _client(monkeypatch, tmp_path) as client:
        unauthorized = client.post(path, json=body)
        malformed = client.post(path, json=invalid, headers=AUTH)

    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "unauthorized"
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "validation_error"
    assert malformed.headers["x-request-id"].startswith("req_")


@pytest.mark.parametrize(
    ("path", "body", "operation", "result_key"),
    [
        ("/api/v1/backtests", BACKTEST_ASYNC_BODY, "backtest", "metrics"),
        ("/api/v1/parameter-sweeps", SWEEP_BODY, "parameter_sweep", "variants"),
        ("/api/v1/compare", COMPARE_BODY, "compare", "candidates"),
        ("/api/v1/regime-comparison", REGIME_BODY, "regime_comparison", "items"),
    ],
)
def test_post_route_persists_executes_and_polls_typed_terminal_result(
    monkeypatch, tmp_path, path, body, operation, result_key
):
    # Break caught: queued POST work could lose polling metadata or a typed terminal result.
    with _client(monkeypatch, tmp_path) as client:
        accepted = client.post(path, json=body, headers=AUTH)
        experiment_id = accepted.json()["experiment_id"]
        client.app.state.experiment_worker.run(experiment_id)
        completed = client.get(f"/api/v1/experiments/{experiment_id}", headers=AUTH)

    assert accepted.status_code == 202
    assert accepted.headers["location"] == accepted.json()["status_url"]
    assert accepted.headers["retry-after"] == "2"
    assert completed.status_code == 200
    assert completed.json()["operation"] == operation
    assert completed.json()["status"] == "completed"
    assert completed.json()["error"] is None
    assert result_key in completed.json()["result"]
    assert completed.json()["retry_after_seconds"] is None


def _different_payload(path, body):
    changed = deepcopy(body)
    if path == "/api/v1/backtests":
        changed["include_trades"] = False
    elif path == "/api/v1/parameter-sweeps":
        changed["objective"] = "sharpe"
    elif path == "/api/v1/compare":
        changed["candidates"][1]["name"] = "wider-stop"
    elif path == "/api/v1/regime-comparison":
        changed["disjoint_periods"] = False
    else:
        raise AssertionError(f"Unhandled POST path: {path}")
    return changed


@pytest.mark.parametrize("path,body", POST_CASES)
def test_post_route_idempotency_replays_same_payload_and_conflicts_on_change(
    monkeypatch, tmp_path, path, body
):
    # Break caught: a shared route could duplicate work or silently reuse a key for new input.
    headers = {**AUTH, "Idempotency-Key": "contract-key"}
    with _client(monkeypatch, tmp_path) as client:
        first = client.post(path, json=body, headers=headers)
        replay = client.post(path, json=body, headers=headers)
        conflict = client.post(
            path, json=_different_payload(path, body), headers=headers
        )

    assert replay.status_code == first.status_code == 202
    assert replay.json()["experiment_id"] == first.json()["experiment_id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert conflict.headers["x-request-id"].startswith("req_")


def test_idempotency_keys_are_scoped_to_the_operation(monkeypatch, tmp_path):
    # Break caught: one key could collide between unrelated POST operation types.
    headers = {**AUTH, "Idempotency-Key": "cross-route-key"}
    with _client(monkeypatch, tmp_path) as client:
        backtest = client.post(
            "/api/v1/backtests", json=BACKTEST_ASYNC_BODY, headers=headers
        )
        comparison = client.post(
            "/api/v1/compare", json=COMPARE_BODY, headers=headers
        )

    assert backtest.status_code == comparison.status_code == 202
    assert backtest.json()["experiment_id"] != comparison.json()["experiment_id"]
