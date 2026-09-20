# BKTSTR system design

**Current release:** v0.6.0
**Design direction:** approved 2026-09-20; implementation remains planned.

## Purpose

BKTSTR turns trading theories into versioned experiments with inspectable evidence.
It is an independent entity, separate from the Bailey Fund. No fund portfolio,
holdings, performance metrics, allocations, or mandates define its behavior.

The initial scope is equity/ETF research using minute bars and holding periods of
minutes to hours. Add broader strategies through configuration and registered
components. Options, sub-second execution, live-money trading, and a general
portfolio-management application are outside the next implementation scope.

Success means completing one auditable chain: hypothesis, frozen strategy,
historical comparison, held-out evaluation, bounded forward paper session, and
replay of the same decisions from saved inputs.

## Existing implementation

| Responsibility | Existing source |
| --- | --- |
| HTTP contracts and routes | `bktstr/api/schemas.py`, `bktstr/api/routes.py` |
| Typed service and comparisons | `bktstr/services/backtest.py` |
| Provider selection and run wiring | `bktstr/runtime.py` |
| Governed evidence and execution | `bktstr/orchestrator.py` |
| Strategy definitions | `bktstr/strategies.py` |
| Variable definitions, snapshots, trust | `bktstr/variables.py`, `bktstr/variable_registry.py`, `bktstr/variable_store.py` |
| Numerical measurements | `bktstr/measurements.py`, `bktstr/regime.py`, `bktstr/sentiment.py` |
| Rules and bar simulation | `bktstr/rules.py`, `bktstr/engine.py` |
| Market data and caching | `bktstr/providers.py`, `bktstr/cache.py`, `bktstr_cache/derived.py` |
| Durable experiments and worker | `bktstr/services/experiments.py` |

The current registry contains `bktstr.bearish-regime-scalp@1.0.0` with no registered
strategy filters. Filter contracts already exist; a configurable macro/Jev layer
does not. Current sentiment is price-derived context, not news interpretation.
No current module connects to Jev, a macro release feed, a paper broker, or
Clear Street.

The current API supports `POST /api/v1/backtests`, sweeps, comparisons, and
`GET /api/v1/experiments/{experiment_id}`. Use bearer `Authorization`.
The removed singular endpoint returns `legacy_endpoint_removed`.
See the [API reference](API_REFERENCE.md) for the implemented contract.

## Target architecture

```text
discussion -> hypothesis -> frozen strategy configuration
                                  |
point-in-time sources -> numerical measurements
                      -> optional Jev judgments via OpenRouter
                                  |
                    deterministic filter evaluation
                                  |
                     entry and risk policy
                         /                 \
               historical replay       paper session
                         \                 /
                     immutable evidence and reports
```

Discussion and strategy authoring happen outside the timed execution loop.
The bot runs a frozen assignment. It cannot rewrite its strategy, choose a new
model, expand its universe, raise its limits, or tune thresholds during a run.

Retain Python, FastAPI, SQLite, the existing experiment worker, and persistent
caches. Use a separate process for the continuous paper runner so HTTP latency
and research jobs do not control candle timing. Do not add a distributed queue,
new database, or web application until there is a demonstrated need.

## Strategy configuration

The [local configuration interface](STRATEGY_CONFIGURATION.md) implements the
Task 1 numerical subset. The broader contract below remains the target design;
macro/model filters, comparison enforcement, and paper execution are future tasks.

A versioned strategy document contains:

- Stable strategy ID, semantic version, schema version, and canonical digest.
- Hypothesis, falsification criteria, and allowed evidence tiers.
- Instrument roles and explicit symbols or a versioned point-in-time universe.
- Calendar, timezone, session, candle interval, and decision timing.
- Ordered macro, market, sector, stock, and technical filter definitions.
- Filter role: gate, rank, or annotate; required inputs and missing-data policy.
- Jev question-set version, exact model ID, answer schema, threshold policy,
  freshness limit, refresh schedule, timeout, and request/token budget.
