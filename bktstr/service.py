from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
import re

from .engine import validate_entry_window as _validate_entry_window
from .provenance import resolve_sentiment_sources
from .regime import validate_regime_rules
from .rules import parse_rules
from .services.data import normalize_market_request


_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
_ALLOWED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "1d"}

INTRADAY_FEATURE_FORMULA_VERSION = "intraday-v1"
REGIME_FORMULA_VERSION = "regime-v1"
SENTIMENT_FORMULA_VERSION = "sentiment-v0.3.3"


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
    regime: str | None = None
    benchmark: str | None = None
    sentiment: bool = False
    sentiment_sector_benchmark: str | None = None
    sentiment_market_benchmark: str | None = None
    sentiment_data_profile: str = "clean"
    sentiment_sources: tuple[str, ...] = ("price",)

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
        regime: str | None = None,
        benchmark: str | None = None,
        sentiment: bool = False,
        sentiment_sector_benchmark: str | None = None,
        sentiment_market_benchmark: str | None = None,
        sentiment_data_profile: str = "clean",
        sentiment_sources: str | tuple[str, ...] | None = None,
    ) -> "BacktestRequest":
        market = normalize_market_request(
            symbol=symbol,
            start=start,
            end=end,
            timeframe=timeframe,
            source="auto",
        )
        symbol = market.symbol
        start_date = market.start
        end_date = market.end
        timeframe = market.timeframe
        if side not in {"long", "short"}:
            raise ValueError("side must be long or short")
        _validate_entry_window(entry_start_time, entry_end_time)
        parse_rules(entry)
        normalized_regime = regime.strip() if regime and regime.strip() else None
        normalized_benchmark = benchmark.strip().upper() if benchmark and benchmark.strip() else None
        if normalized_benchmark and not _SYMBOL.match(normalized_benchmark):
            raise ValueError("invalid benchmark symbol")
        if normalized_regime:
            validate_regime_rules(
                normalized_regime, normalized_benchmark, sentiment_enabled=bool(sentiment)
            )
        normalized_sector_benchmark = (
            sentiment_sector_benchmark.strip().upper()
            if sentiment_sector_benchmark and sentiment_sector_benchmark.strip()
            else None
        )
        normalized_market_benchmark = (
            sentiment_market_benchmark.strip().upper()
            if sentiment_market_benchmark and sentiment_market_benchmark.strip()
            else None
        )
        for value in (normalized_sector_benchmark, normalized_market_benchmark):
            if value and not _SYMBOL.match(value):
                raise ValueError("invalid sentiment benchmark symbol")
        if sentiment and (not normalized_sector_benchmark or not normalized_market_benchmark):
            raise ValueError("sentiment requires both sector and market benchmark symbols")
        normalized_data_profile, normalized_sources = resolve_sentiment_sources(
            sentiment_data_profile, sentiment_sources
        )
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
            regime=normalized_regime,
            benchmark=normalized_benchmark,
            sentiment=bool(sentiment),
            sentiment_sector_benchmark=normalized_sector_benchmark,
            sentiment_market_benchmark=normalized_market_benchmark,
            sentiment_data_profile=normalized_data_profile,
            sentiment_sources=normalized_sources,
        )


def provider_name_for_request(request: BacktestRequest, *, today: date | None = None) -> str:
    from .runtime import select_provider

    return select_provider(
        request.start, request.end, request.timeframe,
        requires_daily_context=bool(request.regime or request.sentiment), today=today,
    )


class SerializedBacktestResult(dict):
    """Frozen compatibility payload with private execution provenance for new services."""

    def __init__(self, payload: dict, execution_provenance: dict) -> None:
        super().__init__(payload)
        self.execution_provenance = MappingProxyType(dict(execution_provenance))


async def execute_backtest(request: BacktestRequest) -> dict:
    from .orchestrator import legacy_request_to_strategy_run
    from .runtime import run_strategy

    result = await run_strategy(legacy_request_to_strategy_run(request))
    return serialize_strategy_run_result(request, result)


def serialize_strategy_run_result(request: BacktestRequest, result) -> dict:
    """Render the domain result through the unchanged v0.3 compatibility payload."""

    payload = {
        "request": {
            "symbol": request.symbol,
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
            "timeframe": request.timeframe,
            "side": request.side,
            "entry": request.entry,
            "regime": request.regime,
            "benchmark": request.benchmark,
            "sentiment": request.sentiment,
            "sentiment_sector_benchmark": request.sentiment_sector_benchmark,
            "sentiment_market_benchmark": request.sentiment_market_benchmark,
            "sentiment_data_profile": request.sentiment_data_profile,
            "sentiment_sources": list(request.sentiment_sources),
            "stop_pct": request.stop_pct,
            "target_pct": request.target_pct,
            "max_hold_minutes": request.max_hold_minutes,
            "position_size": request.position_size,
            "starting_capital": request.starting_capital,
            "slippage_bps": request.slippage_bps,
            "entry_start_time": request.entry_start_time,
            "entry_end_time": request.entry_end_time,
        },
        "data": dict(result.data),
        "summary": dict(result.summary),
        "trades": [dict(item) for item in result.trades],
    }
    # This metadata is deliberately not a JSON key in the frozen v0.5 payload.
    # The typed research service consumes it in-process to retain the governed
    # input lineage needed for reproducibility.
    return SerializedBacktestResult(payload, dict(result.provenance))
