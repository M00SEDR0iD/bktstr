# Reusable trade ideas and event research

Status: adopted direction, September 20, 2026. The research foundation is planned,
not implemented. Tasks 0-2 remain delivered; Jev Task 3 follows this milestone.
The [implementation plan](plans/2026-09-20-trade-idea-research.md) defines RF-A through RF-K.

## Intent and research sequence

An idea container holds a repeatable thesis, the observations used to investigate
it, its categorized variations, and the evidence for any resulting trading policy.
The owner should be able to explain an idea once and study it across explicitly
chosen stocks without rewriting its meaning. BKTSTR remains independent of the
Bailey Fund. The first executable scope is equity/ETF minute bars and holding
periods of minutes to hours.

The research sequence is:

```text
Thesis -> event definition -> context measurements -> outcome labels
       -> exploratory study -> frozen trading policy -> controlled backtest
       -> bounded paper validation
```

Paper validation remains a later delivery phase. Exploration can end in rejection
or an inconclusive assessment without producing a trading policy.

The previous recipe-first design is replaced by this sequence. Preserve its
immutable revisions, data binding, attempt history, and controlled comparisons.
Add an event-study path alongside the existing backtest path. Both share data,
measurements, provenance, the experiment store, and the worker.

## The idea card

```text
Idea: rejection of a prior-session price extreme
  Thesis, proposed mechanism, applicability, disproof criteria
  Base research specification
    Event definition
    Context measurements
    Reference levels
    Outcome labels
  Research variations
    Event definition
    Technical context
    Market / benchmark context
    Macro assumptions and evidence
    Time and session context
    Outcome horizon or label definition
    Explicit combinations
  Trading policies, each linked to supporting and contrary studies
    Entry and selection rules
    Risk, sizing, and exits
    Execution and cost assumptions
  Applications: instruments, calendar, data
  Campaigns and all attempts
  Evidence, limitations, and assessment history
```

The container format is domain agnostic. Executable applications still require
supported data, units, calendars, and execution profiles. Rebinding a template is
not evidence that an effect transfers to a new instrument.

An idea can exist without a policy. Changing the central explanatory mechanism
creates a related idea with a `derived_from` link. Changing how it is measured,
which context is studied, or how it trades creates a categorized revision.
The author records that distinction; the software does not infer semantic
equivalence between narratives.

Categories organize changes; they do not create hidden inheritance. Each variant
has one explicit parent and pinned, ordered modifier revisions. Conflicting field
assignments fail. Display the complete effective specification and differences
against parent and baseline. A study modifier cannot silently change a policy,
and a policy modifier cannot rewrite its supporting study.

## Separate the objects being studied

| Component | Purpose | Timing and execution boundary |
| --- | --- | --- |
| Event definition | Select candidate observations, such as a minute closing back above the prior-session low | Uses only information available by the event cutoff; does not depend on future outcomes or position state |
| Context measurement | Describe conditions, such as wick fraction, normalized volatility, trend, or benchmark return | Continuous values stay continuous until a declared analysis or policy transforms them |
| Reference | Supply an anchor, such as prior-session high/low or VWAP | Formula, session convention, warm-up, and availability are explicit |
| Outcome label | Measure what followed, such as return after 15 elapsed minutes or maximum adverse excursion | Future data is permitted only in the label path and never in an entry input |
| Trading policy | Select events and define entry, risk, sizing, and exit behavior | Compiles supported rules into the existing deterministic engine |

Role, value type, and evidence trust are separate dimensions. A context measurement
may be continuous, boolean, or ordinal. Being a context feature does not make a
model output a trusted numerical observation.

Registered component definitions carry ID/version, formula identity, units,
required inputs, lookback, availability rule, missing-data behavior, and supported
profiles. Labels additionally carry reference price/time, horizon, session boundary
behavior, and overlap rule. Use the existing numerical variable registry where it
fits; do not build a duplicate indicator library or execute arbitrary user code.