- Deterministic entry, sizing, exit, exposure, daily-loss, and session-end rules.
- Execution-model version, spread, slippage, fee, and short-borrow assumptions.
- Development/validation/final test periods, variant budget, and evaluation criteria.

Publish an immutable resolved manifest before running. Unknown fields, unsupported
indicators, incompatible calendars, missing limits, and invalid units fail before
market or model provider calls. The initial authoring format is strict JSON;
do not execute arbitrary code embedded in strategy documents.

The current baseline remains available with its original semantics. A new
generic minute strategy is a separate registered identity. No mandatory QQQ,
SOXX, semiconductor, bearish, or fund-specific defaults apply to all strategies.

## Evidence and macro timing

Task 2 implements the local source/packet contracts described in
[macro evidence](MACRO_EVIDENCE.md), with a prospective-only BLS CPI adapter.
Historical archive coverage and strategy-filter consumers remain pending.

Store source identity, content digest, units, observation/event time, publication
time, ingestion time, availability time, revision/vintage, and coverage.
Historical joins use the version actually available at the decision cutoff.
A later revised economic value must not replace its first release silently.

Retrospective publication-time simulation and prospective ingestion-time replay
are separate declared modes. Prospective evidence is usable only after receipt.
If historical publication/vintage evidence is unavailable, exclude it from
canonical historical evaluation and use it prospectively.

Derive changes in yields, returns, volatility, and relative strength in code.
Jev receives a compact supplied evidence packet and explicit questions, such as
whether a release represents tightening or easing relative to the supplied
expectation. Missing consensus data must produce unavailable/uncertain evidence,
not an invented surprise.

Macro refresh can occur on a new release or a scheduled observation. It need not
repeat every minute. Every reused judgment must remain within its declared
freshness interval; a completed candle triggers deterministic strategy evaluation.

## Jev boundary, planned

Use OpenRouter's Decisions interface behind a Python adapter. Confirm the live
wire schema during integration; do not assume chat-completions compatibility.
Start with the explicitly versioned `typesafe/jev-1.13` identifier and recheck
availability before implementation. Do not use a moving latest alias or silently
fall back to another model.

The adapter returns typed judgments and provider metadata. Jev does not calculate
indicators, size positions, place orders, change risk limits, or control exits.
Model probabilities describe its answer task; they are not trading win rates.
Constrained answers can still be wrong.

Persist the exact evidence packet, question/schema versions, requested and
resolved model/provider identities when exposed, parameters, raw response,
validated response, timestamps, duration, usage, and error classification.
Record unavailable provider identity fields explicitly rather than inventing them.
Keep secrets and unrelated account data out of these records.

Two modes are required:

- Acquisition: request a judgment, validate and persist it before use.
- Replay: consume a specified immutable response record with no model network call.

An input digest alone does not identify a fresh model outcome. Multiple acquisitions
of identical input get distinct response IDs; each experiment pins one. Saving
responses makes engine replay deterministic, not the remote model itself.

Retries are bounded by deadline and budget. Responses arriving after the decision
deadline may be retained for diagnostics but cannot retroactively cause a trade.
Model unavailability, stale evidence, invalid responses, or exhausted budgets block
new entries that depend on Jev. Protective exits continue without Jev.

## Evidence governance

Tier A is immutable point-in-time source data. Tier B is trusted structured point-in-time data or validated deterministic measurement data. Tier C is
lower-trust model-derived evidence. Tier D is experimental or
difficult-to-reconstruct evidence. Current technical measurements, regime, sentiment, and fragility are Tier B variables.

Definitions and snapshots are immutable variables. Monotonic inheritance means
a derived variable cannot claim a higher trust tier than its inputs. A Jev
judgment has a Tier C floor and inherits Tier D if its inputs require it.
A strategy must explicitly opt into lower-trust evidence.

