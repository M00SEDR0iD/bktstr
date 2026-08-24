from bktstr.server import CAPABILITIES, parse_backtest_query


def test_parse_backtest_query_builds_request_controls():
    req,opt=parse_backtest_query("symbol=nvda&start=2026-08-18&end=2026-08-23&timeframe=1m&side=short&entry=close.cross_below%3Avwap&stop_pct=1.2&target_pct=3.5&trade_limit=25")
    assert req.symbol=="NVDA" and req.stop_pct==1.2 and req.target_pct==3.5 and opt=={"trade_limit":25}


def test_query_accepts_regime_sentiment_and_window():
    req,_=parse_backtest_query("symbol=nvda&start=2026-08-18&end=2026-08-23&timeframe=1m&side=short&entry=close.cross_below%3Avwap&entry_start_time=13%3A00&entry_end_time=16%3A00&regime=relative_return20.lt%3A0&benchmark=soxx&sentiment=true&sentiment_sector_benchmark=soxx&sentiment_market_benchmark=qqq&sentiment_data_profile=clean&sentiment_sources=price")
    assert req.entry_start_time=="13:00" and req.benchmark=="SOXX" and req.sentiment and req.sentiment_market_benchmark=="QQQ"


def test_capabilities_v034_contract():
    assert CAPABILITIES["version"]=="0.3.4"
    assert "sentiment_fragility" in CAPABILITIES["regime"]["fields"]
    assert CAPABILITIES["sentiment"]["data_profiles"]["default"]=="clean"
    assert CAPABILITIES["cache"]["derived"]["strategy_decisions_cached"] is False
