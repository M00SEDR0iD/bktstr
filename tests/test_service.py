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


def test_request_accepts_and_validates_entry_time_window():
    req = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-01",
        end="2026-08-10",
        side="short",
        entry="close.cross_below:vwap",
        entry_start_time="13:00",
        entry_end_time="16:00",
    )
    assert req.entry_start_time == "13:00"
    assert req.entry_end_time == "16:00"

    for start_time, end_time in [("13", "16:00"), ("16:00", "13:00")]:
        try:
            BacktestRequest.from_values(
                symbol="NVDA",
                start="2026-08-01",
                end="2026-08-10",
                side="short",
                entry="close.cross_below:vwap",
                entry_start_time=start_time,
                entry_end_time=end_time,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("expected invalid entry time window to be rejected")


def test_request_accepts_regime_and_benchmark_and_validates_dependencies():
    req = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-01",
        end="2026-08-10",
        timeframe="1m",
        side="short",
        entry="close.cross_below:vwap",
        regime="relative_return20.lt:0",
        benchmark="soxx",
    )
    assert req.regime == "relative_return20.lt:0"
    assert req.benchmark == "SOXX"

    try:
        BacktestRequest.from_values(
            symbol="NVDA",
            start="2026-08-01",
            end="2026-08-10",
            timeframe="1m",
            side="short",
            entry="close.cross_below:vwap",
            regime="relative_return20.lt:0",
        )
    except ValueError as exc:
        assert "benchmark is required" in str(exc)
    else:
        raise AssertionError("expected benchmark-dependent regime to require benchmark")


def test_execute_backtest_fetches_and_reports_daily_regime_data(monkeypatch, tmp_path):
    import asyncio
    from datetime import timedelta

    import pandas as pd

    from bktstr.providers import MassiveProvider
    from bktstr.service import execute_backtest

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path))
    calls = []

    def daily_frame(start, end, base):
        dates = pd.date_range(start=start, end=end, freq="B", tz="America/New_York")
        closes = [base + i * 0.1 for i in range(len(dates))]
        return pd.DataFrame(
            {
                "open": closes,
                "high": [v + 1 for v in closes],
                "low": [v - 1 for v in closes],
                "close": closes,
                "volume": [1000.0] * len(dates),
            },
            index=dates,
        )

    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        calls.append((symbol, start, end, timeframe))
        if timeframe == "1d":
            return daily_frame(start, end, 100.0 if symbol == "NVDA" else 200.0)
        idx = pd.DatetimeIndex(
            [
                "2026-08-17 13:00:00",
                "2026-08-17 13:01:00",
                "2026-08-17 13:02:00",
            ],
            tz="America/New_York",
        )
        return pd.DataFrame(
            {
                "open": [100.0, 99.0, 98.0],
                "high": [101.0, 100.0, 99.0],
                "low": [99.0, 98.0, 97.0],
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
        entry="close.lt:1000",
        regime="day_close.gt:0,relative_return20.gt:-100",
        benchmark="SOXX",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=1,
        slippage_bps=0,
    )

    result = asyncio.run(execute_backtest(req))

    assert result["request"]["regime"] == req.regime
    assert result["request"]["benchmark"] == "SOXX"
    assert result["data"]["regime"]["subject_daily_bars"] > 50
    assert result["data"]["regime"]["benchmark_daily_bars"] > 50
    assert result["summary"]["trades"] == 1
    assert any(call[0] == "NVDA" and call[3] == "1d" for call in calls)
    assert any(call[0] == "SOXX" and call[3] == "1d" for call in calls)
    daily_nvda_call = next(call for call in calls if call[0] == "NVDA" and call[3] == "1d")
    assert daily_nvda_call[1] == req.start - timedelta(days=120)


def test_request_accepts_sentiment_and_requires_both_benchmarks():
    req = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-01",
        end="2026-08-10",
        timeframe="1m",
        side="short",
        entry="close.cross_below:vwap",
        sentiment=True,
        sentiment_sector_benchmark="soxx",
        sentiment_market_benchmark="qqq",
    )
    assert req.sentiment is True
    assert req.sentiment_sector_benchmark == "SOXX"
    assert req.sentiment_market_benchmark == "QQQ"

    for sector, market in [(None, "QQQ"), ("SOXX", None)]:
        try:
            BacktestRequest.from_values(
                symbol="NVDA",
                start="2026-08-01",
                end="2026-08-10",
                timeframe="1m",
                side="short",
                entry="close.cross_below:vwap",
                sentiment=True,
                sentiment_sector_benchmark=sector,
                sentiment_market_benchmark=market,
            )
        except ValueError as exc:
            assert "sentiment" in str(exc).lower() and "benchmark" in str(exc).lower()
        else:
            raise AssertionError("expected sentiment to require both benchmarks")


