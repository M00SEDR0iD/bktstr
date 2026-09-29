# Futures Signal Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reproducible indicator lookbacks and a causal efficiency-ratio entry filter.

**Architecture:** Extend the existing futures recipe and shared executor with
execution model 1.2. Existing versions retain their validation and serialization.
Keep entry research in later immutable recipe revisions.

**Tech Stack:** Python, pandas, Pydantic, existing FastAPI/SQLite worker.

**Spec:** [Futures signal controls](../specs/2026-09-28-futures-signal-controls.md)

## Global Constraints

- New execution identity: `futures-ohlcv.1.2.0`; release `0.10.0`.
- Versions 1.0 and 1.1 reject the three new fields, including explicit nulls.
- Omitting the new controls preserves version 1.1 numerical behavior.
- No new dependencies or live execution; retain all saved research.

## Review Focus

- Insufficient indicator history rejects entry without suppressing exits.
- Flat price windows produce ratio zero, never division infinities.
- Equality at the regime cutoff permits entry.
- Later bars cannot change an earlier decision or quantity.
- Old recipes retain identical normalized fields and fills.

### Task 1: Versioned numerical controls

**Files:** Modify `bktstr/futures_execution.py`; create
`tests/test_futures_signal_controls.py`; extend `tests/test_futures_execution.py`.

**Interfaces:** `FuturesRecipe`, `signals(frame, recipe)`, and
`execute_session(frame, signal_values, recipe, terms, contract)` retain their
signatures. Recipe fields and decision metadata follow the spec exactly.

- [ ] Write tests for legacy rejection and normalization, paired/bounded options,
  explicit period signals and causal prefixes for all three signal kinds.
- [ ] Write tests for flat/monotonic/alternating ratio windows, threshold equality,
  unavailable history, next-bar causality, and protective exits despite a filter.
- [ ] Extend the existing worker persistence test to versions 1.0, 1.1, 1.2 and
  verify the new ratio survives in a saved trade.
- [ ] Run the focused futures tests; expect new tests to fail on unsupported 1.2.
- [ ] Implement optional periods and the completed-candle filter in the existing
  module, including rejection reasons and finite Python-float metadata.
- [ ] Run the focused futures tests; expect all to pass. Commit the engine change.

### Task 2: Contract, release, and acceptance

**Files:** Update `docs/FUTURES_RESEARCH.md`, current API/system/README references,
`CHANGELOG.md`, `bktstr/server.py`, release version references and their tests.

**Interfaces:** Retain the existing configured-backtest API and worker. The
capability text advertises 1.2; health and release contracts identify 0.10.0.

- [ ] Document formulas, missing-history behavior, defaults, logs and rollback.
- [ ] Update active release identities and acceptance defaults to 0.10.0, preserving
  historical changelog entries.
- [ ] Run full pytest, release consistency, compileall, and cache benchmark;
  expect all checks to pass. Commit documentation/release metadata.
- [ ] Obtain independent whole-branch review, address material findings with tests,
  open a focused PR and wait for required checks before merging.
- [ ] Verify Railway's exact version/commit and authenticated acceptance; then
  resume predeclared development-only recipe batches with no premature validation.
