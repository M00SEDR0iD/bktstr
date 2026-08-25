from fastapi.testclient import TestClient

from bktstr.api.app import create_app


def test_system_routes_publish_health_and_protect_capabilities(monkeypatch):
    """Removing the API key check must not expose capability metadata."""
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    client = TestClient(create_app())

    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/capabilities").status_code == 401

    response = client.get(
        "/api/v1/capabilities", headers={"Authorization": "Bearer test-key"}
    )

    assert response.status_code == 200
    assert response.json()["strategies"]["baseline"]["id"] == "bktstr.bearish-regime-scalp"


def test_openapi_exposes_typed_system_routes(monkeypatch):
    """Dropping typed route registration must make the public schema fail."""
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")

    document = TestClient(create_app()).get("/openapi.json").json()
    paths = document["paths"]

    assert {"/health", "/api/v1/health", "/api/v1/capabilities"} <= set(paths)
    assert (
        paths["/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/HealthResponse"
    )


def test_unauthorized_response_has_a_request_id(monkeypatch):
    """Replacing API errors with uncorrelatable framework responses must fail."""
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")

    body = TestClient(create_app()).get("/api/v1/capabilities").json()

    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["request_id"].startswith("req_")
