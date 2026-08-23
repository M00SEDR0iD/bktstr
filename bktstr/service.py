from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import os
import re

from .cache import BarCache, CachedProvider
from .engine import BacktestConfig, run_backtest_on_bars
from .providers import MassiveProvider, YahooProvider, can_use_yahoo_intraday
from .rules import parse_rules


_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
_ALLOWED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "1d"}


@dataclass(frozen=True)
class BacktestRequest:
    symbol: str
    start: date
    end: date
    timeframe: str
    side: str
    entry: str
    stop_pct: float = 1.0
    target_pct: float = 3.0
    max_hold_minutes: int = 240
    position_size: float = 1000.0
    starting_capital: float = 10000.0
    slippage_bps: float = 2.0
    regular_hours_only: bool = True
    same_day_only: bool = True
    entry_start_time: str | None = None
    entry_end_time: str | None = None

    @classmethod
    def from_values(
        cls,
        *,
        symbol: str,
        start: str,
        end: str,
        timeframe: str = "1m",
        side: str = "long",
        entry: str,
        stop_pct: float = 1.0,
        target_pct: float = 3.0,
        max_hold_minutes: int = 240,
        position_size: float = 1000.0,
        starting_capital: float = 10000.0,
        slippage_bps: float = 2.0,
        regular_hours_only: bool = True,
        same_day_only: bool = True,
        entry_start_time: str | None = None,
        entry_end_time: str | None = None,
    ) -> "BacktestRequest":
        symbol = symbol.strip().upper()
        if not _SYMBOL.match(symbol):
            raise ValueError("invalid symbol")
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        if end_date < start_date:
            raise ValueError("end must be on or after start")
        if (end_date - start_date).days > 730:
            raise ValueError("date range cannot exceed 730 days")
        if timeframe not in _ALLOWED_TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {sorted(_ALLOWED_TIMEFRAMES)}")
        if side not in {"long", "short"}:
            raise ValueError("side must be long or short")
        _validate_entry_window(entry_start_time, entry_end_time)
        parse_rules(entry)
        return cls(
            symbol=symbol,
            start=start_date,
            end=end_date,
            timeframe=timeframe,
            side=side,
            entry=entry,
            stop_pct=float(stop_pct),
            target_pct=float(target_pct),
            max_hold_minutes=int(max_hold_minutes),
            position_size=float(position_size),
            starting_capital=float(starting_capital),
            slippage_bps=float(slippage_bps),
            regular_hours_only=bool(regular_hours_only),
            same_day_only=bool(same_day_only),
            entry_start_time=entry_start_time,
            entry_end_time=entry_end_time,
        )


def _validate_entry_window(start: str | None, end: str | None) -> None:
    from datetime import datetime

    def parse(value: str | None):
        if value is None:
            return None
        try:
            return datetime.strptime(value, "%H:%M").time()
        except ValueError as exc:
            raise ValueError("entry times must use 24-hour HH:MM format") from exc

    start_time = parse(start)
    end_time = parse(end)
    if start_time is not None and end_time is not None and start_time >= end_time:
        raise ValueError("entry_start_time must be before entry_end_time")


def provider_name_for_request(request: BacktestRequest, *, today: date | None = None) -> str:
    if os.getenv("MASSIVE_API_KEY", ""):
        return "massive"
    if can_use_yahoo_intraday(request.start, request.end, request.timeframe, today=today):
        return "yahoo"
    raise RuntimeError("MASSIVE_API_KEY is required for historical intraday ranges older than the Yahoo fallback window")


async def execute_backtest(request: BacktestRequest) -> dict:
    provider_name = provider_name_for_request(request)
    if provider_name == "massive":
        upstream = MassiveProvider(os.environ["MASSIVE_API_KEY"])
    else:
        upstream = YahooProvider()
    provider = CachedProvider(upstream, BarCache(), provider_name=provider_name)
    bars = await provider.fetch_bars(request.symbol, request.start, request.end, request.timeframe)
    result = run_backtest_on_bars(
        bars,
        BacktestConfig(
            side=request.side,
            entry_rules=request.entry,
            stop_pct=request.stop_pct,
            target_pct=request.target_pct,
            max_hold_minutes=request.max_hold_minutes,
            position_size=request.position_size,
            starting_capital=request.starting_capital,
            slippage_bps=request.slippage_bps,
            regular_hours_only=request.regular_hours_only,
            same_day_only=request.same_day_only,
            entry_start_time=request.entry_start_time,
            entry_end_time=request.entry_end_time,
        ),
    )
    return {
        "request": {
            "symbol": request.symbol,
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
            "timeframe": request.timeframe,
            "side": request.side,
            "entry": request.entry,
            "stop_pct": request.stop_pct,
            "target_pct": request.target_pct,
            "max_hold_minutes": request.max_hold_minutes,
            "position_size": request.position_size,
            "starting_capital": request.starting_capital,
            "slippage_bps": request.slippage_bps,
            "entry_start_time": request.entry_start_time,
            "entry_end_time": request.entry_end_time,
        },
        "data": {
            "bars": int(len(bars)),
            "provider": provider_name,
            "cache": dict(provider.last_stats),
        },
        **result,
    }
