# Derived Cache Integration Reference

The derived cache is already integrated into the live BKTSTR application as of v0.3.4. This document is retained as a reference for the integration boundary and for future refactors; it is **not** a pending merge guide.

## Current principle

**Cache deterministic features, not strategy decisions.**

The active service owns formula execution. `bktstr_cache` stores the resulting deterministic DataFrames using raw-data digests plus semantic/version dimensions. Changing a strategy threshold must reuse features without reusing a stale trading decision.

## Active cached namespaces

The runtime `/api/v1/capabilities` contract exposes these derived namespaces:

- `intraday_features` — session VWAP, RSI14, volume ratio and other deterministic intraday measurements.
- `daily_regime` — deterministic completed-daily regime measurements.
- `daily_sentiment` — deterministic subject/sector/market sentiment/context measurements.

The current semantic versions are published in `capabilities.release.feature_formula_versions`; the on-disk cache schema is published as `capabilities.release.derived_cache_format_version`.

## Storage selection

`DerivedFrameCache` resolves its persistent location in this order:

1. `BKTSTR_DERIVED_CACHE_DIR`
2. `BKTSTR_CACHE_DIR/derived`
3. `RAILWAY_VOLUME_MOUNT_PATH/bktstr-cache/derived`
4. `/tmp/bktstr-cache/derived`

## What remains live on every request

Do **not** cache any of the following as feature/context values:

- entry-rule Boolean decisions
- regime/sentiment threshold decisions
- entry windows
- side
- stop/target
- max hold
- slippage
- position size
- same-day/EOD configuration
- trade simulation
- MFE/MAE

These are evaluated from the cached continuous measurements on every backtest.

## Formula-version invalidation

When deterministic formula semantics change, bump the corresponding version constant rather than deleting old cache files manually. Current constants live in `bktstr/service.py` and the cache format constant lives in `bktstr_cache/derived.py`.

The cache key also incorporates the source DataFrame digest and relevant context dimensions such as symbol/timeframe and subject/sector/market mapping, so raw-data revisions or mapping changes invalidate the affected derived entry.

## Reference wrappers

`integration/example_wrappers.py` remains useful as a small, tested example of the intended boundary around existing formula callbacks. The production service may call the cache directly; these wrappers are reference/testing helpers rather than a second strategy implementation.

## Verification gate

Any future cache refactor must preserve all of the following:

1. Cache-disabled and cache-enabled backtests are trade-for-trade identical.
2. Repeated requests report warm derived-cache hits.
3. Coverage and provenance metadata are unchanged.
4. Strategy thresholds and execution parameters do not enter derived feature semantics.
5. The full test suite and production acceptance script pass before release promotion.

See `scripts/production_acceptance.py` and `MERGE_CHECKLIST.md` for the current v0.3.5 release gate.
