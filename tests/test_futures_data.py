import asyncio
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from bktstr.api.app import create_app


AUTH = {"Authorization": "Bearer test-key"}
START = date(2026, 9, 25)
NS = 1790343000000000000  # 2026-09-25 13:30 UTC


@pytest.fixture(autouse=True)
def isolated_experiments(monkeypatch, tmp_path):
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))


def bar(**changes):
    return dict(ticker="NQZ6", window_start=NS, open=25000, high=25002,
                low=24999, close=25001, volume=42, **changes)


def provider(handler, **kwargs):
    from bktstr.futures_data import MassiveFuturesProvider
    return MassiveFuturesProvider("provider-secret", transport=httpx.MockTransport(handler), **kwargs)


def test_futures_route_requires_auth_and_is_documented(monkeypatch):
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/market-data/futures/bars", params={
            "ticker": "NQZ6", "start": "2026-09-25", "end": "2026-09-25"})
        schema = client.get("/openapi.json").json()
    assert response.status_code == 401
    assert "/api/v1/market-data/futures/contracts" in schema["paths"]


def test_bars_paginate_normalize_nanoseconds_and_keep_contract():
    seen = []
    def handler(request):
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer provider-secret"
        assert "provider-secret" not in str(request.url)
        if len(seen) == 1:
            assert request.url.path == "/futures/v1/aggs/NQZ6"
            assert request.url.params["resolution"] == "1min"
            assert request.url.params["window_start.gte"] == "2026-09-25"
            assert request.url.params["window_start.lt"] == "2026-09-26"
            return httpx.Response(200, json={"status": "OK", "results": [bar()],
                "next_url": "https://api.massive.com/futures/v1/aggs/NQZ6?cursor=abc"})
        second = bar()
        second["window_start"] += 60000000000
        return httpx.Response(200, json={"status": "OK", "results": [second]})
    result = asyncio.run(provider(handler).bars("NQZ6", START, START))
    assert len(result) == 2
    assert result[0]["timestamp"] == "2026-09-25T13:30:00Z"
    assert result[0]["ticker"] == "NQZ6"
    assert result[0]["volume"] == 42
    assert len(seen) == 2


@pytest.mark.parametrize("next_url", [
    "https://evil.example/futures/v1/aggs/NQZ6?cursor=x",
    "http://api.massive.com/futures/v1/aggs/NQZ6?cursor=x",
    "https://api.massive.com/futures/v1/aggs/ESZ6?cursor=x",
    "https://user:password@api.massive.com/futures/v1/aggs/NQZ6?cursor=x",
    "https://api.massive.com/futures/v1/aggs/NQZ6?apiKey=leak",
])
def test_unsafe_pagination_never_receives_credentials(next_url):
    from bktstr.futures_data import FuturesDataError
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"status": "OK", "results": [bar()], "next_url": next_url})
    with pytest.raises(FuturesDataError):
        asyncio.run(provider(handler).bars("NQZ6", START, START))
    assert len(seen) == 1


@pytest.mark.parametrize("change", [
    {"ticker": "ESZ6"}, {"window_start": NS // 1000000},
    {"window_start": NS + 1}, {"high": 24990}, {"volume": -1},
    {"open": "not-a-number"}, {"close": float("inf")},
])
def test_bad_bars_fail_without_fabrication(change):
    from bktstr.futures_data import FuturesDataError
    row = bar()
    row.update(change)
    def handler(request):
        # Serialize non-finite values as a string, as JSON prohibits infinity.
        if row.get("close") == float("inf"):
            row["close"] = "Infinity"
        return httpx.Response(200, json={"status": "OK", "results": [row]})
    with pytest.raises(FuturesDataError):
        asyncio.run(provider(handler).bars("NQZ6", START, START))


def test_contract_discovery_uses_point_in_time_filter():
    def handler(request):
        assert request.url.path == "/futures/v1/contracts"
        assert request.url.params["product_code"] == "NQ"
        assert request.url.params["date"] == "2026-09-25"
        return httpx.Response(200, json={"status": "OK", "results": [{
            "ticker": "NQZ6", "product_code": "NQ", "date": "2026-09-25",
            "active": True, "trade_tick_size": 0.25, "private_extra": "omit"}]})
    result = asyncio.run(provider(handler).contracts("NQ", START))
    assert result[0]["trade_tick_size"] == 0.25
    assert "private_extra" not in result[0]


def test_retries_are_bounded_and_provider_errors_are_safe():
    from bktstr.futures_data import FuturesDataError
    calls = []
    delays = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "999999"},
                              json={"message": "provider-secret"})
    async def sleep(seconds):
        delays.append(seconds)
    with pytest.raises(FuturesDataError) as caught:
        asyncio.run(provider(handler, sleep_fn=sleep, max_retries=1).bars("NQZ6", START, START))
    assert caught.value.code == "futures_rate_limited"
    assert len(calls) == 2 and delays == [2.0]
    assert "provider-secret" not in str(caught.value)


