from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


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


def normalize_symbol(value: str, *, label: str = "symbol") -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip().upper()
    if not _SYMBOL.fullmatch(normalized):
        raise ValueError(f"invalid {label}")
    return normalized


def _normalize_date(value: date | str, *, label: str) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be an ISO date") from exc
    raise TypeError(f"{label} must be a date")


def normalize_market_request(
    *,
    symbol: str,
    start: date | str,
    end: date | str,
    timeframe: str,
    source: str = "auto",
) -> MarketInput:
    """Normalize the public market request without selecting a second data path."""

    normalized_start = _normalize_date(start, label="start")
    normalized_end = _normalize_date(end, label="end")
    if normalized_end < normalized_start:
        raise ValueError("end must be on or after start")
    if (normalized_end - normalized_start).days > 730:
        raise ValueError("date range cannot exceed 730 days")
    if timeframe not in _ALLOWED_TIMEFRAMES:
        raise ValueError(f"timeframe must be one of {sorted(_ALLOWED_TIMEFRAMES)}")
    if not isinstance(source, str):
        raise TypeError("source must be a string")
    normalized_source = source.strip().lower()
    if normalized_source not in _AVAILABLE_SOURCES:
        raise ValueError(
            f"source must be one of {sorted(_AVAILABLE_SOURCES)}; provider selection remains automatic"
        )
    return MarketInput(
        symbol=normalize_symbol(symbol),
        start=normalized_start,
        end=normalized_end,
        timeframe=timeframe,
        source=normalized_source,
    )


__all__ = ["MarketInput", "normalize_market_request", "normalize_symbol"]
