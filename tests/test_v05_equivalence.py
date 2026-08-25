import json
from typing import Any, Mapping

import asyncio

from bktstr.engine import BacktestConfig, run_backtest_on_bars
from bktstr.cache import BarCache, CachedProvider
from bktstr.measurements import baseline_variable_registry
from bktstr.orchestrator import (
    OrchestratorDependencies,
    execute_strategy_run,
    legacy_request_to_strategy_run,
)
from bktstr.providers import MassiveProvider
from bktstr.service import execute_backtest, serialize_strategy_run_result
from bktstr.strategies import baseline_strategy_registry
from bktstr.variable_store import VariableSnapshotStore
from bktstr_cache.derived import DerivedFrameCache

from tests.v05_fixtures import baseline_request, daily_fixture, intraday_fixture


def canonical_trading_output(result: Mapping[str, Any]) -> bytes:
    return json.dumps(
        {"summary": result["summary"], "trades": result["trades"]},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def test_legacy_engine_fixture_remains_frozen():
    result = run_backtest_on_bars(
        intraday_fixture(),
        BacktestConfig(
            side="short",
            entry_rules="close.cross_below:vwap",
            stop_pct=10,
            target_pct=10,
            max_hold_minutes=1,
            slippage_bps=0,
        ),
    )
    assert result["summary"] == {
        "trades": 1,
        "wins": 1,
        "losses": 0,
        "win_rate_pct": 100.0,
        "total_pnl_dollars": 10.204082,
        "expected_pnl_per_trade": 10.204082,
        "average_return_pct": 1.020408,
        "max_drawdown_pct": 0.0,
        "ending_equity": 10010.204082,
    }
    assert result["trades"][0]["entry_price"] == 98.0
    assert result["trades"][0]["exit_price"] == 97.0
    assert result["trades"][0]["exit_reason"] == "end_of_data"


def _direct_dependencies(tmp_path, *, derived_cache_enabled: bool) -> OrchestratorDependencies:
    return OrchestratorDependencies(
        provider=CachedProvider(
            MassiveProvider("test-key"),
            BarCache(),
            provider_name="massive",
        ),
        provider_name="massive",
        variable_store=VariableSnapshotStore(DerivedFrameCache()),
        variable_registry=baseline_variable_registry(),
        strategy_registry=baseline_strategy_registry(),
        derived_cache_enabled=derived_cache_enabled,
        build_identity={"git_commit": "equivalence-fixture"},
    )


def _install_massive_fixture(monkeypatch):
    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        if timeframe == "1d":
            return daily_fixture(
                start,
                end,
                {"NVDA": 300.0, "SOXX": 200.0, "QQQ": 500.0}[symbol],
                {"NVDA": -0.2, "SOXX": 0.1, "QQQ": 0.05}[symbol],
            )
        return intraday_fixture()

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fake_fetch)


def test_legacy_adapter_and_direct_domain_path_have_identical_trading_output(
    monkeypatch, tmp_path
):
    # Break caught: a future adapter change could give the same request different fills or summary math.
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR", str(tmp_path / "derived"))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_ENABLED", "true")
    _install_massive_fixture(monkeypatch)
    request = baseline_request()

    legacy_result = asyncio.run(execute_backtest(request))
    direct_result = asyncio.run(
        execute_strategy_run(
            legacy_request_to_strategy_run(request),
            _direct_dependencies(tmp_path, derived_cache_enabled=True),
        )
    )
    new_result = serialize_strategy_run_result(request, direct_result)

    assert canonical_trading_output(new_result) == canonical_trading_output(legacy_result)
    assert new_result["summary"] == legacy_result["summary"]
    assert new_result["trades"] == legacy_result["trades"]
    assert direct_result.canonical is True
    assert direct_result.data["derived_cache"]["intraday"]["hit"] is True
    assert direct_result.data["derived_cache"]["regime"]["hit"] is True
    assert direct_result.data["derived_cache"]["sentiment"]["hit"] is True


def test_domain_cache_toggle_preserves_trading_bytes_and_warms_variable_cache(
    monkeypatch, tmp_path
):
    # Break caught: disabling persistence could alter inputs or enabled cache reuse could change a result.
    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_DIR", str(tmp_path / "derived"))
    _install_massive_fixture(monkeypatch)
    request = baseline_request()

    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_ENABLED", "false")
    uncached_domain = asyncio.run(
        execute_strategy_run(
            legacy_request_to_strategy_run(request),
            _direct_dependencies(tmp_path, derived_cache_enabled=False),
        )
    )
    uncached = serialize_strategy_run_result(request, uncached_domain)
    assert list((tmp_path / "derived").rglob("*.pkl.gz")) == []

    monkeypatch.setenv("BKTSTR_DERIVED_CACHE_ENABLED", "true")
    first_cached_domain = asyncio.run(
        execute_strategy_run(
            legacy_request_to_strategy_run(request),
            _direct_dependencies(tmp_path, derived_cache_enabled=True),
        )
    )
    second_cached_domain = asyncio.run(
        execute_strategy_run(
            legacy_request_to_strategy_run(request),
            _direct_dependencies(tmp_path, derived_cache_enabled=True),
        )
    )
    first_cached = serialize_strategy_run_result(request, first_cached_domain)
    second_cached = serialize_strategy_run_result(request, second_cached_domain)

    assert canonical_trading_output(uncached) == canonical_trading_output(first_cached)
    assert canonical_trading_output(first_cached) == canonical_trading_output(second_cached)
    assert second_cached_domain.data["derived_cache"]["intraday"]["hit"] is True
    assert second_cached_domain.data["derived_cache"]["regime"]["hit"] is True
    assert second_cached_domain.data["derived_cache"]["sentiment"]["hit"] is True
