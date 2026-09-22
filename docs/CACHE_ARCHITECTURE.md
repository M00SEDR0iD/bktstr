# Cache and replay boundaries

## Existing numerical caches

Raw OHLCV data is cached by provider, symbol, timeframe, and date in
`bktstr/cache.py`. Current-day data is volatile. Historical empty days and actual
coverage must remain distinguishable from successful populated days.

`bktstr_cache/derived.py` stores deterministic DataFrames through
`DerivedFrameCache`. The namespaces are `intraday_features`, `daily_regime`,
and `daily_sentiment`. Keys include input content digests, formula versions, and
semantic dimensions such as session and benchmark mapping.

Do not cache strategy thresholds, gate outcomes, entry decisions, or fills as
reusable numerical features. Re-evaluate them for each frozen strategy.

The current cache uses compressed pickle; read only server-created trusted cache
files. Writes are atomic. Invalid entries become misses and are recomputed.
Formula changes create new identities rather than overwriting old evidence.

Derived storage resolves through:

1. `BKTSTR_DERIVED_CACHE_DIR`
2. `BKTSTR_CACHE_DIR/derived`
3. `RAILWAY_VOLUME_MOUNT_PATH/bktstr-cache/derived`
4. `/tmp/bktstr-cache/derived`

Use a persistent volume in production. Set `BKTSTR_DERIVED_CACHE_ENABLED=false`
for numerical cache equivalence checks.

## Planned model-response storage

Jev responses are acquired evidence, not deterministic formula outputs.
Store them separately with immutable response IDs, input and question digests,
model/provider identity, timing, usage, and validation status.

A repeat acquisition may produce a different response for the same input.
Never overwrite the response referenced by an experiment. Replay resolves the
pinned response ID and makes no model call. A missing response is an error, not
permission to regenerate it.

Reusing a model response in a forward session also requires a matching question,
model policy, input identity, and unexpired freshness window. Recomputing strategy
thresholds from the same response is permitted and creates a separate experiment.

## Decision records

Persist decision records as experiment outputs, including failed gates and
no-trade outcomes. Persisting a decision for audit does not mean reusing it as a
feature for another strategy.

Verification must establish cache-on/cache-off equivalence, identity invalidation
after source/formula changes, replay without network access, and no stale response
substitution. Use `benchmarks/benchmark_cache.py` to measure current numerical
cache behavior; do not treat old benchmark timings as a performance guarantee.
