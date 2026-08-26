# BKTSTR Agent Backtest Runbook

**Current release:** v0.6.0
**Behavioral baseline:** v0.3.3 trading semantics, with v0.3.4 deterministic derived caching, v0.3.5 release infrastructure, and v0.6 typed experiment envelopes
**Research purpose:** identify short-duration scalp opportunities that occur inside a broader bearish or deteriorating market/sector regime.  
**Production API:** `https://bktstr-production.up.railway.app`

This file is the fastest handoff for a future AI agent. Read `docs/BKTSTR_SYSTEM_MANUAL.md` for formulas and full architecture.

## 1. Research theory

BKTSTR is not meant to search for isolated one-minute patterns with no context. The intended hierarchy is:

```text
QQQ broad technology/risk regime
        ↓
SOXX semiconductor sector regime
        ↓
subject-specific state (NVDA, MU, AVGO, AMD...)
        ↓
company-level sentiment / structural disagreement / volatility
        ↓
intraday trigger: VWAP + RSI + volume
        ↓
explicit execution model
```

The current primary short trigger is a scalp entry. The broad regime determines whether short scalps are worth attempting; subject context helps choose the best expression of that regime.

**Do not treat `sentiment_fragility` as automatically bearish.** Recent validation showed that high fragility can describe multiple states. Component disagreement and volatility stress should be inspected independently.

## 2. Proven connection path

Direct browser/container access to Railway is unreliable from some ChatGPT sessions. Use Supabase `pg_net`:

```text
ChatGPT
  → Supabase.execute_sql
  → net.http_get(...) / net.http_post(...)
  → Railway BKTSTR
  → net._http_response
  → ChatGPT
```

### Health

```sql
select net.http_get(
  url := 'https://bktstr-production.up.railway.app/health',
  timeout_milliseconds := 30000
) as request_id;
```

### Capabilities

```sql
select net.http_get(
  url := 'https://bktstr-production.up.railway.app/api/v1/capabilities',
  headers := jsonb_build_object('Authorization', 'Bearer <BKTSTR_API_KEY>'),
  timeout_milliseconds := 30000
) as request_id;
```

Replace `<BKTSTR_API_KEY>` with the bearer key supplied through your approved
secret path; do not store that key in a notebook, table, prompt, or committed
SQL file.

### Poll a request

```sql
select id, status_code, timed_out, error_msg, content
from net._http_response
where id = <request_id>;
```

If no row exists yet, poll the same ID. **Do not resubmit just because the row has not appeared.**

For long 1-minute backtests use `timeout_milliseconds := 120000` or `180000`. Full-year runs can be slower, especially if several are launched concurrently. Warm long periods sequentially before running a large threshold matrix.

## 3. Locked NVDA research template

Use `POST /api/v1/backtests` for each typed experiment. The long locked
control below deliberately requests `async` execution, so it returns a queued
experiment instead of occupying the HTTP request.

```sql
select net.http_post(
  url := 'https://bktstr-production.up.railway.app/api/v1/backtests',
  headers := jsonb_build_object('Authorization', 'Bearer <BKTSTR_API_KEY>'),
  body := jsonb_build_object(
    'strategy', jsonb_build_object(
      'id', 'bktstr.bearish-regime-scalp',
      'version', '1.0.0',
      'parameters', jsonb_build_object('stop_pct', 1.0, 'target_pct', 3.0)
    ),
    'market', jsonb_build_object(
      'symbol', 'NVDA', 'start', '2025-03-01', 'end', '2025-12-31',
      'timeframe', '1m', 'source', 'auto'
    ),
    'side', 'short',
    'entry', 'close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10',
    'regime', jsonb_build_object(
      'enabled', true,
      'rules', 'day_sma20_slope5.lt:0,relative_return20.lt:0',
      'benchmark', 'SOXX',
      'sentiment_enabled', true,
      'sentiment_sector_benchmark', 'SOXX',
      'sentiment_market_benchmark', 'QQQ',
      'sentiment_data_profile', 'clean',
      'sentiment_sources', jsonb_build_array('price')
    ),
    'execution', 'async',
    'include_trades', true
  ),
  timeout_milliseconds := 180000
) as request_id;
```

This long request returns `202 Accepted` with `status: "queued"` and an
`experiment_id` in the response body. Read that ID from `net._http_response`,
then submit bearer-authenticated `GET /api/v1/experiments/{experiment_id}`
requests until its `status` is `completed` or `failed`. A completed backtest
returns `result.metrics`, `result.trades`, `result.configuration`, and
`result.provenance`.

### Critical percentage semantics

```text
stop_pct=1   means 1%
target_pct=3 means 3%
```

Do **not** send `0.01` and `0.03`; that means 0.01% / 0.03% and produces near-immediate exits.

## 4. Standard controls

Every serious semiconductor subject test should include:

1. **Subject control** — bearish regime + frozen technical trigger, no experimental sentiment threshold.
2. **QQQ control** — same short trigger on QQQ with a non-self relative benchmark.
3. **SOXX control** — same short trigger on SOXX with a non-self relative benchmark.
4. **Cross-symbol controls** — at minimum NVDA, AMD, AVGO, MU when the hypothesis is semiconductor-wide.
5. **Time split** — discovery/training period and untouched holdout period.