def test_execute_backtest_fetches_attaches_and_reports_sentiment_data(monkeypatch, tmp_path):
    import asyncio
    from datetime import timedelta

    import pandas as pd

    from bktstr.providers import MassiveProvider
    from bktstr.service import execute_backtest

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path))
    calls = []

    def daily_frame(start, end, base, slope):
        dates = pd.date_range(start=start, end=end, freq="B", tz="America/New_York")
        closes = [base + i * slope for i in range(len(dates))]
        return pd.DataFrame(
            {
                "open": closes,
                "high": [v + 1 for v in closes],
                "low": [v - 1 for v in closes],
                "close": closes,
                "volume": [1000.0] * len(dates),
            },
            index=dates,
        )

    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        calls.append((symbol, start, end, timeframe))
        if timeframe == "1d":
            slopes = {"NVDA": -0.3, "SOXX": 0.1, "QQQ": 0.05}
            bases = {"NVDA": 300.0, "SOXX": 200.0, "QQQ": 500.0}
            return daily_frame(start, end, bases[symbol], slopes[symbol])
        idx = pd.DatetimeIndex(
            ["2026-08-17 13:00", "2026-08-17 13:01", "2026-08-17 13:02"],
            tz="America/New_York",
        )
        return pd.DataFrame(
            {
                "open": [100.0, 99.0, 98.0],
                "high": [100.0, 99.0, 98.0],
                "low": [99.0, 98.0, 97.0],
                "close": [99.5, 98.5, 97.5],
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
        entry="close.lt:1000",
        sentiment=True,
        sentiment_sector_benchmark="SOXX",
        sentiment_market_benchmark="QQQ",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=1,
        slippage_bps=0,
    )

    result = asyncio.run(execute_backtest(req))

    assert result["request"]["sentiment"] is True
    assert result["data"]["sentiment"]["sector_benchmark"] == "SOXX"
    assert result["data"]["sentiment"]["market_benchmark"] == "QQQ"
    assert result["data"]["sentiment"]["warmup_start"] == (req.start - timedelta(days=460)).isoformat()
    assert result["summary"]["trades"] == 1
    assert "sentiment_direction" in result["trades"][0]
    assert any(call[0] == "SOXX" and call[3] == "1d" for call in calls)
    assert any(call[0] == "QQQ" and call[3] == "1d" for call in calls)


def test_v032_sentiment_profile_defaults_to_clean_and_rejects_unavailable_sources():
    req = BacktestRequest.from_values(
        symbol="NVDA", start="2026-08-01", end="2026-08-10", timeframe="1m", side="short",
        entry="close.cross_below:vwap", sentiment=True,
        sentiment_sector_benchmark="SOXX", sentiment_market_benchmark="QQQ",
    )
    assert req.sentiment_data_profile == "clean"
    assert req.sentiment_sources == ("price",)

    try:
        BacktestRequest.from_values(
            symbol="NVDA", start="2026-08-01", end="2026-08-10", timeframe="1m", side="short",
            entry="close.cross_below:vwap", sentiment=True,
            sentiment_sector_benchmark="SOXX", sentiment_market_benchmark="QQQ",
            sentiment_sources="price,news",
        )
    except ValueError as exc:
        assert "unavailable" in str(exc).lower() or "not available" in str(exc).lower()
    else:
        raise AssertionError("expected unavailable sentiment source to fail explicitly")


def test_v032_sentiment_response_reports_clean_provenance(monkeypatch, tmp_path):
    import asyncio
    import pandas as pd
    from bktstr.providers import MassiveProvider
    from bktstr.service import execute_backtest

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path))

    def daily_frame(start, end, base, slope):
        dates = pd.date_range(start=start, end=end, freq="B", tz="America/New_York")
        closes = [base + i * slope for i in range(len(dates))]
        return pd.DataFrame({
            "open": closes,
            "high": [v + 1 for v in closes],
            "low": [v - 1 for v in closes],
            "close": closes,
            "volume": [1000.0] * len(dates),
        }, index=dates)

    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        if timeframe == "1d":
            slopes = {"NVDA": -0.2, "SOXX": 0.1, "QQQ": 0.05}
            bases = {"NVDA": 300.0, "SOXX": 200.0, "QQQ": 500.0}
            return daily_frame(start, end, bases[symbol], slopes[symbol])
        idx = pd.DatetimeIndex(["2026-08-17 13:00", "2026-08-17 13:01", "2026-08-17 13:02"], tz="America/New_York")
        return pd.DataFrame({
            "open": [100.0, 99.0, 98.0], "high": [100.0, 99.0, 98.0],
            "low": [99.0, 98.0, 97.0], "close": [99.5, 98.5, 97.5],
            "volume": [1000.0, 1000.0, 1000.0],
        }, index=idx)

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fake_fetch)
    req = BacktestRequest.from_values(
        symbol="NVDA", start="2026-08-17", end="2026-08-17", timeframe="1m", side="short",
        entry="close.lt:1000", sentiment=True,
        sentiment_sector_benchmark="SOXX", sentiment_market_benchmark="QQQ",
        sentiment_data_profile="clean", sentiment_sources="price",
        stop_pct=10, target_pct=10, max_hold_minutes=1, slippage_bps=0,
    )
    result = asyncio.run(execute_backtest(req))
    provenance = result["data"]["sentiment"]["provenance"]
    assert provenance["profile"] == "clean"
    assert provenance["non_clean_data_used"] is False
    assert provenance["all_point_in_time_safe"] is True
    assert provenance["sources"][0]["id"] == "price"
    assert provenance["sources"][0]["tier"] == "A"


