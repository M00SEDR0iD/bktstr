# Event research and trade idea implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution,
> or superpowers:subagent-driven-development if the user chooses delegated work.
> Implement and verify one task at a time. This document is a plan, not delivered code.

**Goal:** Carry a reusable thesis through event research, a frozen trading policy,
and durable controlled backtests before Jev integration.

**Architecture:** Add a research path above the current numerical registry and
beside the deterministic trading engine. Event studies and configured backtests
share frozen datasets, one SQLite catalog/experiment lifecycle, campaign admission,
history, and reporting. Keep the existing baseline API and engine behavior.

**Tech stack:** Python 3.12, Pydantic/frozen dataclasses, FastAPI, SQLite, pandas,
existing caches and artifact storage. No new service is required.

**Spec:** [Reusable trade ideas and event research](../TRADE_IDEA_CONTAINERS.md).

**Status:** RF-A through RF-K are unstarted. This plan replaces the earlier RF-A
through RF-H recipe-first sequence at the same path. Original Tasks 0-2 are complete.
Original Tasks 3-7 keep their IDs and follow the research foundation milestone.

## Global constraints

- BKTSTR remains independent of fund/account-specific assumptions.
- The first executable scope is equity/ETF minute bars and holding periods of minutes to hours.
- Templates declare roles; applications bind symbols, calendars, units, and data.
- Separate causal predictors from future outcome labels in types and artifacts.
- Persist all eligible events, not only filled trades or profitable observations.
- Freeze research definitions, datasets, analysis choices, and execution assumptions.
- Hypothetical macro scenarios cannot become observed evidence or canonical results.
- Use one existing experiment lifecycle and one local research archive.
- Preserve baseline API and execution version 1.0.0 semantics.
- No automated model search, Jev acquisition, broker orders, or paper runner in this phase.
- First-touch barrier labels are outside this milestone.
- Public capability metadata changes only when an operation is implemented.

## Delivery units and file ownership

| Unit | Tasks | Independently useful outcome |
| --- | --- | --- |
| Idea and event records | A-D | A portable idea creates an inspectable event dataset with causal inputs and separate outcomes |
| Durable controlled studies | E-G | A stored study reports context relationships, uncertainty, and a complete search history |
| Policy and research workflow | H-K | Evidence links to a frozen policy, comparisons, searchable history, and offline replay |

| File or group | Responsibility |
| --- | --- |
| `bktstr/research_ideas.py`, `idea_resolution.py` | Immutable idea/study/policy/modifier/application records and pure resolution |
| `bktstr/research_components.py` | Typed component catalog and event/label contracts; reuses numerical registry |
| `bktstr/dataset_snapshots.py` | Immutable inputs, pinned session schedule, coverage audit, offline provider |
| `bktstr/event_research.py` | Candidate detection, causal feature materialization, separate labels |
| `bktstr/services/research_store.py`, `configured_research.py` | Catalog persistence and durable research operations |
| `bktstr/services/research_protocol.py` | Admission, budgets, splits, exposure, campaign reconciliation |
| `bktstr/services/event_studies.py` | Declared group comparisons, distributions, uncertainty, diagnostics |
| `bktstr/services/idea_reports.py` | Readable idea card and combined evidence/history |
| Existing runtime, engine, registry, API, experiment store | Shared execution, measurements, additive access and worker integration |

All named new files are proposed. Inspect existing seams before each task; do not
duplicate a registry, backtest engine, or queue under these names.

## Review focus

| Failure mode | Required behavior | Owner |
| --- | --- | --- |
| A future return or revised feature leaks into an event filter | Separate label interface; reject unavailable predictors | B, D, H |
| Missing minutes or an early close changes a horizon silently | Pinned schedule and explicit coverage/censor reasons | C-D |
| Different samples, overlapping labels, or searched horizons inflate evidence | Explicit estimand, pairing rules, block uncertainty, full search ledger | F-G |
| A restart or renamed idea resets budgets or final-data exposure | Atomic admission, stable identities, overlap-aware shared ledger | E-F, I |
| A context association is presented as executable profit | Separate study and policy reports, promotion rationale, execution limits | G-H, J |

## RF-A. Define the idea card and immutable revision model

**Files:** Create `bktstr/research_ideas.py`, `tests/test_research_ideas.py`,
and `examples/ideas/vwap-continuation.json`.

