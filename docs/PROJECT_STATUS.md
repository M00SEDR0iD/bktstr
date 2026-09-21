# BKTSTR project report

Assessment date: September 20, 2026. Scope: the local checkout, including Tasks 0-2
and the research foundation. This is not production deployment acceptance or
evidence of a profitable trading strategy.

## Current standalone capability

BKTSTR carries a documented numerical idea through event research, a frozen
trading policy, controlled historical comparisons, and human-readable review.
Python, FastAPI, SQLite, the existing worker, and deterministic numerical
measurements remain the core architecture.

| Area | Implemented locally | Boundary |
| --- | --- | --- |
| Idea organization | Immutable theses, study/policy variants, categorized modifiers, explicit applications | New formulas and asset profiles require code |
| Event research | All detector-eligible events, causal context, separate forward return/excursion labels | Equity/ETF minute bars; registered numerical components only |
| Data | Frozen OHLCV, explicit session schedules, coverage diagnostics, offline replay | Supplied schedule must be authoritative; this is not a calendar/data subscription |
| Studies | Distributions, context groups, direct differences, session-block uncertainty | Exploratory statistics, declared dependence assumptions, no automatic edge certification |
| Policies | Strict compiler, durable configured backtests, numerical entry/risk/exit variations | Existing simplified execution and accounting |
| Controlled campaigns | Frozen candidates, budgets, split boundaries, exposure history, stable child identities | External/manual inspection must be disclosed |
| Human review | Automatic Markdown idea cards and test reports, authenticated API exports, searchable history | No full browser workspace |
| Archive | Database/artifact backup, verified restore, explicit offline replay | Original numerical build is required |
| Macro evidence | Point-in-time records, revision selection, immutable packets, BLS prospective acquisition | No active macro trading gates or historical release archive |
| Jev and forward execution | Defined next steps | No Jev calls, continuous paper runner, or broker connection |

The [research guide](IDEA_RESEARCH_GUIDE.md) describes authoring, generated files,
and interpretation. The [design](TRADE_IDEA_CONTAINERS.md) separates observational
studies from trading policies. The [implementation plan](IMPLEMENTATION_PLAN.md)
owns the task sequence.

## Fit with the intended trading workflow

The focus remains intraday equity/ETF trades lasting minutes to hours. A typical
workflow begins with a thesis such as continuation after a VWAP reclaim. Define
which reclaims count, measure context available at each close, and inspect what
followed. Keep every tested variation beneath the idea. A weak or inconclusive
study can stop there.

If the evidence warrants a policy, freeze its entry, risk, sizing, exits, and cost
assumptions. Compare it on declared instruments and periods through the existing
engine. A stock binding changes the application, not the underlying recipe.

The Markdown card and linked test reports are the human review layer. They show
the specification, attempted variations, failures, outcome counts, numerical
results, limitations, and replay references. The archive retains contrary and
inconclusive assessments.

BKTSTR remains separate from the Bailey Fund. It has no fund holdings, account
balances, allocations, mandates, or portfolio assumptions. Normalized quantities
improve reuse but do not establish transferability between stocks.

## Remaining work

### Execution and accounting

Fixed-bps costs and simplified stop/target behavior remain. Spread, commissions,
borrow costs, partial fills, adverse gap treatment, shared cash, and exposure
limits need a versioned execution/accounting model. New configured research leads
with net EV in R/trade, planned/realized RR, daily Sharpe, and minute-close marked
drawdown. The older baseline API retains closed-trade drawdown and its trade-return
Sharpe. The [research guide](IDEA_RESEARCH_GUIDE.md) defines the distinction.

The new archive does not make those assumptions realistic. Independent symbol
tests are not a shared-account portfolio. Minute OHLC bars do not reliably establish
first-touch order when both barriers occur within a candle.

### Macro and model context

The BLS adapter records CPI index observations after actual receipt. It does not
supply historical release timestamps, vintage history, or timestamped consensus
expectations. Macro gates and Jev context require separately implemented causal
consumers. Model outputs remain lower-trust evidence and cannot control risk.

Task 3 adds recorded Jev acquisition and replay. Tasks 4-5 add shared decisions,
model comparisons, and execution improvements using the existing research catalog
and protocol rather than creating a second history system.

### Forward testing

Task 6 still needs finalized live candles, a separate bounded runner, checkpoints,
stale-data handling, simulated account state, and measured receipt-to-decision
timing. Task 7 adds a separate Clear Street demo adapter. The current checkout
places no brokerage orders.

### Data and deployment

Coverage checks compare bars to a supplied pinned schedule. They do not prove that
the schedule is an accurate exchange calendar, that a universe avoids survivorship
bias, or that adjusted historical prices reproduce historical information vintages.
The direct baseline retains its historical session behavior.

Set an explicit persistent experiment root and keep complete backups. Confirm
deployment identity and authenticated behavior before using a hosted service;
local tests do not certify a running deployment.
