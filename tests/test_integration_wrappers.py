from __future__ import annotations

from pathlib import Path

import pandas as pd

from bktstr_cache import DerivedFrameCache
from integration.example_wrappers import (
    cached_daily_context,
    cached_daily_features,
    cached_intraday_features,
)


def frame(mult: float = 1.0) -> pd.DataFrame:
    idx = pd.date_range("2026-08-01", periods=5, freq="D", tz="UTC")
    return pd.DataFrame({"close": [100, 101, 99, 98, 97], "volume": [1, 2, 3, 4, 5]}, index=idx) * mult


def test_intraday_wrapper_reuses_existing_formula_callback(tmp_path: Path):
    cache = DerivedFrameCache(tmp_path)
    raw = frame()
    calls = 0

    def existing_indicators(df: pd.DataFrame) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return df.assign(vwap=df["close"], rsi14=45.0, volume_ratio20=1.2)

    a = cached_intraday_features(cache, raw, "NVDA", "1m", existing_indicators)
    b = cached_intraday_features(cache, raw.copy(), "NVDA", "1m", existing_indicators)

    assert calls == 1
    assert a.status.hit is False
    assert b.status.hit is True


def test_context_wrapper_keys_subject_sector_market_and_profile(tmp_path: Path):
    cache = DerivedFrameCache(tmp_path)
    subject = frame()
    sector = frame(1.01)
    market = frame(0.99)
    calls = 0

    def existing_context(subject_df, sector_df, market_df):
        nonlocal calls
        calls += 1
        return subject_df.assign(sentiment_direction=0.1, relative_return20=-0.03)

    first = cached_daily_context(
        cache,
        subject,
        sector,
        market,
        subject_symbol="NVDA",
        sector_symbol="SOXX",
        market_symbol="QQQ",
        compute_fn=existing_context,
    )
    changed_benchmark = cached_daily_context(
        cache,
        subject,
        sector,
        market,
        subject_symbol="NVDA",
        sector_symbol="SMH",
        market_symbol="QQQ",
        compute_fn=existing_context,
    )

    assert calls == 2
    assert first.status.key != changed_benchmark.status.key


def test_daily_feature_formula_version_can_be_bumped_without_deleting_cache(tmp_path: Path):
    cache = DerivedFrameCache(tmp_path)
    raw = frame()
    calls = 0

    def existing_daily(df):
        nonlocal calls
        calls += 1
        return df.assign(ema50=df["close"])

    v1 = cached_daily_features(cache, raw, "NVDA", existing_daily, formula_version="daily-v1")
    v2 = cached_daily_features(cache, raw, "NVDA", existing_daily, formula_version="daily-v2")

    assert calls == 2
    assert v1.status.key != v2.status.key
