# BKTSTR v0.3.2 Sentiment Transition & Provenance Design

## Goal
Extend the price-implied sentiment layer with volatility-aware persistence, sentiment momentum, sentiment fragility, and explicit source provenance while preserving point-in-time safety and keeping all non-clean sources disabled by default.

## Scope
v0.3.2 remains a clean-market-data release. It does not add news, analyst, options, macro, social, or other non-price sources. It adds the controls and provenance contract needed to incorporate such sources later without silently mixing them into rigorous backtests.

## Sentiment level
Keep v0.3.1 leadership, trend, and peak components. Replace the persistence component with an EMA/volatility-aware score while retaining legacy raw fields for compatibility and diagnosis.

### Persistence inputs
- `ema50`, `ema100`, `ema200`: exponential moving averages of subject close.
- `atr20_pct`: 20-session simple average of true range divided by close, percent.
- `realized_vol20`, `realized_vol60`: annualized standard deviation of daily close-to-close percentage returns, percent.
- `volatility_ratio`: `realized_vol20 / realized_vol60`.
- `persistence_occupancy`: EWMA(span=40) of an indicator equal to 1 when close < EMA50 and 0 otherwise. Range 0..1.
- `normalized_ema50_distance`: `(close - ema50) / ATR20`.
- `persistence_pressure_raw`: EWMA(span=40) of `normalized_ema50_distance`.
- `sentiment_persistence_score`: equal-weight mean of `1 - 2*persistence_occupancy` and `tanh(persistence_pressure_raw)`, clipped to -1..1.

This lets persistence distinguish time spent below trend from magnitude of below-trend pressure, normalized for changing volatility.

## Sentiment momentum
Calculate sentiment level first, then measure its change:
- `sentiment_momentum20 = clip(sentiment_direction - sentiment_direction.shift(20), -1, 1)`
- `sentiment_momentum60 = clip(sentiment_direction - sentiment_direction.shift(60), -1, 1)`
- `sentiment_momentum = 0.65*momentum20 + 0.35*momentum60`, renormalized across available inputs.

Positive means improving sentiment; negative means deteriorating sentiment.

## Sentiment fragility
Fragility is non-directional and ranges 0..1. It is the weighted mean of three transparent ingredients:
1. `sentiment_component_spread` (50%): weighted standard deviation of available component scores around `sentiment_direction`, clipped to 0..1.
2. `sentiment_volatility_stress` (30%): average of:
   - `clip((volatility_ratio - 1) / 0.75, 0, 1)`
   - `clip((atr20_pct / rolling_median_60(atr20_pct) - 1) / 0.75, 0, 1)`
3. `abs(sentiment_momentum20)` (20%).

The weighted mean is renormalized over available ingredients and clipped to 0..1.

Interpretation: high fragility means the established sentiment state is internally contradictory, changing quickly, experiencing volatility expansion, or some combination of those. Fragility does not imply bullish or bearish direction.

## Confidence and multiplier
Keep v0.3.1 `sentiment_confidence` and informational long/short multipliers unchanged except that the updated persistence component can alter sentiment level. Multipliers remain informational and MUST NOT change position size in v0.3.2.

## Provenance and data profiles
Every sentiment source must be registered with:
- source id
- quality tier
- description
- point-in-time-safe flag
- model-derived flag
- enabled status

Quality tiers:
- A clean: objective point-in-time market data.
- B structured: reliable but interpretation-sensitive structured data.
- C derived: model-transformed narrative or text data.
- D experimental: esoteric or difficult-to-reconstruct inputs.

v0.3.2 implements only source `price` (Tier A). Query controls:
- `sentiment_data_profile=clean` (default when sentiment enabled)
- `sentiment_sources=price` (optional explicit source list)

Requests for unavailable/non-clean sources must fail explicitly rather than silently substitute data. Response metadata must include `non_clean_data_used`, active profile, enabled sources, tiers, point-in-time safety, and model-derived status.

## Look-ahead safety
All daily sentiment rows remain attached strictly from the latest completed daily row before the intraday session date. Momentum and fragility are computed only from those historical daily rows.

## Documentation contract
Add `docs/BKTSTR_SYSTEM_MANUAL.md` as the human-readable system white paper/user manual, including Mermaid architecture/data-flow diagrams, formulas, definitions, score interpretation, provenance tiers, API examples, and GUI guidance. Add `docs/gui/sentiment-data-contract.json` as a machine-readable contract for future GUI work.

## Versioning
Release version is 0.3.2. Continue 0.3.x through 0.3.9 before rolling to 0.4.0.
