# BKTSTR API reference

Base URL: `https://bktstr-production.up.railway.app`

BKTSTR is a read-only equity and ETF research API. It runs historical research and never places brokerage orders. `GET /openapi.json` is the machine-readable contract. This document explains the public request, lifecycle, market-data, and ownership rules.

## Authentication and deployment ownership

Send `Authorization: Bearer <BKTSTR_API_KEY>` on every `/api/v1/*` route except `GET /health` and `GET /api/v1/health`.

`BKTSTR_API_KEY` is one nonempty opaque string. It has no prefix requirement, scopes, built-in expiry, or parallel grace key. The Railway deployment owner creates and distributes it.

To rotate the key, the owner replaces `BKTSTR_API_KEY` in Railway and redeploys. To revoke a key, the owner deletes or replaces it and redeploys. A rotated key stops working when the deployment using the replacement becomes active.

Do not put the key in URLs, request bodies, experiment metadata, or logs.

Start with authenticated `GET /api/v1/capabilities`. It publishes the registered parameter bounds, choices, overridability, strategy version, and evidence rules.

## Routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Unauthenticated deployment health probe. |
| `GET` | `/api/v1/health` | Unauthenticated versioned health probe. |
| `GET` | `/api/v1/capabilities` | Registered API, strategy, and evidence metadata. |
| `POST` | `/api/v1/backtests` | Submit one typed backtest. |
| `POST` | `/api/v1/parameter-sweeps` | Submit a bounded parameter sweep. |
| `POST` | `/api/v1/compare` | Compare completed backtests and named variants. |
| `POST` | `/api/v1/regime-comparison` | Compare labelled market periods. |
| `GET` | `/api/v1/backtests/{experiment_id}` | Retrieve a backtest experiment only. |
| `GET` | `/api/v1/experiments/{experiment_id}` | Retrieve the canonical envelope for any experiment. |
| `GET` | `/api/v1/market-data` | Inspect normalized, paginated OHLCV data. |

The former `GET /api/v1/backtest` route is removed. It returns `410 legacy_endpoint_removed` and identifies `POST /api/v1/backtests` as the replacement.

## Request examples

Every submission uses JSON and bearer authentication. The examples below are complete request bodies for the route named above each example.

### Backtest

`POST /api/v1/backtests`

```json
{
  "strategy": {
    "id": "bktstr.bearish-regime-scalp",
    "version": "1.0.0",
    "parameters": {
      "stop_pct": 1.0,
      "target_pct": 3.0
    }
  },
  "market": {
    "symbol": "NVDA",
    "start": "2026-08-17",
    "end": "2026-08-21",
    "timeframe": "1m",
    "source": "auto"
  },
  "side": "short",
  "entry": "close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10",
  "regime": {
    "enabled": true,
    "rules": "day_sma20_slope5.lt:0,relative_return20.lt:0",
    "benchmark": "SOXX",
    "sentiment_enabled": true,
    "sentiment_sector_benchmark": "SOXX",
    "sentiment_market_benchmark": "QQQ",
    "sentiment_data_profile": "clean",
    "sentiment_sources": ["price"]
  },
  "execution": "auto",
  "include_trades": true
}
```

### Parameter sweep

`POST /api/v1/parameter-sweeps`

```json
{
  "base": {
    "strategy": {
      "id": "bktstr.bearish-regime-scalp",
      "version": "1.0.0",
      "parameters": {
        "stop_pct": 1.0,
        "target_pct": 3.0
      }
    },
    "market": {
      "symbol": "NVDA",
      "start": "2026-08-17",
      "end": "2026-08-21",
      "timeframe": "1m",
      "source": "auto"
    },
    "side": "short",
    "entry": "close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10",
    "regime": {
      "enabled": true,
      "rules": "day_sma20_slope5.lt:0,relative_return20.lt:0",
      "benchmark": "SOXX",
      "sentiment_enabled": true,
      "sentiment_sector_benchmark": "SOXX",
      "sentiment_market_benchmark": "QQQ",
      "sentiment_data_profile": "clean",
      "sentiment_sources": ["price"]
    },
    "execution": "auto",
    "include_trades": true
  },
  "grid": {
    "stop_pct": [1.0, 2.0]
  },
  "objective": "profit_factor",
  "execution": "auto"
}
```

### Mixed comparison

`POST /api/v1/compare`

