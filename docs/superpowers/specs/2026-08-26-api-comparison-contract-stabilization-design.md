# API comparison and contract stabilization design

**Status:** Approved in chat on 2026-08-26. Awaiting written-spec review.

**Target:** BKTSTR v0.6 API stabilization.

**Foundation:** The approved v0.6 API-first research design and the current FastAPI, experiment-store, and worker implementation.

## Purpose

The API can authenticate clients, inspect market data, run backtests, enqueue parameter sweeps, and compare regimes. Comparison jobs are the immediate blocker. A valid `POST /api/v1/compare` request reaches the durable worker, then fails when Pydantic tries to serialize an immutable `mappingproxy` nested in the comparison result.

This change fixes that failure and tightens the surrounding contract. Requests that cannot run must fail before enqueueing. Accepted jobs must tell clients exactly where and when to poll. Failed jobs must retain safe diagnostic details. OpenAPI and the operator documentation must describe what the server actually accepts.

## Goals

- Complete comparisons made from named variants, completed backtest experiment IDs, or a mix of both.
- Reject a backtest whose market timeframe does not match its registered strategy before creating an experiment.
- Return `422 strategy_incompatible` for the current baseline strategy when the requested timeframe is not `1m`.
- Preserve a useful, safe worker error code, message, failure stage, and exception type.
- Type accepted request sources and timeframes in OpenAPI.
- Give every experiment response a canonical status URL and retry timing.
- Define idempotency scope, replay, conflict, and retention behavior.
- Exercise every POST route through HTTP submission, durable storage, worker execution, and terminal polling.
- Publish one API reference with authentication, request examples, lifecycle rules, errors, provider limits, rate limits, cache behavior, and comparison semantics.

## Non-goals

- Add user accounts, scoped API keys, automatic key expiry, or an in-process key-management service.
- Add a BKTSTR ingress rate limiter or quota system.
- Let clients choose `massive` or `yahoo` directly. Provider selection remains automatic.
- Add new strategies or make the baseline strategy compatible with non-`1m` bars.
- Replace the SQLite experiment store, alter completed-record immutability, or redesign the worker lease model.
- Add cancellation, progress percentages, or automatic retry of failed experiments.

## Findings

### Comparison serialization

The research service returns frozen dataclasses. Their mappings use `MappingProxyType` so callers cannot mutate metrics, provenance, or deltas after construction. `bktstr.services.backtest._json_value` already knows how to turn dataclasses, mappings, tuples, enums, dates, and datetimes into ordinary JSON-compatible containers.

The compare worker path does not use that conversion. `_execute_compare_experiment` passes the frozen result directly to `CompareResult.model_validate(..., from_attributes=True)`, then calls `model_dump(mode="json")`. Nested immutable mappings survive validation and reach Pydantic's serializer, which raises `Unable to serialize unknown type: <class 'mappingproxy'>`.

Parameter sweeps and regime comparisons use the same family of immutable result objects, so result normalization belongs at the shared operation-to-public-schema boundary. The fix must not weaken the service's internal immutability.

### Strategy compatibility

`normalize_market_request` checks the global market-data timeframe set `1m`, `5m`, `15m`, `1h`, and `1d`. `BacktestInput` resolves the selected strategy but does not compare the normalized market timeframe with `StrategyDefinition.timeframe`. The baseline strategy registry declares `1m`, so a `1d` request currently enters the queue and fails later in execution.

The service layer must enforce the registry contract because non-HTTP callers use `BacktestInput` directly. OpenAPI must enumerate the globally valid timeframe values and explain that the selected strategy narrows that set. The baseline strategy currently narrows it to `1m`.

### Worker failures

The worker already preserves structured `ExperimentOperationError`, semantic validation, `ValueError`, and HTTP provider failures. Its final `except Exception` branch replaces every other exception with the same `operation_failed` code, generic message, and empty details. That discards the information needed to diagnose a failed experiment.

### OpenAPI and async lifecycle

`source` and `timeframe` are plain strings in request models and query parameters. Runtime validation accepts only `source=auto`, while global market-data timeframes are a closed set. POST responses document a `202` model, but the body has no status link or retry interval and the response declares no `Location` or `Retry-After` headers.

### Idempotency

The experiment store already enforces uniqueness on `(operation, idempotency_key)`. Within one operation, an identical canonical payload returns the existing experiment and a different payload raises `IdempotencyConflictError`. The same key may be used independently for another operation. Records have no idempotency expiry or TTL.

