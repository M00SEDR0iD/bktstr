import asyncio
from datetime import date

import pandas as pd

from bktstr.cache import BarCache, CachedProvider


def sample_bars(day: str) -> pd.DataFrame:
    idx = pd.DatetimeIndex([
        f"{day} 09:30:00",
        f"{day} 09:31:00",
    ], tz="America/New_York")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1000.0, 1200.0],
        },
        index=idx,
    )


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def fetch_bars(self, symbol: str, start: date, end: date, timeframe: str = "1m") -> pd.DataFrame:
        self.calls.append((symbol, start, end, timeframe))
        frames = []
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:
                frames.append(sample_bars(cursor.isoformat()))
            cursor += pd.Timedelta(days=1).to_pytimedelta()
        if not frames:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        return pd.concat(frames).sort_index()


def test_bar_cache_round_trips_timezone_aware_bars(tmp_path):
    cache = BarCache(tmp_path)
    day = date(2026, 8, 17)
    bars = sample_bars(day.isoformat())

    cache.write_day("massive", "NVDA", "1m", day, bars)
    restored = cache.read_day("massive", "NVDA", "1m", day)

    assert restored is not None
    assert list(restored.columns) == ["open", "high", "low", "close", "volume"]
    assert restored.index.tz is not None
    assert restored.index[0].tz_convert("America/New_York").hour == 9
    assert restored.equals(bars)


def test_bar_cache_records_empty_days_as_hits(tmp_path):
    cache = BarCache(tmp_path)
    saturday = date(2026, 8, 22)
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    cache.write_day("massive", "NVDA", "1m", saturday, empty)

    restored = cache.read_day("massive", "NVDA", "1m", saturday)
    assert restored is not None
    assert restored.empty


def test_cached_provider_fetches_missing_days_once_and_reuses_them(tmp_path):
    upstream = FakeProvider()
    cached = CachedProvider(upstream, BarCache(tmp_path), provider_name="massive")
    start = date(2026, 8, 17)
    end = date(2026, 8, 18)

    first = asyncio.run(cached.fetch_bars("NVDA", start, end, "1m"))
    first_stats = cached.last_stats
    second = asyncio.run(cached.fetch_bars("NVDA", start, end, "1m"))
    second_stats = cached.last_stats

    assert len(upstream.calls) == 1
    assert len(first) == 4
    assert second.equals(first)
    assert first_stats == {"hit_days": 0, "miss_days": 2, "fetched_ranges": 1}
    assert second_stats == {"hit_days": 2, "miss_days": 0, "fetched_ranges": 0}


def test_cached_provider_only_fetches_uncached_gap(tmp_path):
    cache = BarCache(tmp_path)
    cache.write_day("massive", "NVDA", "1m", date(2026, 8, 17), sample_bars("2026-08-17"))
    upstream = FakeProvider()
    cached = CachedProvider(upstream, cache, provider_name="massive")

    result = asyncio.run(cached.fetch_bars("NVDA", date(2026, 8, 17), date(2026, 8, 19), "1m"))

    assert upstream.calls == [("NVDA", date(2026, 8, 18), date(2026, 8, 19), "1m")]
    assert len(result) == 6
    assert cached.last_stats == {"hit_days": 1, "miss_days": 2, "fetched_ranges": 1}


def test_cached_provider_does_not_reuse_current_day_snapshot(tmp_path):
    upstream = FakeProvider()
    cached = CachedProvider(
        upstream,
        BarCache(tmp_path),
        provider_name="massive",
        today_fn=lambda: date(2026, 8, 17),
    )

    asyncio.run(cached.fetch_bars("NVDA", date(2026, 8, 17), date(2026, 8, 17), "1m"))
    asyncio.run(cached.fetch_bars("NVDA", date(2026, 8, 17), date(2026, 8, 17), "1m"))

    assert len(upstream.calls) == 2
