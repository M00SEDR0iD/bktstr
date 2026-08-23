from bktstr.server import parse_backtest_query


def test_parse_backtest_query_builds_request_and_output_controls():
    req, options = parse_backtest_query(
        "symbol=nvda&start=2026-08-18&end=2026-08-23&timeframe=1m&side=short&"
        "entry=close.cross_below%3Avwap&stop_pct=1.2&target_pct=3.5&trade_limit=25"
    )
    assert req.symbol == "NVDA"
    assert req.stop_pct == 1.2
    assert req.target_pct == 3.5
    assert options == {"trade_limit": 25}


def test_parse_backtest_query_accepts_entry_time_window():
    req, _ = parse_backtest_query(
        "symbol=nvda&start=2026-08-18&end=2026-08-23&timeframe=1m&side=short&"
        "entry=close.cross_below%3Avwap&entry_start_time=13%3A00&entry_end_time=16%3A00"
    )
    assert req.entry_start_time == "13:00"
    assert req.entry_end_time == "16:00"