**Interfaces:** Strict frozen `IdeaRevision`, `StudySpec`, `PolicyRevision`,
`ModifierRevision`, `VariantRevision`, and `ApplicationSpec` types.
Provide `parse_idea(document) -> IdeaRevision` and equivalent parsers for the other
five types. Canonical JSON and digests are shared, with distinct narrative and
semantic identities. `VariantRevision.kind` is `study` or `policy`.

- [ ] Write tests rejecting unknown fields, mutable nested state, missing disproof
  criteria, duplicate/conflicting revision identity, unpinned ancestry, and policy
  fields in a study modifier.
- [ ] Run `python -m pytest tests/test_research_ideas.py -q`; confirm contract failures.
- [ ] Implement the records, including an idea with no policy and explicit links
  from a policy to study results and a promotion rationale.
- [ ] Add a toy VWAP-reclaim idea. Its event is a same-session close crossing above
  VWAP; research variants alter declared context/labels, policy variants alter
  selection or risk. All outcomes in the example are untested.
- [ ] Verify key-order stability and semantic-versus-wording revisions; commit.

**Acceptance:** One simple card expresses an idea before any trading rule has been
chosen. Stock names, dates, and results remain separate bindings and evidence.

## RF-B. Define reusable event, context, reference, and label components

**Files:** Create `bktstr/research_components.py`,
`tests/test_research_components.py`; extend `bktstr/measurements.py` and
`bktstr/variable_registry.py` only for reusable missing numerical definitions.

**Interfaces:** `ComponentCatalog` resolves exact `ComponentRevision` references.
`resolve_study(spec, catalog) -> ResolvedStudy` produces only registered components.
Predictor inputs are `CausalInputs`; label inputs are `OutcomeInputs`, with no
conversion into a predictor lookup.

- [ ] Test that role, numeric/boolean/ordinal value type, units, and evidence trust
  remain independent. Reject a label in a predictor dependency graph, cycles,
  unknown formulas, and missing availability rules.
- [ ] Run `python -m pytest tests/test_research_components.py -q`; confirm failures.
- [ ] Define versioned event detector, context, reference, and label contracts.
  Include units, inputs, lookback, availability, missing behavior, and profile.
- [ ] Reuse existing VWAP, RSI, volume ratio, and numerical regime measurements.
  Add only the fixture's missing measurements with explicit formulas and timing.
- [ ] Implement initial label definitions for fixed-horizon returns and favorable/
  adverse excursions, with explicit reference price, elapsed session-time horizon,
  boundary behavior, and overlap declaration. Defer first-touch barriers.
- [ ] Run component and existing measurement tests; commit.

**Acceptance:** A label cannot be used by an entry rule; a context value can remain
continuous without first becoming a boolean strategy gate.

## RF-C. Freeze datasets, session schedules, and replay inputs

**Files:** Create `bktstr/dataset_snapshots.py`,
`tests/test_dataset_snapshots.py`; modify `bktstr/runtime.py` and
`bktstr/orchestrator.py` at dependency-injection/provenance boundaries.

**Interfaces:** `freeze_dataset(requests, provider, schedule, artifact_store) -> DatasetSnapshot`;
`snapshot_provider(snapshot_id, artifact_store) -> SnapshotProvider`.
Add optional frozen inputs to `run_configured_strategy(document, *, inputs=None)`.
The supplied session schedule is a versioned, pinned artifact, not inferred from
the bars. Initial schedules may be explicitly supplied and validated.

- [ ] Test changed upstream data, corrupted artifacts, adjustment/unit mismatch,
  duplicates, out-of-order bars, missing minutes, warm-up, holiday/early-close
  schedules, and an offline miss.
- [ ] Run `python -m pytest tests/test_dataset_snapshots.py -q`; confirm failures.
- [ ] Persist raw/derived hashes, source and formula/build identity, adjustment
  convention, requested/actual coverage, and schedule provenance. Use safe JSON/CSV
  for imported data, not untrusted pickle deserialization.
- [ ] Audit expected bars against the supplied schedule. A controlled study blocks
  missing required coverage; exploratory exclusions are explicit and counted.
- [ ] Publish artifacts atomically before marking ready. Replay missing/corrupt
  inputs fails without network fallback.
