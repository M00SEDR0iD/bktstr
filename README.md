# BKTSTR

**Current release: v0.3.4**

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

## v0.3.4 performance architecture

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
- `GET /api/v1/backtest`

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

## Deployment

Railway uses `Dockerfile` and `railway.json`. Set `MASSIVE_API_KEY` as a Railway secret and attach a persistent volume (commonly `/data`). Never commit API credentials.

See [`docs/BKTSTR_SYSTEM_MANUAL.md`](docs/BKTSTR_SYSTEM_MANUAL.md) for the complete architecture, research discipline, look-ahead rules, provenance system, and GUI contract.
