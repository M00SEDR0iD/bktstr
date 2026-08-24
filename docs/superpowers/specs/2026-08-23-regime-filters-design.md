# BKTSTR v0.3.0 Daily Regime Filters Design

## Goal
Add objective, look-ahead-safe daily regime filters to intraday backtests so the same entry setup can be conditioned on the prior completed daily state of the traded symbol and an optional benchmark such as SOXX.

## Public API
Backtest requests gain two optional query parameters:

- `regime`: comma-separated rule expression using the existing rule syntax.
- `benchmark`: optional ticker used for benchmark/relative-return regime features.

Example:

`regime=day_close.lt:day_sma20,relative_return20.lt:0&benchmark=SOXX`

Existing requests without `regime` remain behaviorally compatible.

## Regime features
The initial supported daily feature columns are:

- `day_close`: most recent completed daily close before the intraday session.
- `day_sma20`: 20-session simple moving average through the most recent completed daily bar.
- `day_sma50`: 50-session simple moving average through the most recent completed daily bar.
- `day_sma20_slope5`: percentage change in `day_sma20` versus five completed sessions earlier.
- `day_return20`: percent return of the traded symbol over 20 completed sessions.
- `benchmark_return20`: percent return of the benchmark over 20 completed sessions.
- `relative_return20`: `day_return20 - benchmark_return20` in percentage points.

Regime rules support `lt`, `lte`, `gt`, `gte`, and `eq`. Cross operators are rejected for regime rules in v0.3.0 because daily values are expanded across intraday bars and cross semantics would be ambiguous.

## Look-ahead prevention
For an intraday session on date D, BKTSTR must select the latest daily feature row whose trading date is strictly less than D. A Tuesday trade can therefore use Monday's completed close/indicators, never Tuesday's eventual daily close. This rule also works for live/current sessions whose daily bar does not yet exist.

## Data flow
1. Fetch/cache intraday bars as today.
2. If `regime` is provided, fetch daily bars for the traded symbol beginning 120 calendar days before the requested start date through the request end date.
3. If the regime references benchmark-dependent fields, fetch/cache benchmark daily bars over the same warm-up period.
4. Compute daily features without shifting the raw daily table.
5. Attach to each intraday session using a strict prior-date as-of mapping.
6. Evaluate intraday entry rules and regime rules separately, then AND the signals before next-bar execution.

## Output
`request` echoes `regime` and `benchmark`.
`data.cache` remains the intraday cache statistics for backward compatibility.
When a regime is used, `data.regime` reports subject/benchmark daily bar counts and their cache statistics.

## Validation
- Benchmark tickers use the existing symbol validation rules.
- `benchmark` fields require a benchmark.
- Regime rules may reference only the documented regime fields.
- Regime cross operators are rejected.

## Additional correctness fix
v0.3.0 also prevents `cross_above`/`cross_below` from comparing the first regular-hours bar of a session with the prior session's final bar. Intraday cross rules must occur within the same calendar trading session.

## Versioning
This release is `0.3.0`. Subsequent sub-builds use `0.3.1` through `0.3.9`; the next rollover is `0.4.0`.
