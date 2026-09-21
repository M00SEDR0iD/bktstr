# Configurable research and paper testing implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline implementation,
> or superpowers:subagent-driven-development if the user selects delegated execution.
> Complete and verify one task at a time. Implement only the tasks authorized in the current request.

**Goal:** Carry one theory through event research, a fixed trading policy, historical
comparisons, and a bounded forward paper session, with optional Jev macro interpretation.

**Architecture:** Keep BKTSTR's deterministic research core and existing stores.
Add reusable idea/event-study records, strict versioned strategy configuration,
as-of macro evidence, a recorded OpenRouter Decisions adapter, and a shared policy
evaluator. Run paper sessions
in a separate process and keep broker-demo execution distinct.

**Tech stack:** Python 3.12, FastAPI, Pydantic, pandas, SQLite, httpx, existing
BKTSTR caches and worker. Use existing dependencies where possible.

**Spec:** [BKTSTR system design](BKTSTR_SYSTEM_MANUAL.md)

**Status:** Tasks 0-2 implemented. Tasks 3-7 remain unstarted.
**Next priority:** Close reusable-idea organization, event-study, and controlled-research gaps
before Task 3, as requested by the user. The proposed
[trade idea design](TRADE_IDEA_CONTAINERS.md) and
[research foundation plan](plans/2026-09-20-trade-idea-research.md) define RF-A through
RF-K. The adopted sequence studies events, causal context, and separate outcome
labels before developing a frozen trading policy. These are planning artifacts,
not delivered capabilities.
No strategy, Jev, macro-feed, paper-runner, or broker integration was added by
Task 0. Do not infer that planned API fields already exist.

## Global constraints

- BKTSTR is an independent entity, separate from the Bailey Fund.
- Initial scope is equity/ETF minute bars and holding periods of minutes to hours.
- Live-money trading is outside the next implementation scope.
- Strategies stay frozen during runs; revisions create new versions.
- Use deterministic numerical calculations and explicitly bounded Jev judgments.
- Source availability, revisions, model-response timing, and causal fills are required.
- Jev evidence has a Tier C floor and cannot upgrade lower-trust inputs.
- Replay consumes saved model responses without network calls.
- Missing/stale required evidence blocks new entries; protective exits continue.
- Preserve the existing baseline and public contracts unless a task versions them.
- Do not add fund-specific holdings, allocations, metrics, or account assumptions.
- Keep secrets out of strategy files, prompts, logs, and experiment artifacts.

## Review focus

| Failure mode | Expected behavior | Owning task |
| --- | --- | --- |
| A release is revised or arrives after a signal | Use only the permitted vintage available by the cutoff | 2 |
| Jev times out, changes output, or returns malformed data | Bound retries, persist status, block dependent entry; replay the pinned result | 3 |
| A restart reprocesses a candle or an order event | Reconcile state without duplicate intents or fills | 6 |
| A final test period is reused during tuning | Record contamination and do not call it untouched | RF-F, 5 |
| Prices are missing at an exit or session boundary | Preserve unresolved position state; do not invent a fill | 4, 6 |

## Sequence and delivery gates

| Phase | Tasks | Deliverable and gate |
| --- | --- | --- |
| Foundation | 0-1 | Current docs checks and validated strategy manifests |
| Macro evidence | 2 | Causal macro snapshots |
| Research foundation | RF-A through RF-K | Reusable idea containers, event studies, linked policies, durable comparisons, and searchable history |
| Model evidence | 3 | Immutable Jev response records, after the research foundation gate |
| Research | 4-5 | Shared decisions and an auditable three-way comparison |
| Forward test | 6 | Bounded internal paper session and deterministic replay |
| Broker integration | 7 | Separate Clear Street demo workflow test |

Complete each gate before its dependents. Paper testing does not depend on a
Clear Street account. Macro-provider account selection is an integration input,
not a reason to block fixture-backed domain work.

### Research foundation tasks before Task 3

| Task | Deliverable |
| --- | --- |
| RF-A | Idea cards with separate study and policy revisions |
| RF-B | Versioned events, context measurements, references, and outcome labels |
| RF-C | Frozen datasets, pinned session schedules, coverage audit, offline replay |
| RF-D | All eligible events with causal inputs and separately stored future outcomes |
| RF-E | Durable event-study jobs and revision catalog in the existing experiment store |
| RF-F | Study/policy protocols, full search budgets, split rules, and exposure history |
| RF-G | Event-study distributions, context comparisons, uncertainty, and stability reports |
| RF-H | Evidence-linked frozen policies compiled into the existing engine |
| RF-I | Controlled campaigns that resume without duplicating attempts |
| RF-J | Searchable idea history and readable local/API reports |
| RF-K | Offline end-to-end demonstration, backup/restore, and verification |

