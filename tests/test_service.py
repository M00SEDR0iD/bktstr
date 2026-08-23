from bktstr.service import BacktestRequest


def test_request_rejects_excessive_range():
    try:
        BacktestRequest.from_values(
            symbol="NVDA",
            start="2024-01-01",
            end="2026-01-02",
            timeframe="1m",
            side="short",
            entry="close.cross_below:vwap",
        )
    except ValueError as exc:
        assert "730 days" in str(exc)
    else:
        raise AssertionError("expected excessive range to be rejected")


def test_request_normalizes_symbol_and_defaults():
    req = BacktestRequest.from_values(
        symbol=" nvda ",
        start="2026-08-01",
        end="2026-08-10",
        timeframe="1m",
        side="short",
        entry="close.cross_below:vwap",
    )
    assert req.symbol == "NVDA"
    assert req.stop_pct == 1.0
    assert req.target_pct == 3.0
    assert req.max_hold_minutes == 240


def test_provider_name_uses_yahoo_when_massive_key_missing_for_recent_intraday(monkeypatch):
    from bktstr.service import provider_name_for_request

    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    req = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-18",
        end="2026-08-23",
        timeframe="1m",
        side="short",
        entry="close.cross_below:vwap",
    )
    assert provider_name_for_request(req, today=req.end) == "yahoo"
