from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

import httpx
import pandas as pd


MASSIVE_BASE_URL = "https://api.massive.com"
_TIMEFRAME = re.compile(r"^(?P<n>[1-9][0-9]*)(?P<unit>[mhd])$")


def iter_date_chunks(start: date, end: date, days: int = 30):
    if end < start:
        raise ValueError("end must be on or after start")
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=days - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def _massive_resolution(timeframe: str) -> tuple[int, str]:
    match = _TIMEFRAME.match(timeframe)
    if not match:
        raise ValueError("timeframe must look like 1m, 5m, 1h, or 1d")
    multiplier = int(match.group("n"))
    unit = {"m": "minute", "h": "hour", "d": "day"}[match.group("unit")]
    return multiplier, unit


def massive_aggregate_url(symbol: str, start: date, end: date, timeframe: str) -> str:
    multiplier, timespan = _massive_resolution(timeframe)
    return (
        f"{MASSIVE_BASE_URL}/v2/aggs/ticker/{symbol.upper()}/range/"
        f"{multiplier}/{timespan}/{start.isoformat()}/{end.isoformat()}"
    )


class MassiveProvider:
    def __init__(self, api_key: str, timeout_seconds: float = 30.0):
        if not api_key:
            raise ValueError("MASSIVE_API_KEY is not configured")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def fetch_bars(self, symbol: str, start: date, end: date, timeframe: str = "1m") -> pd.DataFrame:
        records: list[dict] = []
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            for chunk_start, chunk_end in iter_date_chunks(start, end, days=30):
                url: str | None = massive_aggregate_url(symbol, chunk_start, chunk_end, timeframe)
                first = True
                pages = 0
                while url:
                    pages += 1
                    if pages > 10:
                        raise RuntimeError("Massive pagination exceeded safety limit")
                    params = {
                        "adjusted": "true",
                        "sort": "asc",
                        "limit": 50000,
                        "apiKey": self.api_key,
                    } if first else {"apiKey": self.api_key}
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("status") not in {"OK", "DELAYED", None}:
                        raise RuntimeError(f"Massive returned status {payload.get('status')}")
                    records.extend(payload.get("results") or [])
                    url = payload.get("next_url")
                    first = False

        if not records:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        frame = pd.DataFrame.from_records(records)
        required = {"t", "o", "h", "l", "c", "v"}
        if not required.issubset(frame.columns):
            raise RuntimeError("Massive response did not contain expected OHLCV fields")
        index = pd.to_datetime(frame["t"], unit="ms", utc=True).dt.tz_convert("America/New_York")
        result = pd.DataFrame(
            {
                "open": frame["o"].astype(float).values,
                "high": frame["h"].astype(float).values,
                "low": frame["l"].astype(float).values,
                "close": frame["c"].astype(float).values,
                "volume": frame["v"].astype(float).values,
            },
            index=pd.DatetimeIndex(index),
        )
        return result[~result.index.duplicated(keep="last")].sort_index()


def can_use_yahoo_intraday(start: date, end: date, timeframe: str, *, today: date | None = None) -> bool:
    today = today or datetime.now(timezone.utc).date()
    return timeframe in {"1m", "5m", "15m"} and end >= today - timedelta(days=30) and start >= today - timedelta(days=30)


def parse_yahoo_chart_payload(payload: dict) -> pd.DataFrame:
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise RuntimeError(str(chart["error"]))
    results = chart.get("result") or []
    if not results:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote_sets = ((result.get("indicators") or {}).get("quote") or [])
    if not timestamps or not quote_sets:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    q = quote_sets[0]
    frame = pd.DataFrame({
        "open": q.get("open", []),
        "high": q.get("high", []),
        "low": q.get("low", []),
        "close": q.get("close", []),
        "volume": q.get("volume", []),
    }, index=pd.to_datetime(timestamps, unit="s", utc=True).tz_convert("America/New_York"))
    return frame.dropna(subset=["open", "high", "low", "close"]).astype({"open": float, "high": float, "low": float, "close": float, "volume": float})


class YahooProvider:
    BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

    async def fetch_bars(self, symbol: str, start: date, end: date, timeframe: str = "1m") -> pd.DataFrame:
        if not can_use_yahoo_intraday(start, end, timeframe):
            raise RuntimeError("Yahoo fallback only supports recent intraday data; configure MASSIVE_API_KEY for older history")
        records: list[pd.DataFrame] = []
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
            for chunk_start, chunk_end in iter_date_chunks(start, end, days=7):
                period1 = int(datetime.combine(chunk_start, datetime.min.time(), tzinfo=timezone.utc).timestamp())
                period2 = int(datetime.combine(chunk_end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
                r = await client.get(f"{self.BASE}/{symbol.upper()}", params={"period1": period1, "period2": period2, "interval": timeframe, "includePrePost": "true", "events": "div,splits"})
                r.raise_for_status()
                records.append(parse_yahoo_chart_payload(r.json()))
        if not records:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        frame = pd.concat(records).sort_index()
        return frame[~frame.index.duplicated(keep="last")]