The detailed [research plan](plans/2026-09-20-trade-idea-research.md) owns interfaces
and acceptance tests. No trading policy is required to investigate or reject an idea.
Future labels cannot be predictors, and exploratory associations are not strategy PnL.

## Proposed contracts

These are design contracts for new Python modules, not current public APIs.
Use frozen dataclasses or immutable Pydantic models and canonical JSON hashing.

| Contract | Required fields |
| --- | --- |
| StrategyManifest | schema_version, strategy_id, strategy_version, hypothesis, instruments, calendar, timezone, session, filters, entry, risk, execution, evaluation, model_policy, digest |
| EvidenceSnapshot | id, source_id, content_digest, payload, units, observed_at, published_at, ingested_at, available_at, vintage, tier |
| EvidencePacket | id, cutoff, mode, snapshot_ids, payload_digest, normalized_payload |
| JudgmentRecord | id, packet_id, question_digest, requested_model, resolved_model, provider, request_digest, raw_response, validated_answers, requested_at, received_at, usable_at, status, usage |
| DecisionRecord | id, strategy_digest, cutoff, symbol, evidence_ids, judgment_ids, gate_results, action, reasons |
| OrderIntent | id, decision_id, symbol, side, quantity, order_type, limit_price, eligible_at, execution_model_version |
| PaperSessionConfig | id, strategy_digest, start, end, capital, position_limit, gross_limit, daily_loss_limit, stale_after, model_budget, end_policy |
| PaperCheckpoint | session_id, last_event_id, positions, cash, pending_intents, consumed_judgment_ids, accounting_date |

All timestamps are timezone-aware UTC at persistence boundaries. Calendar/session
rules explicitly convert to the exchange timezone. Store money without binary
floating-point accumulation in the new paper ledger. Sort equal-time events by
a documented stable source sequence and event ID.

## Task 0: Align verification with current documentation

**Files:** Modify `tests/test_docs.py`, `tests/test_governance_docs.py`,
`tests/test_github_templates.py`, and only the retired-document assertions in
`tests/test_ops_assets.py`. Extend `scripts/check_release_consistency.py` and
`tests/test_release_consistency.py` for entry-point link coverage. Do not alter runtime logic.

- [x] Run `python -m pytest tests/test_docs.py -q` and record assertions tied to
  deleted release snapshots, old benchmark totals, and bridge instructions.
- [x] Replace obsolete prose assertions with checks that all documentation entry
  points exist and link to the active design/plan, and that future capabilities
  are labelled planned. Preserve GUI/runtime version and active API checks.
- [x] Add a check that Markdown links in agent and integration documents resolve;
  the existing release checker covers root README/contributing/changelog and docs.
- [x] Run `python -m pytest tests/test_docs.py tests/test_governance_docs.py tests/test_ops_assets.py tests/test_github_templates.py tests/test_release_consistency.py -q` and `python scripts/check_release_consistency.py`.
  Run the full suite before merging. Record unrelated failures without modifying
  unrelated workspace artifacts.
- [x] Commit this verification alignment as a focused change.

**Acceptance:** CI no longer demands retired research results or workarounds.
Preserve all workflow and SQL safety checks unrelated to retired documentation. No runtime, strategy, or API semantics change. Verification: 456 tests passed; release consistency, compilation, cache benchmark,
and independent review passed. Application runtime behavior is unchanged.

## Task 1: Compile strict strategy configuration

Delivered through a local file/Python interface documented in
[strategy configuration](STRATEGY_CONFIGURATION.md). Runtime uses the existing
orchestrator. Paper limits apply only to paper documents. Model/question fields
are disabled planning metadata; unsupported execution versions can be compiled
but cannot run. The public HTTP baseline registry is unchanged.

**Files:** Create `bktstr/strategy_config.py`,
`examples/strategies/macro-context-v1.json`,
`tests/test_strategy_config.py`. Modify `bktstr/strategies.py` and
`bktstr/runtime.py` only at their registry/configuration boundaries.

**Interface:** `compile_strategy(document: Mapping[str, object]) -> StrategyManifest`.
The returned manifest is immutable and contains its canonical digest. The example
must use simulation inputs, explicit symbols, and no private portfolio data.

- [x] Write tests rejecting unknown fields, booleans in numeric limits, unsupported
  variables, contradictory windows, absent paper limits, and model aliases.
  Confirm failures occur before provider access.
- [x] Implement normalization, units, semantic version validation, and immutable
  manifests using existing strategy/variable contracts.
