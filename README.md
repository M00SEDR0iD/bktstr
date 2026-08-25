# BKTSTR

**Current release: v0.6.0**

BKTSTR is a read-only equity/ETF research backtester built to identify short-duration scalp opportunities inside a broader bearish or deteriorating market regime. It never places brokerage orders.

## Research hierarchy

```text
QQQ broad technology/risk regime
        ↓
SOXX semiconductor sector regime
        ↓
subject state (NVDA, MU, AVGO, AMD, ...)
        ↓
price-implied sentiment / structural disagreement / volatility
        ↓
intraday VWAP + RSI + volume trigger
        ↓
next-bar-open execution with explicit stop/target/hold/slippage
```

QQQ and SOXX are permanent controls for semiconductor research. High sentiment fragility is diagnostic, not automatically bearish.

## v0.3.4+ performance architecture

BKTSTR now has two persistent cache layers:

1. **Raw OHLCV cache** — daily gzip files by provider/symbol/timeframe/date.
2. **Derived cache** — content-addressed deterministic DataFrames for:
   - `intraday_features` (regular-hours filtering + VWAP/RSI14/volume ratio)
   - `daily_regime`
   - `daily_sentiment`

Strategy decisions are **not** cached. Entry thresholds, regime filters, stops, targets, sizing, slippage, and trade simulation are evaluated fresh on every request. Cache keys include source-data digests and explicit formula versions so changed data/formulas create new entries.

Derived cache is enabled by default. For correctness comparisons:

```text
BKTSTR_DERIVED_CACHE_ENABLED=false
```

Optional path override:

```text
BKTSTR_DERIVED_CACHE_DIR=/data/bktstr-cache/derived
```

Every backtest exposes `data.derived_cache` hit/miss metadata.

## API

Production endpoint: `https://bktstr-production.up.railway.app`

- `GET /health`
- `GET /api/v1/capabilities`
- `POST /api/v1/backtests`
- `POST /api/v1/parameter-sweeps`
- `POST /api/v1/compare`
- `POST /api/v1/regime-comparison`
- `GET /api/v1/experiments/{experiment_id}`
- `GET /api/v1/market-data`
- `GET /openapi.json`

Core short setup used as the frozen NVDA research baseline:

```text
symbol=NVDA
timeframe=1m
side=short
entry=close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10
entry_start_time=12:30
entry_end_time=16:00
stop_pct=1
target_pct=3
max_hold_minutes=240
position_size=1000
slippage_bps=2
same_day=true
eod_exit=true
regime=day_sma20_slope5.lt:0,relative_return20.lt:0
benchmark=SOXX
sentiment=true
sentiment_sector_benchmark=SOXX
sentiment_market_benchmark=QQQ
sentiment_data_profile=clean
sentiment_sources=price
```

`stop_pct=1` means **1%**, not `0.01`. `target_pct=3` means **3%**.

## Agent access

When direct Railway networking is unavailable, use the proven Supabase `pg_net` bridge described in [`AGENT_BACKTEST_RUNBOOK.md`](AGENT_BACKTEST_RUNBOOK.md).

## Local development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python benchmarks/benchmark_cache.py
PORT=8000 python -m bktstr.server
```

## Project and contribution

- [Contributor guide](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Standalone web application roadmap](docs/roadmap/standalone-web-app.md)
- [v1 release plan](docs/roadmap/v1-release-plan.md)
- [Release procedure](docs/development/releases.md)

## v0.6.0 development and release workflow

GitHub Actions now runs the complete test suite, compile checks, repository-hygiene guard, and derived-cache benchmark on pushes to `main` and on pull requests. The standard release path is:

```text
feature branch → GitHub CI → merge main → Railway auto-deploy → production acceptance → tag release
```

Railway GitHub deployments provide `RAILWAY_GIT_COMMIT_SHA` and related repository/deployment variables. `/health` exposes the running `git_commit`, branch/repository, and deployment ID when available. `/api/v1/capabilities` publishes the same build identity plus feature-formula and cache-format versions.

After Railway deploys, run the locked production regression:

```bash
python scripts/production_acceptance.py --base-url https://bktstr-production.up.railway.app
```

The acceptance command checks v0.6.0 deployment identity, the published OpenAPI research contract, bearer-authenticated capabilities, and a completed bounded backtest envelope.

If an agent cannot reach GitHub directly, use the GitHub-through-Supabase recovery bridge in `ops/supabase/GITHUB_BRIDGE.md`. It is an emergency source-recovery path, not the normal development workflow.

## Deployment

Railway uses `Dockerfile` and `railway.json`. Set `MASSIVE_API_KEY` and `BKTSTR_API_KEY` as Railway secrets and attach a persistent volume (commonly `/data`). Never commit API credentials. The FastAPI service also reads these deployment settings:

- `BKTSTR_EXPERIMENT_DIR` — durable SQLite records and immutable experiment artifacts; place it on the Railway volume.
- `BKTSTR_SYNC_MAX_CALENDAR_DAYS` — maximum inclusive calendar span for an inline `sync` backtest (default `31`).
- `BKTSTR_MAX_SWEEP_VARIANTS` — maximum generated parameter-sweep variants (default `500`).
- `BKTSTR_LEGACY_BACKTEST_SUNSET` — migration metadata for the removed `GET /api/v1/backtest` endpoint; it remains a documented `410` response and never restores a second HTTP engine.

See [`docs/BKTSTR_SYSTEM_MANUAL.md`](docs/BKTSTR_SYSTEM_MANUAL.md) for the complete architecture, research discipline, look-ahead rules, provenance system, and GUI contract.
