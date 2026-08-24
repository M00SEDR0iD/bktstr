import pandas as pd

from bktstr.engine import BacktestConfig, run_backtest_on_bars


def bars(rows):
    index = pd.to_datetime([r[0] for r in rows], utc=True).tz_convert("America/New_York")
    return pd.DataFrame(
        {
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
        },
        index=index,
    )


def test_short_signal_enters_next_bar_and_hits_target():
    data = bars(
        [
            ("2026-08-03 13:30:00+00:00", 100, 101, 99, 101, 1000),
            ("2026-08-03 13:31:00+00:00", 101, 101, 98, 99, 1000),
            ("2026-08-03 13:32:00+00:00", 98, 99, 96, 97, 1000),
            ("2026-08-03 13:33:00+00:00", 97, 98, 94, 95, 1000),
        ]
    )
    config = BacktestConfig(
        side="short",
        entry_rules="close.cross_below:vwap",
        stop_pct=2,
        target_pct=3,
        max_hold_minutes=30,
        position_size=1000,
        starting_capital=10000,
        slippage_bps=0,
    )
    result = run_backtest_on_bars(data, config)
    assert result["summary"]["trades"] == 1
    trade = result["trades"][0]
    assert trade["entry_time"].startswith("2026-08-03T09:32")
    assert trade["entry_price"] == 98.0
    assert trade["exit_reason"] == "target"
    assert trade["exit_price"] == 95.06
    assert round(trade["pnl_dollars"], 2) == 30.00


def test_same_bar_stop_and_target_uses_conservative_stop_first():
    data = bars(
        [
            ("2026-08-03 13:30:00+00:00", 100, 101, 99, 101, 1000),
            ("2026-08-03 13:31:00+00:00", 101, 101, 98, 99, 1000),
            ("2026-08-03 13:32:00+00:00", 100, 104, 96, 100, 1000),
        ]
    )
    config = BacktestConfig(
        side="short",
        entry_rules="close.cross_below:vwap",
        stop_pct=2,
        target_pct=2,
        max_hold_minutes=30,
        position_size=1000,
        starting_capital=10000,
        slippage_bps=0,
    )
    result = run_backtest_on_bars(data, config)
    assert result["trades"][0]["exit_reason"] == "stop"
    assert result["trades"][0]["pnl_dollars"] == -20.0


def test_slippage_is_applied_against_the_trader():
    data = bars(
        [
            ("2026-08-03 13:30:00+00:00", 100, 101, 99, 101, 1000),
            ("2026-08-03 13:31:00+00:00", 101, 101, 98, 99, 1000),
            ("2026-08-03 13:32:00+00:00", 100, 100, 97, 98, 1000),
            ("2026-08-03 13:33:00+00:00", 98, 99, 96, 97, 1000),
        ]
    )
    config = BacktestConfig(
        side="short",
        entry_rules="close.cross_below:vwap",
        stop_pct=10,
        target_pct=2,
        max_hold_minutes=30,
        position_size=1000,
        starting_capital=10000,
        slippage_bps=10,
    )
    result = run_backtest_on_bars(data, config)
    trade = result["trades"][0]
    assert trade["entry_price"] == 99.9
    assert trade["exit_price"] > 97.902  # adverse slippage on a short exit


def test_regular_hours_indicators_exclude_premarket_data():
    data = bars(
        [
            # Huge premarket volume at a very different price must not affect RTH VWAP.
            ("2026-08-03 12:00:00+00:00", 50, 50, 50, 50, 1_000_000),
            ("2026-08-03 13:30:00+00:00", 100, 100, 100, 100, 1000),
            ("2026-08-03 13:31:00+00:00", 99, 99, 99, 99, 1000),
            ("2026-08-03 13:32:00+00:00", 98, 98, 97, 97.5, 1000),
        ]
    )
    config = BacktestConfig(
        side="short",
        entry_rules="close.cross_below:vwap",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=30,
        position_size=1000,
        starting_capital=10000,
        slippage_bps=0,
        regular_hours_only=True,
    )
    result = run_backtest_on_bars(data, config)
    assert result["summary"]["trades"] == 1
    assert result["trades"][0]["entry_time"].startswith("2026-08-03T09:32")