## Event dataset and causality

Build candidate events before trading simulation. Each event has a stable identity
derived from specification, application, dataset, instrument, and timestamp. Keep
all events admitted by the declared detector and sampling rule, including events
that a policy later rejects or cannot trade because it already has a position.

Store causal inputs and future labels as separate artifacts keyed by event ID.
Each predictor value records when it became available. Label data is not accessible
through the predictor interface. A completed minute candle is available at its
close; that candle's shape cannot justify a fill at its earlier open. The initial
policy path retains next-bar entry semantics.

Pin a calendar/session schedule in the dataset, including holidays and early closes.
The new research path must not silently assume every session ends at 16:00.
Do not change legacy baseline semantics without a separate versioned change.
Record missing, duplicate, unsorted, and unexpected bars. Missing required coverage
blocks a controlled dataset; documented exclusions remain visible in exploratory
results. A missing label is never silently converted to zero or dropped from counts.

The first label catalog supports fixed-horizon returns and favorable/adverse
excursions. Horizons use explicit elapsed market-session time, not the Nth available
bar. A missing required price or a horizon beyond the session produces a labeled
unavailable/censored observation with a reason. Report the denominator and reasons.
A reference-price return is an observation, not an executable trade return.

First-touch stop/target labels are deferred from this milestone. Minute bars cannot
always establish which barrier came first. A later implementation must preserve
ambiguous outcomes or use a predeclared conservative rule, never invent tick order.

Freeze raw/derived inputs and formula/build identities. A corrupt or missing pinned
artifact blocks replay; it cannot trigger a silent fresh provider download.

## Research variants and comparisons

Freeze the study's event rule, context definitions, labels, application universe,
analysis choices, data splits, primary outcome, and search budget before execution.
Exploratory amendments create new revisions and consume the relevant search budget.
Keep every tried horizon, subgroup, threshold, and feature combination visible,
including unsuccessful work.

The first report includes event and session counts, coverage/exclusions, label
distributions, effect sizes, uncertainty, and per-instrument/period stability.
Support predeclared quantile groups and matched baseline-versus-context comparisons.
Fit quantile boundaries and any scaling on development data only, freeze them for
validation/final data, and report missing values separately. Do not describe
subgroup differences as causal effects.

Use session-block resampling for the initial uncertainty estimator, with a fixed
seed, predeclared contiguous-session block length and resample count. Resample
aligned dates jointly across stocks. State the assumed dependence scale and
report session/block counts; too few usable blocks yields unavailable uncertainty.
Overlapping horizons create dependent observations, not extra independent trials.
This estimator is a declared approximation, not a universal validity guarantee.

Directly estimate the difference between comparable groups or variants with the
same resamples. A significant result and a non-significant result do not by
themselves establish a difference. A confidence interval is not a probability that
the strategy is true or profitable. Show multiple-search counts alongside results;
do not turn one favorable exploratory interval into a promotion rule.

Default to one changed factor at a time. Explicit combinations are allowed and
labeled accordingly. Event-definition variants can change the sample; report common,
added, and removed events rather than pretending their rows are all paired.
Fixed-event context comparisons share event IDs and outcome definitions. Do not
rank different horizon labels as though they measure the same target.

Exploration can suggest a policy but cannot validate it. Freeze the chosen candidate
before final evaluation. Account for label spans when separating development,
validation, and final periods: remove samples whose outcomes enter the next split.
Past-only warm-up is allowed but contributes no scored events or trades. A scored
trade cannot cross a split. Any later learned model will require its own versioned
training and validation contract; automated model search is outside this milestone.

## Immutable records

