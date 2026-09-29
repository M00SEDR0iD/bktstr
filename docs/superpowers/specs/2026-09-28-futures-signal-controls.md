# Futures signal controls

Research has plateaued below the requested account-pass gate using fixed
indicator periods. Add deterministic entry controls to the shared futures
executor so different mean-reversion hypotheses can use the existing saved
research pipeline. This is a capability release, separate from recipe trials.

## Contract

- New execution identity: `futures-ohlcv.1.2.0`; release `0.10.0`.
- Versions 1.0 and 1.1 reject the three new fields, including explicit nulls.
- Optional `signal_period` is an integer from 2 through 390. If omitted,
  preserve 20 bars for Bollinger/VWAP deviation and 14 for RSI. VWAP's center
  still starts at the cash open; its deviation window changes. RSI alpha is
  1/period, adjust=false, with period observations, as in the existing formula.
- Optional `efficiency_period` (integer 2..390) and
  `max_efficiency_ratio` (0..1 inclusive) must appear together. Compute
  abs(close[t]-close[t-n]) / sum(abs(close changes), last n changes).
  A complete flat window has ratio zero. Insufficient history is unavailable.
- Entry uses the ratio at the preceding completed candle. Values above the
  maximum reject new entries with `trending_regime`; unavailable values reject
  with `regime_unavailable`. Equality is allowed. Retain
  `efficiency_ratio_at_entry` in accepted trades and signal decisions when the
  filter is configured, with null for unavailable observations.
- Existing warmup, position, cutoff, cooldown and volatility checks retain
  priority; the new regime checks precede opening-direction eligibility.
  Protective management never depends on the entry filter.
- Omitting the new controls preserves version1.1 numerical behavior. No new
  account assumptions, data source, dependencies, or broker execution.

## Research after release

Keep all user-requested trading rules. Use periods no longer than30 with the
existing30premarket candles, preserving eligibility from9:35. Register new
recipe batches before scoring development data. Compare filter-free controls
on identical inputs. No later-period test until the fixed35% gate is reached.
