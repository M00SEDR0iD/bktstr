# BKTSTR

**Current release: v0.3.3**

Granular, read-only equity backtesting service intended to be called by an AI research workflow.

## What v0.3.2 does

- 1m / 5m / 15m / 1h / 1d OHLCV input
- Long and short underlying-equity simulations
- Signal on bar close, execution on the **next bar open**
- Session VWAP, RSI(14), and 20-bar volume ratio
- Stops, profit targets, max-hold exits, same-day exits
- Adverse slippage on entries and exits
- Conservative stop-first assumption when stop and target both occur inside one OHLC bar
- Trade-by-trade P/L, MFE, MAE, hold time, and aggregate metrics
- Massive historical-data adapter
- Yahoo recent-intraday fallback so the deployment can be smoke-tested without an API key
- Look-ahead-safe daily regime filters with optional benchmark-relative strength

This service never places trades and has no brokerage write access.

## Versioning

BKTSTR uses `major.minor.sub-build` numbering for this research series. Sub-builds advance from `0` through `9` (for example `0.3.0` through `0.3.9`); the next change after `0.3.9` rolls to `0.4.0`.

## Endpoints

### Health

`GET /health`

### Capabilities

`GET /api/v1/capabilities`

### Backtest

Example:

```text
GET /api/v1/backtest?symbol=NVDA&start=2026-08-18&end=2026-08-23&timeframe=1m&side=short&entry=close.cross_below%3Avwap&stop_pct=1&target_pct=3&max_hold_minutes=240&position_size=1000&slippage_bps=2&entry_start_time=13%3A00&entry_end_time=16%3A00
```

Rules are comma-separated and ANDed. Supported examples:

- `close.cross_below:vwap`
- `close.cross_above:vwap`
- `rsi14.lt:45`
- `rsi14.gt:55`
- `volume_ratio20.gt:1.5`

Use URL encoding when necessary (`:` becomes `%3A`, comma can become `%2C`).


## Daily regime filters (v0.3.0)

Use the optional `regime` parameter to require a completed-daily-market condition in addition to the intraday `entry` rules. Use `benchmark` when the regime references benchmark-relative fields. Regime data is fetched at `1d`, cached independently from intraday bars, and computed with a 120-calendar-day warm-up.

Example:

```text
GET /api/v1/backtest?symbol=NVDA&start=2025-01-01&end=2025-12-31&timeframe=1m&side=short&entry=close.cross_below%3Avwap%2Crsi14.lt%3A50%2Cvolume_ratio20.gt%3A1.1&regime=day_close.lt%3Aday_sma20%2Crelative_return20.lt%3A0&benchmark=SOXX&entry_start_time=12%3A30&entry_end_time=16%3A00&stop_pct=1&target_pct=3
```

Supported regime fields:

- `day_close` — latest completed close before the intraday session
- `day_sma20` — 20-session SMA through that completed daily bar
- `day_sma50` — 50-session SMA
- `day_sma20_slope5` — percent change in SMA20 versus five completed sessions earlier
- `day_return20` — traded symbol's 20-session percent return
- `benchmark_return20` — benchmark's 20-session percent return
- `relative_return20` — `day_return20 - benchmark_return20` in percentage points

Regime rules support `lt`, `lte`, `gt`, `gte`, and `eq`. Cross operators are intentionally not supported for regime rules in v0.3.0.

### Look-ahead guard

For an intraday session on date D, regime values come from the latest completed daily feature row whose trading date is **strictly before D**. A Tuesday trade can use Monday's completed daily close and indicators, never Tuesday's eventual close. This also makes live/current-day regime evaluation safe when the current daily candle is incomplete or absent.

When a regime is used, the response keeps `data.cache` for the intraday cache and adds `data.regime` with daily subject/benchmark bar counts and cache statistics.

## Market data

If `MASSIVE_API_KEY` is set, the service uses Massive's aggregates API. Cold historical requests now send the full missing date range and follow Massive's 50,000-row pagination instead of splitting the range into many 30-day calls. The provider authenticates with an `Authorization` header, automatically retries HTTP 429 and transient 5xx responses with `Retry-After`/exponential backoff, and then persists the completed historical days into the Railway cache. Without that key, recent intraday requests can use Yahoo as a temporary fallback. Regime-filter backtests require Massive in v0.3.0 because the fallback is intentionally limited to recent intraday data. The fallback is deliberately not treated as our long-term research dataset.

## Railway

Railway is already configured by `railway.json` and `Dockerfile`. The process listens on the `PORT` environment variable supplied by Railway.

Optional Railway variable:

```text
MASSIVE_API_KEY=<your key>
```

Do not commit API keys to GitHub.

## Local test

```bash
python -m pip install -r requirements-dev.txt
pytest -q
PORT=8000 python -m bktstr.server
```

Then open `http://localhost:8000/health`.

## Important limitations

- Backtests the underlying stock/ETF, not historical option contracts yet.
- Intraday RSI/VWAP/volume indicators are still calculated on the requested base bars; v0.3.0 adds a focused completed-daily regime layer rather than arbitrary multi-timeframe indicators.
- No commissions/borrow fees yet; slippage is modeled.
- Aggregate max drawdown currently uses closed-trade equity. MFE/MAE expose intratrade excursions, but a mark-to-market equity curve is a planned improvement.
- Data-provider quality and entitlements still matter. Yahoo is only a smoke-test fallback; long-history research should use a proper paid feed.

### Optional entry-time window

Use `entry_start_time` and `entry_end_time` to restrict when a new position may actually be entered. Values use 24-hour `HH:MM` in `America/New_York` market time. The start is inclusive and the end is exclusive.

