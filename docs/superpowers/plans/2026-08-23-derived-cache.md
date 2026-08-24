# BKTSTR Derived Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add merge-safe deterministic feature/context caching plus an agent backtest runbook without changing v0.3.3 strategy behavior.

**Architecture:** A standalone `bktstr_cache` package hashes input DataFrames and semantic version dimensions, atomically persists computed DataFrames, and optionally memoizes exact JSON results. Existing BKTSTR computation functions remain authoritative and are passed as callbacks.

**Tech Stack:** Python 3, pandas, hashlib/json/gzip/pickle, pytest.

**Spec:** `docs/superpowers/specs/2026-08-23-derived-cache-design.md`

## Global Constraints

- Preserve v0.3.3 backtest behavior and API semantics.
- No new runtime dependency beyond pandas.
- Do not cache strategy decisions or tuned thresholds.
- Cache invalidation must include input-data digest and explicit semantic versions.
- Writes must be atomic; corrupt cache entries must degrade to misses.

---

### Task 1: Deterministic DataFrame cache

**Files:** Create `bktstr_cache/derived.py`, `bktstr_cache/__init__.py`; test `tests/test_derived_cache.py`.

**Interfaces:** `dataframe_digest(frame) -> str`; `DerivedFrameCache.get_or_compute(namespace, dimensions, inputs, compute) -> CacheResult`.

- [x] Write tests for stable digest, cache hit, input invalidation, semantic-dimension invalidation, corruption recovery, and atomic persisted metadata.
- [x] Run tests and confirm missing module/behavior fails.
- [x] Implement the smallest cache satisfying tests.
- [x] Run tests to green.

### Task 2: Exact result memoization

**Files:** Create `bktstr_cache/result_cache.py`; test `tests/test_result_cache.py`.

**Interfaces:** `JsonResultCache.get_or_compute(dimensions, compute) -> JsonCacheResult`.

- [x] Write miss/hit/invalidation/corruption tests.
- [x] Verify red.
- [x] Implement gzip JSON atomic cache.
- [x] Verify green.

### Task 3: Integration wrappers and benchmark

**Files:** Create `integration/example_wrappers.py`, `integration/INTEGRATION_GUIDE.md`, `benchmarks/benchmark_cache.py`.

- [x] Provide callback wrappers for intraday features, daily features, and subject/sector/market context.
- [x] Add benchmark proving a warm hit does not invoke the expensive compute function.
- [x] Run benchmark and capture cold/warm output.

### Task 4: Documentation and contract

**Files:** Modify `docs/BKTSTR_SYSTEM_MANUAL.md`, `docs/gui/sentiment-data-contract.json`; create `AGENT_BACKTEST_RUNBOOK.md`, `README_PATCH.md`, `requirements-cache.txt`.

- [x] Update manual to v0.3.3 behavioral baseline and document research hierarchy, v0.3.3 coverage behavior, proven findings, and cache architecture.
- [x] Add exact Supabase pg_net control instructions and frozen backtest template.
- [x] Update GUI contract to 0.3.3 and add coverage metadata contract without changing sentiment field meanings.
- [x] Document merge/deployment verification requirements.

### Task 5: Verification/package

- [x] Run full patch test suite.
- [x] Compile all Python files.
- [x] Run benchmark.
- [x] Scan package for secrets/tokens.
- [x] Build ZIP and SHA256 manifest.


> Package implementation completed in the isolated merge bundle. Live application integration remains gated on applying `integration/INTEGRATION_GUIDE.md` to the actual v0.3.3 checkout and passing `MERGE_CHECKLIST.md`.
