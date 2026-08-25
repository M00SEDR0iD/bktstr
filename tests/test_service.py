import asyncio
from datetime import date
import httpx
import pandas as pd
import pytest

import bktstr.server as server
from bktstr.providers import MassiveProvider
from bktstr.orchestrator import StrategyRunResult
from bktstr.service import (
    BacktestRequest,
    execute_backtest,
    provider_name_for_request,
    serialize_strategy_run_result,
)
from bktstr.strategies import ResolvedStrategy
from bktstr.variables import VariableSet


def _bars():
    idx=pd.DatetimeIndex(["2026-08-17 09:30","2026-08-17 09:31","2026-08-17 09:32"],tz="America/New_York")
    return pd.DataFrame({"open":[100.,100.,99.],"high":[100.,100.,99.],"low":[100.,99.,98.],"close":[100.,99.,98.],"volume":[1000.]*3},index=idx)


def _daily(start,end,base=100.,slope=.1):
    idx=pd.date_range(start=start,end=end,freq="B",tz="America/New_York"); c=[base+i*slope for i in range(len(idx))]
    return pd.DataFrame({"open":c,"high":[x+1 for x in c],"low":[x-1 for x in c],"close":c,"volume":[1000.]*len(c)},index=idx)


def test_request_defaults_normalization_and_range_guard():
    req=BacktestRequest.from_values(symbol=" nvda ",start="2026-08-01",end="2026-08-10",timeframe="1m",side="short",entry="close.cross_below:vwap")
    assert req.symbol=="NVDA" and req.stop_pct==1 and req.target_pct==3
    with pytest.raises(ValueError,match="730 days"):
        BacktestRequest.from_values(symbol="NVDA",start="2024-01-01",end="2026-01-02",timeframe="1m",side="short",entry="close.cross_below:vwap")


def test_provider_selection_recent_yahoo_without_massive(monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY",raising=False)
    req=BacktestRequest.from_values(symbol="NVDA",start="2026-08-18",end="2026-08-23",timeframe="1m",side="short",entry="close.cross_below:vwap")
    assert provider_name_for_request(req,today=date(2026,8,23))=="yahoo"


def test_request_validates_regime_sentiment_dependencies():
    with pytest.raises(ValueError,match="benchmark is required"):
        BacktestRequest.from_values(symbol="NVDA",start="2026-08-01",end="2026-08-10",side="short",entry="close.cross_below:vwap",regime="relative_return20.lt:0")
    with pytest.raises(ValueError):
        BacktestRequest.from_values(symbol="NVDA",start="2026-08-01",end="2026-08-10",side="short",entry="close.cross_below:vwap",sentiment=True,sentiment_sector_benchmark="SOXX")
    req=BacktestRequest.from_values(symbol="NVDA",start="2026-08-01",end="2026-08-10",side="short",entry="close.cross_below:vwap",regime="sentiment_fragility.gte:0.35",sentiment=True,sentiment_sector_benchmark="SOXX",sentiment_market_benchmark="QQQ")
    assert req.regime.startswith("sentiment_fragility")


def test_domain_result_serializer_retains_exact_legacy_public_shape():
    # Break caught: the compatibility adapter could expose new provenance/degraded fields or drop legacy request values.
    req=BacktestRequest.from_values(symbol="NVDA",start="2026-08-17",end="2026-08-17",timeframe="1m",side="short",entry="close.cross_below:vwap")
    result=StrategyRunResult(
        resolved_strategy=ResolvedStrategy(
            strategy_id="bktstr.bearish-regime-scalp",
            strategy_version="1.0.0",
            schema_version="1.0.0",
            values={},
            execution_model_id="bktstr.next-bar-open",
            execution_model_version="1.0.0",
        ),
        variables=VariableSet(),
        summary={"trades":0},
        trades=({"entry_price":100.0},),
        data={"provider":"fixture"},
        provenance={"provider":{"name":"fixture"}},
        degraded=True,
        canonical=False,
    )

    serialized=serialize_strategy_run_result(req,result)

    assert serialized=={
        "request":{
            "symbol":"NVDA","start":"2026-08-17","end":"2026-08-17","timeframe":"1m","side":"short","entry":"close.cross_below:vwap","regime":None,"benchmark":None,"sentiment":False,"sentiment_sector_benchmark":None,"sentiment_market_benchmark":None,"sentiment_data_profile":"clean","sentiment_sources":["price"],"stop_pct":1.0,"target_pct":3.0,"max_hold_minutes":240,"position_size":1000.0,"starting_capital":10000.0,"slippage_bps":2.0,"entry_start_time":None,"entry_end_time":None,
        },
        "data":{"provider":"fixture"},
        "summary":{"trades":0},
        "trades":[{"entry_price":100.0}],
    }


def test_execute_backtest_preserves_raw_cache_and_adds_derived(monkeypatch,tmp_path):
    monkeypatch.setenv("MASSIVE_API_KEY","test-key"); monkeypatch.setenv("BKTSTR_CACHE_DIR",str(tmp_path)); monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR",str(tmp_path/"derived"))
    calls=0
    async def fake(self,symbol,start,end,timeframe="1m"):
        nonlocal calls; calls+=1; return _bars()
    monkeypatch.setattr(MassiveProvider,"fetch_bars",fake)
    req=BacktestRequest.from_values(symbol="NVDA",start="2026-08-17",end="2026-08-17",timeframe="1m",side="short",entry="close.cross_below:vwap")
    one=asyncio.run(execute_backtest(req)); two=asyncio.run(execute_backtest(req))
    assert calls==1
    assert one["data"]["cache"]=={"hit_days":0,"miss_days":1,"fetched_ranges":1}
    assert two["data"]["cache"]=={"hit_days":1,"miss_days":0,"fetched_ranges":0}
    assert one["data"]["derived_cache"]["intraday"]["hit"] is False and two["data"]["derived_cache"]["intraday"]["hit"] is True


def test_disabled_derived_cache_retains_legacy_uncached_status_shape(monkeypatch,tmp_path):
    # Break caught: moving to variable snapshots could change the public disabled-cache status payload.
    monkeypatch.setenv("MASSIVE_API_KEY","test-key"); monkeypatch.setenv("BKTSTR_CACHE_DIR",str(tmp_path)); monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR",str(tmp_path/"derived")); monkeypatch.setenv("BKTSTR_DERIVED_CACHE_ENABLED","false")
    async def fake(self,symbol,start,end,timeframe="1m"):
        return _bars()
    monkeypatch.setattr(MassiveProvider,"fetch_bars",fake)
    req=BacktestRequest.from_values(symbol="NVDA",start="2026-08-17",end="2026-08-17",timeframe="1m",side="short",entry="close.cross_below:vwap")

    out=asyncio.run(execute_backtest(req))

    assert out["data"]["derived_cache"] == {
        "enabled":False,
        "intraday":{"hit":False,"elapsed_seconds":0.0,"recovered_corruption":False},
    }


def test_execute_backtest_reraises_http_provider_error_for_legacy_server_classifier(
    monkeypatch, tmp_path
):
    # Break caught: sanitizing the domain error could stop the established 502 classifier.
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR", str(tmp_path / "derived"))
    request = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-17",
        end="2026-08-17",
        timeframe="1m",
        side="short",
        entry="close.cross_below:vwap",
    )
    upstream_request = httpx.Request("GET", "https://market.example/bars")
    provider_error = httpx.HTTPStatusError(
        "market provider rejected the request",
        request=upstream_request,
        response=httpx.Response(503, request=upstream_request),
    )

    async def unavailable(self, symbol, start, end, timeframe="1m"):
        raise provider_error

    monkeypatch.setattr(MassiveProvider, "fetch_bars", unavailable)
    with pytest.raises(httpx.HTTPStatusError) as raised:
        asyncio.run(execute_backtest(request))
    assert raised.value is provider_error

    captured = []
    handler = object.__new__(server.Handler)
    handler.path = "/api/v1/backtest"
    handler._json = lambda status, payload: captured.append((status, payload))
    monkeypatch.setattr(
        server,
        "parse_backtest_query",
        lambda query: (request, {"trade_limit": 25}),
    )
    handler.do_GET()

    assert captured == [
        (
            502,
            {
                "error": "market_data_http_error",
                "detail": str(provider_error),
            },
        )
    ]