## Public contract

### Request enums

OpenAPI will expose one closed market timeframe type with the values `1m`, `5m`, `15m`, `1h`, and `1d`.

- Market-data inspection accepts every value in that set.
- Backtest market fields use the same syntactic enum, then apply the selected strategy's registry contract. The field description and strategy capability schema state that `bktstr.bearish-regime-scalp` version `1.0.0` requires `1m`.

All public request locations that accept `source` will expose the single enum value `auto`. Response provenance continues to report the provider selected at runtime, such as `massive` or `yahoo`.

These enums make generated clients reject unknown timeframe and source strings without pretending that OpenAPI can express a cross-field registry lookup. Service validation remains authoritative for strategy compatibility, direct callers, and future registry changes.

### Strategy compatibility failure

`BacktestInput` will compare the normalized timeframe with the resolved strategy definition. A mismatch raises a dedicated compatibility error with the field `market.timeframe`.

The HTTP response is:

```json
{
  "error": {
    "code": "strategy_incompatible",
    "message": "Strategy 'bktstr.bearish-regime-scalp' version '1.0.0' requires timeframe '1m'; received '1d'.",
    "details": {
      "fields": ["market.timeframe"],
      "strategy_id": "bktstr.bearish-regime-scalp",
      "strategy_version": "1.0.0",
      "required_timeframe": "1m",
      "received_timeframe": "1d"
    },
    "request_id": "req_..."
  }
}
```

The status is `422`. Compound requests retain their prefixes, such as `base.market.timeframe` or `candidates.0.backtest.market.timeframe`. No experiment row or artifact is created.

### Experiment responses

Every typed experiment envelope gains two fields:

```json
{
  "status_url": "/api/v1/experiments/exp_...",
  "retry_after_seconds": 2
}
```

`status_url` is a deployment-independent relative URL. `retry_after_seconds` is `2` while the record is `queued` or `running`, and `null` after it reaches `completed` or `failed`.

All POST routes set `Location` to `status_url`. A POST or polling GET that returns a nonterminal experiment also sets `Retry-After: 2`. The body remains authoritative for clients that cannot inspect headers. Clients poll `GET status_url` with the same bearer key and stop on `completed` or `failed`. They do not resubmit merely because work is still pending.

The status URL is available on inline `200` responses too. This keeps one response shape for inline execution, queued execution, idempotent replay, and later inspection.

### Worker error details

Worker failures keep the existing experiment error envelope:

```json
{
  "code": "operation_failed",
  "message": "Unable to serialize unknown type: <class 'mappingproxy'>",
  "details": {
    "stage": "execution",
    "exception_type": "PydanticSerializationError"
  }
}
```

Expected failures retain their more specific existing codes. The worker will add structured details where the runtime provides them:

- `invalid_request` includes field paths for semantic validation.
- `market_data_http_error` includes the upstream status code when present and whether that status is retryable.
- `result_persistence_failed` identifies the persistence stage and exception type.
- unexpected execution failures retain `operation_failed`, a redacted and length-bounded exception message, `stage=execution`, and the exception class name.

The diagnostic formatter will replace configured API-key values and bearer-token text, remove URL query strings, and cap the persisted message at 1,000 characters. The worker must not include request headers, provider authorization headers, tracebacks, environment variables, or raw provider bodies. Empty exception messages fall back to the current generic message.

This design preserves a stable machine code while making the stored record useful for diagnosis. The comparison fix prevents the known serialization error; the richer fallback protects future jobs from becoming opaque.

### Idempotency

All four POST routes accept `Idempotency-Key` with the current validation rule: 1 through 128 visible ASCII characters, bytes `0x21` through `0x7e`.

Idempotency is scoped to one operation:

| Reuse | Result |
| --- | --- |
| Same operation, key, and canonical typed payload | Return the existing experiment. Do not enqueue or execute another job. |
| Same operation and key, different canonical typed payload | Return `409 idempotency_conflict`. |
| Different operation and same key | Treat as an independent idempotency record. |

The canonical payload includes the normalized typed request, including `execution`. JSON object key order and insignificant input formatting do not create a new payload. A replay returns the experiment's current state. It returns `202` while queued or running and `200` after completion or failure.

Idempotency records do not expire independently. They remain valid as long as the owning experiment remains in the SQLite store. The current API has no experiment-delete route.

## Comparison semantics