Missing required evidence fails with a deterministic suggestion and no automatic backfill. Existing optional/forceable filter contracts support an explicitly
confirmed forced run that is degraded and non-canonical. Do not apply a forced
historical omission as an implicit live-entry fallback.

The capability response publishes registered metadata only; it does not promise confirmation requirements or forced-run status. Run-specific information belongs
in run diagnostics, filter decisions and provenance, and the top-level StrategyRunResult degraded/canonical status. Planned Jev filters must extend
these contracts without weakening them.

## Decisions, execution, and paper sessions

Extract a shared pure evaluator for historical and forward use. It consumes an
as-of state, resolved strategy, and simulated account state. It emits a decision
record and bounded order intents. Log no-trade decisions and failed gates as well
as entries, so every filter's effect is measurable.

Preserve the current next-bar-open baseline. A live-data paper fill cannot use
a price that occurred before the signal and model response were available.
The new execution model must declare gaps, spread, adverse slippage, fees,
borrow assumptions, partial-fill policy, and mark-to-market accounting.
OHLCV alone does not establish quote-level or queue-level fill realism.

Each paper session declares its start, end, maximum positions, per-position
notional, gross exposure, daily loss cap, model budget, and stale-data limits.
Simulation capital is user-supplied; it is never read from a fund portfolio.
Deduplicate candles and intents, persist positions and checkpoints, and recover
without duplicate orders after restart.

Stopping disables new entries immediately. Normal session expiry closes simulated
positions under the declared execution policy. If prices are stale, mark positions
unresolved rather than fabricate a fill. Persist failures and reconciliation state.

Clear Street demo is a later, explicit adapter for testing broker workflows.
Its replayed prices, automatic fills, and daily reset make it unsuitable as the
performance ledger for a live-data paper experiment. Internal paper and broker-demo
sessions have different execution identities and must not mix results.
Production broker order endpoints remain outside scope.

## Evaluation

Compare technical-only, numerical-context, and numerical-plus-Jev variants with
identical dates, data, sizing, costs, and exits. Count rejected opportunities,
trades, exposure, net performance, open-position drawdown, and sensitivity to costs.
Separate model classification/calibration evaluation from trading outcome evaluation.

Record all attempted variants and final-data inspections. Use chronological
development, validation, and untouched final periods; purge overlaps caused by
lookback and holding horizons where needed. Never tune on final evaluation data.
A frozen classifier applied to historical text may still know later events from
training. Document that limitation; forward paper sessions provide stronger
evidence about actual decision-time behavior.

Initial acceptance is operational and scientific: reproducible replay, correct
causal timing, complete lineage, no duplicate paper orders, and an honest
comparison. Profitability is an experiment result, not a delivery promise.

## Storage and delivery

Keep source data, numerical derived caches, model-response records, and decision
logs distinct. See [cache architecture](CACHE_ARCHITECTURE.md).
Existing `BKTSTR_DERIVED_CACHE_ENABLED` controls numerical derived caching;
turning it off must not trigger fresh Jev inference during replay.

Expose build `git_commit`, strategy, schema, formula, execution, and model
identities in research artifacts. Planned capabilities remain labelled planned
until tests and authenticated acceptance establish them.
Follow the [implementation plan](IMPLEMENTATION_PLAN.md).

## External contracts

Reviewed on 2026-09-20; verify again when implementing an adapter.

- [TypeSafe System One concepts](https://docs.typesafe.ai/concepts/system-one)
- [OpenRouter Jev model](https://openrouter.ai/typesafe/jev-1.13/)
- [OpenRouter Decisions example](https://openrouter.ai/labs/jev/compile)
- [Clear Street demo](https://docs.clearstreet.io/studio/docs/sandbox)
- [Clear Street authentication](https://docs.clearstreet.io/studio/docs/oauth2)

Vendor pricing, advertised latency, and account entitlements are not fixed
architecture guarantees. Measure the actual integration and record observed limits.
