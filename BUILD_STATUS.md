# Build Status

## Completed in this package

- Updated canonical manual at `docs/BKTSTR_SYSTEM_MANUAL.md` to the v0.3.3 behavioral baseline and documented the bearish-regime scalp hierarchy.
- Added `AGENT_BACKTEST_RUNBOOK.md` with the proven Supabase `pg_net` → Railway workflow and standard QQQ/SOXX controls.
- Added deterministic L1/L2 DataFrame cache implementation with content/version invalidation and atomic persistence.
- Added optional L3 exact JSON result memoization.
- Added formula-agnostic integration wrappers, cache architecture notes, benchmark, tests, and merge checklist.
- Updated `docs/gui/sentiment-data-contract.json` to v0.3.3 coverage/cache documentation without changing the meaning of existing sentiment fields.

## Deliberately not claimed as completed

The current GitHub source checkout was not reachable from this sandbox, and the earlier full v0.3.3 ZIP was no longer mounted. Therefore this package **does not claim live integration into the existing `main.py` / `backtest.py` / `data.py` / `indicators.py` / `regime.py` / `sentiment.py` code**. Those working files were not reconstructed from guesses.

Use `integration/INTEGRATION_GUIDE.md` on the real repo, then run `MERGE_CHECKLIST.md`. Keep production at v0.3.3 until cache-enabled and cache-disabled trade outputs match exactly.
