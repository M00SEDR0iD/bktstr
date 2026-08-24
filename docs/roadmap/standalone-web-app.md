# BKTSTR Standalone Web App Roadmap

**Status:** Approved product and architecture direction  
**Date:** 2026-08-24  
**Target:** Private, single-user research application hosted on Railway  
**Current baseline:** BKTSTR v0.3.5

## Executive summary

BKTSTR will evolve from a synchronous, query-string-driven backtest service into a private research workspace accessible through both a web page and a versioned JSON API. The first release remains a single-user tool, but its boundaries and records will be designed so that authentication, tenant isolation, quotas, and billing can be added later without rewriting the backtest engine.

The main architectural change is not the React interface. It is the separation of strategy definitions, deterministic indicators and context, market-data acquisition, execution simulation, and saved research records behind stable contracts. Most future strategies should be expressible as versioned declarative definitions. New Python code should be required only when a strategy needs a genuinely new indicator, context model, or execution behavior.

Massive remains the primary market-data provider for v1. Provider-specific responses will be normalized before they reach the engine, allowing Alpaca or another provider to be added later for validation or new asset classes.

## Product decisions

- BKTSTR remains a read-only research and simulation tool. It does not place brokerage orders.
- V1 is a private, single-owner application.
- Railway remains the hosting platform.
- Railway Postgres stores saved strategies, immutable strategy versions, runs, results, notes, tags, authentication records, and durable job state.
- FastAPI supplies the application API and serves the compiled React application.
- A separate Railway worker executes backtests outside HTTP request lifetimes.
- The web interface and API use the same validation models and application services.
- Individual runs, reruns, saved history, and side-by-side comparison are in v1.
- Parameter sweeps and automated optimization are deferred until after v1.
- The strategy system uses a hybrid model: declarative definitions for supported primitives and deployed Python plugins for genuinely new behavior.
- Arbitrary Python uploaded through the web interface is not supported.

## Goals

1. Make BKTSTR usable from any browser without manually constructing a long URL.
2. Provide a stable API for scripts and AI research clients.
3. Preserve strategies, parameters, provenance, results, and notes as durable research records.
4. Add new strategies without repeatedly changing the simulation engine.
5. Preserve the existing causal and conservative execution guarantees.
6. Make every historical result traceable to strategy, engine, formula, data, and build versions.
7. Keep the v1 operating model simple while establishing clean seams for a future multi-user service.

## Non-goals for v1

- Brokerage connectivity or live order placement
- Public registration or multiple user accounts
- Billing, subscriptions, organizations, or tenant administration
- Automated parameter sweeps or strategy optimization
- User-uploaded executable code
- Historical options simulation
- Portfolio-level multi-strategy capital allocation
- A microservice architecture
- Replacing Massive solely for architectural novelty

## Current-state assessment

The existing repository already has a useful domain core:

- causal next-bar-open execution;
- adverse slippage and conservative same-bar stop/target handling;
- Massive and recent-Yahoo provider adapters;
- raw daily OHLCV caching and deterministic derived caching;
- daily regime and price-implied sentiment layers;
- build, formula, and cache version identity;
- Railway deployment and production acceptance coverage.

The current product surface has several limitations:

- `/` returns the JSON health payload rather than a web page.
- `/api/v1/backtest` performs a complete run synchronously inside one GET request.
- Strategy configuration is spread across many query parameters.
- Runs and research notes are not saved.
- The standard-library HTTP server has no generated OpenAPI contract.
- There is no authentication, job lifecycle, cancellation, or persistent failure history.
- The engine orchestration accepts strategy-specific fields directly, which will become difficult to extend across unrelated strategies.
- CORS allows every origin.

### Immediate documentation defect

The published locked example uses `same_day=true` and `eod_exit=true`. The current server accepts `same_day_only` and does not implement `eod_exit`; unknown parameters are silently ignored. This must be corrected before the compatibility endpoint is promoted as an authoritative example.

## Target architecture

```text
Browser / API client
        |
        v
Railway web service
FastAPI + compiled React application
        |
        +--------------------+
        |                    |
        v                    v
Railway Postgres      Railway worker service
records + job state          |
                             v
                    strategy-neutral engine
                             |
                             v
                  normalized market-data API
                             |
                             v
                 Massive + persistent cache
```

The web and worker deployments use the same repository and Docker image with different start commands. The application remains a modular monolith: boundaries are enforced in code and tests, not through independently versioned network services.

### Internal modules

