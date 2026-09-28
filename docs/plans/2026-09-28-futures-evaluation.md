# Futures execution and bounded mean-reversion research

The user authorized implementation, production deployment, and discretionary study settings. Keep generic execution infrastructure in code; keep the NQ account, signals, parameter grid, dates, and conclusions in immutable research records.

## Design

Extend the existing application profile and configured-backtest worker. An explicit futures application supplies multiplier, tick, session-to-contract mapping, and evaluation-account terms. Preserve old equity revision digests and execution behavior. The shared orchestrator dispatches a separately versioned futures OHLCV model. Reuse the existing catalog, dataset snapshots, worker, protocols, artifacts, archive transfer, and reports.

Futures policies contain a validated signal recipe, fixed stop distance, risk budget, contract cap, reward/risk, holding limit, cooldown, and costs. Signals use completed bars; entries occur at the next open. Reset indicators each pinned session. Size integer contracts using planned stop dollars. Round entry/stop/target prices to valid ticks, require the requested reward/risk to be exactly representable. Deduct per-side commission and adverse slippage. Stops fill adversely through opening gaps. Stop wins a same-bar stop/target tie. Flatten at the last session close. Preserve all eligible signals and rejection reasons.

Record trade net PnL, initial R, price and cost details, adverse excursion through simulated exit, conservative intrabar drawdown bound, daily equity, and both closed/marked metrics. One-minute OHLC cannot reveal within-bar ordering; identify bounds as bounds. Evaluation windows start at every held-out session, stop on a $48,000 floor touch or $53,000 completed-trade balance, and expire after ten trades. Also report disjoint ten-trade blocks. Include censored starts. Report pass rates and drawdown without claiming guaranteed compliance.

The research session is the US cash-equity window, 09:30 to scheduled close on XNYS trading dates. This is a deliberate NQ trading-hours restriction, not a claim that CME's full calendar is XNYS. Verify raw data against the pinned schedule; never fill missing executable bars. Exclude any incomplete session for all candidates, retain exclusions, and censor challenge windows that cross excluded sessions. Keep raw contract rollover identity pinned; positions and features never cross sessions or contracts.

## Frozen initial campaign

Before outcomes, persist 36 policies: VWAP deviation re-entry, 20-bar Bollinger re-entry, and 14-bar RSI recovery; two signal thresholds each, stops of 10/20 points, and risk budgets of $250/$400/$500. Cap at two NQ contracts. All use 1.5R, 60-minute maximum hold, five-minute cooldown, 30-minute warmup, and no entries in the final 30 minutes. Base costs are $2.50 per contract per side plus one tick each side; stress uses $3.50 and two ticks. These are stated assumptions, not a broker quote.

Development is October 2024 through March 2025. Monthly walk-forward validation is April 2025 through June 2026, selecting by net EV in R from the preceding six months among candidates with at least 100 training trades and two trades/session; if none qualify, abstain. Require positive training EV, break ties by stable policy ID. Freeze the procedure before validation. July through September 25, 2026 is final holdout. Final settings are selected once from January-June 2026 and remain fixed. Preserve every candidate's development attempts. Do not select or expand parameters from held-out results.

A policy is not promoted merely because one ten-trade window passes. Report independent-block and overlapping-start success, confidence intervals, trade frequency, cost stress, fold stability, and all failures. If the goal has no supported solution, report that result rather than overfit the holdout.

## Implementation and review plan

1. Add failing behavioral tests for futures application compatibility, tick/R sizing, gap stops, ambiguous bars, commissions, causal signals, daily resets, and challenge-floor/target order.
2. Implement typed futures rules, pure execution, challenge summaries, shared-orchestrator dispatch, and configured-worker persistence. Keep equity schemas and metrics unchanged.
3. Audit the existing downloaded inputs using a pinned calendar package and published exchange calendars. Freeze the study, versions, costs, snapshots, and exclusions before measuring returns.
4. Run the bounded campaign through the existing durable worker. Retain artifacts and comparisons; render HTML and Markdown reports. Analyze validation and final outcomes only after the prescribed selection stage.
5. Run focused and full tests, release consistency, compilation, cache benchmark, and independent review. Publish infrastructure changes as a focused PR, wait for CI, deploy, and verify the exact production build.
6. Transfer completed research records and reports to server storage using existing archive operations, verify retrieval, and present results with experiment IDs and limitations.

Review focus: old revision hashes, future data affecting signals or selection, whole-contract risk with costs, adverse stop gaps, floor-before-target ordering, incomplete sessions and censored windows, repeatable saved results, and final holdout exposure.
