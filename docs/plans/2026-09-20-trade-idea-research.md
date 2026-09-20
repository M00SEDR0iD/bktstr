# Trade idea containers and controlled research implementation plan

> For agentic workers: use superpowers:executing-plans for inline execution,
> or superpowers:subagent-driven-development if the user chooses delegated work.
> Implement and verify one task at a time. This is a proposed plan, not completed code.

**Goal:** Turn reusable trade theses and categorized variants into durable,
repeatable, controlled experiments before Jev integration.

**Architecture:** Add typed idea/modifier/application/protocol contracts above
the current strategy compiler. Extend the existing experiment database and worker
with durable configured runs, pinned data, campaign admission, and history/report
operations. Keep the existing simulation and baseline API behavior.

**Tech stack:** Python 3.12, Pydantic/frozen dataclasses, FastAPI, SQLite, pandas,
existing caches and artifact publication. No new service or dependency is required.

**Spec:** [Reusable trade ideas and controlled research](../TRADE_IDEA_CONTAINERS.md).

## Global constraints

- BKTSTR remains independent of fund/account-specific assumptions.
- Templates contain roles and requirements; applications supply explicit symbols.
- The initial executable scope remains equity/ETF minute bars.
- Unsupported rules, macro evaluators, and asset profiles fail before acquisition.
- Prose is documentation; only registered typed components execute.
- Every effective configuration and every artifact reference is frozen before use.
- One existing runtime, one experiment lifecycle, one local research archive.
- Protect baseline semantics; new APIs are additive and capabilities reflect delivery.
- Preserve all admitted attempts and final-data exposures. No deletion resets evidence.
- Existing execution economics remain version 1.0.0; this work does not improve fills.
- No Jev acquisition, live trading, or automatic paper execution in this phase.

## Review focus

| Failure mode | Required behavior | Owner |
| --- | --- | --- |
| A changed parent or modifier alters an old result | Resolve pinned revisions; reject identity/content conflicts | A-B |
| Rebinding a stock silently supplies unsuitable data or units | Validate role requirements and profile before acquisition | B-C |
| A worker dies between budget admission and child creation | Atomic reservation and stable logical identity; reconcile existing child | D-E |
| A new campaign hides final-data reuse or variant attempts | Cross-campaign exposure and lineage-aware budget history | E-F |
| A macro assumption or attached packet appears consumed when it was not | Block unsupported variants; distinguish scenario, reference, and consumed evidence | B, D, G |

## Current seams to reuse

- `bktstr/strategy_config.py`: `compile_strategy` already returns a frozen manifest.
- `bktstr/runtime.py`: `run_configured_strategy` already shares the orchestrator,
  but does not persist an experiment or accept pinned offline data directly.
- `bktstr/services/experiments.py`: SQLite records, artifacts, submission, and worker
  leases exist. Extend their lifecycle rather than saving ad hoc result files.
- `bktstr/services/backtest.py`: typed result projection, sweeps, and comparisons
  exist; public request validation currently targets the baseline registry.
- `bktstr/macro.py` / `evidence_packets.py`: frozen source and packet contracts exist;
  they do not currently power trading gates.
- `bktstr/api/routes.py`: authenticated submission and retrieval by experiment ID
  exist; catalog/history/protocol operations are new.

## A. Define the idea card and revision contracts

**Files:** Create `bktstr/research_ideas.py`, `tests/test_research_ideas.py`, and
`examples/ideas/vwap-continuation.json`. Add authoring guidance to
`docs/TRADE_IDEA_CONTAINERS.md` as features become implemented.

**Interfaces:** `parse_idea(document) -> IdeaRevision`;
`parse_modifier(document) -> ModifierRevision`;
`parse_variant(document) -> VariantRevision`;
`parse_application(document) -> ApplicationSpec`.
Types are frozen and contain canonical digests. `VariantRevision` pins its idea,
parent, and ordered modifier IDs/versions/digests. Categories are organization only.

- [ ] Write tests for unknown fields, missing falsification, duplicate/conflicting
  revision identity, mutable nested inputs, invalid units, unresolved references,
  and secret/account fields outside the schema.
