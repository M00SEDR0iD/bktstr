# BKTSTR v0.3.5 Development Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship BKTSTR v0.3.5 with automated CI, runtime release identity, a deterministic production acceptance CLI, and a reproducible GitHub-through-Supabase recovery bridge without changing trading behavior.

**Architecture:** Keep runtime metadata in a small `build_info.py` module and surface it through existing health/capabilities endpoints. Keep operational tooling outside the trading engine: CI under `.github/workflows`, acceptance logic under `scripts`, and the recovery bridge under `ops/supabase` plus a database migration.

**Tech Stack:** Python 3.12, pandas, httpx, pytest, GitHub Actions, PostgreSQL/Supabase pg_net, Railway.

**Spec:** `docs/superpowers/specs/2026-08-24-v035-development-infrastructure-design.md`

## Global Constraints
- Release version is `0.3.5`.
- No entry/regime/sentiment/execution formula changes.
- No strategy decisions or backtest results are cached by the new infrastructure.
- Existing v0.3.4 49-test baseline must remain semantically compatible.
- Supabase bridge is operational tooling and never enters the live backtest request path.
- No credentials or secrets are committed.

---

### Task 1: Runtime build identity

**Files:**
- Create: `bktstr/build_info.py`
- Create: `tests/test_build_info.py`
- Modify: `bktstr/__init__.py`
- Modify: `bktstr/server.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Produces: `runtime_build_info() -> dict[str, str | None]`
- `/health` returns version plus build identity.
- `CAPABILITIES["release"]` returns build identity and formula/cache versions.

- [ ] Write failing tests for Railway metadata normalization, local overrides, null-safe defaults, v0.3.5 health metadata, and release compatibility identifiers.
- [ ] Run focused tests and verify failures are caused by missing v0.3.5 interfaces.
- [ ] Implement `runtime_build_info`, bump `__version__`, and add health/capabilities release metadata.
- [ ] Run focused tests and require all pass.

### Task 2: Deterministic production acceptance CLI

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/production_acceptance.py`
- Create: `tests/test_production_acceptance.py`

**Interfaces:**
- Produces: `run_acceptance(base_url: str, expected_version: str = "0.3.5", transport=None) -> dict`
- CLI: `python scripts/production_acceptance.py --base-url <url> [--expected-version 0.3.5]`

- [ ] Write failing tests using `httpx.MockTransport` for successful anchor validation, mismatched trade output, missing second-run derived hits, and wrong version.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement minimal acceptance client and canonical result comparison.
- [ ] Run focused tests and require all pass.

### Task 3: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`
- Create/Modify: `tests/test_ops_assets.py`

**Interfaces:**
- Push/PR workflow uses `actions/checkout@v7`, `actions/setup-python@v7`, Python 3.12, pip cache, full pytest, compileall, and cache benchmark.

- [ ] Add a failing static test requiring the CI workflow and exact commands/actions.
- [ ] Run the focused test and verify failure because the workflow is absent.
- [ ] Add the minimal CI workflow.
- [ ] Run the focused test and require pass.

### Task 4: Supabase GitHub recovery bridge

**Files:**
- Create: `ops/supabase/github_bridge.sql`
- Create: `ops/supabase/GITHUB_BRIDGE.md`
- Modify: `tests/test_ops_assets.py`

**Interfaces:**
- Tables: `bktstr_repo_snapshots`, `bktstr_repo_blob_requests`, `bktstr_repo_files`.
- Functions: `bktstr_github_enqueue_commit`, `bktstr_github_enqueue_tree`, `bktstr_github_enqueue_blobs`, `bktstr_github_collect_blobs`.

- [ ] Add failing static tests requiring the migration, helper functions, safe GitHub API host, and no credential literals.
- [ ] Run focused test and verify failure because migration is absent.
- [ ] Implement idempotent SQL migration and exact four-phase runbook.
- [ ] Run focused tests and require pass.
- [ ] Apply the migration to the connected Supabase project and smoke-test commit/tree/blob collection against `M00SEDR0iD/bktstr` without credentials.

### Task 5: Release documentation and compatibility

**Files:**
- Modify: `README.md`
- Modify: `AGENT_BACKTEST_RUNBOOK.md`
- Modify: `BUILD_STATUS.md`
- Modify: `MERGE_CHECKLIST.md`
- Modify: `docs/BKTSTR_SYSTEM_MANUAL.md`
- Modify: `docs/gui/sentiment-data-contract.json`
- Modify: `tests/test_docs.py`

**Interfaces:**
- Documentation describes v0.3.5 release flow and emergency bridge.
- GUI/data contract version is `0.3.5`; sentiment formulas remain unchanged.

- [ ] Update doc tests first to require v0.3.5 and development/recovery sections; verify they fail.
- [ ] Update docs and machine-readable version metadata without altering sentiment definitions.
- [ ] Run doc/server/service tests and require pass.

### Task 6: Full verification and package

**Files:**
- All repository files.
- Update: `PACKAGE_MANIFEST.txt`

- [ ] Run `python -m pytest -q` and require zero failures.
- [ ] Run `python -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests` and require exit code 0.
- [ ] Run `python benchmarks/benchmark_cache.py` and verify cold miss/warm hit/one compute call.
- [ ] Scan tracked source for likely secrets and generated cache artifacts.
- [ ] Generate `PACKAGE_MANIFEST.txt` from the final tree.
- [ ] Package `/mnt/data/bktstr-v0.3.5-development-infrastructure.zip` excluding `.git`, caches, bytecode, and local environments.
- [ ] Verify ZIP integrity and compute SHA-256.