| Module | Responsibility |
| --- | --- |
| Web/API | Authentication, HTTP schemas, generated OpenAPI, static React delivery, and compatibility routes |
| Application | Use cases for strategies, versions, runs, comparison, cancellation, and notes |
| Research records | Database models and repositories for saved state |
| Jobs | Durable enqueue, claim, heartbeat, retry, cancellation, and completion behavior |
| Strategies | Declarative schemas, registry, parameter validation, and plugin resolution |
| Indicators/context | Deterministic feature and context calculations |
| Market data | Provider adapters, normalization, provenance, and raw cache interaction |
| Execution | Signals, fills, stops, targets, time exits, slippage, and trade summaries |
| Operations | Build identity, health, metrics, logging, migrations, and production acceptance |

Dependencies point inward toward the strategy and execution domain. Provider clients, HTTP frameworks, React, and database libraries do not become engine dependencies.

## Strategy model

The engine will consume an immutable, versioned `StrategyDefinition` rather than an expanding set of strategy-specific function arguments.

A definition includes:

- name, description, schema version, and strategy version;
- instruments and their roles, such as subject, sector benchmark, and market benchmark;
- timeframe, calendar, timezone, and session selection;
- required indicators and context features;
- entry and exit rules;
- risk and position-sizing settings;
- execution-model selection and assumptions;
- typed parameters with defaults, allowed ranges, and UI metadata;
- plugin identifiers and versions required to execute the definition.

Edits create a new strategy version. Existing versions and completed runs are immutable.

### Plugin boundaries

- `MarketDataProvider` retrieves normalized data plus source provenance.
- `IndicatorPlugin` computes deterministic technical features.
- `ContextPlugin` computes slower regime, sentiment, or other contextual features.
- `ExecutionModel` converts completed-bar signals into simulated fills and trades.
- `StrategyPlugin` supplies behavior that cannot be represented by the declarative rule schema.

Plugins are registered in source control and deployed through the normal release workflow. The web app exposes only registered capabilities.

### Baseline migration

The current QQQ to SOXX to subject bearish-regime scalp becomes a named baseline strategy. Migration is accepted only when its locked data produces exactly the same signals, fills, trade records, and summary values as v0.3.5.

## Market-data decision

### V1 provider policy

- Massive is the primary equity and ETF provider.
- Massive REST aggregates serve normal per-symbol research.
- Existing raw and derived caches remain part of the design.
- Yahoo remains a clearly labeled, recent-data development fallback and is not an equivalent production source.
- Alpaca is the first planned independent adapter for cross-provider validation and possible future brokerage-adjacent work.
- Composer is not a core dependency or primary data source.

Composer provides hosted strategies, portfolio management, backtests, trading, and selected market-data endpoints. Adopting it as the core would replace or constrain BKTSTR's research semantics rather than merely improve data acquisition.

Massive currently offers full-market US equity aggregates, adjusted and unadjusted REST bars, corporate-action data, and bulk flat files. Its current individual Stocks Starter plan provides five years of history and unlimited calls; Developer provides ten years plus trades. Verify pricing and licensing again before each subscription or before offering BKTSTR to other users.

Sources reviewed on 2026-08-24:

