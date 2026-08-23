from datetime import date

from bktstr.providers import iter_date_chunks, massive_aggregate_url


def test_date_chunks_cover_range_without_overlap():
    chunks = list(iter_date_chunks(date(2026, 1, 1), date(2026, 3, 5), days=30))
    assert chunks == [
        (date(2026, 1, 1), date(2026, 1, 30)),
        (date(2026, 1, 31), date(2026, 3, 1)),
        (date(2026, 3, 2), date(2026, 3, 5)),
    ]


def test_massive_url_uses_minute_aggregate_endpoint():
    url = massive_aggregate_url("NVDA", date(2026, 1, 1), date(2026, 1, 30), "1m")
    assert url == "https://api.massive.com/v2/aggs/ticker/NVDA/range/1/minute/2026-01-01/2026-01-30"


def test_yahoo_recent_window_is_only_used_for_recent_intraday_data():
    from bktstr.providers import can_use_yahoo_intraday

    assert can_use_yahoo_intraday(date(2026, 8, 18), date(2026, 8, 23), "1m", today=date(2026, 8, 23))
    assert not can_use_yahoo_intraday(date(2026, 7, 1), date(2026, 7, 5), "1m", today=date(2026, 8, 23))
    assert not can_use_yahoo_intraday(date(2026, 8, 18), date(2026, 8, 23), "1d", today=date(2026, 8, 23))


def test_parse_yahoo_chart_payload_to_ohlcv():
    from bktstr.providers import parse_yahoo_chart_payload

    payload = {
        "chart": {
            "error": None,
            "result": [{
                "timestamp": [1787491800, 1787491860],
                "indicators": {"quote": [{
                    "open": [100.0, 101.0],
                    "high": [101.0, 102.0],
                    "low": [99.0, 100.0],
                    "close": [100.5, 101.5],
                    "volume": [1000, 1200],
                }]},
            }],
        }
    }
    frame = parse_yahoo_chart_payload(payload)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) == 2
    assert frame.iloc[1]["close"] == 101.5