- [ ] Run `python -m pytest tests/test_research_ideas.py -q`; observe missing-contract failures.
- [ ] Implement strict records and deterministic canonicalization. Separate semantic
  recipe digests from descriptive revision digests, so a wording edit is visible
  without pretending a new numerical strategy was tested.
- [ ] Include a readable toy idea with base, entry confirmation, benchmark, risk,
  and unavailable macro variations; no universal return or portability claim.
- [ ] Verify key-order stability, nested immutability, and fresh revision identities.
- [ ] Run focused tests and commit the contracts/example together.

**Acceptance:** One human-readable card can describe a portable thesis and its
named variations without embedding actual run dates or instruments in the recipe.

## B. Resolve variants and bind applications to the existing compiler

**Files:** Create `bktstr/idea_resolution.py`, `tests/test_idea_resolution.py`.
Modify `bktstr/strategy_config.py` only if an additive adapter needs a public helper.

**Interfaces:** Consumes A records and an immutable `RevisionCatalog` lookup;
`resolve_variant(variant, catalog) -> ResolvedRecipe`;
`bind_recipe(recipe, application, run_window) -> StrategyManifest`.
`ResolvedRecipe` contains the full effective settings, requirements, ordered
modifier provenance, and differences against parent/baseline.

- [ ] Test cycles, missing pinned revisions, incompatible modifier combinations,
  field-assignment conflicts, unknown capabilities, missing benchmark bindings,
  and attempts to execute scenario/unavailable macro declarations.
- [ ] Run `python -m pytest tests/test_idea_resolution.py -q`; observe resolver failures.
- [ ] Implement bounded parent resolution with explicit modifier composition and
  role binding. No implicit sector benchmark, ticker-derived default, or arbitrary code.
- [ ] Convert supported resolved recipes into today's strict strategy document,
  then call `compile_strategy`. Preserve existing parameter validation order.
- [ ] Test the same recipe on two bindings: same recipe digest, different resolved
  manifest/application identities; changed rules create a different recipe digest.
- [ ] Run resolver/config/direct-runtime tests and commit.

**Acceptance:** An instrument change is a new application of a fixed recipe;
changing a trading rule creates a traceable variant. Unsupported intent is explicit.

## C. Freeze datasets and provide an offline replay input

**Files:** Create `bktstr/dataset_snapshots.py`, `tests/test_dataset_snapshots.py`.
Modify `bktstr/runtime.py` and `bktstr/orchestrator.py` only at dependency injection
and input provenance boundaries; reuse bar/cache serialization where appropriate.

**Interfaces:** `freeze_dataset(requests, provider, artifact_store) -> DatasetSnapshot`;
`snapshot_provider(snapshot_id, artifact_store) -> SnapshotProvider`;
`run_configured_strategy(document, *, inputs=None) -> StrategyRunResult`, where
optional `inputs` pins provider/snapshot and formula/cache identities.

- [ ] Test exact replay after upstream values change, missing/corrupt files,
  wrong instrument/timeframe/adjustment scope, warm-up needs, and offline misses.
- [ ] Run `python -m pytest tests/test_dataset_snapshots.py -q`; observe missing replay support.
- [ ] Store immutable raw/derived artifact references with content hashes, source,
  adjustment convention, timestamps, and requested/actual coverage. Persist safe
  canonical JSON/CSV for imported data; do not deserialize untrusted pickle files.
- [ ] Publish artifacts atomically, then mark a dataset ready. Missing ready inputs
  fail replay; only an explicit new acquisition creates a new dataset identity.
- [ ] Inject the snapshot provider into the same runtime. Pin derived artifacts or
  verify formula/build identities before recomputation; no network fallback.
- [ ] Verify numerical baseline equivalence with caches on/off and commit.

**Acceptance:** Replaying a run cannot silently use today's corrected provider data.
This supplies reproducibility, not a claim of complete market-data quality.

## D. Add durable configured experiments and catalog persistence

**Files:** Create `bktstr/services/research_store.py`,
`bktstr/services/configured_research.py`, `tests/test_configured_research.py`.
Modify `bktstr/services/experiments.py`, `bktstr/services/backtest.py`, and worker
operation registration in `bktstr/api/routes.py`.

**Interfaces:** `ResearchCatalog` stores immutable A/B revisions in the existing
`experiments.sqlite3` with additive migrations;
`submit_configured_run(store, manifest, input_refs, lineage, idempotency_key) -> ExperimentRecord`;
registered operation `configured_backtest` consumes a frozen request.

