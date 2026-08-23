from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import os
import re

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
        )


def provider_name_for_request(request: BacktestRequest, *, today: date | None = None) -> str:
    if os.getenv("MASSIVE_API_KEY", ""):
        return "massive"
    if can_use_yahoo_intraday(request.start, request.end, request.timeframe, today=today):
        return "yahoo"
    raise RuntimeError("MASSIVE_API_KEY is required for historical intraday ranges older than the Yahoo fallback window")


async def execute_backtest(request: BacktestRequest) -> dict:
    provider_name = provider_name_for_request(request)
    if provider_name == "massive":
        provider = MassiveProvider(os.environ["MASSIVE_API_KEY"])
    else:
        provider = YahooProvider()
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
        },
        "data": {"bars": int(len(bars)), "provider": provider_name},
        **result,
    }