For example:

```text
entry_start_time=13:00
entry_end_time=16:00
```

This permits entries from 1:00 PM through 3:59 PM ET. Because execution is still the next bar open, a 12:59 PM signal may qualify if its simulated fill occurs at 1:00 PM. Existing positions are still managed normally after entry; the window only controls new entries. Omitting either parameter leaves that side of the window unrestricted.

## Persistent market-data cache

BKTSTR caches raw OHLCV bars by provider, symbol, timeframe, and trading date. Strategy results are **not** cached, so changing entry rules, stops, targets, or other simulation parameters reuses the same market data without returning stale backtest output.

On Railway, attach a persistent Volume to the BKTSTR service. A simple mount path is:

```text
/data
```

Railway automatically exposes the mount path through `RAILWAY_VOLUME_MOUNT_PATH`; BKTSTR will then store cached bars under:

```text
/data/bktstr-cache
```

You can override this with:

```text
BKTSTR_CACHE_DIR=/some/other/path
```

Historical dates are cached persistently. The current New York trading date is always fetched live so an intraday request cannot reuse a stale partial-day snapshot.

Each backtest response reports cache activity in `data.cache`, for example:

```json
{
  "hit_days": 58,
  "miss_days": 0,
  "fetched_ranges": 0
}
```

A cold request will show missing days and one or more fetched ranges. Subsequent strategy variations over the same symbol/date/timeframe should show cache hits and make no Massive request for those historical days.


## Historical download behavior

For a cold long-range request, BKTSTR minimizes Massive API calls by requesting the entire missing date range once and following server-provided pagination. This is especially important on rate-limited plans. If Massive responds with HTTP 429, BKTSTR honors `Retry-After` when supplied and otherwise uses bounded exponential backoff. HTTP 500/502/503/504 responses use the same retry path. API credentials are sent in the Authorization header rather than the URL.

## v0.3.2 background investor sentiment and transition layer

BKTSTR can compute a slow-moving, market-derived sentiment prior separately from the intraday entry rules and daily regime filters. v0.3.2 adds sentiment momentum, fragility, volatility-aware EMA persistence, and explicit source provenance. Enable it with two explicit comparison benchmarks:

```text
sentiment=true
sentiment_sector_benchmark=SOXX
sentiment_market_benchmark=QQQ
sentiment_data_profile=clean
sentiment_sources=price
```

Example NVDA request parameters:

```text
entry=close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.1
regime=day_sma20_slope5.lt:0,relative_return20.lt:0
benchmark=SOXX
sentiment=true
sentiment_sector_benchmark=SOXX
sentiment_market_benchmark=QQQ
entry_start_time=12:30
entry_end_time=16:00
```

The sentiment layer uses completed daily data only. A Tuesday intraday trade can use at most Monday's completed sentiment row; Tuesday's daily close cannot influence Tuesday's trade.

### Sentiment raw features

- 63- and 126-session relative returns versus the sector benchmark.
- 63- and 126-session relative returns versus the market benchmark.
- Distance from the rolling 252-session high.
- 20-session slopes of the 50-, 100-, and 200-session simple moving averages.
- Legacy count of the last 20 completed sessions spent below SMA50 (diagnostic only in v0.3.2).
- EMA50/100/200, ATR20%, 20/60-session realized volatility, volatility ratio, EMA50 occupancy, and ATR-normalized persistence pressure.

Long-lookback fields are allowed to be unavailable when history coverage is short. Available components still produce a score, while `sentiment_completeness` and `sentiment_confidence` fall to reflect missing evidence.

### Sentiment component scores

All scores range from `-1` (bearish) to `+1` (bullish):

- `sentiment_leadership_score`, weight `0.35`
- `sentiment_trend_score`, weight `0.30`
- `sentiment_peak_score`, weight `0.20`
- `sentiment_persistence_score`, weight `0.15`

`sentiment_direction` is their weighted mean over available components. `sentiment_confidence` combines evidence completeness, direction magnitude, and component magnitude. The layer then exposes symmetric bounded modifiers:

```text
sentiment_multiplier_long  = clip(1 + 0.5 * direction * confidence, 0.5, 1.5)
sentiment_multiplier_short = clip(1 - 0.5 * direction * confidence, 0.5, 1.5)
```

In v0.3.2 these multipliers are **informational only**. They are attached to trades and summarized for research, but they do not change `position_size`, fills, or P&L. This lets us validate whether the sentiment prior separates profitable from unprofitable technical setups before allowing it to change risk.

When a sentiment score is available at entry, each trade includes direction, confidence, completeness, both multipliers, the side-specific `sentiment_multiplier`, and the four component scores. Summary output includes the average direction, confidence, and side-specific multiplier across sentiment-scored trades.

Version sequence for this branch is `0.3.0` through `0.3.9`, then `0.4.0`.


## System manual / GUI contract

The white-paper-style architecture and user manual is `docs/BKTSTR_SYSTEM_MANUAL.md`. The stable machine-readable sentiment/provenance contract for future GUI development is `docs/gui/sentiment-data-contract.json`. Runtime field discovery remains available at `/api/v1/capabilities`.

## v0.3.3 sentiment coverage and native filters

- Optional pre-period sentiment warm-up can degrade without failing required-period backtests.
- Responses expose `requested_warmup_start`, common `coverage_start`/`coverage_end`, `warmup_degraded`, and per-symbol coverage diagnostics.
- Sentiment fields can be used natively in `regime=` when `sentiment=true`, for example `sentiment_fragility.gte:0.35`.
- Required-period market-data failures remain fatal; non-clean sentiment sources remain explicit opt-ins only when implemented.