- [ ] Test conflicting writes to one ID/version, API/local submission parity,
  missing referenced evidence, malformed manifests, idempotent retries, and
  provenance that distinguishes attached from consumed evidence.
- [ ] Run `python -m pytest tests/test_configured_research.py -q`; observe absent durable path.
- [ ] Add idea/modifier/variant/application and lineage records without altering
  existing experiment rows or public baseline requests. Use one database for later
  transactional admission; do not split budget and queue writes across databases.
- [ ] Persist the resolved manifest and input references before scheduling. Invoke
  the shared runtime with C inputs; project results without routing through legacy
  request adapters. All configured runs produce durable artifacts and status.
- [ ] Persist blocked/preflight failures as inspectable attempts where an idea or
  campaign was admitted; malformed unauthenticated input still fails at the API boundary.
- [ ] Test restart, missing artifacts, Windows handle closure, and baseline compatibility;
  commit the working durable path.

**Acceptance:** A local recipe run is as retrievable and inspectable as a baseline API run.

## E. Enforce research campaigns, budgets, and data exposure

**Files:** Create `bktstr/services/research_protocol.py`,
`tests/test_research_protocol.py`. Extend `research_store.py` and the existing
experiment lifecycle in `experiments.py`.

**Interfaces:** `register_protocol(document, catalog) -> ResearchProtocol`;
`admit_attempt(protocol_id, variant_ref, application_ref, split, replication_id) -> AttemptRecord`;
`record_inspection(scope, artifact_id, actor, reason) -> InspectionEvent`.
Use stable logical keys and a single SQLite transaction for admission, budget
reservation, attempt creation, and child queue identity.

- [ ] Test split overlap, boundary-crossing trades, warm-up scored accidentally,
  predeclared universe changes, two simultaneous reservations at the final budget
  slot, and retries under a different HTTP idempotency key.
- [ ] Test renamed/forked ideas and new campaigns against already inspected final
  instrument/time scopes, plus explicit externally known-data declarations.
- [ ] Run `python -m pytest tests/test_research_protocol.py -q`; observe missing protocol enforcement.
- [ ] Freeze baseline/candidates, application matrix, evaluation windows, allowed
  differences, metrics, minimum trade counts, stopping rules, and budgets.
  Distinct numerical recipes consume the candidate budget; logical executions
  consume attempts. Infrastructure retries resume the same attempt. Budget changes
  are recorded protocol amendments, never retroactive erasure of failed attempts.
- [ ] Expose development freely; log validation inspection; lock candidate revisions
  before final runs. Record final result exposure before returning/exporting its
  metrics through protocol APIs. Maintain overlap-aware exposure across campaigns.
- [ ] Enforce these guarantees for controlled workflows and disclose legacy/manual
  activity; do not claim filesystem access can be prevented for the local owner.
- [ ] Run protocol, experiment, and recovery tests; commit.

**Acceptance:** Repeated experimentation remains visible, and final-data reuse
cannot receive an untouched label within the controlled research archive.

## F. Execute controlled comparisons with restart reconciliation

**Files:** Extend `bktstr/services/research_protocol.py`,
`bktstr/services/backtest.py`, `bktstr/services/experiments.py`;
create `tests/test_research_campaigns.py`.

**Interface:** `run_protocol(protocol_id, store) -> ProtocolResult` consumes E's
frozen matrix and D's operation. Each cell's stable identity includes protocol,
variant, application, split, and deliberate replication identity.

- [ ] Write fixture tests for one idea, base plus two variants, two symbols,
  zero trades, incomplete candidate work, cancellation, and mismatched input hashes.
- [ ] Run `python -m pytest tests/test_research_campaigns.py -q`; observe missing campaign execution.
- [ ] Acquire C datasets once per declared scope and run each comparison cell on
  matched inputs. Reject undeclared differences; label exploratory comparisons.
  Show risk/cost changes in declared sensitivity panels rather than conflating them
  with evidence for an unrelated filter.
- [ ] Reconcile child identities after interruption. Reuse completed children,
  resume pending work, and preserve failures/cancellation. Recover abandoned inline
  configured work or mark it explicitly interrupted instead of leaving it running.