- [x] Add a generic minute-strategy identity alongside the existing baseline.
  Configuration changes cannot mutate registered baseline definitions.
- [x] Verify JSON key order does not change a digest; a rule, model question,
  execution version, or risk limit change does.
- [x] Run `python -m pytest tests/test_strategy_config.py tests/test_direct_research.py -q`.
  Verify the old baseline remains equivalent with numerical caches on and off.
- [x] Update capabilities only for implemented configuration support, then commit.

**Acceptance:** A theory expressible with registered components can be loaded
without editing trading code. Unsupported theories receive a precise error.

Task 1 review record: added regression coverage and fixed strict semantic-version
validation, early rejection of daily crossing rules, and immutable returned
manifest evidence. Local configuration tests cover numerical regime gates,
unsupported execution modes, duplicate JSON keys, and baseline compatibility.
Ruling: future semantic execution versions may compile for fingerprinting but
cannot execute; compilation alone is not a runtime capability check.
Verification: 486 tests passed; release consistency, compilation, and the cache
benchmark passed. The existing baseline remains compatible with caches on/off.

## Task 2: Add point-in-time macro evidence

Delivered as local evidence selection, immutable packets, deterministic context,
and an append-only source store. The first adapter is BLS API v1 CPI-U NSA,
verified with a live unauthenticated request and recorded response. It is
prospective-only: missing publication/vintage metadata excludes it from canonical
historical use. See [macro evidence](MACRO_EVIDENCE.md) for exact coverage.
Strategy gates and the public experiment workflow do not consume packets yet.

**Files:** Create `bktstr/macro.py`, `bktstr/evidence_packets.py`,
`tests/test_macro_evidence.py`, and fixture records under
`tests/fixtures/macro/`. Modify `bktstr/measurements.py`,
`bktstr/variable_store.py`, and `bktstr/providers.py` at evidence interfaces.

**Interfaces:** `select_as_of(snapshots, cutoff, mode) -> tuple[EvidenceSnapshot, ...]`;
`build_packet(snapshots, cutoff, mode) -> EvidencePacket`.
Mode is explicitly `historical_publication` or `prospective_receipt`.

- [x] Write a fixture with a first release, a later revision, and late ingestion.
  Assert the selected value before/after each availability boundary.
- [x] Implement immutable source identity and as-of joins, with missing publication
  timestamps or unavailable vintages rejected for canonical historical use.
- [x] Add explicit unit normalization and deterministic numerical context fields.
  Missing expectations cannot be treated as zero surprise.
- [x] Test timezone/DST boundaries, non-trading days, delayed releases, missing
  values, duplicate source events, and stale evidence.
- [x] Run `python -m pytest tests/test_macro_evidence.py -q`.
- [x] Select the first provider only after confirming access, retention/licensing,
  release timestamps, and revision history. Integrate one adapter and validate it
  against recorded fixtures; keep unsupported datasets unavailable.
- [x] Update provider documentation with verified coverage, then commit.

**Acceptance:** No future revision or late-received event enters an earlier
canonical decision. Domain behavior is testable without provider credentials.

Ruling: use BLS only prospectively because its time-series response lacks verified
release timestamps and vintage history. Historical macro trading research still
needs an archive-capable adapter. Forecast differences require a documented initial
release and a forecast usable before it. Review regression tests prevent a later
revision from legitimizing a post-release forecast. A live persistence/replay test
also caught and fixed explicit SQLite connection closure on Windows.
Verification: 521 tests passed (35 macro-evidence tests); release consistency,
compilation, cache benchmark, and live BLS acquisition/store/replay checks passed.

## Task 3: Integrate Jev acquisition and replay

Do not start until the [research foundation milestone](plans/2026-09-20-trade-idea-research.md)
passes. Jev must become another explicit evidence component in an already usable
idea/variant/experiment workflow.

**Files:** Create `bktstr/judgments.py`, `bktstr/judgment_store.py`,
`bktstr/jev.py`, `tests/test_jev.py`, and `tests/test_judgment_store.py`.
Modify `bktstr/runtime.py` to inject the adapter and store.

**Interfaces:** `acquire_judgment(packet, questions, policy) -> JudgmentRecord`
is asynchronous; `load_judgment(response_id) -> JudgmentRecord` is offline.
Acquisition always creates a distinct immutable record. Replay never calls
acquisition on a miss.

- [ ] Verify OpenRouter's current Decisions HTTP schema and authentication using
  its official documentation. Capture a sanitized success fixture and error
  fixtures before finalizing field mapping.
- [ ] Write tests for timeout, 429, provider failure, malformed probabilities,
  missing choices, unexpected model identity, and responses after the deadline.
