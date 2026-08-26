import asyncio
from datetime import date, datetime

import pytest

import bktstr.services.backtest as backtest_service
from bktstr.services.backtest import (
    BacktestInput,
    project_research_result,
    run_backtest,
    to_legacy_request,
)
from bktstr.services.data import normalize_market_request
from bktstr.services.regimes import RegimeInput, normalize_regime_request
from bktstr.services.validation import SemanticValidationError, StrategyCompatibilityError


BASE_INPUT = {
    "strategy_id": "bktstr.bearish-regime-scalp",
    "strategy_version": "1.0.0",
    "symbol": "NVDA",
    "start": date(2026, 8, 17),
    "end": date(2026, 8, 17),
    "timeframe": "1m",
    "side": "short",
    "entry": "close.cross_below:vwap",
}


def test_backtest_input_rejects_timeframe_incompatible_with_registered_strategy():
    with pytest.raises(StrategyCompatibilityError) as raised:
        BacktestInput(
            strategy_id="bktstr.bearish-regime-scalp",
            strategy_version="1.0.0",
            symbol="NVDA",
            start=date(2026, 8, 17),
            end=date(2026, 8, 17),
            timeframe="1d",
            side="short",
            entry="close.cross_below:vwap",
        )

    error = raised.value
    assert error.fields == ("market.timeframe",)
    assert error.strategy_id == "bktstr.bearish-regime-scalp"
    assert error.strategy_version == "1.0.0"
    assert error.required_timeframe == "1m"
    assert error.received_timeframe == "1d"


def test_strategy_compatibility_error_keeps_metadata_when_prefixed():
    original = StrategyCompatibilityError(
        "incompatible",
        ("market.timeframe",),
        strategy_id="strategy",
        strategy_version="1",
        required_timeframe="1m",
        received_timeframe="1d",
    )

    prefixed = original.prefixed("base")

    assert isinstance(prefixed, StrategyCompatibilityError)
    assert prefixed.fields == ("base.market.timeframe",)
    assert prefixed.required_timeframe == "1m"
    assert prefixed.received_timeframe == "1d"


def _one_trade_legacy_result() -> dict:
    return {
        "request": {
            "symbol": "NVDA",
            "start": "2026-08-17",
            "end": "2026-08-17",
            "timeframe": "1m",
            "side": "short",
            "entry": "close.cross_below:vwap",
            "regime": None,
            "benchmark": None,
            "sentiment": False,
            "sentiment_sector_benchmark": None,
            "sentiment_market_benchmark": None,
            "sentiment_data_profile": "clean",
            "sentiment_sources": ["price"],
            "stop_pct": 1.0,
            "target_pct": 3.0,
            "max_hold_minutes": 240,
            "position_size": 1000.0,
            "starting_capital": 10000.0,
            "slippage_bps": 2.0,
            "entry_start_time": None,
            "entry_end_time": None,
        },
        "data": {
            "bars": 3,
            "provider": "fixture",
            "cache": {"hit_days": 0, "miss_days": 1, "fetched_ranges": 1},
            "derived_cache": {
                "enabled": True,
                "intraday": {
                    "hit": False,
                    "elapsed_seconds": 0.01,
                    "recovered_corruption": False,
                },
            },
        },
        "summary": {
            "trades": 1,
            "wins": 1,
            "losses": 0,
            "win_rate_pct": 100.0,
            "total_pnl_dollars": 12.5,
            "expected_pnl_per_trade": 12.5,
            "average_return_pct": 1.25,
            "max_drawdown_pct": 0.0,
            "ending_equity": 10012.5,
        },
        "trades": [
            {
                "signal_time": "2026-08-17T09:30:00-04:00",
                "entry_time": "2026-08-17T09:31:00-04:00",
                "entry_price": 100.0,
                "exit_time": "2026-08-17T09:36:00-04:00",
                "exit_price": 98.75,
                "exit_reason": "target",
                "side": "short",
                "position_size": 1000.0,
                "pnl_dollars": 12.5,
                "return_pct": 1.25,
                "mfe_pct": 1.5,
                "mae_pct": -0.25,
                "hold_minutes": 5,
                "sentiment_direction": -0.4,
                "sentiment_confidence": 0.8,
                "sentiment_fragility": 0.3,
            }
        ],
    }


