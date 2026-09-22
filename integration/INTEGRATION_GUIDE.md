# BKTSTR integration boundaries

## Current numerical cache integration

`bktstr/runtime.py` constructs providers and stores and calls
`execute_strategy_run` in `bktstr/orchestrator.py`.
`bktstr/measurements.py` registers numerical definitions;
`bktstr/variable_store.py` materializes governed snapshots through
`bktstr_cache/derived.py`.

`integration/example_wrappers.py` contains tested examples around formula
callbacks. It is not a second production strategy engine or a pending merge.

Preserve numerical cache equivalence, source/formula identity, coverage, and
fresh threshold evaluation. See [cache architecture](../docs/CACHE_ARCHITECTURE.md).

## Planned external adapters

The [system design](../docs/BKTSTR_SYSTEM_MANUAL.md) defines the boundaries:

- Market and macro adapters return timestamped, versioned evidence.
- The OpenRouter adapter acquires typed Jev judgments; it never trades.
- The internal paper adapter simulates execution and maintains its own ledger.
- A Clear Street demo adapter validates broker workflow separately.

Provider calls must be injectable for tests. Timeouts, retries, budgets, and
response validation belong at the adapter boundary. Replay must work without
credentials or network access.

No external adapter in this section is implemented yet. Follow the
[implementation plan](../docs/IMPLEMENTATION_PLAN.md) in dependency order.
