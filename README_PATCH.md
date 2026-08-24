# BKTSTR v0.3.4 Derived-Cache Update Package

This is a **merge-safe cache/documentation package**, not a replacement for the working v0.3.3 application source. The GitHub repository was unreachable from the build environment, so existing production modules were not overwritten or reconstructed from guesses.

## Included

- `docs/BKTSTR_SYSTEM_MANUAL.md` — updated v0.3.3 behavioral documentation + hierarchical research doctrine + cache architecture.
- `AGENT_BACKTEST_RUNBOOK.md` — proven Supabase `pg_net` connection and backtest workflow for future agents.
- `bktstr_cache/` — tested deterministic DataFrame cache and optional exact JSON result cache.
- `integration/` — tested wrappers and exact merge guidance for current BKTSTR functions.
- `tests/` — standalone cache regression tests.
- `benchmarks/benchmark_cache.py` — cold/warm demonstration.
- `docs/gui/sentiment-data-contract.json` — v0.3.3 contract with coverage metadata.
- `docs/superpowers/` — design + implementation plan.

## Recommended GitHub merge

Copy this package into a feature branch of the real BKTSTR repo. Preserve the real repo's existing application files. Integrate at the current feature-computation call sites using `integration/INTEGRATION_GUIDE.md`.

**Do not deploy solely by replacing the repo with this archive.** The package deliberately does not contain guessed copies of `main.py`, `backtest.py`, `data.py`, `indicators.py`, `regime.py`, or `sentiment.py`.

## Start here

1. `AGENT_BACKTEST_RUNBOOK.md` — future-agent API/research workflow.
2. `docs/CACHE_ARCHITECTURE.md` — cache boundaries and invalidation.
3. `integration/INTEGRATION_GUIDE.md` — merge into the real source.
4. `MERGE_CHECKLIST.md` — behavioral-equality gate before v0.3.4 deployment.