- [ ] Implement an httpx adapter with configured connect/read deadlines, bounded
  retry count, request/token budget, and no silent model substitution.
- [ ] Persist inputs and raw/validated outputs before allowing a dependent
  decision. Do not include credentials in request digests or logs.
- [ ] Test two distinct responses for identical inputs; both remain addressable.
  Test that an offline replay still uses the original response.
- [ ] Test Tier C minimum, inherited lower trust, and missing/stale evidence.
- [ ] Run `python -m pytest tests/test_jev.py tests/test_judgment_store.py -q`.
- [ ] Perform one small, budgeted credential-backed smoke test when integration
  access is configured. Record actual latency/usage, then commit.

**Acceptance:** A pinned model decision can be replayed without OpenRouter.
Model errors cannot create entries or disrupt deterministic exits. Failure
records are inspectable without exposing secrets.

## Task 4: Share decisions and version execution realism

**Files:** Create `bktstr/decision_engine.py`, `bktstr/execution_models.py`,
`tests/test_decision_engine.py`, and `tests/test_execution_models.py`.
Modify `bktstr/engine.py`, `bktstr/orchestrator.py`, and
`bktstr/services/backtest.py`.

**Interfaces:** `evaluate(manifest, state, account) -> DecisionRecord`;
`make_intents(decision, manifest, account) -> tuple[OrderIntent, ...]`.
Both are pure. Execution consumes intents only after `eligible_at`.

- [ ] Pin baseline behavior in existing engine fixtures before extracting logic.
- [ ] Test ordered gate/rank/annotate evaluation and evidence attached to both
  accepted and rejected signals. Pure numerical strategies need no Jev dependency.
- [ ] Add a separately versioned execution model covering adverse gaps, spread,
  fees, slippage, borrow assumptions, and mark-to-market equity.
- [ ] For OHLCV-only replay, declare no partial-fill realism and conservative
  ambiguous-bar handling. Do not imply access to quotes that were not supplied.
- [ ] Test a model response arriving after the next bar opens: fill eligibility
  must advance, never use the already elapsed open.
- [ ] Test missing exit prices, stale macro evidence, loss limits, and cash/exposure
  accounting. Missing prices produce unresolved state rather than fabricated P&L.
- [ ] Run `python -m pytest tests/test_engine.py tests/test_direct_research.py tests/test_decision_engine.py tests/test_execution_models.py -q`.
- [ ] Version any altered results, update execution metadata, then commit.

**Acceptance:** Historical and forward decision evaluation share one code path.
The original baseline retains its identity and behavior.

## Task 5: Run controlled research and expose evidence

**Reordered scope:** Generic protocols, configured experiment persistence,
attempt budgets, data-exposure tracking, history, cancellation, and restart
reconciliation move into RF-A through RF-K before Task 3. The checklist below is
the original overall contract; mark its shared items complete when those earlier
tasks deliver them, rather than implementing duplicate services. After Tasks 3-4,
finish the three-way numerical/Jev comparison, decision artifacts, and metrics
that require those new consumers and execution behaviors.

**Files:** Create `bktstr/services/research_protocol.py`,
`tests/test_research_protocol.py`. Modify `bktstr/services/backtest.py`,
`bktstr/services/experiments.py`, `bktstr/api/schemas.py`,
`bktstr/api/routes.py`, and `bktstr/provenance.py`.

**Interface:** `run_protocol(manifest, protocol, store) -> ProtocolResult`,
containing baseline/numerical/Jev child IDs, split metadata, all attempts,
comparison metrics, and final-data inspection records.

- [ ] Write a three-variant fixture with identical market and execution settings.
  Assert only the intended filter layer changes.
- [ ] Persist protocol identity, chronological splits, overlap exclusions, attempted
  variants, stopping rules, and final-data inspections before selecting a winner.
- [ ] Add decision/provenance artifacts, opportunity counts, net costs, exposure,
  drawdown, and explicit unavailable values. Do not infer statistical significance
  from a positive result or a small trade sample.
- [ ] Add paginated experiment discovery, progress, and cancellation. Cancellation
  is cooperative between bounded work units and preserves completed artifacts.
- [ ] Give each child a stable identity and reconcile existing children after a
  worker restart; do not repeat completed acquisitions silently.
- [ ] Test interruption, corrupt/missing artifacts, zero trades, all gates failing,
  holdout overlap, final-data reuse, and cancellation during inference.
- [ ] Run `python -m pytest tests/test_research_protocol.py tests/test_services_research_operations.py tests/test_api_research_operations.py -q`.
- [ ] Update OpenAPI and the API reference to match only delivered routes, then commit.

