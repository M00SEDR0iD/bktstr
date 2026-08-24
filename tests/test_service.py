import asyncio
from datetime import date
import pandas as pd
import pytest

from bktstr.providers import MassiveProvider
from bktstr.service import BacktestRequest, execute_backtest, provider_name_for_request


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
