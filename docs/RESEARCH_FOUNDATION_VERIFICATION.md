# Research foundation verification

Verified locally on September 20, 2026. This records software tests and a synthetic
workflow demonstration. It does not certify market performance or a hosted deployment.

## R-based policy outcomes update, September 21, 2026

Net EV in R/trade is now the default and required objective for new policy
campaigns. Headline results include dollar EV, planned/realized reward-to-risk,
daily Sharpe, and minute-close marked-equity maximum drawdown. Existing stored
results and the older baseline API retain their historical metric definitions.

- Complete suite: **584 passed**, with the same five pre-existing warnings.
- Nine new metric tests cover hand-calculated R expectancy and reward/risk,
  size invariance, open-position drawdown, daily returns with inactive sessions,
  undefined outcomes, nonpositive equity, same-bar exits, missing marks, campaign
  objectives, headline reports, and legacy protocol registration.
- Final documentation checks: **39 passed**. Release consistency and Python
  compilation passed. The cache benchmark retained one computation for 120,000
  rows followed by a cache hit.
- Independent review found no blocking calculation issues. Report labels were
  corrected for historical objectives, and headline rows now include version/date
  information.
- The [R-based example](examples/r-metrics-demo/README.md) completed six studies
  and eight policy runs, with a [generated idea card](examples/r-metrics-demo/vwap-reclaim-idea-card.md)
  and linked individual results. Earlier example files remain unchanged.

The example's three-session policy splits and artificial prices are unsuitable for
market conclusions. Metric assumptions and undefined-value behavior are recorded
in the [research guide](IDEA_RESEARCH_GUIDE.md#primary-policy-outcomes). Missing
scored minute marks fail a configured policy run. Drawdown sampling misses
intraminute extremes. Commission and borrow costs remain unmodeled.

## Results

| Check | Observed result |
| --- | --- |
| Complete repository suite | 575 passed; 5 existing dependency/cache deprecation warnings |
| New research foundation and review regression tests | 54 passed |
| Final report, workflow, API, and documentation checks after presentation edits | 44 passed |
| Independent review | Six important findings and four additional control gaps addressed |
| Release/documentation consistency | Passed |
| Python compilation | Passed |
| Cache benchmark | 120,000 rows; one computation; cold miss followed by warm hit |
| Synthetic research demonstration | Six study jobs and eight policy jobs completed across two artificial instruments |
| Backup, restoration, and offline replay | Restored study result exactly matched its original result |

The complete suite includes original baseline API and runtime behavior. The new
tests cover immutable revisions, pinned component definitions, separate predictors
and labels, data corruption, session/split censoring, event retention, group fitting,
policy compilation, persistence, API authentication, and generated Markdown files.

## Review findings verified by regression tests

- Overlapping final campaigns reserve data scopes in the same transaction as
  admission. A second protocol cannot reserve the same unseen final period.
- Replay retains the original stage/protocol and an explicit parent experiment.
  Replay is labeled as replay, never a new untouched test.
- Numerical build identity covers binding, analysis, execution, snapshot handling,
  protocol code, and numerical-library versions. Changed code blocks replay.
- Study windows outside the pinned schedule fail. Coverage reports distinguish the
  scored window from the complete snapshot.
- Renaming a protocol does not reset the idea family's attempt/candidate budgets.
  Budget increases require recorded amendments. Blocked admissions are durable.
- Study and policy indicators use the same pinned `scored_sessions_only` warm-up
  convention. Missing initial indicator values remain explicit.
- Direct submissions and campaign jobs support cooperative cancellation without
  rewriting completed results or refunding consumed attempts.
- Backup holds a database write boundary while copying immutable records and
  published reports, preserving the relationship to exposure history.
- Session-block resampling preserves scheduled sessions with zero usable events.

## Human review artifacts

- [Synthetic demonstration and comparisons](examples/research-demo/README.md)
- [Generated idea card](examples/research-demo/vwap-reclaim-idea-card.md)
- Each row in the card links a generated Markdown test-result file.
- [Authoring, API, report, and archive guide](IDEA_RESEARCH_GUIDE.md)

The example uses artificial prices and shortened synthetic sessions. Its assessment
is inconclusive for real markets. The policy step demonstrates the software path;
it is not a recommendation to trade the example.

## Implementation choices and limits

Work continues on the existing dedicated feature branch. Unrelated generated files
were preserved. No hosted deployment, broker request, paid model inference, or
live-money action was part of this verification.

Market inputs and a session schedule are supplied explicitly to the frozen-data
adapter. It does not silently infer an exchange calendar or acquire missing bars.
Initial frozen datasets contain minute bars; daily regime consumers require a
separately supported input adapter. Broader warm-up conventions require a versioned
extension so study and policy measurements remain aligned.

The initial campaign runner executes a fixed declared matrix. Its stopping-rule
description is documentation, not an arbitrary executable condition. Context
measurements and outcome formulas are registered code. Automatic feature search,
first-touch barrier inference, and learned-model training are outside this phase.

Event-to-trade mapping is reported as unavailable. The existing engine still uses
simplified fills and costs and does not simulate shared portfolio cash. Those limits
remain part of every policy review. Jev, active macro gates, paper execution, and
Clear Street integration remain later tasks.

SQLite/JSON evidence is authoritative. Markdown is a regenerable human edition.
Publishing a result report records data exposure. A Markdown write failure does not
alter a completed experiment; the report endpoint can regenerate the file.
