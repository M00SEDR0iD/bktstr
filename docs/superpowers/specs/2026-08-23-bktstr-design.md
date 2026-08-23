# BKTSTR v0.1 Design

## Goal
Provide a Railway-hosted, read-only granular backtesting service that ChatGPT can call directly without the user moving strategy files or results between systems.

## Architecture
A small Python HTTP service accepts compact GET requests, validates them, retrieves OHLCV bars through a provider adapter, evaluates causal indicators/rules, and simulates trades with next-bar execution. Massive is the primary historical provider; Yahoo is a recent-intraday bootstrap fallback. Results are JSON and include both aggregate statistics and trade records.

## Safety and realism constraints
- No brokerage connectivity or order placement.
- Signals use only information available through the signal bar close.
- Entry occurs at the following bar open.
- Slippage is always adverse.
- If both stop and target lie inside one OHLC bar, assume stop first.
- Default to regular market hours and same-day closure.
- Limit request range and returned trade count.

## v0.1 scope
Single-symbol underlying equity/ETF tests, long/short, VWAP/RSI/volume rules, stop/target/time exits, MFE/MAE, summary metrics, Massive/Yahoo adapters, Railway deployment.

## Deferred
Historical options, multi-symbol conditions, macro-regime joins, parameter sweeps, persistent result storage, mark-to-market portfolio equity, auth, remote MCP transport.