```json
{
  "candidates": [
    "exp_0123456789abcdef",
    {
      "name": "wider-stop",
      "backtest": {
        "strategy": {
          "id": "bktstr.bearish-regime-scalp",
          "version": "1.0.0",
          "parameters": {
            "stop_pct": 2.0,
            "target_pct": 3.0
          }
        },
        "market": {
          "symbol": "NVDA",
          "start": "2026-08-17",
          "end": "2026-08-21",
          "timeframe": "1m",
          "source": "auto"
        },
        "side": "short",
        "entry": "close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10",
        "regime": {
          "enabled": true,
          "rules": "day_sma20_slope5.lt:0,relative_return20.lt:0",
          "benchmark": "SOXX",
          "sentiment_enabled": true,
          "sentiment_sector_benchmark": "SOXX",
          "sentiment_market_benchmark": "QQQ",
          "sentiment_data_profile": "clean",
          "sentiment_sources": ["price"]
        },
        "execution": "auto",
        "include_trades": true
      }
    }
  ],
  "execution": "auto"
}
```

The first candidate is the reference. A named variant creates a child backtest. An experiment-ID candidate must name a completed backtest when the comparison worker executes. Candidate order controls the reference; the response reports metric deltas against it and does not declare a winner or causal result.

### Regime comparison

`POST /api/v1/regime-comparison`

```json
{
  "base": {
    "strategy": {
      "id": "bktstr.bearish-regime-scalp",
      "version": "1.0.0",
      "parameters": {
        "stop_pct": 1.0,
        "target_pct": 3.0
      }
    },
    "market": {
      "symbol": "NVDA",
      "start": "2025-01-01",
      "end": "2026-08-21",
      "timeframe": "1m",
      "source": "auto"
    },
    "side": "short",
    "entry": "close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10",
    "regime": {
      "enabled": true,
      "rules": "day_sma20_slope5.lt:0,relative_return20.lt:0",
      "benchmark": "SOXX",
      "sentiment_enabled": true,
      "sentiment_sector_benchmark": "SOXX",
      "sentiment_market_benchmark": "QQQ",
      "sentiment_data_profile": "clean",
      "sentiment_sources": ["price"]
    },
    "execution": "auto",
    "include_trades": true
  },
  "labels": [
    {
      "label": "2025",
      "start": "2025-01-01",
      "end": "2025-12-31"
    },
    {
      "label": "2026",
      "start": "2026-01-01",
      "end": "2026-08-21"
    }
  ],
  "disjoint_periods": true,
  "execution": "auto"
}
```

## Strategy and market rules

| Rule | Runtime behavior |
| --- | --- |
| Strategy | `bktstr.bearish-regime-scalp` version `1.0.0` |
| Backtest timeframe | `1m` |
| Market-data inspection timeframes | `1m`, `5m`, `15m`, `1h`, `1d` |
| Symbols | Normalize to uppercase; 1-15 characters; first character A-Z; remaining characters A-Z, 0-9, `.`, or `-` |
| Source request | `auto` only |
| Date span | At most 730 elapsed days |
| Percent parameters | `stop_pct=1` means 1%; `target_pct=3` means 3% |

The baseline strategy evaluates an entry on a completed bar and enters at the next bar open. It applies adverse slippage. When a stop and target both occur in one OHLC bar, it treats the stop as first. Regime rules are hard filters. Sentiment values are research metadata, not sizing instructions.

These are the defaults from `BacktestCreate` and the baseline strategy definition. Strategy parameters belong in `strategy.parameters`; `entry` and `regime` use the top-level request fields.

| Field or parameter | Default |
| --- | --- |
| `side` | `short` |
| `entry` / `entry_rules` | `close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10` |
| `regime_rules` | `day_sma20_slope5.lt:0,relative_return20.lt:0` |
| `stop_pct` | `1.0` |
| `target_pct` | `3.0` |
| `max_hold_minutes` | `240` |
| `position_size` | `1000.0` |
| `starting_capital` | `10000.0` |
| `slippage_bps` | `2.0` |
| `regular_hours_only` | `true` |
| `same_day_only` | `true` |
| `entry_start_time` | `12:30` |
| `entry_end_time` | `16:00` |
| `sentiment` | `true` |
| `sentiment_data_profile` | `clean` |
| `sentiment_sources` | `["price"]` |
| request `execution` | `auto` |
| request `include_trades` | `true` |

## Experiment lifecycle and idempotency

POST operations return `202 Accepted` while an experiment is queued or running. They return `200 OK` for terminal inline execution or a terminal idempotent replay. `Location` is the canonical status URL. While an experiment is nonterminal, both `Retry-After` and `retry_after_seconds` are `2`.

```json
{
  "experiment_id": "exp_0123456789abcdef",
  "status": "queued",
  "status_url": "/api/v1/experiments/exp_0123456789abcdef",
  "retry_after_seconds": 2
}
```