def test_entry_time_window_blocks_entries_before_start_time():
    data = bars(
        [
            ("2026-08-03 16:58:00+00:00", 100, 101, 99, 101, 1000),  # 12:58 ET
            ("2026-08-03 16:59:00+00:00", 101, 101, 98, 99, 1000),   # signal 12:59 ET
            ("2026-08-03 17:00:00+00:00", 98, 99, 97, 98, 1000),     # entry 13:00 ET
            ("2026-08-03 17:01:00+00:00", 98, 99, 97, 98, 1000),
        ]
    )
    allowed = run_backtest_on_bars(
        data,
        BacktestConfig(
            side="short",
            entry_rules="close.cross_below:vwap",
            stop_pct=10,
            target_pct=10,
            max_hold_minutes=1,
            slippage_bps=0,
            entry_start_time="13:00",
            entry_end_time="16:00",
        ),
    )
    blocked = run_backtest_on_bars(
        data,
        BacktestConfig(
            side="short",
            entry_rules="close.cross_below:vwap",
            stop_pct=10,
            target_pct=10,
            max_hold_minutes=1,
            slippage_bps=0,
            entry_start_time="13:01",
            entry_end_time="16:00",
        ),
    )
    assert allowed["summary"]["trades"] == 1
    assert allowed["trades"][0]["entry_time"].startswith("2026-08-03T13:00")
    assert blocked["summary"]["trades"] == 0


def test_regime_rules_gate_an_otherwise_valid_entry():
    data = bars(
        [
            ("2026-08-03 13:30:00+00:00", 100, 101, 99, 101, 1000),
            ("2026-08-03 13:31:00+00:00", 101, 101, 98, 99, 1000),
            ("2026-08-03 13:32:00+00:00", 98, 99, 97, 98, 1000),
            ("2026-08-03 13:33:00+00:00", 98, 99, 97, 98, 1000),
        ]
    )
    data["day_close"] = 100.0

    allowed = run_backtest_on_bars(
        data,
        BacktestConfig(
            side="short",
            entry_rules="close.cross_below:vwap",
            regime_rules="day_close.gt:90",
            stop_pct=10,
            target_pct=10,
            max_hold_minutes=1,
            slippage_bps=0,
        ),
    )
    blocked = run_backtest_on_bars(
        data,
        BacktestConfig(
            side="short",
            entry_rules="close.cross_below:vwap",
            regime_rules="day_close.lt:90",
            stop_pct=10,
            target_pct=10,
            max_hold_minutes=1,
            slippage_bps=0,
        ),
    )

    assert allowed["summary"]["trades"] == 1
    assert blocked["summary"]["trades"] == 0


def test_cross_rule_does_not_compare_first_bar_with_prior_session():
    data = bars(
        [
            ("2026-08-03 19:59:00+00:00", 100, 100, 100, 100, 1000),  # 15:59 ET
            ("2026-08-04 13:30:00+00:00", 100, 110, 90, 95, 1000),    # 09:30 ET
            ("2026-08-04 13:31:00+00:00", 95, 100, 90, 94, 1000),
        ]
    )
    result = run_backtest_on_bars(
        data,
        BacktestConfig(
            side="short",
            entry_rules="close.cross_below:vwap",
            stop_pct=10,
            target_pct=10,
            max_hold_minutes=1,
            slippage_bps=0,
        ),
    )

    assert result["summary"]["trades"] == 0