- [Massive stock pricing](https://massive.com/pricing?product=stocks)
- [Massive aggregate-bar API](https://massive.com/docs/rest/stocks/aggregates/custom-bars)
- [Massive stock flat files](https://massive.com/docs/flat-files/stocks/overview)
- [Composer API](https://api.composer.trade/docs/index.html)
- [Alpaca market-data plans](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [Tiingo pricing](https://www.tiingo.com/about/pricing)
- [Twelve Data pricing](https://twelvedata.com/pricing)
- [Databento pricing](https://databento.com/pricing)

### Canonical bar contract

Provider data is normalized before it reaches indicators or strategies. A dataset carries:

```text
timestamp, open, high, low, close, volume
provider, provider_dataset, asset_class
adjustment_mode, timezone, calendar, session
requested_coverage, actual_coverage, retrieved_at
source_digest, normalization_version
```

Missing intervals remain missing unless an explicit, versioned normalization policy fills them. Adjustment mode and session filtering must never be inferred silently.

### Bulk-data path

Massive flat files are deferred until universe-wide scans or large batch workloads make per-symbol REST retrieval inefficient. Flat-file aggregates are unadjusted, so this path requires an explicit, tested corporate-action normalization stage before results can be compared with adjusted REST data.

### Cache policy

Cache immutable source data and deterministic measurements. Do not cache strategy decisions, threshold outcomes, entries, exits, or position sizing. Every cache key includes input digests and the exact formula, normalization, and plugin versions.

## Persistence model

V1 uses a single seeded workspace and owner account. Domain records carry `workspace_id` so that a later service conversion does not require adding ownership to every table, but v1 does not implement tenant administration or row-level tenant policies.

Core records:

- `workspaces`
- `users`
- `sessions`
- `api_tokens`
- `strategies`
- `strategy_versions`
- `backtest_runs`
- `run_trades`
- `run_notes`
- `run_tags`
- `job_attempts`

Each run stores an immutable snapshot of:

- strategy definition and resolved parameter values;
- symbols, benchmarks, dates, timeframe, and session;
- provider and dataset provenance;
- engine, formula, plugin, schema, and build versions;
- execution assumptions;
- status, attempts, timing, warnings, and structured failure details;
- summary metrics and trade-level results.

Trade rows can remain in Postgres for v1. If larger strategy families make results materially bigger, a later storage policy can move detailed artifacts to object storage while keeping searchable summaries and content digests in Postgres.

## Durable job lifecycle

Creating a run persists both the immutable run request and a queued job in one transaction. The worker claims work using Postgres locking, records its attempt, and emits heartbeats.

```text
queued -> running -> succeeded
                  -> failed
queued/running -> canceled
```

Rules:

- Only one worker may claim a run attempt.
- Repeated create requests with the same idempotency key return the original run.
- Validation and unsupported-strategy errors are not retried.
- Provider throttling, temporary network failures, and worker interruption may be retried with bounded backoff.
- Cancellation is cooperative and is checked between data retrieval, feature construction, and simulation stages.
- A stale heartbeat makes a running attempt recoverable without creating a duplicate completed result.
- Final result persistence and job completion occur atomically.

V1 uses browser polling for status updates. WebSockets or server-sent events are deferred until polling becomes an observed problem.

## API design

The primary API uses JSON bodies and generated OpenAPI documentation.

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/strategies
POST   /api/v1/strategies
GET    /api/v1/strategies/{id}
POST   /api/v1/strategies/{id}/versions
POST   /api/v1/runs
GET    /api/v1/runs
GET    /api/v1/runs/{id}
POST   /api/v1/runs/{id}/cancel
GET    /api/v1/capabilities
GET    /api/v1/health
GET    /health
```

`POST /api/v1/runs` returns `202 Accepted`, a run ID, current state, and status URL. Requests accept an idempotency key.

`GET /health` remains an unauthenticated, lightweight Railway liveness and build-identity probe. `GET /api/v1/health` provides the authenticated owner with detailed database, worker, provider, cache-storage, and migration readiness.

Errors use a stable envelope containing a machine code, user-safe message, field-level validation details when applicable, retryability, and a correlation ID. Provider secrets and raw internal exceptions are never returned.

The legacy GET `/api/v1/backtest` remains temporarily available through a compatibility adapter. It uses the same application service and validation models as the new API, emits deprecation metadata, and receives corrected documentation. Removal requires a separately announced compatibility release.

## Web application

The compiled React application is served by FastAPI from the same origin.

### Dashboard

Shows active jobs, recent completed runs, recent failures, saved strategies, and build/provider health.

### Strategies

Supports creating, cloning, editing, reviewing, and versioning declarative strategy definitions. Controls are generated from registered parameter metadata. The raw validated JSON definition remains viewable for transparency.

### New run

Selects a strategy version, instruments, dates, and allowed overrides. The interface displays resolved defaults and execution assumptions before submission.

### Run detail

Displays summary metrics, equity curve, trade table, exit-reason distribution, MFE/MAE diagnostics, sentiment/regime context where present, cache information, warnings, and full provenance.

### Compare

Compares selected completed runs using aligned metrics and explicitly highlights changed inputs, strategy versions, providers, formulas, and execution assumptions. Comparisons never imply validity from win rate alone.

### Settings

Displays provider configuration status, API-token management, cache state, application build identity, and database/worker health. Secret values are never rendered after storage.

## Authentication and security

- One owner account is provisioned through a Railway deployment command or migration-safe bootstrap process.
- Browser authentication uses a strong password hash and secure, HTTP-only, same-site cookies.
- State-changing browser requests receive CSRF protection.
- API access uses hashed, revocable bearer tokens shown only at creation.
- Massive and other provider credentials remain Railway secrets and are never sent to the React client.
- CORS is same-origin by default; explicitly configured API clients are allow-listed only when needed.
- Login and API-token failures are rate-limited and logged without secrets.
- Database backups and restoration are verified before production cutover.

## Documentation cleanup

The repository contains valuable content but currently mixes product documentation, a research white paper, release snapshots, recovery notes, and agent instructions. The cleanup should preserve useful history while giving each audience an obvious starting point.

### Immediate changes

1. Correct the invalid `same_day` and `eod_exit` examples.
2. Create `docs/index.md` as the documentation entry point.
3. Convert the README into a concise product landing page and quick start.
4. Add `CHANGELOG.md` for durable release summaries.
5. Move v0.3.4/v0.3.5 status and merge material into `docs/archive/releases/`.
6. Remove `README_PATCH.md` after preserving its relevant cache-history note in the changelog/archive.
7. Stop tracking `PACKAGE_MANIFEST.txt`; generate manifests as release artifacts.
8. Replace the nested 554-line `bktstr/AGENT_DEVELOPMENT_STANDARD.md` with concise root `AGENTS.md` instructions and normal contributor/release documentation.
9. Split `docs/BKTSTR_SYSTEM_MANUAL.md` by audience and responsibility.
10. Move Supabase bridge material under operations/recovery and label it as a fallback.
11. Replace overlapping hand-written machine contracts with generated OpenAPI and versioned strategy schemas.
12. Replace phrase-presence documentation tests with executable example, internal-link, schema, and version-consistency checks.

### Target documentation structure

```text
README.md
CHANGELOG.md
AGENTS.md
docs/
  index.md
  roadmap/
    standalone-web-app.md
  architecture/
    overview.md
    engine.md
    strategy-system.md
    market-data.md
    persistence-and-jobs.md
  user-guide/
    getting-started.md
    strategies.md
    running-and-comparing.md
  api/
    examples.md
    compatibility.md
  research/
    methodology.md
    validated-baselines.md
  operations/
    railway.md
    cache.md
    production-acceptance.md
    recovery/
      github-through-supabase.md
  development/
    contributing.md
    releases.md
  archive/
    releases/
      v0.3.4.md
      v0.3.5.md
```

## Delivery roadmap

Each milestone must leave a deployable, testable system. Architecture or infrastructure releases must not silently change trading formulas.

This document sets product direction and milestone boundaries; it is not a single implementation plan. Before work begins, each milestone receives its own scoped design and implementation plan with exact files, migrations, interfaces, tests, deployment steps, and rollback criteria. A milestone may be split further if its design review exposes independently releasable subsystems.

### Milestone 0: Baseline and documentation repair

**Outcome:** The current system has trustworthy documentation and a locked behavioral baseline.

- Correct current API examples and percentage/parameter semantics.
- Add a documentation index and roadmap.
- Archive release-only root documents and introduce a changelog.
- Add executable tests for every published API example.
- Capture the frozen baseline as versioned characterization fixtures.
- Record current engine, formula, provider, adjustment, cache, and build versions with the fixtures.

**Exit criteria:** Current tests and production acceptance pass; published examples are executed by CI; baseline fixtures reproduce v0.3.5 exactly.

### Milestone 1: Strategy-neutral core

**Outcome:** Existing behavior runs through stable domain contracts.

- Define the versioned strategy schema and parameter metadata.
- Introduce provider, indicator, context, execution, and strategy interfaces.
- Add the canonical market-data and provenance contract.
- Move orchestration out of HTTP-specific request models.
- Register the current regime/sentiment scalp as the baseline strategy.
- Preserve raw and deterministic derived-cache behavior.

**Exit criteria:** The migrated baseline produces byte-equivalent normalized trade records and equal summaries with cache both enabled and disabled.

### Milestone 2: FastAPI application foundation

**Outcome:** A typed, documented API replaces the hand-written HTTP layer without breaking current clients.

- Add FastAPI request, response, capability, and error schemas.
- Serve generated OpenAPI documentation.
- Implement the new health and capability endpoints.
- Route the legacy GET endpoint through the same application service.
- Correct CORS defaults and add correlation IDs and structured logs.

**Exit criteria:** API contract tests, legacy compatibility tests, and production baseline acceptance pass through FastAPI.

### Milestone 3: Persistence and single-owner authentication

**Outcome:** Strategies and research records survive deployments and are private.

- Provision Railway Postgres and migrations.
- Add the seeded workspace and owner-account bootstrap.
- Add secure browser sessions and revocable API tokens.
- Persist strategies, immutable versions, runs, trades, notes, and tags.
- Add backup and restore procedures.

**Exit criteria:** Authentication security tests pass; migrations work from an empty database and the previous migration; immutable versions cannot be modified; backup restoration is demonstrated in a non-production environment.

### Milestone 4: Durable execution jobs

**Outcome:** Backtests no longer depend on an open HTTP connection.

- Add transactional enqueue and idempotency.
- Add the Railway worker process and Postgres claim loop.
- Add attempts, heartbeat, progress stages, cancellation, and bounded retry behavior.
- Persist structured failures and correlation IDs.
- Add stale-worker recovery and deploy-interruption tests.

**Exit criteria:** A submitted run survives a web restart; worker interruption does not duplicate a result; cancellation and retry behavior match the documented state machine.

### Milestone 5: React research workspace

**Outcome:** The complete v1 workflow is usable from a browser.

- Build login, navigation, dashboard, and settings surfaces.
- Build strategy listing, cloning, editing, validation, and version review.
- Build run submission with resolved defaults and assumptions.
- Build run status, detail, provenance, diagnostics, notes, and tags.
- Build side-by-side run comparison.
- Provide accessible loading, empty, validation, failure, and recovery states.

**Exit criteria:** Browser end-to-end tests cover login, strategy versioning, run submission, completion, failure display, rerun, note/tag persistence, comparison, and logout.

### Milestone 6: Railway production cutover

**Outcome:** The private web application becomes the normal BKTSTR interface.

- Deploy web and worker services from the same tested image.
- Attach Postgres and persistent cache storage.
- Bootstrap the owner and migrate the baseline strategy.
- Configure secrets, health checks, logs, and alerts.
- Verify database backup/restore and worker recovery.
- Run the frozen production acceptance suite through the new job API.
- Mark the legacy GET endpoint deprecated while retaining it for the compatibility window.

**Exit criteria:** The browser and API are accessible only to the owner; production identity matches the deployed commit; the frozen baseline passes; a saved run remains available after web and worker redeployments.

## Verification strategy

- Characterization tests protect the current locked trading output.
- Unit tests cover every domain contract and plugin.
- Provider contract tests run against recorded normalized fixtures, with optional live smoke tests separated from deterministic CI.
- Cache-on and cache-off executions must have equal trading output.
- Schema tests verify strategy-version migration and generated OpenAPI.
- Database tests verify migrations, ownership, immutability, and transactional job/result behavior.
- Worker tests cover duplicate claims, stale heartbeats, retries, cancellation, deploy interruption, and idempotency.
- React component tests cover state rendering and validation.
- Browser tests cover complete owner workflows against a real test database and worker.
- Security tests cover password hashing, session flags, CSRF, token hashing/revocation, authorization, secret redaction, and rate limits.
- Documentation tests execute published requests, validate internal links, and compare documented versions with runtime schemas.
- Railway acceptance verifies build identity, baseline results, persistent saved state, and cache reuse.

## Operational requirements

- Web and worker processes expose separate health signals.
- Logs are structured and include correlation ID, run ID, attempt ID, build identity, duration, and safe error code.
- Health endpoints distinguish liveness from database, worker, provider, and storage readiness.
- Migrations run as an explicit release step rather than concurrently in every web/worker replica.
- A failed migration prevents cutover.
- Production acceptance runs after deploy and before tagging a release.
- Trading-formula changes use their own releases and validation evidence rather than being hidden inside web or infrastructure work.

## Path from private tool to service

V1 deliberately prepares, but does not implement, the following service concerns:

- `workspace_id` ownership on domain records;
- stable API authentication independent of browser sessions;
- immutable strategy and run provenance;
- idempotent asynchronous jobs;
- explicit provider licensing/provenance;
- isolated application/domain boundaries;
- deployable web and worker scaling;
- structured errors, metrics, and audit-friendly logs.

Converting to a service later will still require tenant authorization, quotas, billing, abuse controls, data-licensing review, retention policies, support tooling, and operational capacity planning. These concerns must be added around the stable engine rather than folded into it.

## Post-v1 sequence

1. Add parameter sweeps as grouped child runs with explicit search-space provenance.
2. Add Alpaca as an independent normalized provider and compare adjusted daily/minute fixtures.
3. Add additional declarative strategy families using existing primitives.
4. Add new indicator/context plugins without changing execution semantics.
5. Add options data and a separate options-aware execution model only after quote, spread, contract-selection, expiry, and corporate-action semantics are specified.
6. Add portfolio and multi-strategy analytics.
7. Evaluate multi-user service requirements and market-data licensing before enabling additional accounts.

## Success criteria for v1

V1 is complete when the owner can sign in through the Railway URL, create or clone a versioned strategy, submit a run, leave the page, return to see its status and results, add notes/tags, rerun it, compare it with another run, and reproduce the result through an API token. The same frozen baseline must still produce the established v0.3.5 trading output, and each result must identify the exact strategy, data, engine, formula, plugin, and deployed-build versions that produced it.