Avoid benchmarking an ETF against itself for `relative_return20`; choose the benchmark mapping deliberately and record it in the result table.

## 5. Current validated research status

These are research findings, not production trading rules:

- NVDA Mar-Dec 2025 bearish-regime control reproduced: 30 trades, 40% wins, EV about -$2.27/trade.
- NVDA Jun-Aug 2026 control reproduced: 7 trades, 85.7% wins, EV about +$6.09/trade.
- Fragility thresholds did **not** show a reliable monotonic standalone short signal.
- `fragility >= 0.40` worked strongly in small NVDA/MU samples but failed on AVGO and produced no AMD trades.
- AVGO high-fragility trades carried much higher volatility stress; stop-outs dominated losses.
- SOXX and QQQ both improved substantially from 2025 to Jun-Aug 2026 under the frozen scalp trigger, indicating a broader regime shift.
- QQQ showed a very small high-component-spread/moderate-volatility subset with positive 2026 results, but 2025 did not validate it.

**Interpretation:** market/sector state likely matters before company-level fragility. Treat the working hypothesis as hierarchical, not as a single fragility threshold.

## 6. Metrics to capture

Always capture at least:

```text
result.metrics.ev_per_trade / win_rate / profit_factor / max_drawdown / sharpe
result.metrics.trade_count / total_pnl / total_return
result.trades[].mfe / mae / exit_reason / holding_time_minutes
result.trades[].signal_values_at_entry / regime_variables
result.configuration (strategy, market, regime, execution)
result.provenance (market-data source/version/coverage, execution model, software build)
```

Do not compare win rate alone. EV, MFE/MAE, stop-out rate, trade count, and provenance matter.

## 7. Clean research rules

- Keep `sentiment_data_profile=clean` and `sentiment_sources=price` for Tier-A baseline research.
- Require `all_point_in_time_safe=true`.
- Record `warmup_degraded`; optional missing warm-up can reduce completeness but required-period data must remain strict.
- Do not silently substitute missing sources or benchmarks.
- Never promote a filter because it improves one period or one symbol.
- Prefer broad useful regions over a single optimized threshold.
- Treat heavily explored NVDA 2025/Jun-Aug 2026 samples as discovery data now.

## 8. Efficient batching

1. Run health/capabilities once per session.
2. Warm the longest control period sequentially.
3. Reuse the same dates/symbol/timeframe so raw and derived caches can hit.
4. Change only one research dimension per comparison.
5. Extract only needed JSON fields from `content` when polling to reduce Supabase response size.
6. Avoid launching many full-year 1-minute jobs concurrently; Railway/pg_net timeouts can reflect contention rather than a backtest error.

## 9. Derived-cache expectations (v0.3.4+)

When the cache patch is integrated, repeated runs should reuse deterministic features/context. A threshold change such as:

```text
sentiment_fragility.gte:0.40
```

or:

```text
sentiment_component_spread.gte:0.50,sentiment_volatility_stress.lt:0.50
```

must **not** recompute unchanged VWAP/RSI/daily EMA/ATR/sentiment primitives. Threshold evaluation and execution simulation still run live.


## v0.3.4+ derived cache verification

Production `/api/v1/capabilities` must report the expected deployed version and the derived namespaces `intraday_features`, `daily_regime`, and `daily_sentiment`. The typed completed envelope preserves market-data provenance alongside the strategy result. For correctness controls, set `BKTSTR_DERIVED_CACHE_ENABLED=false` and verify trade records are exactly equal to the cache-enabled run; this toggle changes computation reuse only, never strategy semantics.


## 10. v0.6 development and deployment workflow

Normal source development is:

```text
feature branch → GitHub CI → merge main → Railway auto-deploy → production acceptance → tag
```

Do not develop directly on `main`. GitHub CI must be green before merge. CI rejects tracked generated Python artifacts in addition to running tests, compile checks, and the cache benchmark.

After Railway deploys, verify `/health` first. Record `version` and `git_commit`; Railway GitHub deployments populate the latter from `RAILWAY_GIT_COMMIT_SHA`. Then run:

```bash
python scripts/production_acceptance.py \
  --base-url https://bktstr-production.up.railway.app
```

Set `BKTSTR_API_KEY` in the environment before running production acceptance. This v0.6 production gate verifies deployed identity, the OpenAPI research contract, bearer-authenticated capabilities, and a completed bounded backtest envelope.

### GitHub-through-Supabase emergency recovery

If direct GitHub access is unavailable, do **not** reconstruct source from memory. Use `ops/supabase/GITHUB_BRIDGE.md`. The fixed flow is:

1. enqueue commit;
2. enqueue tree;
3. enqueue blobs/source bodies;
4. collect blobs into the snapshot tables.

Commit/tree discovery uses the GitHub REST API. File bodies use `raw.githubusercontent.com`, avoiding the unauthenticated REST quota that otherwise becomes a bottleneck on repositories with more than roughly one API request per file. Recovered bodies are stored as `content_base64` alongside the Git blob SHA.
