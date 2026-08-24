from __future__ import annotations

import tempfile
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd

from bktstr_cache import DerivedFrameCache


def main() -> None:
    rows = 120_000
    idx = pd.date_range("2026-01-02 14:30", periods=rows, freq="min", tz="UTC")
    close = 100 + np.cumsum(np.sin(np.arange(rows) / 5000) * 0.001)
    raw = pd.DataFrame({"close": close, "volume": np.arange(rows) % 4000 + 100}, index=idx)
    calls = 0

    def simulated_existing_feature_builder() -> pd.DataFrame:
        nonlocal calls
        calls += 1
        # Deliberately representative deterministic pandas work; no BKTSTR formula is reimplemented.
        out = raw.copy()
        out["rolling_mean_50"] = out["close"].rolling(50).mean()
        out["rolling_std_60"] = out["close"].rolling(60).std()
        time.sleep(0.15)  # stand-in for additional current indicator/context computation
        return out

    with tempfile.TemporaryDirectory() as tmp:
        cache = DerivedFrameCache(Path(tmp))
        t0 = time.perf_counter()
        cold = cache.get_or_compute(
            "benchmark_features",
            {"symbol": "NVDA", "timeframe": "1m", "formula_version": "benchmark-v1"},
            {"raw": raw},
            simulated_existing_feature_builder,
        )
        cold_wall = time.perf_counter() - t0

        t1 = time.perf_counter()
        warm = cache.get_or_compute(
            "benchmark_features",
            {"symbol": "NVDA", "timeframe": "1m", "formula_version": "benchmark-v1"},
            {"raw": raw},
            simulated_existing_feature_builder,
        )
        warm_wall = time.perf_counter() - t1

        print(f"rows={rows}")
        print(f"compute_calls={calls}")
        print(f"cold_hit={cold.status.hit} cold_seconds={cold_wall:.4f}")
        print(f"warm_hit={warm.status.hit} warm_seconds={warm_wall:.4f}")
        if calls != 1 or cold.status.hit or not warm.status.hit:
            raise SystemExit("cache behavior verification failed")


if __name__ == "__main__":
    main()