- [ ] Verify current backtests retain numerical equivalence and baseline session
  semantics; the new research path uses the pinned schedule. Commit.

**Acceptance:** A study or policy can replay its original inputs after provider data
changes. A hash establishes identity, not completeness or source accuracy.

## RF-D. Build event datasets independently of trading positions

**Files:** Create `bktstr/event_research.py`,
`tests/test_event_research.py`, and `tests/fixtures/research/events.json`.

**Interfaces:** `build_events(study, application, snapshot) -> EventDataset`;
`label_events(events, label_specs, outcome_inputs) -> LabelDataset`.
`EventDataset` owns causal rows and coverage diagnostics. `LabelDataset` owns
future outcomes and censor reasons. Both are immutable artifacts joined by event ID.

- [ ] Write fixtures containing several same-session VWAP reclaims, an event while
  a sample policy holds a position, a session boundary, missing price, and a late
  predictor. Assert all detector-eligible events survive regardless of positions.
- [ ] Run `python -m pytest tests/test_event_research.py -q`; confirm failures.
- [ ] Materialize event IDs and per-value availability. Keep missing context rows
  with reasons; apply only the predeclared detector and sampling rule.
- [ ] Generate labels separately. Require the exact scheduled horizon price, censor
  an incomplete horizon, and exclude outcomes crossing a scored split. Do not
  reinterpret 15 minutes as 15 available rows.
- [ ] Add a future-perturbation test: changing bars strictly after a cutoff leaves
  events and predictors through the cutoff identical, while affected labels change.
- [ ] Verify on manually calculated fixture rows, including positive/negative
  excursions and boundary cases. Commit.

**Acceptance:** We can investigate an event distribution before defining a strategy,
and trace every included, missing, or censored observation.

## RF-E. Persist catalog records and durable event-study jobs

**Files:** Create `bktstr/services/research_store.py`,
`bktstr/services/configured_research.py`, `tests/test_configured_research.py`;
extend `bktstr/services/experiments.py` and worker registration.

**Interfaces:** `ResearchCatalog` stores immutable revisions in the existing
`experiments.sqlite3`. `submit_research_run(store, request, idempotency_key)`
returns an `ExperimentRecord`. `ResearchRunRequest` contains operation, resolved
specification, input references, lineage, and analysis configuration. Register
`event_study` now; H adds `configured_backtest` to the same dispatcher.

- [ ] Test conflicting revision writes, input validation, idempotent retries,
  preflight failures, artifact publication interruption, restart, and handle closure.
- [ ] Run `python -m pytest tests/test_configured_research.py -q`; confirm failures.
- [ ] Add catalog/attempt links through additive migrations. Persist exact inputs
  before execution and dispatch D through the existing worker lifecycle.
- [ ] Store causal/label artifacts separately. Attachments and consumed inputs have
  different provenance fields. Persist admitted blocked/failed/empty attempts.
- [ ] Verify store reopening, legacy experiment retrieval, and Windows file release.
  Commit the durable event dataset operation before adding statistical reports.

**Acceptance:** A research event dataset is retrievable after restart without
remembering local filenames. Statistical summaries arrive in G.

## RF-F. Enforce study protocols, search budgets, and data exposure

**Files:** Create `bktstr/services/research_protocol.py`,
`tests/test_research_protocol.py`; extend E's catalog and experiment lifecycle.

**Interfaces:** `register_protocol(document, catalog) -> ResearchProtocol`;
`admit_attempt(protocol_id, variant_ref, application_ref, split, replication_id) -> AttemptRecord`;
`record_inspection(scope, artifact_id, actor, reason) -> InspectionEvent`.
Protocol kinds are `study` and `backtest`; both use the same ledger.

- [ ] Test overlapping splits/label spans, warm-up scored by mistake, changed
  universes, two concurrent reservations for one slot, repeated HTTP keys, renamed
  ideas, and overlapping final-data exposure.
- [ ] Run `python -m pytest tests/test_research_protocol.py -q`; confirm failures.
- [ ] Freeze candidates, universe, splits, metrics, sample minima, analysis choices,
  stopping rules, and candidate/attempt budgets. Count changed horizons, subgroups,
  transforms, thresholds, and combinations as research choices.
- [ ] Reserve budget, create attempt, and assign queue/child identity in one SQLite
  transaction. Retries reconcile the same attempt; amendments retain prior history.