- [ ] Report per-symbol paired effects and declared aggregation with dispersion,
  sample counts, and unavailable metrics. Never infer shared-portfolio returns.
- [ ] Verify attempt/budget counts survive crashes at admission, child completion,
  and artifact publication; commit.

**Acceptance:** A campaign produces an auditable comparison and resumes without
duplicating completed tests or concealing incomplete work.

## G. Expose idea history and a readable research report

**Files:** Create `bktstr/services/idea_reports.py`,
`tests/test_idea_reports.py`, `tests/test_api_ideas.py`.
Extend `bktstr/api/schemas.py`, `bktstr/api/routes.py`,
`docs/API_REFERENCE.md`, and `AGENT_BACKTEST_RUNBOOK.md`.

**Interfaces:** `idea_report(idea_id, store) -> IdeaReport` and additive authenticated
routes for idea revisions, modifier/variant revisions, application registration,
protocol registration/submission, and paginated history. Proposed route families:
`/api/v1/ideas`, `/api/v1/modifiers`, `/api/v1/variants`, `/api/v1/applications`,
`/api/v1/research-protocols`, `/api/v1/configured-backtests`, and
`/api/v1/experiments`. Existing retrieval routes retain behavior.

- [ ] Test lineage discovery, stable pagination, filters, validation/authentication,
  progress, cooperative cancellation, final-inspection logging on exports, and
  correct blocked/scenario labels.
- [ ] Run `python -m pytest tests/test_idea_reports.py tests/test_api_ideas.py -q`;
  observe absent report/routes.
- [ ] Generate a simple JSON plus Markdown idea card: thesis, recipe, categorized
  variants, effective differences, stock applications, every attempt, matched
  comparisons, exposure status, known limitations, and assessment history.
- [ ] Provide status/history/report operations to both local and HTTP clients with
  one service implementation. List filters include idea, variant, instrument,
  campaign, status, and date; follow existing auth/error/pagination conventions.
- [ ] Update capabilities and OpenAPI for delivered operations only. Keep baseline
  compatibility and explicitly label today's metric definitions. Commit.

**Acceptance:** The owner can find an idea, understand its variations and failures,
and reproduce a result without retaining experiment IDs manually.

## H. Verify the standalone research milestone and update the roadmap

**Files:** Create `tests/test_idea_research_workflow.py`; update `README.md`,
`docs/TRADE_IDEA_CONTAINERS.md`, `docs/IMPLEMENTATION_PLAN.md`,
`docs/PROJECT_STATUS.md`, and `docs/development/local-credentials.md` only if local
setup instructions require cross-linking. Do not change credential handling.

- [ ] Build an offline end-to-end fixture from A-G: create idea, branch modifiers,
  bind two stocks, freeze data, register splits and budgets, run a campaign,
  interrupt/resume, inspect report, and replay an earlier revision after a new edit.
- [ ] Include failures for unavailable macro execution, corrupted pinned data,
  overlapping final exposure, budget races, and mismatched comparison inputs.
- [ ] Document one explicit persistent research root; test backup/restore of the
  database plus referenced artifacts and evidence bundles, not just SQLite alone.
- [ ] Run focused tests, `python -m pytest tests -q`, release consistency,
  compilation, and the cache benchmark. Obtain an independent final review.
- [ ] Update completed capabilities and preserve the still-pending execution-realism,
  macro evaluator, Jev, and paper work. Commit only the completed milestone.

**Acceptance:** The design's completion gate is demonstrated without network or
Jev. Only then return to Task 3.

## Dependencies and self-review

Execute A -> B -> C -> D -> E -> F -> G -> H. C's runtime injection is consumed
by D; E uses the same SQLite database as D so admission and queue identity are
atomic; G's report/export endpoints participate in E's inspection ledger.

The proposal closes gaps 1 and 2. It does not require Task 4's new fill model or
macro gates, and must not pretend those capabilities exist. Original Task 5's
generic protocol, history, and recovery work moves here; its later work is limited
to consuming real Jev/decision records and new execution metrics through these
interfaces. This avoids building a second protocol system after Task 3.

The user-facing container remains one idea with variations and results. Separate
internal records serve reproducibility, not a requirement for a large dashboard.
No production implementation is part of this planning change.
