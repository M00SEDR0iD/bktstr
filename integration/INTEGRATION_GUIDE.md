# Integrating `bktstr_cache` into the live v0.3.3 repo

This package was produced without access to the current GitHub checkout. The cache library is therefore intentionally merge-safe and formula-agnostic: wire it around the existing functions instead of replacing their internals.

## Expected existing modules

Prior BKTSTR builds used `data.py`, `indicators.py`, `regime.py`, `sentiment.py`, `backtest.py`, `models.py`, and a FastAPI service/main module. Adjust paths to the current repo if they moved.

## 1. Instantiate one cache

Near service startup or backtest orchestration:

```python
from bktstr_cache import DerivedFrameCache

derived_cache = DerivedFrameCache()
```

Default location order:

1. `BKTSTR_DERIVED_CACHE_DIR`
2. `BKTSTR_CACHE_DIR/derived`
3. `RAILWAY_VOLUME_MOUNT_PATH/bktstr-cache/derived`
4. `/tmp/bktstr-cache/derived`

On Railway the persistent volume path should therefore be selected automatically when the same environment used by the raw cache is present.

## 2. Wrap intraday feature construction

Do not copy formulas into the cache module. If current code resembles:

```python
featured = add_indicators(raw_bars)
```

change the orchestration to the equivalent of:

```python
from integration.example_wrappers import cached_intraday_features

cached = cached_intraday_features(
    derived_cache,
    raw_bars,
    symbol,
    timeframe,
    add_indicators,
    formula_version="intraday-v0.3.3",
)
featured = cached.frame
```

Bump `formula_version` whenever indicator semantics change.

## 3. Wrap deterministic daily subject features

Wrap the function that builds SMA/EMA/returns/ATR/volatility/persistence primitives:

```python
cached = cached_daily_features(
    derived_cache,
    raw_daily,
    symbol,
    build_daily_features,
    formula_version="daily-features-v0.3.3",
)
daily_features = cached.frame
```

## 4. Wrap context/sentiment construction

Once subject, sector, and market daily feature frames exist:

```python
cached = cached_daily_context(
    derived_cache,
    subject_daily_features,
    sector_daily_features,
    market_daily_features,
    subject_symbol=symbol,
    sector_symbol=sentiment_sector_benchmark,
    market_symbol=sentiment_market_benchmark,
    compute_fn=build_context,
    formula_version="context-sentiment-v0.3.3",
    data_profile=sentiment_data_profile,
    sources=sentiment_sources,
)
context = cached.frame
```

The key includes all three input frames plus benchmark mapping/profile/source/formula dimensions.

## 5. Do not cache these

Keep live per request:

- regime Boolean rules (`lt`, `gte`, etc.)
- sentiment thresholds
- entry rules
- entry windows
- side
- stop/target
- max hold
- slippage
- position size
- same-day/EOD configuration
- trade simulation and MFE/MAE

The cache stores deterministic measurements, not decisions.

## 6. API diagnostics (optional)

A future compatible response can expose non-strategy diagnostics such as:

```json
{
  "derived_cache": {
    "intraday": {"hit": true, "key": "..."},
    "daily": {"hit": true, "key": "..."},
    "context": {"hit": false, "key": "..."}
  }
}
```

Do not make clients depend on this until `/api/v1/capabilities` and tests define it.

## 7. Deployment gate

Before calling this v0.3.4 or deploying:

1. Copy `bktstr_cache/` into the real repo.
2. Add the three wrapper integrations at current computation call sites.
3. Run the existing v0.3.3 test suite; the prior bundle baseline was 64/64.
4. Run the new cache tests.
5. Run one cold and one warm NVDA production-equivalent control locally.
6. Confirm trade-by-trade equality between cache disabled and cache enabled.
7. Confirm coverage/provenance metadata equality.
8. Confirm warm run reports cache hits and is faster.
9. Only then bump service version/deploy.
