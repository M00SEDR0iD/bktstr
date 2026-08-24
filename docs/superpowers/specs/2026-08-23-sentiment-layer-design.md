# BKTSTR v0.3.1 Background Investor Sentiment Layer Design

## Goal
Add a slow-moving, historically reconstructable investor-sentiment layer that is independent of intraday technical entries and intermediate regime filters. The layer produces a continuous directional prior, confidence, and bounded long/short multipliers without changing trade sizing in v0.3.1.

## Interface
A backtest may enable sentiment with two explicit benchmarks:
- `sentiment=true`
- `sentiment_sector_benchmark=SOXX`
- `sentiment_market_benchmark=QQQ`

When enabled, BKTSTR fetches daily bars for the subject and both benchmarks with a 400-calendar-day warm-up. Sentiment is computed once per completed daily bar and attached to each intraday session using only the latest sentiment row strictly before that session date.

## Raw Features
- `relative_return63_sector`
- `relative_return126_sector`
- `relative_return63_market`
- `relative_return126_market`
- `distance_from_52w_high`
- `sma50_slope20`
- `sma100_slope20`
- `sma200_slope20`
- `days_below_sma50` (count over the latest 20 completed daily bars)

Missing long-lookback features are allowed. They lower score completeness/confidence rather than invalidating otherwise available shorter-horizon evidence.

## Component Scores
All component scores are bounded to `[-1, +1]`, where negative is bearish background sentiment and positive is bullish.

- Leadership, weight 0.35: average of tanh-normalized 63/126-day relative returns versus sector and market benchmarks. Scales are 10 percentage points for 63-day and 20 percentage points for 126-day returns.
- Trend acceptance, weight 0.30: average of tanh-normalized 20-day slopes of SMA50/SMA100/SMA200. Scales are 5/4/3 percentage points respectively.
- Peak psychology, weight 0.20: `clip(1 + distance_from_52w_high / 20, -1, 1)`. At the 52-week high this is +1, a 20% drawdown is neutral, and a 40% drawdown is -1.
- Persistence, weight 0.15: `clip(1 - days_below_sma50 / 10, -1, 1)`. Zero of the last 20 days below SMA50 is +1, 10 is neutral, 20 is -1.

## Final Score
`sentiment_direction` is the weighted mean of available component scores, renormalizing weights over available components only.

`sentiment_completeness` is the sum of weights for available components, from 0 to 1.

`sentiment_confidence = completeness * sqrt(abs(direction) * weighted_mean_abs_component_score)`, bounded to `[0, 1]`. This falls when evidence is missing, weak, or internally conflicting.

Directional multipliers are bounded and symmetric:
- `sentiment_multiplier_long = clip(1 + 0.5 * direction * confidence, 0.5, 1.5)`
- `sentiment_multiplier_short = clip(1 - 0.5 * direction * confidence, 0.5, 1.5)`

v0.3.1 exposes these multipliers but does not alter `position_size` or P&L. This prevents unvalidated sentiment weights from silently changing risk.

## Trade Output
When sentiment is enabled, each trade includes:
- `sentiment_direction`
- `sentiment_confidence`
- `sentiment_completeness`
- `sentiment_multiplier_long`
- `sentiment_multiplier_short`
- `sentiment_multiplier` (the side-specific multiplier)
- `sentiment_leadership_score`
- `sentiment_trend_score`
- `sentiment_peak_score`
- `sentiment_persistence_score`

The summary includes average direction, confidence, and side-specific multiplier over executed trades.

## Data and Look-ahead Rules
- Subject/benchmark daily bars use the existing persistent raw-bar cache.
- Intraday session D may only use a sentiment row with date `< D`.
- Current-session daily close can never affect that session's trade.
- The score uses only market-derived historical data in v0.3.1; options/news/analyst/social inputs are intentionally deferred.

## API / Capabilities
`/api/v1/backtest` accepts the three sentiment parameters above. `/api/v1/capabilities` documents the sentiment outputs, components, weights, benchmark parameters, and look-ahead guard.

## Versioning
This release is `0.3.1`. Continue `0.3.2` through `0.3.9`, then roll to `0.4.0`.
