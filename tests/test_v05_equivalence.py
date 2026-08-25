import json
from typing import Any, Mapping

from bktstr.engine import BacktestConfig, run_backtest_on_bars

from tests.v05_fixtures import intraday_fixture


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
