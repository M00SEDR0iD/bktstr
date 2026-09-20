# BKTSTR project report

Assessment date: September 20, 2026. Scope: the current checkout, including Tasks
1-2. This is a source review and local verification report, not a production
deployment acceptance test or an assessment of trading profitability.

Task 2 verification: 521 tests passed, including 35 macro-evidence tests. Release
consistency, compilation, and the cache benchmark passed. The live BLS adapter,
local source persistence, and offline packet reconstruction were checked together.

## Current position

BKTSTR is a useful standalone historical research service for an agent working
with its owner. It can already test explicit equity/ETF rules on minute bars,
vary parameters, compare results, and preserve baseline experiments. It is still
incomplete as the full application that carries a discussed theory through
controlled historical research and a bounded forward paper session.

The foundation is suitable. FastAPI, Python, SQLite, workers, and deterministic
caches are reasonable choices for a personal research tool. There is no measured
reason to replace them or build a broad web product first. The most important
work is connecting the existing pieces into one reliable research workflow.

| Area | Usable now | Important boundary |
| --- | --- | --- |
| Historical simulation | Long/short minute rules, stops, targets, holding limits, numerical context | Simplified fills and accounting; one subject at a time |
| Strategy authoring | Strict JSON, explicit symbols, frozen configuration and digest | Generic configured runs use the local Python interface |
| Experiments | Durable baseline backtests, parameter sweeps, comparisons, provenance | New manifests are not automatically saved through this workflow |
| Macro evidence | Publication/receipt cutoffs, revision selection, frozen packets, SQLite replay | Macro evidence is not yet a strategy gate |
| First macro adapter | Public BLS CPI-U NSA monthly index collection after actual receipt | No historical release timestamps, vintage reconstruction, or consensus feed |
| Model interpretation | Defined architecture and boundaries | Jev acquisition and recorded-response replay remain Task 3 |
| Forward execution | Planned shared decisions and paper runner | No continuous paper trading, broker connection, or measured minute-loop deadline |
| Human interface | API/OpenAPI and agent-operated local tools | No complete browser research workspace |

## What Task 2 delivered

The new evidence layer distinguishes what was published by a historical decision
time from what the running system had actually received. A revision cannot leak
backward into an earlier decision. Repeated deliveries are deduplicated; conflicting
source versions, missing required values, and stale packets fail explicitly.

Numerical context normalizes units and computes changes in code. Forecast
comparisons require evidence available before an explicitly identified initial
release. A forecast published after the outcome cannot become valid merely
because the actual was revised later. Missing forecast or initial-release evidence
leaves surprise unavailable.

Evidence records have immutable IDs and source digests, can be persisted separately
from feature caches, and can reconstruct identical packets offline. A live check
of the implemented BLS adapter returned 32 monthly records and reproduced the
packet after saving and reloading them. Tests also cover synthetic first releases,
revisions, delayed arrivals, daylight-saving boundaries, non-trading days, missing
data, staleness, lower-trust inheritance, and corrupted storage.

The provider choice is intentionally narrow. BLS offers a public API and permits
reuse of its published data, but its time-series response does not establish
historical intraday release vintages. Consequently, this adapter is prospective
only. Historical inflation-event research still needs a verified release archive
and, for surprise theories, timestamped expectations. Current-vintage CPI history
is not a substitute. See [verified provider coverage](MACRO_EVIDENCE.md).

## Fit with your trading goals

Your stated focus is intraday equity/ETF trades lasting minutes to hours, with
broader market or macro ideas layered over technical triggers. BKTSTR's minute-bar
scope fits that research horizon. Sub-second execution and order-book simulation
would be separate work; their absence does not prevent the intended first stage.

The useful division of labor is:

1. We discuss a theory and define what would disprove it.
2. A versioned strategy expresses the supported numerical conditions.
3. BKTSTR tests the same trigger with and without each added filter.
4. Jev eventually contributes bounded judgments from recorded evidence.
5. A frozen candidate advances to a limited paper session and replay review.

Today we can ask whether a VWAP/RSI/volume rule improves with a previous-day trend
or benchmark-relative gate. The desired extension is asking whether a macro
interpretation adds anything beyond those numerical filters. That requires the
remaining evidence consumers and controlled comparisons; installing a model
wrapper alone will not answer it.