`POST /api/v1/compare` accepts 2 through 20 unique candidates. A candidate is either:

- an experiment ID beginning with `exp_`; or
- a named variant containing a complete typed backtest request.

Experiment-ID candidates must resolve to completed `backtest` experiments when the worker executes the comparison. Named variants create linked child backtest experiments and use their completed results. A request may mix both forms.

Candidate order matters. The first candidate is the reference. `metric_deltas` subtract each reference metric from the corresponding candidate metric. `changed_inputs` compares canonical backtest requests. The operation reports no winner and makes no causal claim.

If an experiment ID is missing, belongs to another operation, or is not completed, the comparison experiment fails with `invalid_request` and a useful message. The API cannot reject these references before enqueueing without moving experiment-store lookup into request parsing, and queued experiments may change state before execution. Named variant schema and strategy compatibility errors are rejected before enqueueing.

## Internal design

### JSON normalization boundary

Promote the existing recursive JSON conversion to a named service helper used by every operation adapter. Each adapter will:

1. Execute the service operation and receive its immutable domain result.
2. Convert the result to ordinary dicts, lists, strings, numbers, booleans, and nulls.
3. Validate that normalized value against the operation-specific Pydantic response model.
4. Dump JSON mode and persist the validated payload and provenance.

This keeps immutable domain types inside `services/backtest.py` and JSON containers at the API and storage boundary. The comparison worker no longer depends on Pydantic accepting `MappingProxyType` as an implementation detail.

### Compatibility error

Add a focused `StrategyCompatibilityError` beside the existing semantic validation type. It carries strategy identity, required timeframe, received timeframe, and field paths. Prefix operations return a new instance with prefixed fields while preserving the compatibility metadata.

FastAPI registers a handler for this subtype before the general semantic handler and returns `422 strategy_incompatible`. Direct service callers receive the typed exception rather than an HTTP type.

### Response metadata

One route helper derives experiment metadata from `ExperimentRecord`:

- status URL from the experiment ID;
- retry delay from whether the state is terminal;
- `Location` for POST responses;
- `Retry-After` for nonterminal POST and GET responses;
- HTTP status `202` for queued or running POST responses, otherwise `200`.

Typed envelope construction uses the same status URL and retry function for every operation. The helper does not store deployment hostnames or infer proxy headers.

### Error classification

The worker will build errors through small private classifier helpers rather than repeating dictionaries in each exception branch. Classification remains in `services/experiments.py`, where lifecycle failures are persisted. Operation adapters may raise `ExperimentOperationError` when they can provide a safer or more specific domain code.

## Documentation

Create `docs/API_REFERENCE.md` and link it from the README and system manual. It will contain:

- Authentication. The key is the exact nonempty opaque value in `BKTSTR_API_KEY`. The API has one service-level key, no scopes, and no built-in expiry. The deployment owner issues it. Rotation replaces the Railway secret and redeploys. Revocation deletes or replaces the secret and redeploys. Clients must not log it.
- Complete requests. Copyable JSON for backtests, sweeps, mixed comparisons, and regime comparisons.
- Strategy rules. The current strategy identity and version, required `1m` timeframe, symbol syntax, parameter discovery through capabilities, defaults, and percentage semantics.
- Async lifecycle. `200` versus `202`, `Location`, `Retry-After`, body fields, polling, terminal states, replay, and client retry rules.
- Error catalog. Public HTTP statuses, stable codes, example bodies, request IDs, and the `X-Request-ID` response header.
- Market data. Accepted query values, 730-day request maximum, pagination, automatic provider selection, provider fallback, and cache rules.
- Comparison. Candidate forms, completion requirements, first-candidate reference behavior, deltas, child experiments, and failure cases.

The provider and rate-limit section will document current code, not plan-dependent marketing claims:

