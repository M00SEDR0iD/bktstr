# Idea research and human review

The research foundation supports equity/ETF minute-bar event studies and frozen
policies. Jev, active macro gates, paper sessions, and broker execution remain pending.

## Primary policy outcomes

New policy campaigns optimize **net EV in R/trade**. This is the default and the
required primary metric for newly registered backtest protocols. Study protocols
continue to compare their declared forward-outcome mean. Existing frozen protocols
and results retain their original metrics; changing objectives requires a new
protocol and does not reset exposure history or research budgets.

The idea card and individual test reports lead with these outcomes:

| Metric | Version 1 definition |
| --- | --- |
| EV, R/trade | Mean of each trade's net PnL divided by its initial planned dollar risk, including breakeven trades |
| EV, dollars/trade | Mean net PnL per completed trade |
| Planned reward/risk | Initial target percentage divided by initial stop percentage |
| Realized reward/risk | Mean positive net R divided by the magnitude of mean negative net R |
| Daily Sharpe | Mean daily equity return divided by sample standard deviation, multiplied by sqrt(252), using zero risk-free return |
| Maximum drawdown | Largest equity decline from a previous peak, including starting capital, in dollars and percent as positive loss magnitudes |

For the current fixed-notional policy engine, initial dollar risk is filled-entry
notional times stop percentage divided by 100. It is frozen at entry and excludes
prospective exit costs. A 100-dollar planned risk and 25-dollar net profit give
0.25R. Stop changes alter this denominator; increases in R/trade must still be
reviewed alongside dollar EV, loss size, and drawdown. Losses can exceed 1R.

Net PnL includes modeled entry and exit slippage. Commissions, borrow fees, and
other unimplemented costs are not silently estimated. R is computed per trade
before averaging; position-size changes alone cannot improve normalized EV.

Open positions are marked at each minute close; exited positions settle at the
engine's recorded net PnL. The resulting marked equity includes unrealized changes
for drawdown. Daily returns use each scored session's final equity divided by
previous session equity, with starting capital for the first session. Inactive
sessions remain in the sample. This does not simulate shared cash across symbols.
Configured policy metrics require every scored minute; missing marks fail the run
rather than silently understate drawdown, including with exploratory snapshots.
Intraminute extremes are not observable from this equity sampling, and square-root
annualization does not correct for serial dependence or a short sample.

No trades means unavailable EV. Realized RR needs both a winner and a loser.
Sharpe is unavailable with fewer than two sessions, zero daily-return variance,
or nonpositive marked equity. Reasons are stored and rendered. A flat, no-trade
equity path has zero drawdown. Undefined values are never represented as infinity.

Campaign comparisons lead with candidate-minus-baseline EV in R/trade and include
baseline, candidate, and difference values for every headline metric. Positive
drawdown differences mean worse drawdown. Trade-count requirements and descriptive
status remain visible; a high sample EV does not automatically promote a variant.
Compare the same instruments, data, and chronological windows. Keep total profit,
trade frequency, uncertainty, and held-out results as supporting evidence.

Structured policy results expose `metrics`, `metric_definitions`,
`metric_unavailable_reasons`, and `daily_equity`. Each trade adds
`initial_risk_dollars` and `net_r`. Numerical build identity includes these formulas.
The legacy `summary.max_drawdown_pct` remains a negative closed-trade statistic;
the new positive marked-equity metric is `metrics.max_drawdown_pct`. The older
baseline API's trade-return Sharpe is unchanged and must not be mixed with the new
daily Sharpe. Historical results without the new fields display unavailable values.
The stored engine PnL has six-decimal precision; normalized metrics inherit that
precision. Initial risk uses the unrounded fixed notional from the policy.

See the [R-metric example](examples/r-metrics-demo/README.md) and its linked
[visual idea card](examples/r-metrics-demo/vwap-reclaim-idea-card.html). The older synthetic
demonstration is retained as a record of the prior metric contract.

## Files a human reviews

Use the server's authenticated HTML/Markdown endpoints. They render permanent
saved results on demand without writing report files or rerunning tests. Explicit
local export functions can still write `<idea-id>-idea-card.html`,
`<idea-id>-idea-card.md`, and `<experiment-id>-results.md` under `research/reports/`.
See [server storage](SERVER_RESEARCH_STORAGE.md) for retention, fresh-data reruns,
pinning and migration. The visual card works offline and provides
instrument, period/campaign, and variation selectors, headline outcomes, a
session-end equity chart, and expandable history, definitions, and assessments.
Failed and untested results remain visible; event observations are never presented
as trade EV. The Markdown edition retains links to individual result exports.

The visual card flags fewer than 30 sessions as a short sample. This is a display
cue, not a statistical sufficiency threshold or a modification to stored metrics.
Sharpe is unbounded; the synthetic example's near-identical daily losses create
a tiny denominator and an extreme negative value. The full number remains visible.
Publication uses the same exposure ledger as other exports. The authenticated
`GET /api/v1/ideas/{id}/html` endpoint returns the same standalone page.

Each test report contains the exact specification, period, application, results,
limitations, pinned data/build references, and stored replay request. A report
publication failure does not rewrite a committed experiment; request the report
again. JSON/SQLite records remain authoritative after input-cache expiry.