Poll `status_url` with an authenticated `GET`, wait two seconds between nonterminal polls, and stop at `completed` or `failed`. Do not resubmit pending work. The legal transitions are `queued -> running -> completed|failed`.

All four POST routes accept `Idempotency-Key`. It must contain 1 through 128 visible ASCII characters, bytes `0x21` through `0x7e`.

Idempotency is scoped to one operation:

| Reuse | Result |
| --- | --- |
| Same operation, key, and canonical JSON payload | Return the existing experiment. Do not enqueue or execute another job. |
| Same operation and key, different canonical JSON payload | Return `409 idempotency_conflict`. |
| Different operation and same key | Treat as an independent idempotency record. |

The canonical payload is canonical JSON of the validated typed request, including enum values, defaults, and `execution`. JSON object key order and insignificant input formatting do not create a new payload. This does not promise domain normalization, such as normalizing symbol case. A replay returns the experiment's current state, `202` while queued or running and `200` after completion or failure. Idempotency records do not expire independently. They remain valid as long as their owning experiment remains in SQLite; the API has no experiment-delete route.

## Errors and request IDs

Immediate HTTP errors use this envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": {
      "fields": ["market.symbol"]
    },
    "request_id": "req_..."
  }
}
```

Every immediate HTTP error includes `error.request_id` and the same value in `X-Request-ID`.

| Status | Code | Meaning |
| --- | --- | --- |
| `400` | `invalid_request` | Semantic request validation failed before durable work is created. |
| `401` | `unauthorized` | The bearer key is missing or does not match the configured key. |
| `404` | `experiment_not_found` | The requested experiment does not exist, or a backtest-only route received another operation. |
| `409` | `idempotency_conflict` | An idempotency key was reused for a different canonical payload in the same operation. |
| `409` | `execution_not_available` | An explicitly synchronous request is outside the inline execution policy. |
| `410` | `legacy_endpoint_removed` | The retired `GET /api/v1/backtest` route was used. |
| `422` | `validation_error` | Request parsing or field validation failed. |
| `422` | `strategy_incompatible` | The selected strategy cannot use the requested configuration, such as its required timeframe. |
| `500` | `internal_error` | An unexpected immediate server failure occurred. |
| `502` | `market_data_http_error` | A market-data provider request failed during an immediate request. |

Worker errors appear inside a failed experiment envelope instead of as an HTTP error. They do not have an HTTP request ID because they may occur after the submitting request ends. Worker codes include `operation_failed` for an execution failure, `result_persistence_failed` when result persistence fails, and `market_data_http_error` for an upstream market-data HTTP failure. A worker may also record `invalid_request` if a durable request cannot be executed.

## Market-data inspection, providers, and caches

`GET /api/v1/market-data` accepts `symbol`, `start`, `end`, and `timeframe`, plus optional `source`, `limit`, and `cursor`. `limit` is 1 through 1000. The response contains normalized `timestamp`, `open`, `high`, `low`, `close`, and `volume` rows. Pass `next_cursor` unchanged to read the next page. A cursor is bound to the symbol, date range, timeframe, and source, so it cannot page a different request.

Massive is selected when configured. It requests 50,000 rows per page, permits 100 pages, and retries `429`, `500`, `502`, `503`, and `504` six times after the first request. A numeric upstream `Retry-After` wins. Otherwise, delay doubles from two seconds and caps at 30 seconds. Massive history depends on the account; BKTSTR promises only the 730-day request maximum.

Yahoo is a development fallback for `1m`, `5m`, and `15m` data wholly within the latest 30 calendar days. It fetches seven-day chunks. Older history, `1h`, `1d`, regime, and sentiment runs require Massive.

BKTSTR has no ingress request-per-minute limit. Clients must still follow the two-second polling interval and provider and deployment limits.

Historical raw-cache keys are provider, symbol, timeframe, and day. Historical empty days are cached. The current day is volatile and is not stored as a completed historical day. Derived caches contain deterministic measurements and context, never strategy decisions or simulation results.

## Comparison semantics

`POST /api/v1/compare` accepts 2 through 20 unique candidates. A candidate is either a completed backtest experiment ID beginning with `exp_`, or a named variant containing a complete typed backtest request. The first candidate is the reference. Named variants create linked child backtests. `metric_deltas` subtract the reference metric from each candidate metric, and `changed_inputs` compares canonical backtest requests.

`POST /api/v1/regime-comparison` accepts 2 through 12 labels. Each label supplies a name, date range, and optional rule. Set `disjoint_periods` to require labelled ranges not to overlap. Both comparison operations create experiment records and return their results through the same polling lifecycle.
