# BKTSTR

Granular, read-only equity backtesting service intended to be called by an AI research workflow.

## What v0.1 does

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

This service never places trades and has no brokerage write access.

## Endpoints

### Health

`GET /health`

### Capabilities

`GET /api/v1/capabilities`

### Backtest

Example:

```text
GET /api/v1/backtest?symbol=NVDA&start=2026-08-18&end=2026-08-23&timeframe=1m&side=short&entry=close.cross_below%3Avwap&stop_pct=1&target_pct=3&max_hold_minutes=240&position_size=1000&slippage_bps=2
```

Rules are comma-separated and ANDed. Supported examples:

- `close.cross_below:vwap`
- `close.cross_above:vwap`
- `rsi14.lt:45`
- `rsi14.gt:55`
- `volume_ratio20.gt:1.5`

Use URL encoding when necessary (`:` becomes `%3A`, comma can become `%2C`).

## Market data

If `MASSIVE_API_KEY` is set, the service uses Massive's aggregates API and chunks long ranges into 30-day requests. Without that key, recent intraday requests can use Yahoo as a temporary fallback. The fallback is deliberately not treated as our long-term research dataset.

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

## Important v0.1 limitations

- Backtests the underlying stock/ETF, not historical option contracts yet.
- No multi-symbol regime rules yet (for example `NVDA` signal conditioned on `SOXX`).
- No multi-timeframe indicators yet; RSI is calculated on the requested base bars.
- No commissions/borrow fees yet; slippage is modeled.
- Aggregate max drawdown currently uses closed-trade equity. MFE/MAE expose intratrade excursions, but a mark-to-market equity curve is a planned improvement.
- Data-provider quality and entitlements still matter. Yahoo is only a smoke-test fallback; long-history research should use a proper paid feed.

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
