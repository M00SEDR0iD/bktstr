# BKTSTR Derived Cache Architecture

**Status:** v0.3.4 performance candidate. Behavioral reference remains v0.3.3 until integrated into the live repo and verified trade-for-trade.

## Why this cache exists

BKTSTR already persists underlying OHLCV. Repeated research runs nevertheless reuse the same bars while rebuilding the same deterministic indicators and daily context. Threshold sweeps, benchmark comparisons, stop/target changes, and entry-window experiments should not pay that computation cost repeatedly.

The derived cache stores **measurements**, never **decisions**.

## Layers

| Layer | Stores | Changes when |
|---|---|---|
| L0 raw | OHLCV | provider/cache coverage changes |
| L1 intraday | VWAP, RSI14, volume ratio, other deterministic bar features | raw bars/formula/session model changes |
| L1 daily | returns, SMA/EMA, ATR, realized vol, high-distance, persistence primitives | daily bars/formula changes |
| L2 context | relative returns, sentiment components, direction/momentum/spread/vol stress/fragility | subject/sector/market inputs, benchmark mapping, profile/sources/formula change |
| L3 optional result | exact JSON backtest response | any request/engine/data dimension changes |

## Key structure

A derived key hashes:

```text
cache format version
namespace
semantic dimensions
  symbol / timeframe
  formula_version
  session model
  subject / sector / market mapping
  data profile / sources
  look-ahead rule
input DataFrame digests
```

The DataFrame digest covers schema, index, and values. A content change creates a new cache key; old entries remain harmless and can be pruned later.

## Disk format

The candidate uses gzip-compressed pandas pickle plus JSON metadata. This was chosen because the current repository already depends on pandas and the cache patch should not force a new production dependency. The storage implementation is private to `DerivedFrameCache`; Parquet can replace it later behind the same interface.

Only server-created cache files should be loaded. Do not point the cache at untrusted user-controlled pickle files.

## Atomicity and corruption

Payload and metadata are written to unique temporary files and moved into place with `os.replace`. If an entry is unreadable or metadata does not match the expected key/dimensions/input digests, it is deleted and recomputed as a miss.

## Railway path selection

```text
BKTSTR_DERIVED_CACHE_DIR
  else BKTSTR_CACHE_DIR/derived
  else RAILWAY_VOLUME_MOUNT_PATH/bktstr-cache/derived
  else /tmp/bktstr-cache/derived
```

The Railway volume should be preferred in production.

## What remains live

Never cache these as part of L1/L2:

```text
regime pass/fail
sentiment threshold pass/fail
entry pass/fail
side
entry window
stop_pct / target_pct
max_hold_minutes
slippage_bps
position_size
same_day / eod_exit
trade path / MFE / MAE
```

This separation is what makes threshold research fast without turning the cache into an accidental fitted strategy.

## Benchmark included with this package

`PYTHONPATH=. python benchmarks/benchmark_cache.py`

Reference sandbox run on 120,000 synthetic minute rows:

```text
rows=120000
compute_calls=1
cold_hit=False cold_seconds=0.9800
warm_hit=True warm_seconds=0.0273
```

This is a **cache-mechanism benchmark, not a production BKTSTR speed claim**. The expensive callback deliberately performs deterministic pandas work plus a fixed delay. The important correctness result is `compute_calls=1`: the warm request hashes its input and loads persisted derived values instead of invoking the builder again.

## Further optimization after integration

If DataFrame hashing becomes measurable on multi-year minute data, the existing raw cache can expose a revision token per cached date/range. `DerivedFrameCache` already accepts a non-empty digest string instead of a DataFrame in `inputs`, so a trusted raw-cache revision can eventually replace full frame hashing without changing cache semantics.
