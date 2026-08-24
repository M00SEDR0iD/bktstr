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


def test_parse_backtest_query_accepts_regime_and_benchmark():
    req, _ = parse_backtest_query(
        "symbol=nvda&start=2026-08-18&end=2026-08-23&timeframe=1m&side=short&"
        "entry=close.cross_below%3Avwap&regime=relative_return20.lt%3A0&benchmark=soxx"
    )
    assert req.regime == "relative_return20.lt:0"
    assert req.benchmark == "SOXX"


def test_capabilities_report_v031_regime_support():
    from bktstr.server import CAPABILITIES

    assert CAPABILITIES["version"] == "0.3.2"
    assert "regime" in CAPABILITIES
    assert "relative_return20" in CAPABILITIES["regime"]["fields"]


def test_parse_backtest_query_accepts_sentiment_layer_parameters():
    req, _ = parse_backtest_query(
        "symbol=nvda&start=2026-08-18&end=2026-08-23&timeframe=1m&side=short&"
        "entry=close.cross_below%3Avwap&sentiment=true&"
        "sentiment_sector_benchmark=soxx&sentiment_market_benchmark=qqq"
    )
    assert req.sentiment is True
    assert req.sentiment_sector_benchmark == "SOXX"
    assert req.sentiment_market_benchmark == "QQQ"


def test_capabilities_report_v031_sentiment_support():
    from bktstr.server import CAPABILITIES

    assert CAPABILITIES["version"] == "0.3.2"
    assert "sentiment" in CAPABILITIES
    assert CAPABILITIES["sentiment"]["direction_range"] == [-1.0, 1.0]
    assert CAPABILITIES["sentiment"]["multipliers_are_informational"] is True


def test_v032_query_accepts_clean_sentiment_profile_and_sources():
    req, _ = parse_backtest_query(
        "symbol=nvda&start=2026-08-18&end=2026-08-23&timeframe=1m&side=short&"
        "entry=close.cross_below%3Avwap&sentiment=true&sentiment_sector_benchmark=soxx&"
        "sentiment_market_benchmark=qqq&sentiment_data_profile=clean&sentiment_sources=price"
    )
    assert req.sentiment_data_profile == "clean"
    assert req.sentiment_sources == ("price",)


def test_v032_capabilities_publish_transition_and_provenance_contract():
    from bktstr.server import CAPABILITIES

    assert CAPABILITIES["version"] == "0.3.2"
    sentiment = CAPABILITIES["sentiment"]
    assert sentiment["fragility_range"] == [0.0, 1.0]
    assert sentiment["momentum_range"] == [-1.0, 1.0]
    assert "sentiment_fragility" in sentiment["outputs"]
    assert sentiment["data_profiles"]["default"] == "clean"
    assert sentiment["data_profiles"]["tiers"]["A"]["label"] == "clean"
