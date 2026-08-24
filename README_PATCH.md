# BKTSTR Derived-Cache History Note

This file is retained for repository history. The original v0.3.4 work began as a merge-safe cache package while direct GitHub access from the build environment was unavailable.

That limitation no longer describes the application state:

- The deterministic derived cache was integrated into the real BKTSTR service in v0.3.4.
- Production v0.3.4 was verified with cache-off/cache-on trading equality and warm cache hits.
- v0.3.5 adds development/release infrastructure and does **not** change trading formulas.

For current instructions, use:

1. `README.md` — current application and release overview.
2. `AGENT_BACKTEST_RUNBOOK.md` — API, Supabase tunnel, development, deployment, and production-verification workflow.
3. `docs/CACHE_ARCHITECTURE.md` — derived-cache boundaries and invalidation rules.
4. `MERGE_CHECKLIST.md` — v0.3.5 release/deployment gate.

The guiding cache rule remains: **cache deterministic measurements, never strategy decisions.**
