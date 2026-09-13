import asyncio
from datetime import date

import pytest

import bktstr.service as legacy_service
import bktstr.services.backtest as research
from bktstr.providers import MassiveProvider
from bktstr.services.regimes import RegimeInput
from tests.v05_fixtures import daily_fixture, intraday_fixture


@pytest.mark.parametrize("start,end", [("25:00", "16:00"), ("15:00", "10:00")])
def test_invalid_entry_window_is_rejected_before_provider_selection(monkeypatch, start, end):
    # Break caught: invalid research must fail before credentials or data are needed.
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    value = research.BacktestInput(
        strategy_id="bktstr.bearish-regime-scalp", strategy_version="1.0.0",
        symbol="NVDA", start=date(2020, 1, 2), end=date(2020, 1, 2),
        timeframe="1m", side="short", entry="close.lt:1000",
        parameters={"entry_start_time": start, "entry_end_time": end},
    )
    with pytest.raises(ValueError, match="entry.*time"):
        asyncio.run(research.run_backtest(value))


def _without_cache_observations(value):
    """Compare research evidence independently of cache warmth and timing."""
    if isinstance(value, dict):
        return {
            key: _without_cache_observations(item)
            for key, item in value.items()
            if key not in {"cache", "elapsed_seconds"}
        }
    if isinstance(value, list):
        return [_without_cache_observations(item) for item in value]
    return value


@pytest.mark.parametrize("cache_enabled", [False, True])
@pytest.mark.parametrize("with_context", [False, True])
def test_research_preserves_results_without_legacy_adapters(
    monkeypatch, tmp_path, cache_enabled, with_context
):
    # Break caught: bypassing compatibility adapters must preserve resolved
    # parameters, trades, metrics and source/formula evidence for real execution.
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR", str(tmp_path / "derived"))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_ENABLED", str(cache_enabled).lower())

    async def fetch(self, symbol, start, end, timeframe="1m"):
        if timeframe == "1d":
            return daily_fixture(
                start, end,
                {"NVDA": 300.0, "SOXX": 200.0, "QQQ": 500.0}[symbol],
                {"NVDA": -0.2, "SOXX": 0.1, "QQQ": 0.05}[symbol],
            )
        return intraday_fixture()

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fetch)
    value = research.BacktestInput(
        strategy_id="bktstr.bearish-regime-scalp",
        strategy_version="1.0.0",
        symbol="NVDA", start=date(2026, 8, 17), end=date(2026, 8, 17),
        timeframe="1m", side="short", entry="close.lt:1000",
        parameters={
            "stop_pct": 10.0, "target_pct": 10.0,
            "max_hold_minutes": 1, "slippage_bps": 0.0,
            "entry_start_time": None, "entry_end_time": None,
        },
        regime=RegimeInput(
            enabled=True,
            rules="day_sma20_slope5.lt:999,relative_return20.lt:999",
            benchmark="SOXX", sentiment_enabled=True,
            sentiment_sector_benchmark="SOXX", sentiment_market_benchmark="QQQ",
        ) if with_context else None,
    )
    legacy = asyncio.run(legacy_service.execute_backtest(research.to_legacy_request(value)))
    expected = research.project_research_result(
        value, legacy, execution_provenance=legacy.execution_provenance,
    )

    def obsolete_adapter(*args, **kwargs):
        pytest.fail("research execution still requires a legacy adapter")

    monkeypatch.setattr(research, "to_legacy_request", obsolete_adapter)
    monkeypatch.setattr(legacy_service.BacktestRequest, "from_values", obsolete_adapter)
    monkeypatch.setattr(legacy_service, "serialize_strategy_run_result", obsolete_adapter)
    actual = asyncio.run(research.run_backtest(value))

    assert actual.metrics.trade_count > 0
    assert actual.provenance.market_data["source"] == "massive"
    assert actual.provenance.market_data["cache"]["hit_days"] == 1
    assert actual.metrics == expected.metrics
    assert actual.trades == expected.trades
    assert actual.configuration == expected.configuration
    assert _without_cache_observations(research.to_json_value(actual.provenance)) == (
        _without_cache_observations(research.to_json_value(expected.provenance))
    )