def test_api_reports_entitlement_without_leaking_provider_body(monkeypatch):
    import bktstr.api.futures_routes as routes
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setattr(routes, "get_provider", lambda: provider(
        lambda request: httpx.Response(403, json={"message": "provider-secret"})))
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/market-data/futures/bars", headers=AUTH,
                              params={"ticker": "NQZ6", "start": START, "end": START})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "futures_access_denied"
    assert "provider-secret" not in response.text


def test_api_rejects_root_symbol_and_large_range_before_provider(monkeypatch):
    import bktstr.api.futures_routes as routes
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    def unexpected():
        pytest.fail("invalid input must not reach provider")
    monkeypatch.setattr(routes, "get_provider", unexpected)
    with TestClient(create_app()) as client:
        for params in [{"ticker": "NQ", "start": START, "end": START},
                       {"ticker": "NQZ6", "start": "2026-01-01", "end": START}]:
            response = client.get("/api/v1/market-data/futures/bars", headers=AUTH, params=params)
            assert response.status_code == 422


def test_api_download_is_typed_unadjusted_and_not_an_execution_claim(monkeypatch):
    import bktstr.api.futures_routes as routes
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setattr(routes, "get_provider", lambda: provider(lambda request:
        httpx.Response(200, json={"status": "OK", "results": [bar()]})))
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/market-data/futures/bars", headers=AUTH,
                              params={"ticker": "NQZ6", "start": START, "end": START})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "massive" and body["adjustment"] == "unadjusted"
    assert body["execution_supported"] is False
    assert body["bars"][0]["timestamp"] == "2026-09-25T13:30:00Z"
    assert body["bars"][0]["close"] == 25001


def test_api_missing_key_is_configuration_error(monkeypatch):
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/market-data/futures/contracts", headers=AUTH,
                              params={"product_code": "NQ", "as_of": START})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "futures_not_configured"


@pytest.mark.parametrize("mode", ["redirect", "duplicate", "reverse", "wrong_date", "malformed", "missing_results"])
def test_provider_rejects_incomplete_or_inconsistent_response(mode):
    from bktstr.futures_data import FuturesDataError
    def handler(request):
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "https://evil.example"})
        if mode == "malformed":
            return httpx.Response(200, text="not JSON")
        if mode == "missing_results":
            return httpx.Response(200, json={"status": "OK"})
        a, b = bar(), bar()
        if mode == "reverse":
            b["window_start"] -= 60000000000
        if mode == "wrong_date":
            b["window_start"] += 86400000000000
        return httpx.Response(200, json={"status": "OK", "results": [a, b]})
    with pytest.raises(FuturesDataError):
        asyncio.run(provider(handler).bars("NQZ6", START, START))


def test_empty_results_stay_empty():
    result = asyncio.run(provider(lambda request: httpx.Response(200,
        json={"status": "OK", "results": []})).bars("NQZ6", START, START))
    assert result == []


def test_contract_api_preserves_tick_metadata(monkeypatch):
    import bktstr.api.futures_routes as routes
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setattr(routes, "get_provider", lambda: provider(lambda request:
        httpx.Response(200, json={"status": "OK", "results": [{"ticker": "NQZ6",
            "product_code": "NQ", "date": "2026-09-25", "trade_tick_size": 0.25}]})))
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/market-data/futures/contracts", headers=AUTH,
                              params={"product_code": "NQ", "as_of": START})
    assert response.status_code == 200
    assert response.json()["contracts"][0]["trade_tick_size"] == 0.25


@pytest.mark.parametrize("as_of", [date(2024, 10, 1), START])
def test_contract_discovery_excludes_combinations_without_losing_outrights(as_of):
    def handler(request):
        if as_of >= date(2025, 3, 12):
            assert request.url.params["type"] == "single"
        else:
            assert "type" not in request.url.params
        return httpx.Response(200, json={"status": "OK", "results": [
            {"ticker": "NQZ6", "product_code": "NQ", "date": as_of.isoformat()},
            {"ticker": "NQZ6-NQH7", "product_code": "NQ", "date": as_of.isoformat(),
             "type": "combo" if as_of >= date(2025, 3, 12) else None}]})
    rows = asyncio.run(provider(handler).contracts("NQ", as_of))
    assert [x["ticker"] for x in rows] == ["NQZ6"]


def test_contract_discovery_rejects_wrong_root():
    from bktstr.futures_data import FuturesDataError
    def handler(request):
        return httpx.Response(200, json={"status": "OK", "results": [
            {"ticker": "ESZ6", "product_code": "NQ", "date": START.isoformat(), "type": "single"}]})
    with pytest.raises(FuturesDataError):
        asyncio.run(provider(handler).contracts("NQ", START))
