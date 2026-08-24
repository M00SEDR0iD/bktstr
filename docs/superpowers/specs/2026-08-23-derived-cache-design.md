# BKTSTR Derived Cache + Agent Research Workflow Design

**Target:** v0.3.4 cache candidate built on the verified v0.3.3 behavioral baseline.

## Goal

Make repeated BKTSTR backtests materially faster without changing signal formulas, execution semantics, look-ahead safety, or API behavior, and document a reliable agent workflow for finding short-duration scalp opportunities inside a broader bearish/deteriorating market regime.

## Research hierarchy

BKTSTR should treat context hierarchically:

1. QQQ: broad technology/risk environment.
2. SOXX: semiconductor sector regime.
3. Subject (NVDA/MU/AVGO/AMD/etc.): company-specific trend, leadership, sentiment level/momentum/disagreement/volatility.
4. Intraday technical trigger: VWAP/RSI/volume.
5. Execution: next-bar-open, adverse slippage, stop/target/max-hold/EOD.

The cache must never convert research hypotheses into stored trade decisions. Store deterministic values; evaluate thresholds and strategy rules live.

## Cache layers

### L0 raw OHLCV
Existing BKTSTR cache. Unchanged.

### L1 deterministic features
Persist computed intraday/daily feature DataFrames keyed by input-data digest plus feature/formula/session versions and symbol/timeframe.

Examples: VWAP, RSI14, volume_ratio20, moving averages/slopes, returns, EMA, ATR, realized volatility, 52-week-high distance, persistence primitives.

### L2 context
Persist deterministic regime/sentiment context DataFrames keyed by subject/sector/market input digests plus formula version, profile, sources, and benchmark mapping.

Examples: relative_return20, leadership/trend/peak/persistence scores, sentiment direction/confidence/momentum/component spread/volatility stress/fragility.

### L3 exact result memoization
Optional JSON result cache keyed by a complete canonical request/engine/data fingerprint. It is disabled unless explicitly integrated because L1/L2 provide the larger research-speed benefit.

## Invalidation

Cache keys include deterministic input DataFrame digests and explicit version dimensions. Any input value, index, formula version, session model, benchmark mapping, profile, or sources change creates a new key. Writes are atomic. Corrupt payloads are treated as misses.

## Storage

Default storage is gzip-compressed pandas pickle on the existing Railway persistent cache volume. This adds no dependency. The interface keeps serialization private so Parquet can replace it later without changing callers.

## Observability

Cache calls return a status object with hit/miss, key, namespace, path, and compute/load elapsed time. These diagnostics can later be surfaced in API data metadata without affecting strategy results.

## Operational access

Future agents use Supabase `pg_net` rather than direct Railway browsing:
ChatGPT -> Supabase.execute_sql -> net.http_get -> Railway -> net._http_response -> ChatGPT.

The agent runbook specifies 120-180s timeouts, request-id polling, sequential warming for long full-year jobs, percentage-point stop/target semantics, provenance checks, and standard QQQ/SOXX controls.

## Safety / correctness constraints

- Never cache Boolean regime pass/fail, entry pass/fail, "take short", or tuned thresholds.
- Strict prior-completed-session daily attachment remains unchanged.
- Cache must not hide missing coverage or provenance state.
- Cache corruption becomes a miss, never a partial result.
- Existing v0.3.3 baseline tests and known production controls must match before deployment.
