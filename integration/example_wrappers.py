from __future__ import annotations

from typing import Callable, Iterable

import pandas as pd

from bktstr_cache import CacheResult, DerivedFrameCache


def cached_intraday_features(
    cache: DerivedFrameCache,
    raw: pd.DataFrame,
    symbol: str,
    timeframe: str,
    compute_fn: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    formula_version: str = "intraday-v0.3.3",
    session_model_version: str = "regular-hours-session-v1",
) -> CacheResult:
    """Wrap the existing intraday indicator function without changing formulas."""
    return cache.get_or_compute(
        namespace="intraday_features",
        dimensions={
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "formula_version": formula_version,
            "session_model_version": session_model_version,
        },
        inputs={"raw": raw},
        compute=lambda: compute_fn(raw),
    )


def cached_daily_features(
    cache: DerivedFrameCache,
    raw_daily: pd.DataFrame,
    symbol: str,
    compute_fn: Callable[[pd.DataFrame], pd.DataFrame],
    *,
    formula_version: str = "daily-features-v0.3.3",
) -> CacheResult:
    """Wrap existing deterministic daily feature construction."""
    return cache.get_or_compute(
        namespace="daily_features",
        dimensions={
            "symbol": symbol.upper(),
            "timeframe": "1d",
            "formula_version": formula_version,
        },
        inputs={"raw_daily": raw_daily},
        compute=lambda: compute_fn(raw_daily),
    )


def cached_daily_context(
    cache: DerivedFrameCache,
    subject_daily_features: pd.DataFrame,
    sector_daily_features: pd.DataFrame,
    market_daily_features: pd.DataFrame,
    *,
    subject_symbol: str,
    sector_symbol: str,
    market_symbol: str,
    compute_fn: Callable[[pd.DataFrame, pd.DataFrame, pd.DataFrame], pd.DataFrame],
    formula_version: str = "context-sentiment-v0.3.3",
    data_profile: str = "clean",
    sources: Iterable[str] = ("price",),
    lookahead_rule: str = "strictly-prior-completed-session",
) -> CacheResult:
    """Cache subject/sector/market context while keeping thresholds live."""
    source_list = sorted(str(source) for source in sources)
    return cache.get_or_compute(
        namespace="daily_context",
        dimensions={
            "subject": subject_symbol.upper(),
            "sector": sector_symbol.upper(),
            "market": market_symbol.upper(),
            "formula_version": formula_version,
            "data_profile": data_profile,
            "sources": source_list,
            "lookahead_rule": lookahead_rule,
        },
        inputs={
            "subject_daily_features": subject_daily_features,
            "sector_daily_features": sector_daily_features,
            "market_daily_features": market_daily_features,
        },
        compute=lambda: compute_fn(subject_daily_features, sector_daily_features, market_daily_features),
    )
