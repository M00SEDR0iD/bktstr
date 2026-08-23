from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import os
import re
import threading
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

import pandas as pd


_COLUMNS = ["open", "high", "low", "close", "volume"]
_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")
_CACHE_FILL_LOCK = threading.Lock()


class BarProvider(Protocol):
    async def fetch_bars(self, symbol: str, start: date, end: date, timeframe: str = "1m") -> pd.DataFrame: ...


def default_cache_root() -> Path:
    configured = os.getenv("BKTSTR_CACHE_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if configured:
        return Path(configured) / "bktstr-cache"
    return Path("/tmp/bktstr-cache")


def _component(value: str) -> str:
    if not _SAFE.match(value):
        raise ValueError(f"unsafe cache key component: {value!r}")
    return value


def _days(start: date, end: date):
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def _contiguous_ranges(days: list[date]) -> list[tuple[date, date]]:
    if not days:
        return []
    ordered = sorted(days)
    ranges: list[tuple[date, date]] = []
    start = previous = ordered[0]
    for current in ordered[1:]:
        if current == previous + timedelta(days=1):
            previous = current
            continue
        ranges.append((start, previous))
        start = previous = current
    ranges.append((start, previous))
    return ranges


class BarCache:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else default_cache_root()

    def _path(self, provider: str, symbol: str, timeframe: str, day: date) -> Path:
        return (
            self.root
            / _component(provider.lower())
            / _component(symbol.upper())
            / _component(timeframe)
            / f"{day.isoformat()}.csv.gz"
        )

    def read_day(self, provider: str, symbol: str, timeframe: str, day: date) -> pd.DataFrame | None:
        path = self._path(provider, symbol, timeframe, day)
        if not path.exists():
            return None
        frame = pd.read_csv(path, compression="gzip")
        if frame.empty:
            empty = pd.DataFrame(columns=_COLUMNS)
            empty.index = pd.DatetimeIndex([], tz="America/New_York")
            return empty
        required = {"timestamp_ms", *_COLUMNS}
        if not required.issubset(frame.columns):
            raise RuntimeError(f"cache file is malformed: {path}")
        index = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True).dt.tz_convert("America/New_York")
        result = pd.DataFrame(
            {column: frame[column].astype(float).values for column in _COLUMNS},
            index=pd.DatetimeIndex(index),
        )
        result.index.name = None
        return result.sort_index()

    def write_day(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        day: date,
        bars: pd.DataFrame,
    ) -> None:
        path = self._path(provider, symbol, timeframe, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")

        if bars.empty:
            serializable = pd.DataFrame(columns=["timestamp_ms", *_COLUMNS])
        else:
            frame = bars.copy().sort_index()
            if frame.index.tz is None:
                raise ValueError("cached bars must use a timezone-aware DatetimeIndex")
            utc_index = frame.index.tz_convert("UTC")
            serializable = pd.DataFrame({
                "timestamp_ms": (utc_index.asi8 // 1_000_000).astype("int64"),
                **{column: frame[column].astype(float).values for column in _COLUMNS},
            })
        serializable.to_csv(tmp, index=False, compression="gzip", float_format="%.17g")
        os.replace(tmp, path)


class CachedProvider:
    def __init__(
        self,
        upstream: BarProvider,
        cache: BarCache,
        *,
        provider_name: str,
        today_fn: Callable[[], date] | None = None,
    ):
        self.upstream = upstream
        self.cache = cache
        self.provider_name = provider_name
        self.today_fn = today_fn or (lambda: datetime.now(ZoneInfo("America/New_York")).date())
        self.last_stats = {"hit_days": 0, "miss_days": 0, "fetched_ranges": 0}

    def _read_available(
        self, symbol: str, start: date, end: date, timeframe: str
    ) -> tuple[dict[date, pd.DataFrame], list[date]]:
        available: dict[date, pd.DataFrame] = {}
        missing: list[date] = []
        for day in _days(start, end):
            cached = self.cache.read_day(self.provider_name, symbol, timeframe, day)
            if cached is None:
                missing.append(day)
            else:
                available[day] = cached
        return available, missing

    async def fetch_bars(self, symbol: str, start: date, end: date, timeframe: str = "1m") -> pd.DataFrame:
        if end < start:
            raise ValueError("end must be on or after start")

        today = self.today_fn()
        historical_end = min(end, today - timedelta(days=1))
        available: dict[date, pd.DataFrame] = {}
        missing: list[date] = []
        initial_hits = 0
        initial_misses = 0
        fetched_ranges = 0

        if start <= historical_end:
            available, missing = self._read_available(symbol, start, historical_end, timeframe)
            initial_hits = len(available)
            initial_misses = len(missing)

            if missing:
                _CACHE_FILL_LOCK.acquire()
                try:
                    # Another request may have filled some or all missing days while we waited.
                    available, missing = self._read_available(symbol, start, historical_end, timeframe)
                    for gap_start, gap_end in _contiguous_ranges(missing):
                        fetched_ranges += 1
                        fetched = await self.upstream.fetch_bars(symbol, gap_start, gap_end, timeframe)
                        if fetched.empty:
                            local_dates = pd.Series(dtype="object")
                        else:
                            if fetched.index.tz is None:
                                raise ValueError("provider bars must use a timezone-aware DatetimeIndex")
                            local_dates = pd.Series(fetched.index.tz_convert("America/New_York").date, index=fetched.index)
                        for day in _days(gap_start, gap_end):
                            if fetched.empty:
                                day_bars = fetched.copy()
                            else:
                                mask = local_dates.values == day
                                day_bars = fetched.loc[mask]
                            self.cache.write_day(self.provider_name, symbol, timeframe, day, day_bars)
                    available, still_missing = self._read_available(symbol, start, historical_end, timeframe)
                    if still_missing:
                        raise RuntimeError("cache fill completed with unresolved days")
                finally:
                    _CACHE_FILL_LOCK.release()

        frames = [
            available[day]
            for day in _days(start, historical_end)
            if day in available and not available[day].empty
        ] if start <= historical_end else []

        volatile_start = max(start, today)
        if volatile_start <= end:
            volatile_days = (end - volatile_start).days + 1
            initial_misses += volatile_days
            fetched_ranges += 1
            volatile = await self.upstream.fetch_bars(symbol, volatile_start, end, timeframe)
            if not volatile.empty:
                frames.append(volatile)

        if frames:
            result = pd.concat(frames).sort_index()
            result = result[~result.index.duplicated(keep="last")]
        else:
            result = pd.DataFrame(columns=_COLUMNS)
            result.index = pd.DatetimeIndex([], tz="America/New_York")

        self.last_stats = {
            "hit_days": initial_hits,
            "miss_days": initial_misses,
            "fetched_ranges": fetched_ranges,
        }
        return result
