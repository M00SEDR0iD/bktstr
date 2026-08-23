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
