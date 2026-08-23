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
