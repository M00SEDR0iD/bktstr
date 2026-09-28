# Futures data through Massive

BKTSTR uses its existing server-side `MASSIVE_API_KEY` for two authenticated,
read-only operations. No new credential is required by BKTSTR, but the Massive
account must allow the requested futures dataset and historical period.
Capabilities describe the adapter; only a successful provider request establishes
access to that requested data. Contract metadata access does not establish candle access.

## Discover contracts

`GET /api/v1/market-data/futures/contracts?product_code=NQ&as_of=2026-09-25`

Supply an uppercase product code and a point-in-time date. The response includes
`source`, `product_code`, `as_of`, `acquired_at`, and `contracts`, with explicit
tickers and available trade dates, tick sizes, settlement and venue metadata.
Only outright delivery contracts are returned. From March 12, 2025 onward,
discovery requests single-contract metadata; older records without type metadata
are filtered by exact product and delivery code. Combination contracts are excluded.
Use returned contract identifiers rather than inventing them. Contract discovery
does not select a continuous series or determine which contract was most liquid.

## Download candles

`GET /api/v1/market-data/futures/bars?ticker=NQZ6&start=2026-09-25&end=2026-09-25`

This ticker is illustrative; first confirm it through discovery. Dates are inclusive
UTC calendar dates, at most 31 per request. A futures trading session can start on
the previous UTC date, so fetch enough dates and apply the intended exchange
schedule explicitly. Break longer histories into adjacent, nonoverlapping ranges.

The response identifies the ticker, dates, acquisition time, Massive source,
`asset_class: futures`, `timeframe: 1m`, `adjustment: unadjusted`, and
`timestamp_convention: minute-open UTC`. Each bar includes timestamp, contract,
OHLC prices and contract volume. Available `dollar_volume` and `transactions` are
preserved. Massive's dollar_volume is price times contract volume, without a dollar
contract multiplier; it must not be treated as dollar notional.

Prices are raw. No stock split adjustment, back adjustment, contract stitching,
forward filling, or Yahoo fallback occurs. Empty results stay empty. Bars must be
strictly increasing, unique, on minute boundaries, within the requested dates,
and for the requested contract. Invalid OHLCV or incomplete pagination fails the
request; a partial download is not returned as complete. Missing minutes are not
proof of missing feed data: Massive omits intervals without trades. Coverage and
exchange-calendar checks remain necessary before controlled research.

These endpoints return downloads directly. Save the response with its acquisition
metadata and a content digest for reproducibility. They do not write strategy
experiments, populate equity caches, or register futures research applications.

## Errors and credentials

Use the normal BKTSTR bearer credential and the existing local credential helper.
The provider key stays on the server, in an authorization header. Redirects are
rejected and pagination stays on the same Massive HTTPS endpoint. Provider bodies
and credential-bearing URLs are never included in error responses.

| HTTP status | Error code | Meaning |
| --- | --- | --- |
| 401 | Existing API authentication error | BKTSTR access was not authenticated |
| 403 | `futures_access_denied` | Massive rejected its key or futures entitlement |
| 422 | `validation_error` | Invalid contract, date or range |
| 429 | `futures_rate_limited` | Bounded provider retries exhausted |
| 502 | `futures_provider_error`, `futures_provider_unavailable`, `futures_invalid_response` | Provider failure or unusable data |
| 503 | `futures_not_configured` | Server Massive key is absent |

## Data infrastructure versus strategy research

Futures downloads explicitly return `execution_supported: false`. The current
strategy engine and research application schema remain equity-based. Data access
does not establish correct futures P&L, contract sizing, commission, margin,
intrabar loss-floor, or rollover behavior. Do not send these candles through the
equity engine and label the result an NQ evaluation backtest.

Strategy theses, thresholds, risk budgets and evaluation targets continue to belong
in versioned ideas, policies, applications and protocols. Provider support is an
infrastructure change and contains no particular strategy or account defaults.

The change adds routes and capability metadata without changing stored records or
existing execution formulas. Rollback is a redeployment of the preceding version;
the new routes become unavailable, and existing research storage remains compatible.

Provider references: [contracts](https://massive.com/docs/rest/futures/contracts)
and [aggregates](https://massive.com/docs/rest/futures/aggregates).
