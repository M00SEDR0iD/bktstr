# v0.3.3 Partial Warm-up + Fragility Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make sentiment warm-up best-effort without weakening required-period data integrity, expose exact sentiment coverage metadata, and allow native sentiment fragility/momentum rules in the regime layer.

**Architecture:** Required intraday and requested-period daily data remain strict. Sentiment pre-period history is fetched as an optional prefix: use cached history first, attempt the desired warm-up, and if the optional prefix cannot be fetched, retry the required period only and report reduced coverage instead of failing the entire backtest. Sentiment fields are attached before regime-rule evaluation and may be referenced only when sentiment is enabled.

**Tech Stack:** Python, pandas, FastAPI-style HTTP server, pytest, Railway, Massive daily/minute aggregates.

**Spec:** Approved in conversation after v0.3.2 live testing.

## Global Constraints
- Version is 0.3.3.
- No look-ahead: sentiment/regime values must remain strictly prior completed daily rows.
- Required backtest-period data failures remain fatal.
- Optional warm-up failures may degrade completeness but must be explicit in response metadata.
- No non-clean sentiment source may be enabled implicitly.
- Sentiment multipliers remain informational only.

---

### Task 1: Best-effort optional sentiment warm-up
**Files:** Modify `bktstr/service.py`; test `tests/test_service.py`.
- [ ] Add a failing test where full warm-up daily fetch fails but requested-period daily fetch succeeds.
- [ ] Verify the test fails under v0.3.2 behavior.
- [ ] Implement a focused helper that retries required-period daily data only when optional prefix fetch fails.
- [ ] Report requested/actual coverage start/end and warm-up degradation.
- [ ] Verify required-period daily failure still propagates.

### Task 2: Native sentiment rule fields
**Files:** Modify `bktstr/regime.py`, `bktstr/service.py`, `bktstr/engine.py`; tests `tests/test_regime.py`, `tests/test_service.py`, `tests/test_engine.py`.
- [ ] Add failing validation tests for `sentiment_fragility.gte:0.35` and sentiment dependency.
- [ ] Add sentiment rule fields to the regime vocabulary without cross operators.
- [ ] Require `sentiment=true` when sentiment fields are referenced.
- [ ] Ensure sentiment is attached before rule evaluation and native filtering works.

### Task 3: API/docs/version contract
**Files:** Modify `bktstr/__init__.py`, `bktstr/server.py`, `README.md`, `docs/BKTSTR_SYSTEM_MANUAL.md`, `docs/gui/sentiment-data-contract.json`; tests `tests/test_server.py`, `tests/test_docs.py`.
- [ ] Publish v0.3.3 and filterable sentiment fields in capabilities.
- [ ] Document partial warm-up semantics and coverage metadata.
- [ ] Update GUI contract with coverage fields and filterable sentiment dimensions.
- [ ] Run full test/compile/document validation.
