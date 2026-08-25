from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from .validation import SemanticValidationError


_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
_ALLOWED_TIMEFRAMES = frozenset({"1m", "5m", "15m", "1h", "1d"})
_AVAILABLE_SOURCES = frozenset({"auto"})


@dataclass(frozen=True)
class MarketInput:
    symbol: str
    start: date
    end: date
    timeframe: str
    source: str = "auto"


@dataclass(frozen=True)
class MarketDataBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MarketDataInspection:
    symbol: str
    start: date
    end: date
    timeframe: str
    source: str
    bars: tuple[MarketDataBar, ...]
    next_cursor: str | None


def normalize_symbol(
    value: str, *, label: str = "symbol", field_path: str | None = None
) -> str:
    field = field_path or label
    if not isinstance(value, str):
        raise SemanticValidationError(f"{label} must be a string", (field,))
    normalized = value.strip().upper()
    if not _SYMBOL.fullmatch(normalized):
        raise SemanticValidationError(f"invalid {label}", (field,))
    return normalized


def _normalize_date(value: date | str, *, label: str, field_path: str) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise SemanticValidationError(
                f"{label} must be an ISO date", (field_path,)
            ) from exc
    raise SemanticValidationError(f"{label} must be a date", (field_path,))


def normalize_market_request(
    *,
    symbol: str,
    start: date | str,
    end: date | str,
    timeframe: str,
    source: str = "auto",
    field_prefix: str | None = "market",
) -> MarketInput:
    """Normalize the public market request without selecting a second data path."""

    def field(name: str) -> str:
        return f"{field_prefix}.{name}" if field_prefix else name

    normalized_start = _normalize_date(
        start, label="start", field_path=field("start")
    )
    normalized_end = _normalize_date(end, label="end", field_path=field("end"))
    if normalized_end < normalized_start:
        raise SemanticValidationError(
            "end must be on or after start", (field("start"), field("end"))
        )
    if (normalized_end - normalized_start).days > 730:
        raise SemanticValidationError(
            "date range cannot exceed 730 days", (field("start"), field("end"))
        )
    if timeframe not in _ALLOWED_TIMEFRAMES:
        raise SemanticValidationError(
            f"timeframe must be one of {sorted(_ALLOWED_TIMEFRAMES)}",
            (field("timeframe"),),
        )
    if not isinstance(source, str):
        raise SemanticValidationError("source must be a string", (field("source"),))
    normalized_source = source.strip().lower()
    if normalized_source not in _AVAILABLE_SOURCES:
        raise SemanticValidationError(
            f"source must be one of {sorted(_AVAILABLE_SOURCES)}; provider selection remains automatic",
            (field("source"),),
        )
    return MarketInput(
        symbol=normalize_symbol(symbol, field_path=field("symbol")),
        start=normalized_start,
        end=normalized_end,
        timeframe=timeframe,
        source=normalized_source,
    )


def _canonical_identity(market: MarketInput) -> str:
    return json.dumps(
        {
            "symbol": market.symbol,
            "start": market.start.isoformat(),
            "end": market.end.isoformat(),
            "timeframe": market.timeframe,
            "source": market.source,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _encode_cursor(identity: str, timestamp: datetime) -> str:
    payload = json.dumps(
        {"identity": identity, "timestamp": timestamp.isoformat()},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, *, identity: str) -> datetime:
    if not cursor or len(cursor) > 2048:
        raise SemanticValidationError("invalid cursor", ("cursor",))
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload: Any = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(payload, dict) or payload.get("identity") != identity:
            raise SemanticValidationError(
                "cursor does not match the requested market data", ("cursor",)
            )
        timestamp = datetime.fromisoformat(payload["timestamp"])
    except SemanticValidationError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise SemanticValidationError("invalid cursor", ("cursor",)) from exc
    if timestamp.tzinfo is None:
        raise SemanticValidationError("invalid cursor", ("cursor",))
    return timestamp


def _cached_provider_for_market(market: MarketInput):
    """Resolve the same governed raw-bar provider/cache pair used by backtests."""
    from bktstr.cache import BarCache, CachedProvider
    from bktstr.providers import MassiveProvider, YahooProvider
    from bktstr.service import BacktestRequest, provider_name_for_request

    selection = BacktestRequest.from_values(
        symbol=market.symbol,
        start=market.start.isoformat(),
        end=market.end.isoformat(),
        timeframe=market.timeframe,
        entry="close.cross_below:vwap",
    )
    provider_name = provider_name_for_request(selection)
    upstream = (
        MassiveProvider(os.environ["MASSIVE_API_KEY"])
        if provider_name == "massive"
        else YahooProvider()
    )
    return CachedProvider(upstream, BarCache(), provider_name=provider_name)


def _normalized_bar(timestamp: Any, row: Any) -> MarketDataBar:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        raise ValueError("provider bars must use a timezone-aware DatetimeIndex")
    return MarketDataBar(
        timestamp=value.to_pydatetime(),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
    )


async def inspect_market_data(
    *,
    symbol: str,
    start: date | str,
    end: date | str,
    timeframe: str,
    source: str = "auto",
    limit: int = 100,
    cursor: str | None = None,
) -> MarketDataInspection:
    """Return a safe, normalized, cache-backed inspection page of raw OHLCV bars."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise SemanticValidationError(
            "limit must be between 1 and 1000", ("limit",)
        )
    market = normalize_market_request(
        symbol=symbol,
        start=start,
        end=end,
        timeframe=timeframe,
        source=source,
        field_prefix=None,
    )
    identity = _canonical_identity(market)
    after = _decode_cursor(cursor, identity=identity) if cursor is not None else None
    provider = _cached_provider_for_market(market)
    frame = await provider.fetch_bars(
        market.symbol, market.start, market.end, market.timeframe
    )
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError("provider bars must include normalized OHLCV columns")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("provider bars must use a timezone-aware DatetimeIndex")
    ordered = frame.sort_index()
    if after is not None:
        ordered = ordered.loc[ordered.index > pd.Timestamp(after)]
    selected = ordered.iloc[:limit]
    bars = tuple(_normalized_bar(timestamp, row) for timestamp, row in selected.iterrows())
    next_cursor = (
        _encode_cursor(identity, bars[-1].timestamp)
        if len(ordered) > len(selected) and bars
        else None
    )
    return MarketDataInspection(
        symbol=market.symbol,
        start=market.start,
        end=market.end,
        timeframe=market.timeframe,
        source=provider.provider_name,
        bars=bars,
        next_cursor=next_cursor,
    )


__all__ = [
    "MarketDataBar",
    "MarketDataInspection",
    "MarketInput",
    "inspect_market_data",
    "normalize_market_request",
    "normalize_symbol",
]
