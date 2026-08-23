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


def test_execute_backtest_reuses_market_data_cache(monkeypatch, tmp_path):
    import asyncio
    import pandas as pd

    from bktstr.providers import MassiveProvider
    from bktstr.service import execute_backtest

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path))
    calls = {"count": 0}

    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        calls["count"] += 1
        idx = pd.DatetimeIndex(
            [
                "2026-08-17 09:30:00",
                "2026-08-17 09:31:00",
                "2026-08-17 09:32:00",
            ],
            tz="America/New_York",
        )
        return pd.DataFrame(
            {
                "open": [100.0, 100.0, 99.0],
                "high": [100.0, 100.0, 99.0],
                "low": [100.0, 99.0, 98.0],
                "close": [100.0, 99.0, 98.0],
                "volume": [1000.0, 1000.0, 1000.0],
            },
            index=idx,
        )

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fake_fetch)
    req = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-17",
        end="2026-08-17",
        timeframe="1m",
        side="short",
        entry="close.cross_below:vwap",
    )

    first = asyncio.run(execute_backtest(req))
    second = asyncio.run(execute_backtest(req))

    assert calls["count"] == 1
    assert first["data"]["cache"] == {"hit_days": 0, "miss_days": 1, "fetched_ranges": 1}
    assert second["data"]["cache"] == {"hit_days": 1, "miss_days": 0, "fetched_ranges": 0}
