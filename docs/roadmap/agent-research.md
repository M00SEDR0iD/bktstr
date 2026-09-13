# Agent research priorities

Direction recorded on 2026-09-12: focus BKTSTR on private research into intraday trades held for minutes to hours. Sub-second research is a later option with different data and execution requirements.

The immediate objective is a repeatable workflow: state a hypothesis, run a bounded comparison, inspect the decisions, test execution assumptions, evaluate unseen periods, and retrieve the complete experiment later.

## Keep the existing foundation

Retain FastAPI, SQLite experiment records, the existing worker, raw-data caching, versioned measurements, and source/formula provenance. Change storage or deployment topology when a measured limitation requires it. Browser features can follow research needs; a full React workspace and Postgres migration are not prerequisites for the work below.

The older [standalone application roadmap](standalone-web-app.md) describes a possible broader product. Its inventory needs reconciliation with the implementation: typed operations, persistent experiments, a worker, and parameter sweeps already exist.

## Work order and acceptance criteria

1. **Simplify execution.** Route typed research requests directly into strategy execution and project its result once. Share provider selection with legacy clients and market-data inspection. Preserve public results, early validation, provider errors, and cache behavior. Verify recorded-fixture equivalence with caches on and off, including regime and sentiment inputs.

2. **Improve execution and risk reporting.** Specify and test fills when prices gap past a stop. Define spread, fee, and short-borrow assumptions and expose cost sensitivity. Distinguish closed-trade drawdown from equity measured while positions are open. Define or rename the current trade-return Sharpe statistic. Version changes that affect results; preserve the old baseline as a historical reference rather than forcing corrected calculations to match it.

3. **Explain each decision.** Record the indicator and context values available at signal time, the rules evaluated, and the signal and fill timestamps. Verify that recorded evidence contains no information from later bars. Keep bar-level excursion approximations clearly identified.

4. **Make batches recoverable and discoverable.** Add experiment listing/filtering, progress, and cancellation for long work. Give sweep variants stable identities and reuse completed children after interruption. Test that recovery reconciles interrupted children and does not silently repeat completed work.

5. **Make research validation repeatable.** Record development and held-out periods, the search space, all attempted variants, and the chosen evaluation criteria. Compare across symbols and market periods. Keep final evaluation data separate from parameter selection, and record when it has been inspected or reused.

These items are priorities, not claims of released capability. Implement each as a focused change with its own verification evidence. Do not combine trading-formula changes with compatibility refactoring.

## Evaluate the trading hypothesis

Treat market, sector, stock, and price-derived sentiment conditions as hypotheses whose contribution must be measured. Compare the same intraday trigger with each layer enabled and disabled using aligned dates and execution assumptions. Record how many opportunities each layer removes and whether its effect persists on unseen periods.

Price-derived sentiment is not an independent news or investor-opinion dataset. Its value must be demonstrated beyond the price and trend information already present in other filters.

## Later capabilities

Add a small human inspection interface when it improves review of experiments. Consider a separate worker deployment or database migration when concurrency, recovery, or storage requirements justify it.

If research moves to sub-second strategies, define quote/event data, timestamps, latency, queue position, and fill assumptions before implementing a separate execution backend. Retain experiment identity and provenance where they fit; do not stretch minute-bar fills into an order-book simulator.