This makes BKTSTR useful for eliminating weak ideas and identifying candidates
worth further testing. Current results should not be interpreted as account-level
performance or proof that a scalp survives actual costs. BKTSTR remains independent
of the Bailey Fund and contains no fund mandate or portfolio assumptions.

## Structural priorities

### 1. One durable workflow for every theory

The public API saves baseline requests through the experiment store. Local
configured runs return a result directly. Macro evidence now has its own store.
Those are valid boundaries, but the application needs a single research operation
that ties a manifest, data snapshots, evidence packets, later model records, and
results to a stable experiment ID.

Add searchable history, progress, cancellation, and a compact report/export around
that identity. Today retrieval depends on knowing an experiment ID. This is the
most useful application glue to make explicit in Task 5.

### 2. Controlled comparisons and an honest research history

Existing sweeps and comparison tools are useful, but comparing arbitrary runs
does not enforce identical inputs or an untouched final test period. The next
layer must track every attempted variant, development/validation/final periods,
test-set reuse, and actual search-budget consumption. Report uncertainty and trade
counts, not only a winning score.

Restart recovery also needs stable child-run identities: an abandoned sweep can
currently rerun completed children. That becomes expensive and misleading once
retries consume model calls or variant budgets. Task 5 should cover reconciliation,
including interrupted inline work, before paid research becomes routine.

### 3. Execution realism and account accounting

The current engine uses fixed slippage and simplified stop/target prices. It lacks
spread, commissions, borrow costs, liquidity/partial-fill behavior, and adverse
gap fills. Fixed notional sizing does not enforce shared cash or exposure across
symbols. Those omissions can change a short-horizon strategy's apparent edge.

Two metrics require clear labels: drawdown is based on closed-trade P&L, and the
reported Sharpe is a trade-return statistic rather than annualized daily account
Sharpe. Task 4 should add a versioned execution/accounting model, preserving the
existing baseline for comparison. Multi-symbol shared capital becomes necessary
before a watchlist bot, though single-symbol research can proceed first.

### 4. Data acceptance and explanations for every decision

Current checks do not establish complete expected trading-minute coverage. Fixed
09:30-16:00 filtering is not a full holiday/early-close calendar. Add a per-run
data-quality report covering missing minutes, adjustments, corporate actions,
warm-up history, and session coverage, with explicit acceptance rules.

Alongside it, record accepted and rejected signals and their gate reasons. Without
opportunity counts, an added filter can appear to help simply by discarding almost
all trades. This is essential for learning from layered filters and belongs with
the shared decision work in Task 4 and comparisons in Task 5.

### 5. Forward testing that measures actual behavior

Task 6 needs finalized live candles, a separate runner process, bounded sessions,
stale-data handling, checkpoints, and restart-safe simulated account state. It
must measure receipt-to-decision timing rather than assume minute trading is fast
enough because an HTTP call succeeds. Internal paper testing can come before
Clear Street; Task 7's broker demo remains a separate integration test.

### 6. A dependable personal research installation

Configure explicit persistent directories for experiments and macro evidence,
and test backup restoration. The experiment store can otherwise fall back to a
temporary directory. Worker recovery and hashes help, but do not replace backups.

A small results viewer or research notebook would be valuable after the records
are unified. A frontend rewrite, distributed queue, multiuser permissions, or
larger model autonomy would add complexity before closing the current gaps.

## Delivery sequence and evidence

Tasks 0-2 establish documentation checks, strict strategy configuration, and macro
evidence contracts. Task 3 is next: bounded Jev acquisition with persisted responses
and offline replay. Tasks 4-6 turn those components into shared decisions, controlled
research, and forward paper testing. Task 7 adds the separate broker demo.

The most valuable standalone milestone is a saved theory that produces a controlled
baseline comparison, an inspectable decision record, and a replayable bounded paper
session. A larger feature inventory is less useful than completing that path.

Source anchors: [shared runtime](../bktstr/runtime.py),
[strategy compiler](../bktstr/strategy_config.py),
[simulation engine](../bktstr/engine.py),
[research services](../bktstr/services/backtest.py),
[experiment store](../bktstr/services/experiments.py),
[API routes](../bktstr/api/routes.py),
[macro selection](../bktstr/macro.py), and
[evidence packets](../bktstr/evidence_packets.py).
The [implementation plan](IMPLEMENTATION_PLAN.md) remains the authoritative task
sequence; this report records an assessment, not additional implemented features.
