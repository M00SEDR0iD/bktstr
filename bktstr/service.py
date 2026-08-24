from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import os
import re

import httpx
import pandas as pd

from bktstr_cache.derived import DerivedFrameCache

from .cache import BarCache, CachedProvider
from .engine import BacktestConfig, prepare_bars_for_backtest, run_backtest_on_bars
from .providers import MassiveProvider, YahooProvider, can_use_yahoo_intraday
from .regime import (
    attach_regime_to_intraday,
    build_daily_regime,
    regime_uses_market_fields,
    validate_regime_rules,
)
from .sentiment import attach_sentiment_to_intraday, build_daily_sentiment
from .provenance import resolve_sentiment_sources, sentiment_provenance
from .rules import parse_rules


_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
_ALLOWED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "1d"}

INTRADAY_FEATURE_FORMULA_VERSION = "intraday-v1"
REGIME_FORMULA_VERSION = "regime-v1"
SENTIMENT_FORMULA_VERSION = "sentiment-v0.3.3"


def _derived_cache_enabled() -> bool:
    value = os.getenv("BKTSTR_DERIVED_CACHE_ENABLED", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _cache_status(status) -> dict:
    return {
        "hit": bool(status.hit),
        "elapsed_seconds": round(float(status.elapsed_seconds), 6),
        "recovered_corruption": bool(status.recovered_corruption),
    }


def _derived_frame(cache, enabled: bool, namespace: str, dimensions: dict, inputs: dict, compute):
    if not enabled:
        return compute(), {"hit": False, "elapsed_seconds": 0.0, "recovered_corruption": False}
    result = cache.get_or_compute(namespace, dimensions, inputs, compute)
    return result.frame, _cache_status(result.status)


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


def _coverage_bounds(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    if frame.empty:
        return None, None
    index = frame.index
    if index.tz is None:
        local = index.tz_localize("UTC").tz_convert("America/New_York")
    else:
        local = index.tz_convert("America/New_York")
    return local[0].date().isoformat(), local[-1].date().isoformat()


async def _fetch_sentiment_daily(
    provider: CachedProvider,
    symbol: str,
    requested_start: date,
    required_start: date,
    end: date,
) -> tuple[pd.DataFrame, dict]:
    fallback_used = False
    try:
        frame = await provider.fetch_bars(symbol, requested_start, end, "1d")
        cache_stats = dict(provider.last_stats)
    except httpx.HTTPStatusError:
        if requested_start >= required_start:
            raise
        fallback_used = True
        # Requested-period data is mandatory. If this fails, propagate the error.
        await provider.fetch_bars(symbol, required_start, end, "1d")
        cache_stats = dict(provider.last_stats)
        # Preserve any older successful cache history rather than discarding it.
        frame, cached_stats = provider.read_cached_bars(symbol, requested_start, end, "1d")
        cache_stats = {**cache_stats, **cached_stats}
    coverage_start, coverage_end = _coverage_bounds(frame)
    return frame, {
        "requested_start": requested_start.isoformat(),
        "required_start": required_start.isoformat(),
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "fallback_used": fallback_used,
        "daily_bars": int(len(frame)),
        "cache": cache_stats,
    }


def provider_name_for_request(request: BacktestRequest, *, today: date | None = None) -> str:
    if os.getenv("MASSIVE_API_KEY", ""):
        return "massive"
    if request.regime or request.sentiment:
        raise RuntimeError("MASSIVE_API_KEY is required for regime or sentiment backtests")
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

    derived_enabled = _derived_cache_enabled()
    derived_cache = DerivedFrameCache()
    derived_stats: dict = {"enabled": derived_enabled}

    raw_bars = await provider.fetch_bars(request.symbol, request.start, request.end, request.timeframe)
    intraday_cache = dict(provider.last_stats)
    bars, derived_stats["intraday"] = _derived_frame(
        derived_cache,
        derived_enabled,
        "intraday_features",
        {
            "symbol": request.symbol,
            "timeframe": request.timeframe,
            "regular_hours_only": request.regular_hours_only,
            "formula_version": INTRADAY_FEATURE_FORMULA_VERSION,
        },
        {"raw": raw_bars},
        lambda: prepare_bars_for_backtest(raw_bars, regular_hours_only=request.regular_hours_only),
    )
    regime_data = None

    if request.regime and regime_uses_market_fields(request.regime):
        warmup_start = request.start - timedelta(days=120)
        subject_daily = await provider.fetch_bars(request.symbol, warmup_start, request.end, "1d")
        subject_cache = dict(provider.last_stats)
        benchmark_daily = None
        benchmark_cache = None
        if request.benchmark:
            benchmark_daily = await provider.fetch_bars(request.benchmark, warmup_start, request.end, "1d")
            benchmark_cache = dict(provider.last_stats)

        regime_inputs = {"subject": subject_daily}
        if benchmark_daily is not None:
            regime_inputs["benchmark"] = benchmark_daily
        daily_regime, derived_stats["regime"] = _derived_frame(
            derived_cache,
            derived_enabled,
            "daily_regime",
            {
                "subject": request.symbol,
                "benchmark": request.benchmark,
                "formula_version": REGIME_FORMULA_VERSION,
            },
            regime_inputs,
            lambda: build_daily_regime(subject_daily, benchmark_daily),
        )
        bars = attach_regime_to_intraday(bars, daily_regime)
        regime_data = {
            "subject": request.symbol,
            "subject_daily_bars": int(len(subject_daily)),
            "subject_cache": subject_cache,
            "benchmark": request.benchmark,
            "benchmark_daily_bars": int(len(benchmark_daily)) if benchmark_daily is not None else 0,
            "benchmark_cache": benchmark_cache,
            "warmup_start": warmup_start.isoformat(),
        }

    sentiment_data = None
    if request.sentiment:
        sentiment_warmup_start = request.start - timedelta(days=460)
        sentiment_subject_daily, subject_coverage = await _fetch_sentiment_daily(
            provider, request.symbol, sentiment_warmup_start, request.start, request.end
        )
        sector_daily, sector_coverage = await _fetch_sentiment_daily(
            provider, request.sentiment_sector_benchmark, sentiment_warmup_start, request.start, request.end
        )
        market_daily, market_coverage = await _fetch_sentiment_daily(
            provider, request.sentiment_market_benchmark, sentiment_warmup_start, request.start, request.end
        )
        daily_sentiment, derived_stats["sentiment"] = _derived_frame(
            derived_cache,
            derived_enabled,
            "daily_sentiment",
            {
                "subject": request.symbol,
                "sector_benchmark": request.sentiment_sector_benchmark,
                "market_benchmark": request.sentiment_market_benchmark,
                "data_profile": request.sentiment_data_profile,
                "sources": list(request.sentiment_sources),
                "formula_version": SENTIMENT_FORMULA_VERSION,
            },
            {
                "subject": sentiment_subject_daily,
                "sector": sector_daily,
                "market": market_daily,
            },
            lambda: build_daily_sentiment(sentiment_subject_daily, sector_daily, market_daily),
        )
        bars = attach_sentiment_to_intraday(bars, daily_sentiment)
        coverage_items = (subject_coverage, sector_coverage, market_coverage)
        starts = [x["coverage_start"] for x in coverage_items]
        ends = [x["coverage_end"] for x in coverage_items]
        common_coverage_start = max(starts) if all(starts) else None
        common_coverage_end = min(ends) if all(ends) else None
        sentiment_data = {
            "subject": request.symbol,
            "sector_benchmark": request.sentiment_sector_benchmark,
            "market_benchmark": request.sentiment_market_benchmark,
            "warmup_start": sentiment_warmup_start.isoformat(),
            "requested_warmup_start": sentiment_warmup_start.isoformat(),
            "coverage_start": common_coverage_start,
            "coverage_end": common_coverage_end,
            "warmup_degraded": any(x["fallback_used"] for x in coverage_items) or common_coverage_start is None,
            "coverage": {
                "subject": subject_coverage,
                "sector": sector_coverage,
                "market": market_coverage,
            },
            "subject_daily_bars": int(len(sentiment_subject_daily)),
            "sector_daily_bars": int(len(sector_daily)),
            "market_daily_bars": int(len(market_daily)),
            "subject_cache": subject_coverage["cache"],
            "sector_cache": sector_coverage["cache"],
            "market_cache": market_coverage["cache"],
            "multipliers_are_informational": True,
            "provenance": sentiment_provenance(request.sentiment_data_profile, request.sentiment_sources),
        }

    result = run_backtest_on_bars(
        bars,
        BacktestConfig(
            side=request.side,
            entry_rules=request.entry,
            regime_rules=request.regime,
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
            features_precomputed=True,
        ),
    )
    data = {
        "bars": int(len(raw_bars)),
        "provider": provider_name,
        "cache": intraday_cache,
        "derived_cache": derived_stats,
    }
    if regime_data is not None:
        data["regime"] = regime_data
    if sentiment_data is not None:
        data["sentiment"] = sentiment_data

    return {
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
        "data": data,
        **result,
    }
