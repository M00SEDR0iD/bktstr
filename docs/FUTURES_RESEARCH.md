# Configured futures research

The existing configured-backtest worker accepts an explicit `futures-minute`
application. Equity application hashes and execution behavior are preserved.
Futures simulations use the shared orchestrator and the versioned
`futures-ohlcv.1.0.0`, `futures-ohlcv.1.1.0` and `futures-ohlcv.1.2.0` execution models. This is historical simulation only.

## Signal lookbacks and entry regime in version 1.2

Version 1.2 adds optional `signal_period` (integer 2 through 390). It sets the
Bollinger mean and population standard-deviation window, the VWAP deviation
window, or the RSI exponential lookback. The defaults remain 20 for Bollinger
and VWAP and 14 for RSI. RSI uses alpha `1 / signal_period`, `adjust=false`,
and that many observations. VWAP's center still accumulates from the cash open.

An optional entry filter uses `efficiency_period` (integer 2 through 390) and
`max_efficiency_ratio` (0 through 1 inclusive); specify both or neither.
For each completed candle, calculate:

```text
efficiency_ratio = abs(close[t] - close[t-n]) / sum(abs(close changes), last n changes)
```

A complete flat window has ratio zero. The ratio is one for a monotonic price
path and lower when prices reverse. This measures the observed price path; it
does not label future returns or establish a trading edge. Entry uses only the
preceding completed candle. A ratio above the configured maximum rejects the
entry as `trending_regime`; equality is allowed. Missing history rejects as
`regime_unavailable`. Existing position, warmup, cutoff, cooldown and volatility
checks retain priority. Protective stops and exits continue independently.

When the filter is enabled, signal decisions and accepted trades retain
`efficiency_ratio_at_entry`, with null for unavailable observations. The engine
does not create signals while detector history is insufficient. Supply enough
premarket candles if entries must become eligible immediately after the stated
opening exclusion; a period is not a substitute for warmup data.

All three new fields require execution model 1.2; older models reject them even
when explicitly null. Omitting the controls retains version 1.1 numerical
behavior and does not add ratio metadata. Existing saved recipes and results
remain available. A rollback can replay older model versions but cannot execute
1.2 recipes; retain their build and pinned inputs for exact replay.

## Opening reference and volatility sizing in version 1.1

Version 1.1 explicitly requires `opening_bias`, `cash_start_offset`, and
`quantity_step`. `cash_start_offset` counts supplied warmup bars before the cash
open; `warmup_minutes` counts the entry exclusion after that open. Supply complete
premarket bars within the pinned dataset schedule when indicators need them.
Rolling close indicators and ATR may use those earlier bars; session VWAP starts
at the cash open. The opening reference is the first cash candle's high/low
midpoint, available only after that candle closes. With `opening_bias: true`, a
long requires both signal close and slipped entry below the reference; a short
requires both above it. Equality rejects the trade. The reference changes only
trade direction eligibility, never the fixed stop or target.

Optional `atr_period` and `atr_reference_points` must appear together. ATR is the
simple rolling mean of true range over completed candles, including the preceding
close in true range. Entry quantity is:

```text
base_quantity = risk_budget / (stop_points * instrument_multiplier)
scaled_quantity = base_quantity * atr_reference_points / prior_bar_ATR
quantity = floor(min(max_contracts, scaled_quantity) / quantity_step) * quantity_step
```

Without ATR options, use the unscaled base quantity. Insufficient or zero ATR
blocks entry; a quantity below one step also blocks entry. Freeze quantity for
the entire position. `risk_budget` is a reference sizing budget under ATR scaling,
not a hard dollar-risk cap; `max_contracts` is the explicit cap. Decisions and
trades retain the reference price, entry ATR and proposed integer quantity.
No fractional exchange contracts are created. For MNQ, five contracts represent
half an NQ's dollar exposure, with MNQ candles, multiplier and commissions.

Zero cooldown allows the next minute's eligible entry after a closed trade. It
does not create repeated fills within one candle. `last_entry_buffer: 0` allows
entries through the last supplied minute, followed by mandatory session close.
Version 1.0 rejects all new options and preserves its previous serialized recipe.

## Application and policy

Register applications through `/api/v1/research/revisions/application`. Supply
one subject instrument, a complete unadjusted dataset snapshot, and `futures`
terms: `multiplier`, `tick_size`, `starting_balance`, `failure_floor`,
`profit_target`, `max_trades`, `contracts` mapping every scored session date to
its explicit delivery contract, and `excluded_sessions`. No account size or
instrument multiplier is an engine default. The pinned XNYS schedule represents
the chosen cash-hours research window, not the full CME exchange calendar.

Register policies through the existing policy revision route. The futures recipe
requires `execution_model`, `signal` with `kind` and `threshold`, `stop_points`,
`risk_budget`, `max_contracts`, `reward_risk`, `commission_per_side`,
`slippage_ticks`, `warmup_minutes`, `last_entry_buffer`, `max_hold_minutes`, and
`cooldown_minutes`. Unsupported fields fail validation. Application bindings and
strategy parameters remain separate immutable revisions.

Available detectors are session VWAP deviation recovery, 20-bar Bollinger
re-entry, and 14-bar exponential RSI threshold recovery. VWAP deviation uses
the rolling 20-close population standard deviation. RSI uses exponential means
with alpha 1/14, adjust=false, and 14 observations. Each session resets all
indicators. Detectors return long and short events after completed bars.

## Execution and accounting

Signals enter at the next minute open with adverse tick slippage. Stops and
targets must be exact tick multiples. Size is the smaller of the whole-contract
risk-budget quantity and the declared contract cap. Planned R excludes costs;
actual losses can exceed it. Fees apply on both sides, including time exits.
Stops fill beyond their level on adverse opening gaps. A candle touching both
stop and target exits at the stop. Targets receive no favorable gap improvement.
Positions close at the last scored session close and never cross roll boundaries.

The worker retains trades, signal acceptances and rejections, daily equity,
versioned metric definitions, and evaluation attempts. Main drawdown is a
conservative intrabar liquidation-equity bound; minute-close drawdown is also
reported. The bound assumes favorable extremes precede adverse extremes when
OHLC cannot establish order. Daily Sharpe uses all scored session returns.

Evaluation attempts stop at a fixed floor touch, a completed-trade profit target,
or the declared trade limit. Attempts crossing excluded sessions are censored.
Failed attempts retain the last closed balance and a breach-equity bound; they
do not invent an exact forced-liquidation fill. Reports distinguish overlapping
session starts from disjoint trade blocks. Neither establishes independent trials
or guaranteed future success.

## Research controls

Use existing ideas, studies, policy revisions, protocols, and durable experiment
IDs. Freeze the candidate budget, chronological selection rule, dates, costs,
input hashes, and exclusions before outcomes. Keep outcome labels out of signal
inputs. Chronological walk-forward selection belongs in a frozen campaign,
not in an adaptive execution loop. Keep all tested candidates and failed runs.

No quote/queue model, margin schedule, overnight trading, broker order flow,
firm-specific consistency rules, or trailing prop-firm floor is implemented.
Data downloads require separate coverage checks before snapshot registration.
The existing equity acquisition/rerun recipe is not a futures data recipe;
futures exact replay uses its pinned uploaded snapshot and original build.

Rollback to the preceding release leaves futures records stored but not runnable.
Export retained research before a rollback; do not reinterpret a futures record
through the old equity engine.
