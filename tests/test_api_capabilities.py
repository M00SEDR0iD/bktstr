from fastapi.testclient import TestClient

from bktstr.api.app import create_app


AUTH = {"Authorization": "Bearer test-key"}


def test_capabilities_publish_api_limits_and_exact_execution_policy(monkeypatch, tmp_path):
    # Break caught: generated clients could not discover auth, limits, or queue behavior.
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/capabilities", headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["api"]["openapi_url"] == "/openapi.json"
    assert body["api"]["authentication"] == {"scheme": "bearer", "header": "Authorization"}
    assert body["api"]["limits"]["market_data_page_size"] == {"minimum": 1, "maximum": 1000}
    assert body["experiments"]["execution_policy"] == {
        "auto_inline": ["backtest"],
        "auto_queues": ["parameter_sweep", "compare", "regime_comparison"],
        "sync_max_calendar_days": 31,
        "sync_refusal_code": "execution_not_available",
    }


def test_capabilities_retain_registered_v05_contracts_and_publish_operations(monkeypatch, tmp_path):
    # Break caught: API expansion could hide immutable v0.5 registry metadata from clients.
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))
    with TestClient(create_app()) as client:
        body = client.get("/api/v1/capabilities", headers=AUTH).json()

    assert {"research_variables", "strategies", "cache", "release"} <= set(body)
    assert body["strategies"]["baseline"]["id"] == "bktstr.bearish-regime-scalp"
    assert body["api"]["operations"] == [
        "backtest",
        "parameter_sweep",
        "compare",
        "regime_comparison",
        "market_data",
    ]
    assert body["experiments"]["idempotency"] == {
        "header": "Idempotency-Key",
        "behavior": "same canonical operation request returns the existing experiment",
    }


def test_openapi_explicitly_types_capability_contracts(monkeypatch, tmp_path):
    # Break caught: capability payloads could become undocumented additional-properties blobs.
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))
    with TestClient(create_app()) as client:
        schemas = client.get("/openapi.json").json()["components"]["schemas"]

    capability = schemas["CapabilityResponse"]
    assert capability["additionalProperties"] is False
    for name in [
        "api",
        "experiments",
        "rule_syntax",
        "regime",
        "sentiment",
        "execution_model",
        "providers",
        "release",
        "cache",
        "research_variables",
        "strategies",
    ]:
        assert capability["properties"][name]["$ref"].startswith("#/components/schemas/")

    api = schemas["ApiCapabilities"]
    assert api["properties"]["openapi_url"]["type"] == "string"
    assert api["properties"]["authentication"]["$ref"].endswith(
        "/BearerAuthenticationCapabilities"
    )
    assert api["properties"]["limits"]["$ref"].endswith("/ApiLimitsCapabilities")
    experiments = schemas["ExperimentCapabilities"]
    assert experiments["properties"]["execution_policy"]["$ref"].endswith(
        "/ExecutionPolicyCapabilities"
    )
    assert experiments["properties"]["idempotency"]["$ref"].endswith(
        "/IdempotencyCapabilities"
    )
    policy = schemas["ExecutionPolicyCapabilities"]
    assert policy["properties"]["auto_queues"]["items"]["type"] == "string"
    assert policy["properties"]["sync_max_calendar_days"]["type"] == "integer"
    assert schemas["ResearchVariableDefinitionCapabilities"]["additionalProperties"] is False
    assert schemas["StrategyCapabilities"]["additionalProperties"] is False
