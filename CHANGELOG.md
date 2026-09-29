# Changelog

## 0.10.0

- Add futures execution model 1.2 with configurable signal lookbacks and a completed-candle efficiency-ratio entry filter.
- Retain filter measurements and rejection reasons in durable research, with existing exits and older execution models preserved.
- Keep the engine capability release separate from recipe selection and account-pass research.

## 0.9.0

- Add explicit futures execution 1.1 with opening-candle direction filtering, causal ATR quantity scaling, integer quantity increments and premarket indicator warmup.
- Retain version 1.0 execution and saved research identities. Record sizing and fair-value inputs with accepted and rejected signals.
- Keep strategy recipes and prop-evaluation account scoring separate from the shared execution extension.

## 0.8.0

- Persist futures evaluation drawdown flags as native JSON booleans, including nonempty trade results.

- Reuse the immutable dataset fingerprint during event preparation. Large studies produce identical event records without rehashing all input bars for every event.

- Add a versioned futures execution profile to configured research and the shared orchestrator, preserving equity identities and behavior.
- Model whole contracts, tick-valid brackets, commissions, adverse slippage and gap stops, conservative intrabar drawdown, and fixed-floor evaluation attempts.
- Keep signals and account/contract bindings in separate research revisions. Add VWAP, Bollinger and RSI recovery detectors with session resets.
- Retain signal decisions and report overlapping versus disjoint evaluation windows, including incomplete-data censorship.
- Futures downloads now advertise execution support through the explicit research profile. Broker execution, margin and firm-specific rules remain unsupported.

## 0.7.1

- Add authenticated Massive futures contract discovery and raw one-minute candle downloads using the existing server credential.
- Bound downloads to 31 inclusive UTC dates and validate pagination, contract identity, timestamps, and OHLCV integrity.
- Report missing configuration, denied futures access, rate limits, and provider errors without exposing credentials.
- Keep futures data acquisition separate from equity strategy execution and saved research. No futures backtest, continuous-contract series, or prop-evaluation simulator is introduced.

## 0.7.0

- Publish reusable idea research, controlled studies, configured policies and R-based outcomes.
- Retain server results permanently; render HTML/Markdown only when requested.
- Add fresh-data reruns, acquisition recipes, dataset pinning/expiry and online archive transfer.
- Require persistent Railway storage; add daily application backups before automatic cleanup.
- Keep exact offline replay optional and preserve existing baseline execution behavior.

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
