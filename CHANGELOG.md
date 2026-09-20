# Changelog

This file records compatibility-relevant changes. Historical development journals
and research results belong in Git history and experiment artifacts.

## Unreleased

- Document the direction: configurable deterministic strategies, optional Jev
  macro judgments through OpenRouter, controlled comparisons, and bounded paper
  testing. These capabilities remain planned.
- Consolidate agent guidance and project documentation around BKTSTR as an
  independent system, separate from the Bailey Fund.
- The current source includes direct typed strategy execution and a local Windows
  credential helper. Read the current API and credential references for usage.

## 0.6.0

- Typed historical research operations, experiment retrieval, parameter sweeps,
  comparisons, and market-data inspection.
- Durable SQLite experiments, idempotency, worker recovery, and immutable artifacts.
- Versioned strategy and evidence contracts, governed dependencies, and provenance.
- The retired singular backtest endpoint returns HTTP 410.

## Earlier compatibility foundations

- Deterministic raw and derived caches with source/formula identity.
- Completed-bar signals, next-bar-open execution, adverse slippage, and stop-first
  handling for ambiguous bars.
- Build identity and authenticated production acceptance.

Consult Git tags for the complete historical change record.
