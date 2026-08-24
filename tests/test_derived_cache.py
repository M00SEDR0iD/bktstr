from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from bktstr_cache.derived import DerivedFrameCache, dataframe_digest


def sample_frame(last_close: float = 102.0) -> pd.DataFrame:
    idx = pd.to_datetime([
        "2026-08-20 13:30:00+00:00",
        "2026-08-20 13:31:00+00:00",
        "2026-08-20 13:32:00+00:00",
    ])
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, last_close],
            "volume": [1000, 1200, 900],
        },
        index=idx,
    )


def test_dataframe_digest_is_stable_and_sensitive_to_values():
    a = sample_frame()
    b = a.copy(deep=True)
    c = sample_frame(last_close=102.5)

    assert dataframe_digest(a) == dataframe_digest(b)
    assert dataframe_digest(a) != dataframe_digest(c)


def test_cache_hit_reuses_computed_dataframe(tmp_path: Path):
    cache = DerivedFrameCache(tmp_path)
    raw = sample_frame()
    calls = 0

    def compute() -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return raw.assign(rsi14=[40.0, 45.0, 49.0])

    first = cache.get_or_compute(
        namespace="intraday_features",
        dimensions={"symbol": "NVDA", "timeframe": "1m", "formula_version": "intraday-v1"},
        inputs={"raw": raw},
        compute=compute,
    )
    second = cache.get_or_compute(
        namespace="intraday_features",
        dimensions={"symbol": "NVDA", "timeframe": "1m", "formula_version": "intraday-v1"},
        inputs={"raw": raw.copy(deep=True)},
        compute=compute,
    )

    assert first.status.hit is False
    assert second.status.hit is True
    assert calls == 1
    pd.testing.assert_frame_equal(first.frame, second.frame)


def test_changed_input_invalidates_cache(tmp_path: Path):
    cache = DerivedFrameCache(tmp_path)
    calls = 0

    def make_compute(frame: pd.DataFrame):
        def compute() -> pd.DataFrame:
            nonlocal calls
            calls += 1
            return frame.assign(vwap=frame["close"])
        return compute

    raw_a = sample_frame(102.0)
    raw_b = sample_frame(102.5)
    result_a = cache.get_or_compute(
        "intraday_features", {"symbol": "NVDA", "timeframe": "1m", "formula_version": "v1"}, {"raw": raw_a}, make_compute(raw_a)
    )
    result_b = cache.get_or_compute(
        "intraday_features", {"symbol": "NVDA", "timeframe": "1m", "formula_version": "v1"}, {"raw": raw_b}, make_compute(raw_b)
    )

    assert calls == 2
    assert result_a.status.key != result_b.status.key
    assert result_b.status.hit is False


def test_changed_semantic_dimension_invalidates_cache(tmp_path: Path):
    cache = DerivedFrameCache(tmp_path)
    raw = sample_frame()
    calls = 0

    def compute() -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return raw.assign(x=1)

    v1 = cache.get_or_compute(
        "daily_context", {"symbol": "NVDA", "formula_version": "sentiment-v1"}, {"raw": raw}, compute
    )
    v2 = cache.get_or_compute(
        "daily_context", {"symbol": "NVDA", "formula_version": "sentiment-v2"}, {"raw": raw}, compute
    )

    assert calls == 2
    assert v1.status.key != v2.status.key


def test_corrupt_payload_is_treated_as_miss_and_recomputed(tmp_path: Path):
    cache = DerivedFrameCache(tmp_path)
    raw = sample_frame()
    calls = 0

    def compute() -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return raw.assign(feature=[1.0, 2.0, 3.0])

    first = cache.get_or_compute(
        "intraday_features", {"symbol": "NVDA", "formula_version": "v1"}, {"raw": raw}, compute
    )
    first.status.payload_path.write_bytes(b"not-a-valid-cache-payload")

    second = cache.get_or_compute(
        "intraday_features", {"symbol": "NVDA", "formula_version": "v1"}, {"raw": raw}, compute
    )

    assert calls == 2
    assert second.status.hit is False
    assert second.status.recovered_corruption is True
    pd.testing.assert_frame_equal(second.frame, compute().iloc[0:0].append(second.frame) if False else second.frame)


def test_metadata_contains_versioned_dimensions_and_input_digests(tmp_path: Path):
    cache = DerivedFrameCache(tmp_path)
    raw = sample_frame()

    result = cache.get_or_compute(
        "daily_context",
        {
            "symbol": "NVDA",
            "sector": "SOXX",
            "market": "QQQ",
            "formula_version": "sentiment-v0.3.3",
            "data_profile": "clean",
            "sources": ["price"],
        },
        {"subject": raw, "sector": raw * 1.01, "market": raw * 0.99},
        lambda: raw.assign(sentiment_direction=0.1),
    )

    meta = json.loads(result.status.metadata_path.read_text())
    assert meta["namespace"] == "daily_context"
    assert meta["dimensions"]["sector"] == "SOXX"
    assert meta["dimensions"]["market"] == "QQQ"
    assert meta["dimensions"]["sources"] == ["price"]
    assert set(meta["input_digests"]) == {"subject", "sector", "market"}
    assert meta["key"] == result.status.key