**Acceptance:** A report traces every result to exact data and model records.
Baseline comparison, causal timing, and held-out evaluation are independently
inspectable. Partial work is discoverable and recoverable.

## Task 6: Add bounded forward paper sessions

**Files:** Create `bktstr/paper_runner.py`, `bktstr/paper_store.py`,
`bktstr/paper_execution.py`, `bktstr/live_data.py`,
`tests/test_paper_runner.py`, and `tests/test_paper_recovery.py`.
Modify API routes/schemas only for explicit paper-session controls.

**Interfaces:** `run_session(config, feed, evaluator, execution, store)` is
asynchronous; feed yields timestamped finalized candles/events; execution accepts
`OrderIntent`; the store persists `PaperCheckpoint` and append-only events.

- [ ] Drive a fixture session through the same evaluator as Task 4 and compare
  its decision log to offline replay.
- [ ] Implement separate-process scheduling, exchange calendar boundaries,
  finalized-candle deduplication, and explicit gap detection.
- [ ] Enforce configured capital/exposure/loss limits, model budget, freshness,
  start/end times, and operator stop. No runtime strategy mutation is allowed.
- [ ] Persist intents before execution and fills/checkpoints transactionally.
  Restart reconciles pending intent IDs instead of creating new IDs.
- [ ] Test duplicate/out-of-order candles, restart between intent and fill,
  market closure, stale exit data, model outage, and session expiration.
- [ ] Select and verify a real-time feed entitlement and bar-finalization behavior.
  Demo broker prices cannot substitute for this feed.
- [ ] Run `python -m pytest tests/test_paper_runner.py tests/test_paper_recovery.py -q`.
- [ ] Complete a bounded prospective session, save all evidence, replay it offline,
  and report latency percentiles, missed deadlines, unresolved positions, and costs.
- [ ] Update operational documentation and commit.

**Acceptance:** No real-money orders. No duplicate simulated orders after restart.
Stops/exits continue without model access. Offline replay reproduces recorded
decisions and ledger outcomes for the same event sequence and execution version.

## Task 7: Validate Clear Street demo independently

**Files:** Create `bktstr/brokers/clearstreet_demo.py`,
`tests/test_clearstreet_demo.py`, and `docs/CLEAR_STREET_DEMO.md`.
Add configuration for demo credentials independently of BKTSTR/OpenRouter keys.

**Interface:** A demo-only adapter accepts `OrderIntent` and returns normalized
broker events. Its ledger and execution-model ID are distinct from internal paper.

- [ ] Confirm demo provisioning, connecting IPs, account permissions, separate
  OAuth credentials, token lifetime behavior, and supported symbols.
- [ ] Implement a demo-host allowlist and reject production order destinations.
  Research configuration cannot override this restriction.
- [ ] Test token refresh, reconnect/replay deduplication, rejected orders, partial
  events, cancellation races, and ambiguous submission timeouts. Reconcile before
  retrying an order whose acceptance is unknown.
- [ ] Run `python -m pytest tests/test_clearstreet_demo.py -q`.
- [ ] Perform a bounded demo-only order lifecycle exercise after account access
  is configured. Measure REST acknowledgment and streaming update delays.
- [ ] Record success as integration evidence, never as a profitability result.
  Document the daily reset and unsupported-symbol limitations, then commit.

**Acceptance:** The adapter cannot send production orders. Demo records cannot be
combined with live-data paper P&L.

## First end-to-end experiment

Use one explicitly configured equity/ETF subject and its chosen sector/market
controls. The hypothesis is that a defined macro tightening classification adds
information beyond numerical context and a fixed technical trigger.

Before acquisition, supply the selected instruments, source entitlements,
historical coverage, dated evaluation splits, Jev question set, model budget,
cost assumptions, and paper-session limits. These are experiment inputs, not
permanent project defaults.

Run technical-only, numerical-context, and numerical-plus-Jev variants.
Freeze thresholds before final evaluation. Run the frozen candidate prospectively
for a declared number of sessions and compare with its concurrent baseline.
Record weak or negative findings without expanding the search after the fact.

## Handoff and completion

Start the next code phase at Task 1. Resolve provider-specific wire contracts and
entitlements at their adapter tasks, not by inventing support now.

After each phase, report files changed, tests, capability status, and remaining
integration inputs. Before release, run the full suite, release consistency,
compilation, cache benchmark, and authenticated deployment acceptance as
applicable. No phase is complete merely because the service starts.

Implementation is complete when the first experiment has a full evidence chain,
a bounded forward session, and offline replay. A profitable strategy, live broker
deployment, and a fund portfolio are not acceptance criteria.