def test_v033_sentiment_optional_warmup_http_failure_degrades_instead_of_failing(monkeypatch, tmp_path):
    import asyncio
    from datetime import timedelta
    import httpx
    import pandas as pd

    from bktstr.providers import MassiveProvider
    from bktstr.service import execute_backtest

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path))
    required_start = pd.Timestamp("2026-01-02").date()
    required_end = pd.Timestamp("2026-04-30").date()
    daily_calls = []

    def daily_frame(start, end, base):
        dates = pd.date_range(start=start, end=end, freq="B", tz="America/New_York")
        closes = [base + i * 0.2 for i in range(len(dates))]
        return pd.DataFrame({
            "open": closes,
            "high": [v + 1 for v in closes],
            "low": [v - 1 for v in closes],
            "close": closes,
            "volume": [1000.0] * len(dates),
        }, index=dates)

    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        if timeframe == "1d":
            daily_calls.append((symbol, start, end))
            if start < required_start:
                request = httpx.Request("GET", "https://example.invalid/history")
                response = httpx.Response(502, request=request)
                raise httpx.HTTPStatusError("history unavailable", request=request, response=response)
            base = {"NVDA": 100.0, "SOXX": 200.0, "QQQ": 300.0}[symbol]
            return daily_frame(start, end, base)
        idx = pd.DatetimeIndex(
            ["2026-04-30 13:00", "2026-04-30 13:01", "2026-04-30 13:02"],
            tz="America/New_York",
        )
        return pd.DataFrame({
            "open": [100.0, 99.0, 98.0],
            "high": [100.0, 99.0, 98.0],
            "low": [99.0, 98.0, 97.0],
            "close": [99.5, 98.5, 97.5],
            "volume": [1000.0, 1000.0, 1000.0],
        }, index=idx)

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fake_fetch)
    req = BacktestRequest.from_values(
        symbol="NVDA",
        start=required_start.isoformat(),
        end=required_end.isoformat(),
        timeframe="1m",
        side="short",
        entry="close.lt:1000",
        sentiment=True,
        sentiment_sector_benchmark="SOXX",
        sentiment_market_benchmark="QQQ",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=1,
        slippage_bps=0,
    )

    result = asyncio.run(execute_backtest(req))
    sentiment = result["data"]["sentiment"]
    assert sentiment["warmup_degraded"] is True
    assert sentiment["requested_warmup_start"] == (required_start - timedelta(days=460)).isoformat()
    assert sentiment["coverage_start"] == required_start.isoformat()
    assert sentiment["coverage_end"] == required_end.isoformat()
    assert sentiment["coverage"]["subject"]["fallback_used"] is True
    assert sentiment["coverage"]["sector"]["fallback_used"] is True
    assert sentiment["coverage"]["market"]["fallback_used"] is True
    assert any(start == required_start for _, start, _ in daily_calls)


