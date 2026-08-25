from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy

import pytest
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


def test_invalid_sweep_is_rejected_before_it_creates_a_durable_experiment(monkeypatch, tmp_path):
    # Break caught: invalid queued work could become a pollable failed experiment.
    invalid = {**SWEEP_BODY, "grid": {}}
    with _client(monkeypatch, tmp_path) as client:
        response = client.post("/api/v1/parameter-sweeps", json=invalid, headers=AUTH)
        assert client.app.state.experiment_store.claim_next() is None

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["details"]["fields"] == ["grid"]


def _body_with_backtest_error(operation, path, value, inner_path):
    bodies = {
        "sweep": ("/api/v1/parameter-sweeps", deepcopy(SWEEP_BODY), "base"),
        "compare": (
            "/api/v1/compare",
            {
                "candidates": [
                    {"name": "invalid", "backtest": deepcopy(BACKTEST_BODY)},
                    "exp_valid",
                ],
                "execution": "auto",
            },
            "candidates.0.backtest",
        ),
        "regime": (
            "/api/v1/regime-comparison",
            deepcopy(REGIME_BODY),
            "base",
        ),
    }
    endpoint, body, prefix = bodies[operation]
    target = body["candidates"][0]["backtest"] if operation == "compare" else body["base"]
    cursor = target
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value
    return endpoint, body, f"{prefix}.{inner_path}"


@pytest.mark.parametrize("operation", ["sweep", "compare", "regime"])
@pytest.mark.parametrize(
    ("path", "value", "inner_path"),
    [
        (("market", "source"), "manual", "market.source"),
        (
            ("regime",),
            {"rules": "relative_return20.lt:0", "benchmark": "bad symbol"},
            "regime.benchmark",
        ),
        (("strategy", "parameters", "foo"), 1, "strategy.parameters.foo"),
    ],
)
def test_compound_backtests_prefix_exact_inner_semantic_paths(
    monkeypatch, tmp_path, operation, path, value, inner_path
):
    # Break caught: compound adapters could leak an unscoped inner backtest path.
    endpoint, body, expected = _body_with_backtest_error(
        operation, path, value, inner_path
    )
    with _client(monkeypatch, tmp_path) as client:
        response = client.post(endpoint, json=body, headers=AUTH)

    assert response.status_code == 400
    assert response.json()["error"]["details"]["fields"] == [expected]


def test_compare_experiment_id_error_keeps_candidate_index(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        response = client.post(
            "/api/v1/compare",
            json={**COMPARE_BODY, "candidates": ["not-an-experiment", "exp_valid"]},
            headers=AUTH,
        )

    assert response.status_code == 400
    assert response.json()["error"]["details"]["fields"] == ["candidates.0"]


@pytest.mark.parametrize(
    ("first_label", "fields"),
    [
        (
            {"label": "bad dates", "start": "2026-01-02", "end": "2026-01-01"},
            ["labels.0.start", "labels.0.end"],
        ),
        (
            {
                "label": "bad rule",
                "start": "2026-01-01",
                "end": "2026-01-02",
                "rule": "day_close.cross_below:day_sma20",
            },
            ["labels.0.rule"],
        ),
        (
            {"label": "2026", "start": "2025-01-01", "end": "2025-01-02"},
            ["labels.0.label", "labels.1.label"],
        ),
    ],
)
def test_regime_comparison_label_errors_keep_indexed_paths(
    monkeypatch, tmp_path, first_label, fields
):
    body = deepcopy(REGIME_BODY)
    body["labels"][0] = first_label
    with _client(monkeypatch, tmp_path) as client:
        response = client.post(
            "/api/v1/regime-comparison", json=body, headers=AUTH
        )

    assert response.status_code == 400
    assert response.json()["error"]["details"]["fields"] == fields


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
        for status in ("400", "401", "409", "422", "500"):
            assert operation["responses"][status]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")

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

    schemas = document["components"]["schemas"]
    assert schemas["SweepVariantResponse"]["properties"]["provenance"] == {
        "$ref": "#/components/schemas/ResearchProvenanceResponse"
    }
    assert schemas["ComparisonCandidateResponse"]["properties"]["provenance"] == {
        "$ref": "#/components/schemas/ResearchProvenanceResponse"
    }
    assert schemas["RegimeComparisonItemResponse"]["properties"]["provenance"] == {
        "$ref": "#/components/schemas/ResearchProvenanceResponse"
    }
    for result_name, provenance_name in (
        ("ParameterSweepResult", "ParameterSweepProvenanceResponse"),
        ("CompareResult", "CompareProvenanceResponse"),
        ("RegimeComparisonResult", "RegimeComparisonProvenanceResponse"),
    ):
        assert schemas[result_name]["properties"]["provenance"] == {
            "$ref": f"#/components/schemas/{provenance_name}"
        }

    assert set(schemas["ParameterSweepProvenanceResponse"]["properties"]) == {
        "parent_experiment_id",
        "objective",
        "grid",
        "child_experiment_ids",
    }
    assert set(schemas["CompareProvenanceResponse"]["properties"]) == {
        "parent_experiment_id",
        "candidate_experiment_ids",
        "comparison_reference",
    }
    assert set(schemas["RegimeComparisonProvenanceResponse"]["properties"]) == {
        "parent_experiment_id",
        "labels",
        "disjoint_periods",
        "child_experiment_ids",
    }
    assert schemas["RegimeComparisonProvenanceResponse"]["properties"]["labels"][
        "items"
    ] == {"$ref": "#/components/schemas/RegimeLabelProvenanceResponse"}
