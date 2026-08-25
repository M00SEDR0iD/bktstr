# BKTSTR v0.5 Strategy-Neutral Core Design

**Status:** Approved design

**Date:** 2026-08-24

**Release target:** v0.5.0 — Strategy-neutral core

**Release tracker:** [#4](https://github.com/M00SEDR0iD/bktstr/issues/4)

## Purpose

V0.5 separates data, reusable research variables, strategy-specific filters, strategy definitions, orchestration, and execution behind stable internal contracts. The current bearish-regime scalp becomes the first immutable strategy definition and must retain exactly the same signals, normalized trades, summaries, cache behavior, and execution assumptions.

The design also formalizes BKTSTR's research hierarchy. Tier A and Tier B data are immutable foundations. Tier C and Tier D evidence can qualify, rank, or annotate a strategy, but it cannot rewrite or silently influence higher-trust data. New strategies are composed from saved research variables and explicit rules rather than new arguments added to the simulation engine.

## Decisions

- Implement stable internal contracts and migrate only the frozen baseline in v0.5.
- Keep the existing GET backtest surface as a compatibility adapter. FastAPI and new public schemas remain v0.6 work.
- Represent source data, measurements, and filter outputs as versioned research-variable objects with typed indexed arrays.
- Treat normalized point-in-time source data as Tier A.
- Treat trusted structured data and validated deterministic indicators as Tier B.
- Classify regime, sentiment, fragility, VWAP, RSI, and volume ratio as Tier B.
- Allow Tier C and Tier D only as explicit, strategy-owned evidence filters in v0.5.
- Make tier propagation monotonic: composition can preserve or lower trust, never raise it.
- Save immutable variable snapshots in content-addressed storage using the existing deterministic-cache foundation.
- Define GUI metadata now, but defer database-backed management and GUI rendering to v0.7 and v0.9.
- Fail on missing required evidence by default. Permit explicit degraded research overrides only where a strategy declares them safe enough to inspect.
- Diagnose missing data and suggest a versioned replication baseline, but do not perform backfills in v0.5.

## Goals

- Make the engine consume an immutable `StrategyDefinition` instead of an expanding strategy-specific request object.
- Make research variables simple to create, save, load, inspect, and reuse in future strategies.
- Enforce Tier A and Tier B immutability in code and tests.
- Preserve complete lineage from every result to its source arrays, variable formulas, filters, strategy, execution model, and build.
- Separate reusable measurements from strategy-owned interpretation.
- Keep strategy decisions outside raw and derived caches.
- Preserve causal timing, conservative fills, adverse slippage, stop/target behavior, sizing, and summaries.
- Prove that the new and legacy paths produce equivalent normalized output with caching enabled and disabled.

## Non-goals

- Adding a second strategy family
- Enabling Tier C or Tier D production sources
- Uploading arbitrary data or executable Python
- Automatically applying a suggested backfill
- Database-backed strategy or variable persistence
- FastAPI, OpenAPI, authentication, jobs, or React UI work
- Changing the public compatibility response
- Changing any trading formula or frozen baseline value
- Changing position size from sentiment, fragility, or another research variable
- Building a general-purpose dependency-graph platform beyond the contracts needed by the baseline

## Architectural boundaries

```text
Registered research-variable definitions
        |
        v
Tier A normalized source snapshots
        |
        +---------------------------+
        |                           |
        v                           v
Tier B trusted source data   Tier B deterministic measurements
                                    |
                                    v
                         strategy-owned C/D filters
                                    |
                                    v
                         immutable StrategyDefinition
                                    |
                                    v
                         strategy-neutral orchestrator
                                    |
                                    v
                         unchanged execution model
```

Dependencies point toward immutable data and measurement contracts. HTTP parsing, provider clients, persistence frameworks, and future GUI code do not become execution-engine dependencies.

The principal units are:

| Unit | Responsibility |
| --- | --- |
| Research-variable registry | Resolve immutable definitions by stable ID and version |
| Snapshot store | Save and load immutable indexed arrays by content digest |
| Variable resolver | Validate dependencies, tiers, coverage, and formula versions |
| Measurement plugins | Compute reusable deterministic variables |
| Strategy-filter plugins | Compute strategy-owned evidence without mutating shared variables |
| Strategy registry | Resolve immutable strategy definitions and permitted overrides |
| Orchestrator | Acquire data, resolve variables, evaluate filters/rules, and invoke execution |
| Compatibility adapter | Convert the legacy request into a baseline `StrategyRunRequest` |
| Execution model | Preserve current signals-to-fills simulation and summary behavior |

## Data-tier model

### Tier A — objective baseline

Tier A contains objective, point-in-time raw or normalized source arrays. Examples include subject, sector, and broad-market OHLCV. A Tier A snapshot records the provider, dataset, asset class, adjustment mode, timezone, calendar, session, requested and actual coverage, normalization version, retrieval time, and content digest.

Tier A values are immutable. Corrections or normalization changes create new snapshots and, when semantics change, a new definition version.

### Tier B — trusted clean research data

Tier B contains data safe to use as foundational strategy evidence:

- trusted structured source data with explicit revision and point-in-time rules; and
- deterministic, validated, versioned measurements derived exclusively from Tier A.

The current regime, sentiment, fragility, VWAP, RSI, and volume-ratio outputs are Tier B. Their values and rules never change in place. A formula change creates a new formula version, research-variable version, and content digest while preserving historical versions.

Tier B cannot depend on Tier C or Tier D. Tier C or Tier D processing cannot overwrite, rescale, backfill, reclassify, or otherwise alter Tier A or Tier B arrays.

### Tier C — optional derived evidence

Tier C contains optional higher-order evidence whose inputs or methods introduce additional interpretation or model dependence. In v0.5, Tier C outputs are owned by a strategy and used only through an explicit `gate`, `rank`, or `annotate` rule.

### Tier D — experimental evidence

Tier D contains experimental evidence with the weakest confidence, reconstruction, or point-in-time guarantees. It always requires explicit strategy opt-in, visible warnings, and complete provenance.

### Tier propagation

Tier assignment is monotonic. An output inherits at least the lowest-trust input tier and may be assigned a lower-trust tier because of its method.

```text
Tier A source transformation -> Tier B measurement
Tier B + Tier C             -> Tier C filter output
Any input or method Tier D  -> Tier D filter output
```

No transformation promotes Tier C or Tier D data into Tier A or Tier B. A result cannot hide lower-tier influence behind a higher-tier label.

## Research-variable model

One abstraction represents source arrays, reusable measurements, and strategy-filter outputs. A variable has a definition and one or more immutable calculated snapshots.

### `ResearchVariableDefinition`

The definition contains:

- stable variable ID and semantic version;
- kind: `source`, `measurement`, or `filter`;
- assigned tier and method-tier floor;
- description, value type, frequency, timezone, units, and expected range;
- ordered input variable IDs and exact version requirements;
- source adapter or calculation plugin ID and version;
- formula version;
- point-in-time and revision guarantees;
- missing-data policy and deterministic suggestion policy;
- validation constraints;
- owner: shared registry or a specific strategy;
- GUI metadata.

Definitions are immutable after registration. A changed dependency, formula, schema, tier rule, or missing-data policy requires a new version.

### `ResearchVariableSnapshot`

A snapshot contains:

- a reference to its exact definition;
- an immutable typed indexed value array;
- requested and actual coverage;
- ordered input snapshot digests;
- source and transformation provenance;
- calculation time and build identity;
- warnings and quality observations;
- a deterministic content digest.

The public Python interface exposes a read-only series-like value while retaining metadata:

```python
variables["sentiment.direction"].series
variables["sentiment.fragility"].tier
variables["regime.relative_return20"].provenance
```

Callers do not receive a mutable reference to stored values. Conversion to pandas, NumPy, or a future Arrow representation returns a view that cannot update the snapshot or a defensive copy.

### `VariableSet`

A `VariableSet` is a read-only mapping of resolved variable IDs to snapshots for one run. It validates:

- unique IDs and compatible versions;
- dependency completeness and absence of cycles;
- compatible time axes, frequencies, calendars, and coverage;
- tier propagation;
- schema and formula identity;
- causal availability at every evaluation time.

Rules and plugins address values by stable variable ID rather than by assuming an incidental DataFrame column layout.

## Creating and saving variables

Creating a reusable variable follows a governed sequence:

1. Define its identity, purpose, tier, schema, inputs, and GUI metadata.
2. Declare point-in-time, revision, missing-data, and suggestion policies.
3. Implement the source adapter or deterministic calculation plugin.
4. Validate dependency tiers and method-tier floor.
5. Add fixed fixtures for formula, coverage, causality, and missing values.
6. Register the immutable definition in source control.
7. Materialize content-addressed snapshots from exact input digests.
8. Reuse the stable ID and version from strategy definitions.

Registering Tier B requires either a trusted structured-data contract or exclusively Tier A dependencies, deterministic calculation, point-in-time safety, and explicit validation. Strategy-owned Tier C and Tier D filters use a strategy namespace such as:

```text
strategy.bearish-regime-scalp.filter.context-confirmation
```

A strategy-owned filter is not silently promoted into the shared registry. Reuse requires a separately reviewed shared definition and version.

## Storage model

V0.5 extends the deterministic derived-cache foundation into an immutable variable-snapshot store:

- arrays are content-addressed by definition, formula, inputs, coverage, and values;
- manifests store metadata, provenance, input digests, and GUI fields;
- existing valid snapshots are never overwritten;
- corrupt or incomplete snapshots are rejected and recomputed from immutable inputs when possible;
- strategy decisions, rule thresholds, accepted signals, sizing, and execution results are not stored as research-variable snapshots;
- cache-disabled execution computes the same arrays in memory and must produce identical trading output.

Database indexing and user-managed persistence are deferred. The snapshot and manifest contracts are designed so v0.7 can index them without changing strategy or execution interfaces.

## GUI abstraction metadata

Every variable definition includes future-facing display metadata:

- display name and short label;
- tier badge and tier explanation;
- description and research interpretation;
- units, precision, and expected range;
- confidence and warning semantics;
- source and input-lineage labels;
- formula/version label;
- chart preference and color hints;
- whether the variable is shared or strategy-owned.

V0.5 only validates and serializes this metadata. The later GUI will use it to distinguish Tier A, B, C, and D visually and explain which variables gated, ranked, or annotated a signal.

## Strategy model

### `StrategyDefinition`

An immutable strategy definition contains:

- strategy ID, schema version, strategy version, name, and description;
- instrument roles such as subject, sector benchmark, and market benchmark;
- timeframe, calendar, timezone, and session selection;
- required variable IDs and exact compatible versions;
- typed parameters, defaults, ranges, permitted overrides, and UI metadata;
- entry and context rules;
- strategy-owned filter definitions and their `gate`, `rank`, or `annotate` roles;
- risk and position-sizing settings;
- execution-model ID, version, and assumptions;
- required tier profile and explicit Tier C/D opt-ins.

Edits create a new strategy version. A run resolves all defaults and permitted overrides into an immutable `ResolvedStrategy` before data acquisition.

### Filter behavior

Filters emit immutable typed measurements such as booleans, normalized scores, confidence, and warnings. A filter does not directly mutate a source, measurement, signal, position size, or execution setting.

The strategy explicitly declares how an output is used:

- `gate`: a threshold must pass before a signal is accepted;
- `rank`: a score orders otherwise eligible candidates;
- `annotate`: the value is recorded but does not change eligibility.

Each decision records the filter ID/version, input snapshot digests and tiers, observed value, threshold, role, and outcome.

### `StrategyRunRequest`

A run request references an exact strategy version and supplies:

- instrument-role bindings;
- start, end, and timeframe where overridable;
- permitted parameter overrides;
- an optional explicit degraded-run confirmation token or flag.

HTTP query parameters are not part of this domain contract.

## Baseline migration

The current QQQ to SOXX to subject bearish-regime scalp becomes the first registered strategy. Its mapping is:

- subject, SOXX, and QQQ OHLCV snapshots: Tier A;
- VWAP, RSI14, volume ratio, daily regime, price-implied sentiment, and fragility: Tier B;
- existing entry, regime, risk, time-window, and execution settings: versioned strategy parameters;
- existing next-bar-open execution, adverse slippage, conservative same-bar stop-first behavior, stops, targets, same-day behavior, maximum hold, and summaries: unchanged execution model;
- sentiment multipliers and fragility: informational unless an explicit baseline rule already consumes them;
- Tier C/D variables: none.

The legacy `BacktestRequest` remains temporarily available. A compatibility adapter converts it into a baseline `StrategyRunRequest`, resolves the same parameters, and calls the same orchestrator used by future APIs.

## Orchestration flow

```text
Resolve StrategyDefinition and permitted overrides
        -> validate variable graph and tier policy
        -> acquire and normalize Tier A snapshots
        -> load declared trusted Tier B source snapshots
        -> compute required Tier B measurements
        -> compute isolated strategy-owned C/D filters
        -> evaluate explicit gate/rank/annotate rules
        -> create completed-bar signals
        -> invoke unchanged execution model
        -> return results plus full tier and dependency trace
```

Provider selection and retrieval remain outside the execution model. The orchestrator depends on provider, registry, snapshot-store, and execution interfaces that can be supplied by the application layer.

## Missing data and degraded research overrides

Missing required data fails by default. The structured diagnostic contains:

- missing variable ID, version, and tier;
- required and available coverage;
- affected dependent variables, filters, and strategy rules;
- source or calculation failure;
- whether a degraded research override is allowed;
- the expected effect of omitting the unavailable filter;
- the variable's deterministic replication suggestion.

Each variable definition owns a versioned suggestion policy. Supported policy descriptions include neutral value, last valid observation, historical median, reference series, or `no_safe_suggestion`. The diagnostic includes the suggested method, value or reference, rationale, confidence, and affected range.

V0.5 does not apply or save a backfill. A future disconnected import workflow can use the diagnostic to prepare user-selected data for validation and a second non-ideal-data confirmation.

An explicit forced run may omit an unavailable optional evidence filter only when the strategy declares that filter forceable. The run records the diagnostic and confirmation, marks the filter `not_evaluated`, and marks the result `degraded` and `non_canonical`. It cannot satisfy equivalence, validation, or release evidence.

A missing variable required to calculate the primary entry signal is not forceable because the signal cannot be evaluated. Dependency cycles, illegal tier promotion, schema mismatch, formula-version mismatch, corrupt immutable Tier A/B data, and mutation attempts are also never forceable.

## Errors and observability

Internal errors use stable machine codes in v0.5 even though public error-envelope work belongs to v0.6. Error families include:

- invalid strategy or parameter override;
- unknown or incompatible variable version;
- variable dependency cycle;
- illegal tier dependency or promotion;
- missing coverage;
- causal-availability violation;
- schema, frequency, calendar, or timezone mismatch;
- immutable snapshot corruption;
- non-forceable degraded execution.

Every successful run returns a dependency trace listing source tiers, definition and formula versions, snapshot digests, coverage, cache status, warnings, filter decisions, resolved strategy, execution-model version, and build identity. Provider secrets and raw internal exceptions are never included.

## Testing strategy

Development uses focused tests for each contract. Completed governance tests are not repeatedly run during each step. The complete suite runs once at the final local gate and again in CI.

### Tier and immutability tests

- Tier propagation never improves trust.
- Tier B rejects Tier C/D dependencies.
- Tier A/B definitions and snapshots cannot be mutated.
- Formula or schema changes require new versions and digests.
- C/D filters cannot overwrite or reclassify A/B values.

### Variable-contract tests

- Typed arrays retain deterministic indexes, schemas, and serialization.
- Stable inputs produce stable content digests.
- Snapshot corruption is detected.
- Dependency cycles, missing inputs, and incompatible time axes fail clearly.
- Causal availability and prior-day context behavior remain enforced.
- Suggestion policies produce deterministic diagnostics but never alter values.

### Strategy and filter tests

- Definitions resolve defaults and reject undeclared overrides.
- `gate`, `rank`, and `annotate` remain separate behaviors.
- Filter outputs retain input lineage and inherited tiers.
- Forced runs require explicit permission and confirmation.
- Forced results are degraded, non-canonical, and excluded from acceptance evidence.

### Compatibility and equivalence tests

The same frozen baseline inputs run through both the legacy adapter and the strategy-neutral path. Tests compare:

- completed-bar signals;
- normalized trade arrays byte-for-byte;
- summary dictionaries exactly;
- execution reasons, prices, MFE/MAE, and timestamps;
- cache-enabled and cache-disabled trading output;
- required provenance identities.

The v0.5 release exit criterion is satisfied only when the migrated baseline produces byte-equivalent normalized trades and equal summaries with derived caching enabled and disabled. Live provider variability is not used as equivalence evidence; locked fixtures and the existing production acceptance remain the authoritative gates.

## Delivery sequence

1. Freeze canonical baseline fixtures and normalized-output comparison helpers.
2. Add tier, definition, snapshot, registry, and `VariableSet` contracts.
3. Adapt current intraday, regime, sentiment, and fragility calculations into Tier B measurement definitions.
4. Add immutable snapshot storage over the existing derived-cache foundation.
5. Add strategy, filter, resolved-strategy, and run-request contracts.
6. Register the baseline strategy.
7. Add the strategy-neutral orchestrator and legacy compatibility adapter.
8. Prove legacy/new and cache-on/cache-off equivalence.
9. Publish v0.5 capabilities, documentation, and release evidence without changing trading semantics.

## Acceptance criteria

- Tier A through Tier D semantics and monotonic propagation are executable contracts.
- Regime, sentiment, fragility, and current technical measurements are registered Tier B variables.
- Research variables can be created, saved, loaded, inspected, and reused by stable ID/version.
- Tier A/B artifacts are immutable and isolated from C/D filters.
- Strategy filters emit separate gate/rank/annotate measurements with full lineage.
- The baseline runs through an immutable `StrategyDefinition` and strategy-neutral orchestrator.
- The legacy endpoint remains compatible through an adapter.
- Missing data fails with deterministic replication suggestions and no automatic backfill.
- Explicit forced research runs are visibly degraded and non-canonical.
- Legacy/new paths produce byte-equivalent normalized trades and equal summaries.
- Cache-enabled and cache-disabled runs produce identical trading output.
- No existing trading formula, execution assumption, cache semantic, or frozen baseline value changes.

## Deferred work

- Additional strategy families
- Production Tier C/D sources and filters
- User-selected backfill import and confirmation workflow
- Database indexing and owner-managed variable persistence
- Public FastAPI schemas and structured error envelopes
- GUI creation, editing, tier visualization, and lineage exploration
- Worker execution and durable run records

## References

- [Standalone web-app roadmap](../../roadmap/standalone-web-app.md)
- [v1 release plan](../../roadmap/v1-release-plan.md)
- [BKTSTR system manual](../../BKTSTR_SYSTEM_MANUAL.md)
- [v0.5 release tracker](https://github.com/M00SEDR0iD/bktstr/issues/4)
