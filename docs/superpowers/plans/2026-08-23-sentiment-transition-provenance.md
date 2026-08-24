# Sentiment Transition & Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build BKTSTR v0.3.2 with volatility-aware EMA persistence, sentiment momentum/fragility, clean-data provenance controls, and a GUI-ready system manual/data contract.

**Architecture:** Extend `sentiment.py` with OHLC-derived clean features and separate level/momentum/fragility outputs. Add a small provenance registry module and wire its profile/source controls through service/server responses. Preserve informational-only multipliers and strict prior-day attachment.

**Tech Stack:** Python 3.12+, pandas, numpy, stdlib HTTP server, pytest.

**Spec:** `docs/superpowers/specs/2026-08-23-sentiment-transition-provenance-design.md`

## Global Constraints
- Version exactly 0.3.2.
- Only Tier A price data may be active in this release.
- No source may be silently substituted or promoted between quality tiers.
- All sentiment inputs used by an intraday session must be completed before that session date.
- Sentiment multipliers remain informational and do not alter position sizing.
- Existing v0.3.1 fields remain available unless explicitly superseded by documented persistence scoring behavior.

---

### Task 1: Clean transition features and persistence
**Files:** Modify `bktstr/sentiment.py`; Test `tests/test_sentiment.py`.
**Produces:** EMA/ATR/volatility/persistence raw fields and updated `sentiment_persistence_score`.
- [ ] Add failing tests for EMA fields, volatility normalization, occupancy/pressure, and bullish-vs-bearish persistence ordering.
- [ ] Run targeted tests and confirm RED.
- [ ] Implement minimal daily OHLC normalization, EMA/ATR/volatility and persistence calculations.
- [ ] Run targeted tests and confirm GREEN.

### Task 2: Momentum and fragility
**Files:** Modify `bktstr/sentiment.py`; Test `tests/test_sentiment.py`.
**Produces:** `sentiment_momentum20`, `sentiment_momentum60`, `sentiment_momentum`, `sentiment_component_spread`, `sentiment_volatility_stress`, `sentiment_fragility`.
- [ ] Add failing tests proving coherent steady trends have lower fragility than conflicted/volatile transitions, and deteriorating sentiment produces negative momentum.
- [ ] Confirm RED.
- [ ] Implement transparent formulas from spec, renormalizing missing inputs.
- [ ] Confirm GREEN and prior-day attachment for new outputs.

### Task 3: Data provenance profiles
**Files:** Create `bktstr/provenance.py`; Modify `bktstr/service.py`, `bktstr/server.py`; Test `tests/test_service.py`, `tests/test_server.py`.
**Produces:** `sentiment_data_profile`, `sentiment_sources`, response provenance metadata, source registry.
- [ ] Add failing tests for clean default, explicit price source, rejection of unavailable/non-clean sources, and capability metadata.
- [ ] Confirm RED.
- [ ] Implement source registry/profile resolution and wire request parsing/service response.
- [ ] Confirm GREEN.

### Task 4: Trade/summary exposure and version
**Files:** Modify `bktstr/engine.py`, `bktstr/__init__.py`, `bktstr/server.py`; Test `tests/test_engine.py`, `tests/test_server.py`.
**Produces:** new sentiment outputs attached to trades and summary averages; version 0.3.2.
- [ ] Add failing tests for trade metadata and version.
- [ ] Confirm RED.
- [ ] Implement metadata and summary fields without changing sizing.
- [ ] Confirm GREEN.

### Task 5: White paper/manual and GUI contract
**Files:** Create `docs/BKTSTR_SYSTEM_MANUAL.md`, `docs/gui/sentiment-data-contract.json`; Modify `README.md`.
**Produces:** human and machine-readable future GUI documentation.
- [ ] Document architecture, layers, formulas, provenance tiers, data-flow schematic, field definitions, API examples, limitations, and GUI recommendations.
- [ ] Add JSON contract matching v0.3.2 capability/output field names and ranges.
- [ ] Add tests or validation script to parse JSON contract and cross-check key capability field names.

### Task 6: Release verification
**Files:** all release files.
- [ ] Run full pytest suite.
- [ ] Run `python -m compileall -q bktstr`.
- [ ] Run whitespace/diff checks where available.
- [ ] Scan release tree/archive for credential patterns and temporary/cache files.
- [ ] Build v0.3.2 zip, extract fresh, rerun tests/compile, inspect version and documentation artifacts.