def test_execute_regime_sentiment_reports_context(monkeypatch,tmp_path):
    monkeypatch.setenv("MASSIVE_API_KEY","test-key"); monkeypatch.setenv("BKTSTR_CACHE_DIR",str(tmp_path)); monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR",str(tmp_path/"derived"))
    async def fake(self,symbol,start,end,timeframe="1m"):
        if timeframe=="1d": return _daily(start,end,{"NVDA":300.,"SOXX":200.,"QQQ":500.}[symbol],{"NVDA":-.2,"SOXX":.1,"QQQ":.05}[symbol])
        return _bars()
    monkeypatch.setattr(MassiveProvider,"fetch_bars",fake)
    req=BacktestRequest.from_values(symbol="NVDA",start="2026-08-17",end="2026-08-17",timeframe="1m",side="short",entry="close.lt:1000",regime="relative_return20.lt:999",benchmark="SOXX",sentiment=True,sentiment_sector_benchmark="SOXX",sentiment_market_benchmark="QQQ",stop_pct=10,target_pct=10,max_hold_minutes=1,slippage_bps=0)
    out=asyncio.run(execute_backtest(req))
    assert out["data"]["regime"]["benchmark"]=="SOXX"
    assert out["data"]["sentiment"]["market_benchmark"]=="QQQ"
    assert out["data"]["sentiment"]["provenance"]["all_point_in_time_safe"] is True
    assert "sentiment_direction" in out["trades"][0]


def test_regime_uses_only_explicit_legacy_benchmark_not_sentiment_sector(monkeypatch, tmp_path):
    # Break caught: a sector needed only for sentiment could silently alter a day-only regime request.
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR", str(tmp_path / "derived"))

    async def fake(self, symbol, start, end, timeframe="1m"):
        if timeframe == "1d":
            return _daily(
                start,
                end,
                {"NVDA": 300.0, "SOXX": 200.0, "QQQ": 500.0}[symbol],
                {"NVDA": -0.2, "SOXX": 0.1, "QQQ": 0.05}[symbol],
            )
        return _bars()

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fake)
    request = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-17",
        end="2026-08-17",
        timeframe="1m",
        side="short",
        entry="close.lt:1000",
        regime="day_sma20_slope5.lt:999",
        sentiment=True,
        sentiment_sector_benchmark="SOXX",
        sentiment_market_benchmark="QQQ",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=1,
        slippage_bps=0,
    )

    result = asyncio.run(execute_backtest(request))

    assert result["data"]["regime"]["benchmark"] is None
    assert result["data"]["regime"]["benchmark_daily_bars"] == 0
    assert result["data"]["regime"]["benchmark_cache"] is None
