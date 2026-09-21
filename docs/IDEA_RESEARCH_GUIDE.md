# Idea research and human review

The research foundation supports equity/ETF minute-bar event studies and frozen
policies. Jev, active macro gates, paper sessions, and broker execution remain pending.

## Files a human reviews

Use an explicit persistent `BKTSTR_EXPERIMENT_DIR`. Its `research/reports/` directory
contains `<idea-id>-idea-card.md` and `<experiment-id>-results.md`. The worker
generates these after completion or failure. The card links every attempt and
records categorized variations, disproof criteria, and assessment history.

Each test report contains the exact specification, period, application, results,
limitations, pinned data/build references, and stored replay request. A report
publication failure does not rewrite a committed experiment; regenerate the file
through the Markdown endpoint. JSON/SQLite records remain authoritative.

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