- [ ] Restrict controlled final access until candidate freeze. Log exposure before
  metrics, raw labels, plots, or exports are returned. Shared benchmark/source
  dependencies participate in scope overlap checks.
- [ ] Record external/manual inspection disclosures and distinguish uncontrolled
  legacy work. Do not promise protection against direct owner filesystem access.
- [ ] Run protocol/recovery tests; commit.

**Acceptance:** Exploration is visible, and relabeling a study or inspecting raw
final labels cannot manufacture an untouched test.

## RF-G. Produce interpretable event-study comparisons

**Files:** Create `bktstr/services/event_studies.py`,
`tests/test_event_studies.py`; extend the E event-study operation.

**Interfaces:** `StudyAnalysisSpec` freezes primary label, reference/comparison,
group definitions, development-fitted transforms, uncertainty settings, minima,
and seed. `summarize_study(events, labels, analysis) -> StudyResult` returns
counts, distributions, effect estimates, intervals, coverage, and limitations.

- [ ] Test a known-effect fixture, null fixture, missing groups, small sample,
  correlated same-session events, changed event samples, and different horizons.
- [ ] Run `python -m pytest tests/test_event_studies.py -q`; confirm failures.
- [ ] Report event/session counts, mean/median/quantiles, favorable/adverse excursions,
  missing/censored counts, and predeclared instrument/period stability.
- [ ] Fit quantile groups/scaling on development data only and pin parameters before
  later splits. Label context-group contrasts as associations.
- [ ] Implement deterministic contiguous-session block resampling. Freeze block
  length, resample count, seed, and minimum usable blocks. Resample the full declared
  statistic and aligned dates across stocks, then report uncertainty assumptions.
- [ ] Estimate differences directly using shared resamples. Fixed-event variants
  pair on event IDs; changed detectors disclose common/added/removed samples.
  Incompatible label definitions cannot enter one primary comparison.
- [ ] Attach search counts and exposure status. Unavailable uncertainty remains
  unavailable; no automatic significance-to-promotion decision. Commit.

**Acceptance:** We can see where an event relationship appears, its size and
uncertainty, and how much searching produced it without calling it trading profit.

## RF-H. Link evidence to a frozen policy and the existing engine

**Files:** Create `bktstr/idea_resolution.py`,
`tests/test_idea_resolution.py`; extend `configured_research.py`,
`tests/test_configured_research.py`, and `strategy_config.py` only as needed.

**Interfaces:** `resolve_variant(variant, catalog) -> ResolvedSpecification`
returns a discriminated study or policy specification.
`bind_policy(policy, application, run_window) -> StrategyManifest`
calls the existing `compile_strategy`. E's dispatcher gains `configured_backtest`.

- [ ] Test cycles, conflicting modifiers, missing pinned references, unknown
  capabilities, missing benchmark bindings, future-label rules, and unsupported
  macro/scenario execution before provider access.
- [ ] Run `python -m pytest tests/test_idea_resolution.py tests/test_configured_research.py -q`;
  confirm missing policy-path failures.
- [ ] Resolve one parent and explicit typed changes. Require study evidence links,
  contrary findings, selection rationale, and limits for a promoted policy.
  A manually authored exploratory policy is allowed with an untested status.
- [ ] Map only supported policy fields to today's strict strategy document and
  run through the shared runtime with C inputs. Preserve early entry validation.
- [ ] Persist manifests/results and link signals to event IDs when definitions
  match. Disclose unmatched/unavailable mappings rather than claiming equivalence.
- [ ] Verify next-bar eligibility, unchanged baseline behavior, and two applications
  sharing a policy digest with distinct resolved manifests. Commit.

**Acceptance:** A discovered relationship can inform a tested trading policy.
The study result and simulated trade return remain separate evidence.

## RF-I. Run controlled campaigns with restart reconciliation

**Files:** Extend `research_protocol.py`, `services/backtest.py`,
`services/experiments.py`; create `tests/test_research_campaigns.py`.

**Interface:** `run_protocol(protocol_id, store) -> ProtocolResult` executes the
frozen matrix. Stable child identity includes protocol, variant, application, split,
and declared replication. It consumes E operations and F admission.

- [ ] Test base plus two variants on two symbols, zero events/trades, cancellation,
  partial completion, mismatched inputs, and crashes before/after publication.
