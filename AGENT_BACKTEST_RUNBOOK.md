# BKTSTR Agent Backtest Runbook

**Current release:** v0.3.5  
**Behavioral baseline:** v0.3.3 trading semantics, with v0.3.4 deterministic derived caching and v0.3.5 release infrastructure  
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
  → net.http_get(...)
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
  timeout_milliseconds := 30000
) as request_id;
```

### Poll a request

```sql
select id, status_code, timed_out, error_msg, content
from net._http_response
where id = <request_id>;
```

If no row exists yet, poll the same ID. **Do not resubmit just because the row has not appeared.**

For long 1-minute backtests use `timeout_milliseconds := 120000` or `180000`. Full-year runs can be slower, especially if several are launched concurrently. Warm long periods sequentially before running a large threshold matrix.

## 3. Locked NVDA research template

```sql
select net.http_get(
  url := 'https://bktstr-production.up.railway.app/api/v1/backtest',
  params := jsonb_build_object(
    'symbol','NVDA',
    'start','2025-03-01',
    'end','2025-12-31',
    'timeframe','1m',
    'side','short',
    'entry','close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.1',
    'regime','day_sma20_slope5.lt:0,relative_return20.lt:0',
    'benchmark','SOXX',
    'sentiment','true',
    'sentiment_sector_benchmark','SOXX',
    'sentiment_market_benchmark','QQQ',
    'sentiment_data_profile','clean',
    'sentiment_sources','price',
    'stop_pct','1',
    'target_pct','3',
    'max_hold_minutes','240',
    'slippage_bps','2',
    'entry_start_time','12:30',
    'entry_end_time','16:00',
    'same_day','true',
    'eod_exit','true',
    'position_size','1000',
    'trade_limit','1000'
  ),
  timeout_milliseconds := 180000
) as request_id;
```

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
trades
wins / losses
win_rate_pct
total_pnl_dollars
expected_pnl_per_trade
profit factor (derive from trades if not in summary)
average winner / loser
max_drawdown_pct
MFE / MAE
exit_reason distribution
average sentiment direction / momentum / fragility
component spread
volatility stress
coverage_start / coverage_end
warmup_degraded
fallback_used
non_clean_data_used
all_point_in_time_safe
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

Production `/api/v1/capabilities` must report the expected deployed version and the derived namespaces `intraday_features`, `daily_regime`, and `daily_sentiment`. Backtest responses expose `data.derived_cache`. For correctness controls, set `BKTSTR_DERIVED_CACHE_ENABLED=false` and verify trade records are exactly equal to the cache-enabled run; this toggle changes computation reuse only, never strategy semantics.


## 10. v0.3.5 development and deployment workflow

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

This is the canonical v0.3.5 production gate. It runs the frozen NVDA Jun-Aug 2026 anchor twice and requires the known summary, identical trading output, and warm hits for intraday/regime/sentiment derived caches.

### GitHub-through-Supabase emergency recovery

If direct GitHub access is unavailable, do **not** reconstruct source from memory. Use `ops/supabase/GITHUB_BRIDGE.md`. The fixed flow is:

1. enqueue commit;
2. enqueue tree;
3. enqueue blobs/source bodies;
4. collect blobs into the snapshot tables.

Commit/tree discovery uses the GitHub REST API. File bodies use `raw.githubusercontent.com`, avoiding the unauthenticated REST quota that otherwise becomes a bottleneck on repositories with more than roughly one API request per file. Recovered bodies are stored as `content_base64` alongside the Git blob SHA.
