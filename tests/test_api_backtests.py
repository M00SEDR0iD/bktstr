from __future__ import annotations

from contextlib import contextmanager
from types import MappingProxyType

import pytest
from fastapi.testclient import TestClient

import bktstr.api.routes as api_routes
from bktstr.api.app import create_app
from bktstr.services.backtest import (
    BacktestConfiguration,
    BacktestMetrics,
    BacktestResearchResult,
    ResearchProvenance,
)
from bktstr.services.experiments import ExperimentWorker


AUTH = {"Authorization": "Bearer test-key"}
BACKTEST_BODY = {
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
    "execution": "auto",
    "include_trades": True,
}


def _research_result(value) -> BacktestResearchResult:
    strategy = MappingProxyType(
        {
            "id": value.strategy_id,
            "version": value.strategy_version,
            "schema_version": "1.0.0",
            "parameters": dict(value.parameters),
        }
    )
    return BacktestResearchResult(
        metrics=BacktestMetrics(
            total_pnl=12.5,
            total_return=0.125,
            ev_per_trade=12.5,
            win_rate=100.0,
            profit_factor=None,
            max_drawdown=0.0,
            sharpe=None,
            trade_count=1,
        ),
        trades=(),
        configuration=BacktestConfiguration(
            strategy=strategy,
            market=MappingProxyType(
                {
                    "symbol": value.symbol,
                    "start": value.start.isoformat(),
                    "end": value.end.isoformat(),
                    "timeframe": value.timeframe,
                    "source": value.source,
                }
            ),
            regime=MappingProxyType({"enabled": False}),
            execution=MappingProxyType(
                {
                    "mode": value.execution,
                    "model_id": "bktstr.next-bar-open",
                    "model_version": "1.0.0",
                    "slippage_bps": 2.0,
                    "position_size": 1000.0,
                    "starting_capital": 10000.0,
                }
            ),
        ),
        provenance=ResearchProvenance(
            strategy=strategy,
            market_data=MappingProxyType(
                {
                    "source": "fixture",
                    "requested_source": value.source,
                    "version": "fixture-v1",
                    "coverage": {
                        "requested_start": value.start.isoformat(),
                        "requested_end": value.end.isoformat(),
                        "bars": 3,
                    },
                }
            ),
            execution_model=MappingProxyType(
                {"id": "bktstr.next-bar-open", "version": "1.0.0", "slippage_bps": 2.0}
            ),
            software=MappingProxyType(
                {"bktstr_version": "0.5.0", "git_commit": "fixture-commit"}
            ),
        ),
    )


@contextmanager
def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))

    async def deterministic_backtest(value):
        return _research_result(value)

    monkeypatch.setattr(api_routes, "run_backtest", deterministic_backtest)
    with TestClient(create_app()) as client:
        yield client