Publishing a report records data exposure. Viewing final outcomes means those
periods cannot later be described as untouched. The application cannot prevent
the local owner inspecting files directly; disclose external/manual inspection.

## Author and run an idea

1. Register an idea with thesis, mechanism, disproof criteria, applicability, and
   input roles. `examples/ideas/vwap-continuation.json` is an untested toy example.
2. Register a study with causal event rules, context fields, and separate labels.
   Supported predictors reuse OHLCV, VWAP, RSI14, and volume ratio20. Labels are
   fixed-horizon return, favorable excursion, and adverse excursion in percent.
3. Freeze explicit OHLCV frames and a session schedule with source, adjustment, and
   schedule provenance. Bars use timezone-aware minute-open timestamps. A bar's
   measurements become available at its close. Missing controlled coverage blocks.
4. Register applications binding symbols to the dataset. Register optional typed
   study modifiers and variants with exact ID/version/digest references.
5. Freeze a campaign's candidates, applications, chronological splits, primary
   label/metric, differences, sample minimum, budgets, and stopping rule. Quantile
   grouping can be fitted on development events and reused with a pinned artifact.
6. Submit the campaign. Review the Markdown card and test reports, including failures,
   censored outcomes, uncertainty assumptions, and every searched configuration.
7. Record an assessment. If justified, register a fixed policy with study evidence,
   rationale, contrary findings, and limitations. Compile and compare its variations
   through the existing engine. Policies may also be explicitly untested exploration.

The local entry points are `ResearchCatalog`, `freeze_dataset`, `register_protocol`,
`run_protocol`, `idea_report`, and the Markdown export functions. API operations use
the same services and existing experiment worker. HTTP submissions queue work;
local `run_protocol` can execute its admitted matrix using the worker lease.

## Scope and interpretation

All detector-eligible events remain in the study regardless of position state.
Outcome labels never enter predictor interfaces. Missing or boundary-crossing
outcomes are counted and censored, not changed to zero. Policy tests require full
pinned sessions because the existing engine does not implement intraday split exits.

Event means and context differences describe observations, not executable profit.
Session-block uncertainty uses an explicit seed, block length, resample count, and
minimum usable blocks. Its dependence assumptions may be insufficient for a market
sample. Exploratory intervals do not correct for a multiple-hypothesis search.

Configured backtests retain the current engine's fixed-bps costs, stop/gap behavior,
fixed notional sizing, and closed-trade accounting limitations. Independent symbols
do not form a shared-cash portfolio. Event-to-trade mapping is explicitly unavailable.

The component catalog is registered code, not arbitrary executable formulas.
Unimplemented macro/scenario evaluators block selected variants. Replay requires
the original pinned numerical build and fails on missing/corrupt artifacts.

## Offline demonstration and archive

Run from the repository root in the project environment:

```powershell
python -m scripts.research_demo --root .bktstr-research/demo --reports docs/examples/research-demo
```

Use a new root after changing numerical code; immutable dataset/revision identities
are not overwritten. The demonstration uses two synthetic instruments, a base study
and two study variations, then a base policy and two policy variations on later
sessions. A final baseline runs on a further period. Prices and shortened sessions
are artificial. The output demonstrates software behavior, not profitable trading.

Local archive functions accept explicit paths:

```python
from bktstr.services.experiments import ExperimentStore
from bktstr.services.research_archive import backup_research, restore_research, replay_research

store = ExperimentStore(".bktstr-research/demo")
backup_research(store, ".bktstr-research/demo-backup")
restored = restore_research(".bktstr-research/demo-backup", ".bktstr-research/demo-restored")
# Use an actual experiment ID from the generated idea card:
# replay = replay_research(experiment_id, restored)
```

Backup and restore require new destination directories. The bundle includes the
database and referenced market, event, label, result, and report files, with hashes.
Keep the original repository revision and Python dependency environment as well.

The checked-in [synthetic demonstration](examples/research-demo/README.md) includes
an [idea card](examples/research-demo/vwap-reclaim-idea-card.md) and linked individual
test reports. These files are examples of the generated human review artifacts.

## Controlled workflow details

Studies and policies initialize numerical indicators at the first scored session.
The frozen convention is `scored_sessions_only`. Earlier snapshot sessions do not
silently provide warm-up to one path but not the other. Within a scored session,
earlier bars can initialize later measurements. Initial missing measurements remain
explicit, and no warm-up observation contributes a scored event or trade.

Budgets belong to an idea lineage and research kind, across protocol names and
revisions. Study and policy budgets are separate. Increasing a family budget requires
`amendment_of` and `amendment_reason`; prior attempts and blocked admissions remain
visible. Changing analysis choices consumes the same family's candidate budget.

Final scopes are reserved transactionally. Only the predeclared cells in the same
frozen protocol can share that reservation. External exposure after admission blocks
execution. An exact replay retains the original protocol/stage and an explicit
`replay_of` link; it is never a fresh final test.

Uncertainty resampling preserves the pinned session axis, including sessions with
no usable events. Backup holds a database write boundary while copying the bundle,
so published reports cannot outrun their persisted exposure history.