| Record | Owns |
| --- | --- |
| Idea revision | Thesis, mechanism, disproof criteria, applicability, input roles, base study reference, related-idea links |
| Component revision | Typed event/measurement/reference/label definition and timing contract |
| Modifier and variant revisions | Study or policy target, category, rationale, pinned ancestry, explicit changes, effective digest |
| Study specification | Resolved event detector, context/reference components, outcome labels, sampling rules |
| Policy revision | Supported selection and execution recipe, links to study evidence, promotion rationale |
| Application | Role bindings, domain profile, units, currency, calendar, timeframe, frozen data/evidence references |
| Campaign | Study or backtest purpose, candidates, application matrix, splits, analysis settings, metrics, budgets, stopping rules |
| Attempt and experiment | Exact inputs, software/formula/execution identities, lifecycle, artifacts, metrics, lineage |
| Assessment event | Author, timestamp, linked evidence, conclusion, limitations, promotion/rejection reason |

Narrative and semantic digests are separate: a wording edit remains visible without
claiming that a different numerical experiment was run. Empirical status is separate
from schema validity. Untested, inconclusive, rejected, or supported within a sample
are possible outcomes; none authorizes live trading.

## Persistence, budgets, and exposure

Extend the existing SQLite experiment store and worker. Add `event_study` and
`configured_backtest` operations using one lifecycle. Persist resolved inputs before
queuing. Both local and API access use the same admission, history, and reporting
services. Existing baseline endpoints retain their contracts.

A campaign freezes candidate definitions, universe, allowed differences, primary
metrics, sample requirements, stopping rules, distinct-candidate budget, and attempt
budget. Candidate identity includes outcome and analysis choices, not just strategy
rules. Renaming a study or changing a request key cannot conceal an earlier search.

Budget reservation, attempt creation, stable child identity, and queue creation
share one transaction. Infrastructure retries resume the same attempt. Deliberate
replications are separate, declared attempts. Preserve blocked, failed, canceled,
empty, and inconclusive outcomes. Restart reconciliation reuses completed children.

Record validation inspection and final exposure before returning metrics, labels,
plots, exports, or reports through controlled interfaces. Final labels remain
restricted until the candidate is frozen and admitted. Track overlapping data/time
scopes across ideas and campaigns, with shared-source dependencies included.
Renaming an idea cannot restore untouched status. Disclose external/manual inspection;
a local application cannot prevent its owner reading files outside its interfaces.

Compare a fixed policy across stocks with paired baseline-versus-variant results
per stock and a predeclared aggregate with dispersion. Independent symbol tests are
not shared-account portfolio simulations.

## Macro and Jev boundaries

Each macro claim has a proxy or question, timing/freshness requirements, units, and
one mode: `evidence_required`, `scenario_only`, or `unavailable`.
A hypothetical condition is labeled non-canonical and excluded from confirmatory
promotion. Unsupported evaluators block the selected variant instead of falling
back to the baseline.

Before Task 3, research uses supported deterministic numerical components.
Macro ideas may be documented and linked to immutable evidence; active macro
features/gates await a separately implemented causal adapter/evaluator.
The current BLS adapter remains prospective-only. Distinguish attached evidence
from consumed inputs.

Later Jev judgments can become recorded context under the same cutoff and replay
rules. Jev does not select its own outcomes, revise a running strategy, decide
statistical significance, or manage risk and execution.

## Completion gate before Jev

Demonstrate one toy thesis with a base study and two research variants on two stocks.
Keep all eligible events, inspect causal context and separate forward outcomes,
and record an inconclusive/rejected finding as well as a policy promotion rationale.
Compile one supported policy and compare its base and two policy variants on frozen
data through the existing engine.

Show leakage rejection, split-boundary handling, missing-data accounting, a context
comparison, all attempts, stable restart, exact offline replay, and backup/restore.
Reject incompatible bindings, conflicting modifiers, unsupported macro consumption,
exhausted budgets, invalid pairing, and reused final data claimed as untouched.
An edited revision must leave old evidence reproducible.

This demonstrates a functioning research workflow, not profitable performance.
The current fill and accounting limitations remain explicit. Execution realism
must be addressed before relying on paper or live economic conclusions.