- [ ] Run `python -m pytest tests/test_research_campaigns.py -q`; confirm failures.
- [ ] Reuse pinned inputs within comparison cells. Reconcile completed/pending
  children and recover interrupted inline work without duplicate admitted attempts.
- [ ] Report per-symbol effects and predeclared aggregation with dispersion.
  Keep study associations, policy PnL, and cost/risk sensitivities in separate panels.
- [ ] Verify budgets and exposure survive retries and restart; commit.

**Acceptance:** Controlled studies and backtests share a durable campaign mechanism.
Independent stock tests never imply shared-account portfolio returns.

## RF-J. Expose searchable idea history and readable reports

**Files:** Create `bktstr/services/idea_reports.py`, `tests/test_idea_reports.py`,
`tests/test_api_ideas.py`; extend API schemas/routes, `docs/API_REFERENCE.md`,
and `AGENT_BACKTEST_RUNBOOK.md`.

**Interfaces:** `idea_report(idea_id, store) -> IdeaReport`; additive authenticated
routes for ideas, components, study/policy variants, applications, protocols,
event studies, configured backtests, and paginated experiments.
Local and HTTP clients use the same service and exposure checks.

- [ ] Test lineage, pagination/filters, auth/validation, progress/cancellation,
  blocked/scenario labels, and exposure recording on raw-label/report exports.
- [ ] Run `python -m pytest tests/test_idea_reports.py tests/test_api_ideas.py -q`;
  confirm failures.
- [ ] Generate JSON and Markdown idea cards containing thesis, study components,
  categorized changes, evidence, promotion rationale, policies, every attempt,
  comparisons, exposure state, and append-only assessments.
- [ ] Add history filters for idea, kind, variant, instrument, campaign, status,
  and date. Show current metric definitions and execution limits.
- [ ] Update delivered capabilities and OpenAPI only; commit.

**Acceptance:** The owner can find an idea, understand what changed and what failed,
and retrieve either research observations or trading results without stored IDs.

## RF-K. Verify the complete standalone research milestone

**Files:** Create `tests/test_idea_research_workflow.py`; update README, design,
roadmap, project status, and runbook to distinguish delivered and pending features.

- [ ] Demonstrate one VWAP-reclaim thesis, base plus two study variants, two stocks,
  context/label reports, an inconclusive assessment, and a documented policy choice.
- [ ] Run the policy base plus two variants through a controlled frozen-data campaign.
  Interrupt/resume, edit a revision, retrieve all attempts, and replay an older run.
- [ ] Include failures for leakage, invalid pairing, missing/corrupt data, unavailable
  macro consumption, budget races, and reused final data claimed as untouched.
- [ ] Configure an explicit persistent research root. Back up and restore the SQLite
  database together with every referenced data, schedule, evidence, and result artifact.
- [ ] Run focused tests, `python -m pytest tests -q`,
  `python scripts/check_release_consistency.py`,
  `python -m compileall -q bktstr bktstr_cache integration scripts`, and
  `python benchmarks/benchmark_cache.py`. Obtain one independent final review.
- [ ] Record delivered capabilities and known execution/metric limitations; commit.

**Acceptance:** The spec's completion gate works offline without Jev or a broker.
It demonstrates research correctness and reproducibility, not a profitable strategy.

## Dependency order and later work

Execute A -> B -> C -> D -> E -> F -> G -> H -> I -> J -> K.
Each task has a focused verification gate; K verifies integration. Use the existing
project virtual environment. Windows sandbox restrictions on temporary test folders
may require the normal permission mechanism; do not weaken tests to bypass them.

Then resume original Task 3 for recorded Jev context and replay. Tasks 4-5 add shared
macro decisions and execution improvements, using this research catalog and protocol.
Task 6 adds bounded internal paper validation. Task 7 tests Clear Street demo
workflows separately. There is no requirement to use Jev for a numerical study.

Generic history, budgets, exposure, and restart work formerly assigned to Task 5
are delivered here. Later Task 5 adds actual model/decision records and updated
execution metrics to these interfaces, not a second campaign system.

Automatic feature selection, complex ML, a broad dashboard, universal asset execution,
and first-touch barrier inference remain outside this milestone. The first useful
deliverable is an honest, replayable event study for one idea.