def test_engine_records_sentiment_metadata_without_changing_position_size():
    import pandas as pd

    from bktstr.engine import BacktestConfig, run_backtest_on_bars

    idx = pd.DatetimeIndex(
        ["2026-08-18 13:00", "2026-08-18 13:01", "2026-08-18 13:02"],
        tz="America/New_York",
    )
    bars = pd.DataFrame(
        {
            "open": [100.0, 99.0, 98.0],
            "high": [100.0, 99.0, 98.0],
            "low": [99.0, 98.0, 97.0],
            "close": [99.5, 98.5, 97.5],
            "volume": [1000.0, 1000.0, 1000.0],
            "sentiment_direction": [-0.6, -0.6, -0.6],
            "sentiment_confidence": [0.8, 0.8, 0.8],
            "sentiment_completeness": [1.0, 1.0, 1.0],
            "sentiment_multiplier_long": [0.76, 0.76, 0.76],
            "sentiment_multiplier_short": [1.24, 1.24, 1.24],
            "sentiment_leadership_score": [-0.7, -0.7, -0.7],
            "sentiment_trend_score": [-0.5, -0.5, -0.5],
            "sentiment_peak_score": [-0.4, -0.4, -0.4],
            "sentiment_persistence_score": [-0.8, -0.8, -0.8],
        },
        index=idx,
    )
    result = run_backtest_on_bars(
        bars,
        BacktestConfig(
            side="short",
            entry_rules="close.lt:1000",
            stop_pct=10,
            target_pct=10,
            max_hold_minutes=1,
            position_size=1000,
            slippage_bps=0,
        ),
    )

    assert result["summary"]["trades"] == 1
    trade = result["trades"][0]
    assert trade["position_size"] == 1000.0
    assert trade["sentiment_direction"] == -0.6
    assert trade["sentiment_confidence"] == 0.8
    assert trade["sentiment_multiplier"] == 1.24
    assert trade["sentiment_multiplier_short"] == 1.24
    assert trade["sentiment_multiplier_long"] == 0.76
    assert result["summary"]["average_sentiment_direction"] == -0.6
    assert result["summary"]["average_sentiment_confidence"] == 0.8
    assert result["summary"]["average_sentiment_multiplier"] == 1.24


def test_v032_engine_records_sentiment_transition_metadata_without_resizing():
    idx = pd.DatetimeIndex(
        ["2026-08-18 13:00", "2026-08-18 13:01", "2026-08-18 13:02"],
        tz="America/New_York",
    )
    bars = pd.DataFrame(
        {
            "open": [100.0, 99.0, 98.0], "high": [100.0, 99.0, 98.0],
            "low": [99.0, 98.0, 97.0], "close": [99.5, 98.5, 97.5],
            "volume": [1000.0, 1000.0, 1000.0],
            "sentiment_direction": [-0.2] * 3,
            "sentiment_confidence": [0.4] * 3,
            "sentiment_completeness": [1.0] * 3,
            "sentiment_multiplier_long": [0.96] * 3,
            "sentiment_multiplier_short": [1.04] * 3,
            "sentiment_leadership_score": [-0.6] * 3,
            "sentiment_trend_score": [0.5] * 3,
            "sentiment_peak_score": [0.4] * 3,
            "sentiment_persistence_score": [-0.2] * 3,
            "sentiment_momentum20": [-0.5] * 3,
            "sentiment_momentum60": [-0.3] * 3,
            "sentiment_momentum": [-0.43] * 3,
            "sentiment_component_spread": [0.7] * 3,
            "sentiment_volatility_stress": [0.6] * 3,
            "sentiment_fragility": [0.65] * 3,
        }, index=idx,
    )
    cfg = BacktestConfig(
        side="short", entry_rules="close.lt:1000", stop_pct=10, target_pct=10,
        max_hold_minutes=1, position_size=1000, starting_capital=10000, slippage_bps=0,
    )
    result = run_backtest_on_bars(bars, cfg)
    trade = result["trades"][0]
    assert trade["position_size"] == 1000.0
    assert trade["sentiment_fragility"] == 0.65
    assert trade["sentiment_momentum"] == -0.43
    assert result["summary"]["average_sentiment_fragility"] == 0.65
    assert result["summary"]["average_sentiment_momentum"] == -0.43