def _governed_subject_provenance(
    *,
    digest: str = "a" * 64,
    available_start: str = "2026-08-17",
    available_end: str = "2026-08-17",
    observations: int = 3,
    cache: dict | None = None,
    elapsed_seconds: float = 0.01,
) -> dict:
    return {
        "dependency_trace": (
            {
                "id": "market.subject.close",
                "tier": "A",
                "materializations": (
                    {
                        "artifact_id": (
                            "market.subject.close@intraday:subject:1m:"
                            "2026-08-17:2026-08-18"
                        ),
                        "definition": {
                            "id": "market.subject.close",
                            "version": "1.0.0",
                            "kind": "source",
                            "tier": "A",
                            "column": "close",
                        },
                        "digest": digest,
                        "coverage": {
                            "requested_start": "2026-08-17",
                            "requested_end": "2026-08-18",
                            "available_start": available_start,
                            "available_end": available_end,
                            "observations": observations,
                        },
                        "cache": cache
                        or {"hit_days": 0, "miss_days": 1, "fetched_ranges": 1},
                        "scope": {
                            "purpose": "intraday",
                            "role": "subject",
                            "symbol": "NVDA",
                            "timeframe": "1m",
                        },
                    },
                ),
            },
            {
                "id": "technical.vwap",
                "tier": "B",
                "materializations": (
                    {
                        "digest": "b" * 64,
                        "cache": {"hit": True, "elapsed_seconds": elapsed_seconds},
                        "scope": {
                            "purpose": "intraday_features",
                            "role": "subject",
                            "symbol": "NVDA",
                            "timeframe": "1m",
                        },
                    },
                ),
            },
        ),
        "attachments": {
            "regime": {
                "cache": {"hit": True, "elapsed_seconds": elapsed_seconds}
            }
        },
    }


def test_typed_backtest_projects_research_fields_and_calls_legacy_once(monkeypatch):
    # Break caught: the service could re-run execution or omit reproducible trade context.
    calls = []

    async def deterministic_execute(request):
        calls.append(request)
        return _one_trade_legacy_result()

    monkeypatch.setattr(backtest_service, "execute_backtest", deterministic_execute)
    backtest_input = BacktestInput(**BASE_INPUT)

    result = asyncio.run(run_backtest(backtest_input))

    assert len(calls) == 1
    assert calls[0] == to_legacy_request(backtest_input)
    assert result.metrics.trade_count == 1
    assert result.metrics.ev_per_trade == 12.5
    assert result.metrics.win_rate == 100.0
    assert result.metrics.profit_factor is None
    assert result.metrics.sharpe is None
    assert result.metrics.total_pnl == 12.5
    assert result.metrics.total_return == 0.125
    assert result.provenance.strategy["id"] == "bktstr.bearish-regime-scalp"
    assert result.provenance.market_data["source"] == "fixture"
    # A completed experiment must be able to distinguish changed source data even
    # when the provider does not report a vendor version.
    assert result.provenance.market_data["snapshot_id"].startswith("sha256:")
    assert result.provenance.market_data["coverage"] == {
        "requested_start": "2026-08-17",
        "requested_end": "2026-08-17",
        "available_start": None,
        "available_end": None,
        "observations": 3,
        "bars": 3,
    }
    assert result.provenance.market_data["cache"] == {
        "hit_days": 0,
        "miss_days": 1,
        "fetched_ranges": 1,
    }
    assert result.provenance.execution_model == {
        "id": "bktstr.next-bar-open",
        "version": "1.0.0",
        "slippage_bps": 2.0,
    }
    trade = result.trades[0]
    assert trade.entry_timestamp == datetime.fromisoformat("2026-08-17T09:31:00-04:00")
    assert trade.exit_timestamp == datetime.fromisoformat("2026-08-17T09:36:00-04:00")
    assert trade.entry_price == 100.0
    assert trade.exit_price == 98.75
    assert trade.holding_time_minutes == 5
    assert trade.realized_pnl == 12.5
    assert trade.mfe == 1.5
    assert trade.mae == -0.25
    assert dict(trade.signal_values_at_entry) == {}
    assert dict(trade.regime_variables) == {
        "sentiment_confidence": 0.8,
        "sentiment_direction": -0.4,
        "sentiment_fragility": 0.3,
    }


def test_zero_trade_projection_returns_empty_trades_and_explicit_null_metrics():
    # Break caught: no-trade research could invent profit factor or Sharpe values.
    legacy = _one_trade_legacy_result()
    legacy["summary"] = {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": 0.0,
        "total_pnl_dollars": 0.0,
        "expected_pnl_per_trade": 0.0,
        "average_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "ending_equity": 10000.0,
    }
    legacy["trades"] = []

    result = project_research_result(BacktestInput(**BASE_INPUT), legacy)

    assert result.trades == ()
    assert result.metrics.trade_count == 0
    assert result.metrics.profit_factor is None
    assert result.metrics.sharpe is None


def test_market_snapshot_identity_ignores_cache_timing_and_attachments():
    # Break caught: cache hits or timing diagnostics could identify executions
    # instead of the immutable subject intraday market data.
    value = BacktestInput(
        **{**BASE_INPUT, "start": date(2026, 8, 17), "end": date(2026, 8, 18)}
    )
    miss = project_research_result(
        value,
        _one_trade_legacy_result(),
        execution_provenance=_governed_subject_provenance(
            cache={"hit_days": 0, "miss_days": 1, "fetched_ranges": 1},
            elapsed_seconds=0.01,
        ),
    )
    hit = project_research_result(
        value,
        _one_trade_legacy_result(),
        execution_provenance=_governed_subject_provenance(
            cache={"hit_days": 1, "miss_days": 0, "fetched_ranges": 0},
            elapsed_seconds=99.0,
        ),
    )
    changed = project_research_result(
        value,
        _one_trade_legacy_result(),
        execution_provenance=_governed_subject_provenance(
            digest="c" * 64,
            cache={"hit_days": 1, "miss_days": 0, "fetched_ranges": 0},
            elapsed_seconds=99.0,
        ),
    )

    assert miss.provenance.market_data["snapshot_id"] == hit.provenance.market_data[
        "snapshot_id"
    ]
    assert miss.provenance.market_data["snapshot_id"] != changed.provenance.market_data[
        "snapshot_id"
    ]


