from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient

from bktstr.api.app import create_app
from bktstr.services.experiments import ExperimentWorker


AUTH = {"Authorization": "Bearer test-key"}
BACKTEST_BODY = {
    "strategy": {
        "id": "bktstr.bearish-regime-scalp",
        "version": "1.0.0",
        "parameters": {},
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
SWEEP_BODY = {
    "base": BACKTEST_BODY,
    "grid": {"stop_pct": [1.0, 2.0], "target_pct": [2.0, 3.0]},
    "objective": "profit_factor",
    "execution": "auto",
}
COMPARE_BODY = {
    "candidates": ["exp_a", "exp_b"],
    "execution": "auto",
}
REGIME_BODY = {
    "base": BACKTEST_BODY,
    "labels": [
        {"label": "2025", "start": "2025-01-01", "end": "2025-12-31"},
        {"label": "2026", "start": "2026-01-01", "end": "2026-08-17"},
    ],
    "execution": "auto",
}


@contextmanager
def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))
    monkeypatch.setattr(ExperimentWorker, "run_forever", lambda self, stop_event: None)
    with TestClient(create_app()) as client:
        yield client


def test_research_operation_routes_queue_in_auto_mode(monkeypatch, tmp_path):
    # Break caught: costly research operations could run inline and block the API worker.
    with _client(monkeypatch, tmp_path) as client:
        sweep = client.post("/api/v1/parameter-sweeps", json=SWEEP_BODY, headers=AUTH)
        compare = client.post("/api/v1/compare", json=COMPARE_BODY, headers=AUTH)
        regime = client.post("/api/v1/regime-comparison", json=REGIME_BODY, headers=AUTH)

    assert sweep.status_code == compare.status_code == regime.status_code == 202
    assert sweep.json()["operation"] == "parameter_sweep"
    assert compare.json()["operation"] == "compare"
    assert regime.json()["operation"] == "regime_comparison"


def test_known_research_experiments_poll_through_typed_shared_envelopes(
    monkeypatch, tmp_path
):
    # Break caught: Task 5's all-operation polling could regress to an opaque envelope.
    with _client(monkeypatch, tmp_path) as client:
        created = [
            client.post("/api/v1/parameter-sweeps", json=SWEEP_BODY, headers=AUTH),
            client.post("/api/v1/compare", json=COMPARE_BODY, headers=AUTH),
            client.post("/api/v1/regime-comparison", json=REGIME_BODY, headers=AUTH),
        ]
        polled = [
            client.get(
                f"/api/v1/experiments/{response.json()['experiment_id']}",
                headers=AUTH,
            )
            for response in created
        ]

    assert [response.status_code for response in polled] == [200, 200, 200]
    assert [response.json()["operation"] for response in polled] == [
        "parameter_sweep",
        "compare",
        "regime_comparison",
    ]
    assert polled[0].json()["request"]["grid"] == SWEEP_BODY["grid"]
    assert polled[1].json()["request"]["candidates"] == COMPARE_BODY["candidates"]
    assert polled[2].json()["request"]["labels"] == [
        {**label, "rule": None} for label in REGIME_BODY["labels"]
    ]


def test_sync_research_operation_is_refused_by_shared_execution_policy(
    monkeypatch, tmp_path
):
    # Break caught: one endpoint could bypass the Task 4 no-inline policy for costly work.
    with _client(monkeypatch, tmp_path) as client:
        response = client.post(
            "/api/v1/parameter-sweeps",
            json={**SWEEP_BODY, "execution": "sync"},
            headers=AUTH,
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "execution_not_available"


def test_research_routes_are_typed_in_openapi_and_polling_discriminator(
    monkeypatch, tmp_path
):
    # Break caught: generated clients could lose operation request/result contracts.
    with _client(monkeypatch, tmp_path) as client:
        document = client.get("/openapi.json").json()

    assert {
        "/api/v1/parameter-sweeps",
        "/api/v1/compare",
        "/api/v1/regime-comparison",
    } <= set(document["paths"])
    for path, request_name, response_name in (
        ("/api/v1/parameter-sweeps", "ParameterSweepCreate", "ParameterSweepExperimentResponse"),
        ("/api/v1/compare", "CompareCreate", "CompareExperimentResponse"),
        ("/api/v1/regime-comparison", "RegimeComparisonCreate", "RegimeComparisonExperimentResponse"),
    ):
        operation = document["paths"][path]["post"]
        assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
            f"/{request_name}"
        )
        assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
            f"/{response_name}"
        )

    canonical = document["paths"]["/api/v1/experiments/{experiment_id}"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    assert set(canonical["discriminator"]["mapping"]) == {
        "backtest",
        "parameter_sweep",
        "compare",
        "regime_comparison",
        "pending",
    }