- The application selects Massive when `MASSIVE_API_KEY` exists. Massive aggregate requests use up to 50,000 rows per page and stop after 100 pages.
- Massive retries HTTP `429`, `500`, `502`, `503`, and `504` up to six times after the first request. It honors numeric `Retry-After`; otherwise it uses exponential delays from 2 through 30 seconds.
- Massive historical availability depends on the attached account and provider plan. BKTSTR adds a 730-day per-request maximum but does not promise a provider retention period.
- Without Massive, Yahoo is a development fallback for `1m`, `5m`, and `15m` requests wholly inside the most recent 30 calendar days. Fetches use seven-day chunks. Older ranges, hourly/daily bars, regimes, and sentiment require Massive under the current selection rules.
- BKTSTR has no ingress request-per-minute limit. Deployment capacity and upstream providers still apply limits. Clients must follow `Retry-After`, avoid polling faster than two seconds, and avoid duplicate submissions by using idempotency keys.
- Historical raw bars are cached by provider, symbol, timeframe, and day. Past days, including empty days, remain until storage is removed. The current day is fetched as volatile data and is not persisted as a completed historical day.
- Derived caches store deterministic measurements and context. They do not cache entry decisions, exits, stops, targets, sizing, or simulation results. Source digests and formula versions invalidate derived entries by creating new keys.

## Testing

### Regression tests

Add a test that sends a comparison through the same adapter used by `ExperimentWorker`, runs the worker, and proves the stored experiment completes. Cover completed experiment IDs and named variants. The test must assert JSON persistence of nested candidate provenance and metric deltas so replacing the result with an empty mapping cannot pass.

Add a direct service test for `BacktestInput` timeframe compatibility and API tests for direct and nested requests. Each API test must assert `422 strategy_incompatible`, the exact prefixed field, and absence of a durable experiment.

Add worker tests for an unexpected exception, an HTTP status error, and a result-persistence error. Assert safe diagnostic fields and confirm that secrets and response bodies are absent.

### POST contract tests

Add one end-to-end contract suite for:

- `POST /api/v1/backtests`;
- `POST /api/v1/parameter-sweeps`;
- `POST /api/v1/compare`;
- `POST /api/v1/regime-comparison`.

Each case uses the real FastAPI route, canonical persistence, real worker dispatch, and canonical polling route. Only upstream market-data/backtest execution is replaced with a deterministic local fixture. The suite asserts:

- request schema and authentication;
- `200` or `202` policy;
- `Location`, `Retry-After`, `status_url`, and `retry_after_seconds`;
- operation-specific typed request and result bodies;
- terminal `completed` state after worker execution;
- same-key replay and different-payload conflict;
- request ID presence on errors.

OpenAPI contract tests will inspect every POST operation for its request model, `200` and `202` success models, standard error models, response headers, source enums, and timeframe enums.

## Compatibility and rollout

This is a tightening release. Existing valid `1m` requests keep their payload fields and results. Clients that sent unsupported source or timeframe strings already failed at runtime; they will now receive a schema-level `422` with a precise field. Experiment responses gain fields and headers without removing existing ones.

The known comparison failure has no successful response behavior to preserve. Completed experiment IDs and named variants remain accepted. The worker and stored experiment schema do not need a database migration because richer errors fit the existing JSON column and response metadata is derived at read time.

Deploy the code and documentation together. Production acceptance must submit at least one comparison, poll it to `completed`, and verify the deployed OpenAPI enum and async metadata contracts.

## Files expected to change

- `bktstr/services/backtest.py` for compatibility validation and JSON normalization.
- `bktstr/services/validation.py` for the typed compatibility error.
- `bktstr/services/experiments.py` for safe worker error details.
- `bktstr/api/schemas.py` for enums and experiment metadata.
- `bktstr/api/routes.py` for normalized adapters, response headers, and query enums.
- `bktstr/api/app.py` for the compatibility error handler.
- Service, worker, API, OpenAPI, and new POST contract tests under `tests/`.
- `docs/API_REFERENCE.md`, `README.md`, and `docs/BKTSTR_SYSTEM_MANUAL.md` for public documentation.
- `scripts/production_acceptance.py` for one terminal comparison made from two completed backtests, reusing cached market data from the existing acceptance backtest where possible.

## Acceptance criteria

- Both comparison candidate forms complete without a `mappingproxy` serialization error.
- A `1d` baseline backtest returns `422 strategy_incompatible` and creates no experiment.
- Failed worker records contain a safe reason, exception type, and stage.
- OpenAPI advertises `source=auto`, exact timeframe enums, both POST success statuses, and async headers and fields.
- Every POST response includes a status URL. Nonterminal responses include a two-second retry interval in the body and header.
- Idempotency replay and conflict behavior match this specification on every POST route.
- Every POST route passes an end-to-end contract test through terminal polling.
- The API reference answers every requested authentication, strategy, lifecycle, error, market-data, cache, and comparison question.
- Focused tests, the full test suite, compilation, release checks, and repository hygiene checks pass without adding generated artifacts.
