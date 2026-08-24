# Background Investor Sentiment Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add BKTSTR v0.3.1 continuous background investor sentiment scores and attach them to backtest trades without changing trade sizing.

**Architecture:** Create a focused `bktstr/sentiment.py` module that converts subject/sector/market daily bars into raw features, component scores, final direction/confidence, and bounded multipliers. The service fetches cached daily data and attaches the latest strictly prior-day sentiment row to intraday bars; the engine only records the attached scores on executed trades.

**Tech Stack:** Python 3.12, pandas, existing async providers/cache, pytest.

**Spec:** `docs/superpowers/specs/2026-08-23-sentiment-layer-design.md`

## Global Constraints
- Version is exactly `0.3.1`.
- Sentiment does not alter position size or P&L in this release.
- Intraday session D can only use sentiment rows dated strictly before D.
- Default behavior with sentiment disabled remains backward-compatible.
- Sentiment requires explicit sector and market benchmark symbols when enabled.

---

### Task 1: Daily sentiment feature and score module

**Files:**
- Create: `bktstr/sentiment.py`
- Create: `tests/test_sentiment.py`

**Interfaces:**
- Produces: `build_daily_sentiment(subject_daily, sector_daily, market_daily) -> pd.DataFrame`
- Produces: `attach_sentiment_to_intraday(intraday, daily_sentiment) -> pd.DataFrame`

- [ ] Write failing tests for raw feature names, bounded scoring, bullish/bearish ordering, missing-data completeness, multiplier symmetry, and strict prior-day attachment.
- [ ] Run `pytest -q tests/test_sentiment.py` and verify failure because `bktstr.sentiment` does not exist.
- [ ] Implement the formulas exactly as specified in the design document.
- [ ] Run `pytest -q tests/test_sentiment.py` and verify all sentiment tests pass.

### Task 2: Engine trade metadata and summary

**Files:**
- Modify: `bktstr/engine.py`
- Modify: `tests/test_engine.py`

**Interfaces:**
- Consumes attached `sentiment_*` columns when present.
- Produces sentiment fields on trade records and average sentiment fields in summary without changing shares/P&L.

- [ ] Write failing tests that attach known sentiment columns and assert trade metadata/summary values while position size and P&L remain unchanged.
- [ ] Run the focused engine tests and verify RED.
- [ ] Add optional sentiment metadata extraction at entry and sentiment summary aggregation.
- [ ] Run focused engine tests and verify GREEN.

### Task 3: Service/API wiring and cached daily fetches

**Files:**
- Modify: `bktstr/service.py`
- Modify: `bktstr/server.py`
- Modify: `tests/test_service.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Adds request fields `sentiment`, `sentiment_sector_benchmark`, `sentiment_market_benchmark`.
- When enabled, fetches subject/sector/market `1d` bars from `start - 400 days` through end, builds/attaches sentiment, and reports separate cache metadata.

- [ ] Write failing request-validation, query-parser, capabilities, and execute-backtest integration tests.
- [ ] Run focused service/server tests and verify RED.
- [ ] Implement request normalization, explicit benchmark dependency validation, data fetch/attachment, response metadata, and capabilities documentation.
- [ ] Run focused service/server tests and verify GREEN.

### Task 4: Version/docs/final verification

**Files:**
- Modify: `bktstr/__init__.py`
- Modify: `README.md`

**Interfaces:**
- Publishes v0.3.1 and documented request/output examples.

- [ ] Bump `__version__` to `0.3.1` and update capability tests.
- [ ] Document score semantics, formulas, benchmark parameters, and the fact that multipliers are informational only in v0.3.1.
- [ ] Run `pytest -q`, `python -m compileall -q bktstr`, and a secret/version scan.
- [ ] Package the verified source tree excluding caches/bytecode into `bktstr-v0.3.1-sentiment-layer.zip`.