def test_v033_sentiment_required_period_http_failure_remains_fatal(monkeypatch, tmp_path):
    import asyncio
    import httpx
    import pandas as pd

    from bktstr.providers import MassiveProvider
    from bktstr.service import execute_backtest

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path))

    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        if timeframe == "1d":
            request = httpx.Request("GET", "https://example.invalid/required")
            response = httpx.Response(502, request=request)
            raise httpx.HTTPStatusError("required unavailable", request=request, response=response)
        idx = pd.DatetimeIndex(
            ["2026-04-30 13:00", "2026-04-30 13:01"], tz="America/New_York"
        )
        return pd.DataFrame({
            "open": [100.0, 99.0], "high": [100.0, 99.0], "low": [99.0, 98.0],
            "close": [99.5, 98.5], "volume": [1000.0, 1000.0],
        }, index=idx)

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fake_fetch)
    req = BacktestRequest.from_values(
        symbol="NVDA", start="2026-04-30", end="2026-04-30", timeframe="1m", side="short",
        entry="close.lt:1000", sentiment=True,
        sentiment_sector_benchmark="SOXX", sentiment_market_benchmark="QQQ",
    )
    try:
        asyncio.run(execute_backtest(req))
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("required-period daily failure must remain fatal")


def test_v033_request_allows_sentiment_fragility_regime_when_sentiment_enabled():
    req = BacktestRequest.from_values(
        symbol="NVDA", start="2026-08-01", end="2026-08-10", timeframe="1m", side="short",
        entry="close.cross_below:vwap", regime="sentiment_fragility.gte:0.35",
        sentiment=True, sentiment_sector_benchmark="SOXX", sentiment_market_benchmark="QQQ",
    )
    assert req.regime == "sentiment_fragility.gte:0.35"

    try:
        BacktestRequest.from_values(
            symbol="NVDA", start="2026-08-01", end="2026-08-10", timeframe="1m", side="short",
            entry="close.cross_below:vwap", regime="sentiment_fragility.gte:0.35",
        )
    except ValueError as exc:
        assert "sentiment=true" in str(exc)
    else:
        raise AssertionError("sentiment regime fields must require sentiment=true")


def test_v033_sentiment_fallback_preserves_older_cached_daily_history(monkeypatch, tmp_path):
    import asyncio
    import httpx
    import pandas as pd

    from bktstr.cache import BarCache
    from bktstr.providers import MassiveProvider
    from bktstr.service import execute_backtest

    monkeypatch.setenv("MASSIVE_API_KEY", "test-key")
    monkeypatch.setenv("BKTSTR_CACHE_DIR", str(tmp_path))
    required_start = pd.Timestamp("2026-01-02").date()
    required_end = pd.Timestamp("2026-04-30").date()
    cached_day = pd.Timestamp("2025-12-01").date()

    cache = BarCache()
    for symbol, base in [("NVDA", 100.0), ("SOXX", 200.0), ("QQQ", 300.0)]:
        frame = pd.DataFrame({
            "open": [base], "high": [base + 1], "low": [base - 1],
            "close": [base], "volume": [1000.0],
        }, index=pd.DatetimeIndex([pd.Timestamp(cached_day, tz="America/New_York")]))
        cache.write_day("massive", symbol, "1d", cached_day, frame)

    def daily_frame(start, end, base):
        dates = pd.date_range(start=start, end=end, freq="B", tz="America/New_York")
        closes = [base + i * 0.2 for i in range(len(dates))]
        return pd.DataFrame({
            "open": closes, "high": [v + 1 for v in closes], "low": [v - 1 for v in closes],
            "close": closes, "volume": [1000.0] * len(dates),
        }, index=dates)

    async def fake_fetch(self, symbol, start, end, timeframe="1m"):
        if timeframe == "1d":
            if start < required_start:
                request = httpx.Request("GET", "https://example.invalid/history")
                response = httpx.Response(502, request=request)
                raise httpx.HTTPStatusError("history unavailable", request=request, response=response)
            return daily_frame(start, end, {"NVDA": 100.0, "SOXX": 200.0, "QQQ": 300.0}[symbol])
        idx = pd.DatetimeIndex(["2026-04-30 13:00", "2026-04-30 13:01"], tz="America/New_York")
        return pd.DataFrame({
            "open": [100.0, 99.0], "high": [100.0, 99.0], "low": [99.0, 98.0],
            "close": [99.5, 98.5], "volume": [1000.0, 1000.0],
        }, index=idx)

    monkeypatch.setattr(MassiveProvider, "fetch_bars", fake_fetch)
    req = BacktestRequest.from_values(
        symbol="NVDA", start=required_start.isoformat(), end=required_end.isoformat(),
        timeframe="1m", side="short", entry="close.lt:1000", sentiment=True,
        sentiment_sector_benchmark="SOXX", sentiment_market_benchmark="QQQ",
    )
    result = asyncio.run(execute_backtest(req))
    assert result["data"]["sentiment"]["coverage_start"] == cached_day.isoformat()
    assert result["data"]["sentiment"]["subject_daily_bars"] > 1
