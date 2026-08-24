from __future__ import annotations

import asyncio

import pandas as pd

from bktstr.engine import BacktestConfig, prepare_bars_for_backtest, run_backtest_on_bars
from bktstr.providers import MassiveProvider
from bktstr.service import BacktestRequest, execute_backtest


def _intraday() -> pd.DataFrame:
    idx = pd.DatetimeIndex(
        [
            "2026-08-17 12:00:00",
            "2026-08-17 09:30:00",
            "2026-08-17 09:31:00",
            "2026-08-17 09:32:00",
        ],
        tz="America/New_York",
    )
    return pd.DataFrame(
        {
            "open": [50.0, 100.0, 101.0, 98.0],
            "high": [50.0, 101.0, 101.0, 99.0],
            "low": [50.0, 99.0, 98.0, 96.0],
            "close": [50.0, 101.0, 99.0, 97.0],
            "volume": [1_000_000.0, 1000.0, 1000.0, 1000.0],
        },
        index=idx,
    ).sort_index()


def _daily(start, end, base: float, slope: float) -> pd.DataFrame:
    idx = pd.date_range(start=start, end=end, freq="B", tz="America/New_York")
    close = [base + i * slope for i in range(len(idx))]
    return pd.DataFrame(
        {
            "open": close,
            "high": [x + 1 for x in close],
            "low": [x - 1 for x in close],
            "close": close,
            "volume": [1000.0] * len(idx),
        },
        index=idx,
    )


def test_precomputed_indicator_path_is_trade_identical():
    bars = _intraday()
    config = BacktestConfig(
        side="short",
        entry_rules="close.cross_below:vwap",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=1,
        slippage_bps=0,
        regular_hours_only=True,
    )
    normal = run_backtest_on_bars(bars, config)

    prepared = prepare_bars_for_backtest(bars, regular_hours_only=True)
    cached_path = run_backtest_on_bars(
        prepared,
        BacktestConfig(
            side="short",
            entry_rules="close.cross_below:vwap",
            stop_pct=10,
            target_pct=10,
            max_hold_minutes=1,
            slippage_bps=0,
            regular_hours_only=True,
            features_precomputed=True,
        ),
    )
    assert cached_path == normal


def test_execute_backtest_reports_derived_cache_miss_then_hit(monkeypatch, tmp_path):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR", str(tmp_path / "derived"))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_ENABLED", "true")

    calls = {"intraday": 0, "daily": 0}

    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        if timeframe == "1d":
            calls["daily"] += 1
            base = {"NVDA": 300.0, "SOXX": 200.0, "QQQ": 500.0}[symbol]
            slope = {"NVDA": -0.2, "SOXX": 0.1, "QQQ": 0.05}[symbol]
            return _daily(start, end, base, slope)
        calls["intraday"] += 1
        return _intraday()

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fake_fetch)
    req = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-17",
        end="2026-08-17",
        timeframe="1m",
        side="short",
        entry="close.lt:1000",
        regime="day_sma20_slope5.lt:999,relative_return20.lt:999",
        benchmark="SOXX",
        sentiment=True,
        sentiment_sector_benchmark="SOXX",
        sentiment_market_benchmark="QQQ",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=1,
        slippage_bps=0,
    )

    first = asyncio.run(execute_backtest(req))
    second = asyncio.run(execute_backtest(req))

    assert first["summary"] == second["summary"]
    assert first["trades"] == second["trades"]
    assert first["data"]["derived_cache"]["intraday"]["hit"] is False
    assert first["data"]["derived_cache"]["regime"]["hit"] is False
    assert first["data"]["derived_cache"]["sentiment"]["hit"] is False
    assert second["data"]["derived_cache"]["intraday"]["hit"] is True
    assert second["data"]["derived_cache"]["regime"]["hit"] is True
    assert second["data"]["derived_cache"]["sentiment"]["hit"] is True


def test_cache_disable_switch_preserves_trade_output(monkeypatch, tmp_path):
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR", str(tmp_path / "derived"))

    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        return _intraday()

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fake_fetch)
    req = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-17",
        end="2026-08-17",
        timeframe="1m",
        side="short",
        entry="close.cross_below:vwap",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=1,
        slippage_bps=0,
    )

    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_ENABLED", "false")
    uncached = asyncio.run(execute_backtest(req))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_ENABLED", "true")
    cached = asyncio.run(execute_backtest(req))

    assert uncached["summary"] == cached["summary"]
    assert uncached["trades"] == cached["trades"]
    assert uncached["data"]["derived_cache"]["enabled"] is False
    assert cached["data"]["derived_cache"]["enabled"] is True

def test_v034_capabilities_publish_derived_cache_contract():
    from bktstr import __version__
    from bktstr.server import CAPABILITIES

    assert __version__ == "0.3.5"
    assert CAPABILITIES["version"] == "0.3.5"
    assert CAPABILITIES["cache"]["derived"]["type"] == "deterministic feature/context DataFrames"
    assert CAPABILITIES["cache"]["derived"]["toggle"] == "BKTSTR_DERIVED_CACHE_ENABLED"
    assert set(CAPABILITIES["cache"]["derived"]["namespaces"]) >= {
        "intraday_features", "daily_regime", "daily_sentiment"
    }
