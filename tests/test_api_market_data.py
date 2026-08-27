import asyncio
from datetime import date, datetime

from fastapi.testclient import TestClient
import pandas as pd
import pytest

import bktstr.api.routes as api_routes
from bktstr.api.app import create_app
from bktstr.services.validation import SemanticValidationError


AUTH = {"Authorization": "Bearer test-key"}
QUERY = (
    "/api/v1/market-data?symbol=NVDA&start=2026-08-17&end=2026-08-17"
    "&timeframe=1m&limit=2"
)


def _market_page(*, cursor: str | None = None) -> dict:
    bars = [
        {
            "timestamp": datetime(2026, 8, 17, 13, 30),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1_000.0,
        },
        {
            "timestamp": datetime(2026, 8, 17, 13, 31),
            "open": 100.5,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1_200.0,
        },
    ]
    return {
        "symbol": "NVDA",
        "start": "2026-08-17",
        "end": "2026-08-17",
        "timeframe": "1m",
        "source": "fixture",
        "bars": bars if cursor is None else [],
        "next_cursor": "fixture-next" if cursor is None else None,
    }


def test_market_data_is_normalized_paginated_and_secret_free(monkeypatch, tmp_path):
    # Break caught: the inspection route could disappear or leak provider-shaped data.
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))

    async def fixture_market_data(**kwargs):
        return _market_page(cursor=kwargs["cursor"])

    monkeypatch.setattr(
        api_routes, "inspect_market_data", fixture_market_data, raising=False
    )
    with TestClient(create_app()) as client:
        response = client.get(QUERY, headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert {"timestamp", "open", "high", "low", "close", "volume"} <= set(
        body["bars"][0]
    )
    assert body["next_cursor"] == "fixture-next"
    assert "api_key" not in response.text.lower()


def test_market_data_rejects_cursor_for_different_canonical_request(monkeypatch, tmp_path):
    # Break caught: a cursor for one data identity could silently page another market range.
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))

    async def fixture_market_data(**kwargs):
        if kwargs["cursor"] == "wrong-identity":
            raise SemanticValidationError(
                "cursor does not match the requested market data", ("cursor",)
            )
        return _market_page(cursor=kwargs["cursor"])

    monkeypatch.setattr(
        api_routes, "inspect_market_data", fixture_market_data, raising=False
    )
    with TestClient(create_app()) as client:
        response = client.get(f"{QUERY}&cursor=wrong-identity", headers=AUTH)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert response.json()["error"]["details"]["fields"] == ["cursor"]


def test_market_data_validates_page_bounds_and_enum_openapi_contract(monkeypatch, tmp_path):
    # Break caught: unbounded inspection pages could exhaust a service worker or typed clients.
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))
    with TestClient(create_app()) as client:
        invalid = client.get(QUERY.replace("limit=2", "limit=1001"), headers=AUTH)
        invalid_source = client.get(f"{QUERY}&source=massive", headers=AUTH)
        document = client.get("/openapi.json").json()

    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"]["fields"] == ["limit"]
    assert invalid_source.status_code == 422
    assert invalid_source.json()["error"]["code"] == "validation_error"
    assert invalid_source.json()["error"]["details"]["fields"] == ["source"]
    operation = document["paths"]["/api/v1/market-data"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/MarketDataResponse")
    for status in ("400", "401", "422", "500", "502"):
        assert operation["responses"][status]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    schemas = document["components"]["schemas"]
    assert schemas["MarketCreate"]["properties"]["timeframe"]["$ref"].endswith(
        "/MarketTimeframe"
    )
    assert schemas["MarketCreate"]["properties"]["source"]["$ref"].endswith(
        "/AutomaticSource"
    )
    assert schemas["MarketTimeframe"]["enum"] == ["1m", "5m", "15m", "1h", "1d"]
    assert schemas["AutomaticSource"]["enum"] == ["auto"]
    market_parameters = {item["name"]: item for item in operation["parameters"]}
    assert market_parameters["timeframe"]["schema"]["$ref"].endswith(
        "/MarketTimeframe"
    )
    assert market_parameters["source"]["schema"]["$ref"].endswith(
        "/AutomaticSource"
    )


@pytest.mark.parametrize(
    ("overrides", "fields", "status_code"),
    [
        ({"symbol": "bad symbol"}, ["symbol"], 400),
        ({"start": "2026-08-18", "end": "2026-08-17"}, ["start", "end"], 400),
        ({"timeframe": "2m"}, ["timeframe"], 422),
        ({"source": "massive"}, ["source"], 422),
    ],
)
def test_market_data_invalid_query_errors_use_flat_query_paths(
    monkeypatch, tmp_path, overrides, fields, status_code
):
    # Break caught: a shared nested-market normalizer could leak `market.*`
    # paths into the flat /market-data query contract.
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_EXPERIMENT_DIR", str(tmp_path / "experiments"))
    query = {
        "symbol": "NVDA",
        "start": "2026-08-17",
        "end": "2026-08-17",
        "timeframe": "1m",
        "source": "auto",
        "limit": 2,
        **overrides,
    }

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/market-data", params=query, headers=AUTH)

    assert response.status_code == status_code
    assert response.json()["error"]["details"]["fields"] == fields


def test_market_data_service_uses_cached_bars_and_binds_cursors_to_identity(monkeypatch):
    # Break caught: a new data path could bypass the cache contract or reuse a cursor for another symbol.
    from bktstr.services import data

    class CachedBars:
        provider_name = "fixture"

        async def fetch_bars(self, symbol, start, end, timeframe):
            assert (symbol, start, end, timeframe) == (
                "NVDA",
                date(2026, 8, 17),
                date(2026, 8, 17),
                "1m",
            )
            index = pd.DatetimeIndex(
                ["2026-08-17 09:30:00", "2026-08-17 09:31:00", "2026-08-17 09:32:00"],
                tz="America/New_York",
            )
            return pd.DataFrame(
                {
                    "open": [100.0, 101.0, 102.0],
                    "high": [101.0, 102.0, 103.0],
                    "low": [99.0, 100.0, 101.0],
                    "close": [100.5, 101.5, 102.5],
                    "volume": [1000.0, 1100.0, 1200.0],
                },
                index=index,
            )

    monkeypatch.setattr(data, "_cached_provider_for_market", lambda market: CachedBars())
    first = asyncio.run(
        data.inspect_market_data(
            symbol="NVDA",
            start="2026-08-17",
            end="2026-08-17",
            timeframe="1m",
            limit=2,
        )
    )
    second = asyncio.run(
        data.inspect_market_data(
            symbol="NVDA",
            start="2026-08-17",
            end="2026-08-17",
            timeframe="1m",
            limit=2,
            cursor=first.next_cursor,
        )
    )

    assert [bar.close for bar in first.bars] == [100.5, 101.5]
    assert [bar.close for bar in second.bars] == [102.5]
    with pytest.raises(ValueError, match="cursor does not match"):
        asyncio.run(
            data.inspect_market_data(
                symbol="AMD",
                start="2026-08-17",
                end="2026-08-17",
                timeframe="1m",
                limit=2,
                cursor=first.next_cursor,
            )
        )
