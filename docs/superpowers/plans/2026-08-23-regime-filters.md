# Daily Regime Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add look-ahead-safe daily regime and benchmark filters to BKTSTR intraday backtests.

**Architecture:** Daily subject and optional benchmark bars are fetched through the existing cached provider with a 120-calendar-day warm-up. A focused `regime.py` module computes daily features and attaches the latest strictly prior trading-day features to each intraday session; the engine evaluates the separate regime rule set alongside existing entry rules.

**Tech Stack:** Python 3.12+, pandas, httpx, pytest, stdlib HTTP server.

**Spec:** `docs/superpowers/specs/2026-08-23-regime-filters-design.md`

## Global Constraints

- Release version is `0.3.0`.
- No current-session daily bar may influence an intraday trade.
- Existing requests without `regime` remain compatible.
- Regime rules support only `lt`, `lte`, `gt`, `gte`, `eq` in v0.3.0.
- `relative_return20` equals subject 20-session return minus benchmark 20-session return, in percentage points.
- Daily warm-up starts 120 calendar days before the requested intraday start.
- Intraday cross rules cannot cross session boundaries.

---

### Task 1: Daily regime feature module

**Files:**
- Create: `bktstr/regime.py`
- Create: `tests/test_regime.py`

**Interfaces:**
- Produces: `REGIME_FIELDS`, `BENCHMARK_FIELDS`, `build_daily_regime(subject_daily, benchmark_daily=None) -> pd.DataFrame`, `attach_regime_to_intraday(intraday, daily_regime) -> pd.DataFrame`, `validate_regime_rules(spec, benchmark)`.

- [ ] Write failing tests proving feature calculations, prior-day attachment, benchmark relative return, and validation.
- [ ] Run `pytest tests/test_regime.py -q` and verify failure because the module is absent.
- [ ] Implement the minimal regime module.
- [ ] Run `pytest tests/test_regime.py -q` and verify it passes.

### Task 2: Engine regime signal and session-safe crosses

**Files:**
- Modify: `bktstr/engine.py`
- Modify: `bktstr/rules.py`
- Modify: `tests/test_engine.py`

**Interfaces:**
- `BacktestConfig` gains `regime_rules: str | None = None`.
- `evaluate_rules(frame, rules, cross_group=None)` accepts an optional grouping series used only by cross operators.

- [ ] Write failing tests proving regime rules gate an otherwise valid trade and first-bar session crosses are rejected.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement grouped cross evaluation and regime-rule ANDing.
- [ ] Run focused tests and verify pass.

### Task 3: Service fetch/alignment and API validation

**Files:**
- Modify: `bktstr/service.py`
- Modify: `tests/test_service.py`

**Interfaces:**
- `BacktestRequest` gains `regime: str | None` and `benchmark: str | None`.
- `execute_backtest` fetches daily subject/benchmark bars when needed, attaches regime features, and reports regime data/cache metadata.

- [ ] Write failing request-validation and service integration tests.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement request fields, warm-up daily fetching, alignment, and output metadata.
- [ ] Run focused tests and verify pass.

### Task 4: HTTP API, versioning, and documentation

**Files:**
- Modify: `bktstr/server.py`
- Modify: `bktstr/__init__.py`
- Modify: `README.md`
- Modify: `tests/test_server.py`

**Interfaces:**
- `/api/v1/backtest` accepts `regime` and `benchmark`.
- `/health` and `/api/v1/capabilities` report `0.3.0` and regime capabilities.

- [ ] Write failing parser/capabilities tests.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement HTTP/version/docs changes.
- [ ] Run focused tests and verify pass.

### Task 5: Full verification and package

**Files:**
- All changed files.

- [ ] Run `pytest -q` and require zero failures.
- [ ] Run `python -m compileall -q bktstr` and require exit code 0.
- [ ] Scan the implementation for API keys/secrets and generated cache artifacts.
- [ ] Package the repository as `/mnt/data/bktstr-v0.3.0-regime-filters.zip` excluding `__pycache__` and `.pytest_cache`.
