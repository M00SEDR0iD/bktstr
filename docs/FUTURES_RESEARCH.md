# Configured futures research

The existing configured-backtest worker accepts an explicit `futures-minute`
application. Equity application hashes and execution behavior are preserved.
Futures simulations use the shared orchestrator and the versioned
`futures-ohlcv.1.0.0` execution model. This is historical simulation only.

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