def test_market_coverage_uses_governed_subject_intraday_materialization():
    # Break caught: requested bounds or legacy counters could masquerade as the
    # actual governed market observations available to the experiment.
    value = BacktestInput(
        **{**BASE_INPUT, "start": date(2026, 8, 17), "end": date(2026, 8, 18)}
    )

    result = project_research_result(
        value,
        _one_trade_legacy_result(),
        execution_provenance=_governed_subject_provenance(
            available_start="2026-08-17",
            available_end="2026-08-17",
            observations=3,
        ),
    )

    assert result.provenance.market_data["coverage"] == {
        "requested_start": "2026-08-17",
        "requested_end": "2026-08-18",
        "available_start": "2026-08-17",
        "available_end": "2026-08-17",
        "observations": 3,
        "bars": 3,
    }


def test_non_overridable_strategy_parameter_is_rejected():
    # Break caught: callers could replace the registered execution model through parameters.
    with pytest.raises(ValueError, match="overridable"):
        BacktestInput(**BASE_INPUT, parameters={"execution_model": "other"})


def test_market_and_regime_normalization_reuse_legacy_constraints():
    # Break caught: the typed service could accept data or regime inputs the v0.5 path rejects.
    market = normalize_market_request(
        symbol=" nvda ",
        start=date(2026, 8, 17),
        end=date(2026, 8, 17),
        timeframe="1m",
        source="auto",
    )
    regime = normalize_regime_request(
        RegimeInput(
            enabled=True,
            rules="relative_return20.lt:0",
            benchmark=" spy ",
        )
    )

    assert market.symbol == "NVDA"
    assert regime is not None
    assert regime.benchmark == "SPY"
    with pytest.raises(ValueError, match="source"):
        normalize_market_request(
            symbol="NVDA",
            start=date(2026, 8, 17),
            end=date(2026, 8, 17),
            timeframe="1m",
            source="unregistered",
        )
    with pytest.raises(ValueError, match="benchmark is required"):
        normalize_regime_request(
            RegimeInput(enabled=True, rules="relative_return20.lt:0")
        )


@pytest.mark.parametrize(
    ("regime", "fields"),
    [
        (
            RegimeInput(rules="relative_return20.lt:0", benchmark="bad symbol"),
            ("regime.benchmark",),
        ),
        (
            RegimeInput(rules="relative_return20.lt:0"),
            ("regime.benchmark",),
        ),
        (
            RegimeInput(rules="sentiment_fragility.gte:0.35"),
            ("regime.sentiment_enabled",),
        ),
        (
            RegimeInput(rules="day_close.cross_below:day_sma20"),
            ("regime.rules",),
        ),
        (
            RegimeInput(
                rules="sentiment_fragility.gte:0.35", sentiment_enabled=True
            ),
            (
                "regime.sentiment_sector_benchmark",
                "regime.sentiment_market_benchmark",
            ),
        ),
        (
            RegimeInput(sentiment_data_profile="experimental"),
            ("regime.sentiment_data_profile",),
        ),
        (
            RegimeInput(sentiment_sources=("news",)),
            ("regime.sentiment_sources",),
        ),
    ],
)
def test_regime_normalization_reports_exact_structured_fields(regime, fields):
    # Break caught: human-readable labels or a broad `regime` path could escape
    # the typed service boundary and make API errors ambiguous.
    with pytest.raises(SemanticValidationError) as raised:
        normalize_regime_request(regime)

    assert raised.value.fields == fields


def test_legacy_request_mapping_preserves_registered_execution_parameters():
    # Break caught: typed parameters could be lost or remapped before frozen execution.
    request = to_legacy_request(
        BacktestInput(
            **BASE_INPUT,
            parameters={
                "stop_pct": 2.0,
                "target_pct": 4.0,
                "max_hold_minutes": 30,
                "position_size": 500.0,
                "starting_capital": 20000.0,
                "slippage_bps": 1.0,
                "regular_hours_only": False,
                "same_day_only": False,
                "entry_start_time": "10:00",
                "entry_end_time": "15:00",
            },
        )
    )

    assert request.stop_pct == 2.0
    assert request.target_pct == 4.0
    assert request.max_hold_minutes == 30
    assert request.position_size == 500.0
    assert request.starting_capital == 20000.0
    assert request.slippage_bps == 1.0
    assert request.regular_hours_only is False
    assert request.same_day_only is False
    assert request.entry_start_time == "10:00"
    assert request.entry_end_time == "15:00"