def test_completed_backtest_returns_typed_experiment(monkeypatch, tmp_path):
    # Break caught: a bounded request could bypass persistence or lose research fields.
    with _client(monkeypatch, tmp_path) as client:
        response = client.post("/api/v1/backtests", json=BACKTEST_BODY, headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["experiment_id"].startswith("exp_")
    assert {"metrics", "trades", "configuration", "provenance"} <= body["result"].keys()
    assert body["request"] == BACKTEST_BODY


def test_async_idempotent_submission_can_be_polled(monkeypatch, tmp_path):
    # Break caught: a retry could duplicate durable research or become unpollable.
    monkeypatch.setattr(ExperimentWorker, "run_forever", lambda self, stop_event: None)
    with _client(monkeypatch, tmp_path) as client:
        headers = {**AUTH, "Idempotency-Key": "once"}
        request = {**BACKTEST_BODY, "execution": "async"}
        first = client.post("/api/v1/backtests", json=request, headers=headers)
        second = client.post("/api/v1/backtests", json=request, headers=headers)
        experiment_id = first.json()["experiment_id"]
        polled = client.get(f"/api/v1/experiments/{experiment_id}", headers=AUTH)
        backtest = client.get(f"/api/v1/backtests/{experiment_id}", headers=AUTH)

    assert first.status_code == second.status_code == 202
    assert second.json()["experiment_id"] == experiment_id
    assert polled.status_code == 200
    assert polled.json()["experiment_id"] == experiment_id
    assert backtest.status_code == 200
    assert backtest.json()["operation"] == "backtest"


def test_completed_async_idempotent_retry_returns_current_terminal_state(monkeypatch, tmp_path):
    # Break caught: a completed idempotent retry could be mislabeled as newly accepted work.
    monkeypatch.setattr(ExperimentWorker, "run_forever", lambda self, stop_event: None)
    with _client(monkeypatch, tmp_path) as client:
        headers = {**AUTH, "Idempotency-Key": "completed-retry"}
        request = {**BACKTEST_BODY, "execution": "async"}
        first = client.post("/api/v1/backtests", json=request, headers=headers)
        completed = client.app.state.experiment_worker.run_one()
        second = client.post("/api/v1/backtests", json=request, headers=headers)

    assert first.status_code == 202
    assert completed is not None and completed.status == "completed"
    assert second.status_code == 200
    assert second.json()["status"] == "completed"


def test_reusing_idempotency_key_for_different_request_is_a_conflict(monkeypatch, tmp_path):
    # Break caught: one client key could silently alias two distinct hypotheses.
    with _client(monkeypatch, tmp_path) as client:
        headers = {**AUTH, "Idempotency-Key": "one-hypothesis"}
        assert client.post(
            "/api/v1/backtests",
            json={**BACKTEST_BODY, "execution": "async"},
            headers=headers,
        ).status_code == 202
        response = client.post(
            "/api/v1/backtests",
            json={
                **BACKTEST_BODY,
                "market": {**BACKTEST_BODY["market"], "symbol": "AMD"},
                "execution": "async",
            },
            headers=headers,
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"


@pytest.mark.parametrize("key", ["", "contains space", "x" * 129])
def test_idempotency_key_requires_visible_bounded_ascii(monkeypatch, tmp_path, key):
    # Break caught: ambiguous or unbounded keys could enter the durable uniqueness index.
    with _client(monkeypatch, tmp_path) as client:
        response = client.post(
            "/api/v1/backtests",
            json=BACKTEST_BODY,
            headers={**AUTH, "Idempotency-Key": key},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_oversized_sync_backtest_is_refused_with_stable_error(monkeypatch, tmp_path):
    # Break caught: an explicitly synchronous expensive request could block an API worker.
    request = {
        **BACKTEST_BODY,
        "market": {**BACKTEST_BODY["market"], "end": "2026-10-17"},
        "execution": "sync",
    }
    with _client(monkeypatch, tmp_path) as client:
        response = client.post("/api/v1/backtests", json=request, headers=AUTH)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "execution_not_available"


def test_canonical_polling_retains_non_backtest_lifecycle_while_typed_route_rejects_it(
    monkeypatch, tmp_path
):
    # Break caught: typed backtest polling could expose another operation or leak a KeyError.
    monkeypatch.setattr(ExperimentWorker, "run_forever", lambda self, stop_event: None)
    with _client(monkeypatch, tmp_path) as client:
        unknown = client.get("/api/v1/experiments/exp_missing", headers=AUTH)
        other, _ = client.app.state.experiment_store.create_experiment(
            "compare", {"experiment_ids": ["exp_a", "exp_b"]}, "async", None
        )
        wrong_operation = client.get(
            f"/api/v1/backtests/{other.experiment_id}", headers=AUTH
        )
        shared_poll = client.get(
            f"/api/v1/experiments/{other.experiment_id}", headers=AUTH
        )

    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "experiment_not_found"
    assert wrong_operation.status_code == 404
    assert wrong_operation.json()["error"]["code"] == "experiment_not_found"
    assert shared_poll.status_code == 200
    assert shared_poll.json() == {
        "experiment_id": other.experiment_id,
        "operation": "pending",
        "stored_operation": "compare",
        "status": "queued",
        "created_at": other.created_at.isoformat().replace("+00:00", "Z"),
        "started_at": None,
        "completed_at": None,
        "execution": "async",
        "request": {"experiment_ids": ["exp_a", "exp_b"]},
        "result": None,
        "error": None,
        "provenance": None,
    }


def test_legacy_backtest_is_explicitly_removed_without_a_second_engine(monkeypatch, tmp_path):
    # Break caught: the singular endpoint could accidentally revive independent execution logic.
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/api/v1/backtest", headers=AUTH)

    assert response.status_code == 410
    error = response.json()["error"]
    assert error["code"] == "legacy_endpoint_removed"
    assert error["details"]["replacement"] == "/api/v1/backtests"
    assert "POST /api/v1/backtests" in error["message"]
    assert response.headers["link"] == '</openapi.json>; rel="alternate"'


def test_openapi_types_backtest_submissions_and_both_polling_views(monkeypatch, tmp_path):
    # Break caught: generated clients could lose a declared route or typed response schema.
    with _client(monkeypatch, tmp_path) as client:
        document = client.get("/openapi.json").json()

    assert {
        "/api/v1/backtests",
        "/api/v1/backtests/{experiment_id}",
        "/api/v1/experiments/{experiment_id}",
    } <= set(document["paths"])
    post = document["paths"]["/api/v1/backtests"]["post"]
    assert post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/BacktestCreate"
    )
    assert post["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/BacktestExperimentResponse"
    )


def test_openapi_polling_discriminates_operations_and_types_reproducibility_fields(
    monkeypatch, tmp_path
):
    # Break caught: canonical polling could regress to opaque request/result/provenance objects.
    with _client(monkeypatch, tmp_path) as client:
        document = client.get("/openapi.json").json()

    schemas = document["components"]["schemas"]
    canonical = document["paths"]["/api/v1/experiments/{experiment_id}"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert canonical["discriminator"] == {
        "propertyName": "operation",
        "mapping": {
            "backtest": "#/components/schemas/BacktestExperimentResponse",
            "parameter_sweep": "#/components/schemas/ParameterSweepExperimentResponse",
            "compare": "#/components/schemas/CompareExperimentResponse",
            "regime_comparison": "#/components/schemas/RegimeComparisonExperimentResponse",
            "pending": "#/components/schemas/PendingExperimentResponse",
        },
    }
    assert canonical["oneOf"] == [
        {"$ref": "#/components/schemas/BacktestExperimentResponse"},
        {"$ref": "#/components/schemas/ParameterSweepExperimentResponse"},
        {"$ref": "#/components/schemas/CompareExperimentResponse"},
        {"$ref": "#/components/schemas/RegimeComparisonExperimentResponse"},
        {"$ref": "#/components/schemas/PendingExperimentResponse"},
    ]

    configuration = schemas["BacktestConfigurationResponse"]["properties"]
    assert configuration["strategy"]["$ref"].endswith("/StrategyConfigurationResponse")
    assert configuration["market"]["$ref"].endswith("/MarketConfigurationResponse")
    assert configuration["execution"]["$ref"].endswith("/ExecutionConfigurationResponse")
    provenance = schemas["ResearchProvenanceResponse"]["properties"]
    assert provenance["market_data"]["$ref"].endswith("/MarketDataProvenanceResponse")
    assert provenance["software"]["$ref"].endswith("/SoftwareProvenanceResponse")
    envelope = schemas["BacktestExperimentResponse"]["properties"]
    assert envelope["provenance"]["anyOf"][0]["$ref"].endswith(
        "/ResearchProvenanceResponse"
    )


def test_openapi_documents_legacy_migration_header(monkeypatch, tmp_path):
    # Break caught: generated clients could miss the machine-readable migration link.
    with _client(monkeypatch, tmp_path) as client:
        response = client.get("/openapi.json").json()["paths"]["/api/v1/backtest"][
            "get"
        ]["responses"]["410"]

    assert response["headers"]["Link"]["schema"] == {"type": "string"}
    assert "OpenAPI" in response["headers"]["Link"]["description"]
