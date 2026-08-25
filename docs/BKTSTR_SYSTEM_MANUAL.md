# BKTSTR System Manual

**Release:** v0.3.5  
**Behavioral baseline:** v0.3.3 trading semantics preserved; v0.3.4 adds integrated deterministic derived caching and v0.3.5 adds development/release reproducibility  
**Purpose:** architecture reference, research-methodology white paper, API/user manual, and future GUI implementation guide.

BKTSTR is a read-only historical market-research service. It separates slow background context from intermediate market regime and fast technical entries so that each layer can be tested independently and combined without hiding assumptions. It never places brokerage orders.

## Operational research doctrine — bearish-regime scalp discovery

BKTSTR's primary research use is to identify **short-duration scalp opportunities inside a broader bearish or deteriorating market regime**. The system should not promote an isolated intraday pattern merely because it backtests well on one subject or one period. Context is evaluated hierarchically:

```text
QQQ broad technology/risk environment
        ↓
SOXX semiconductor sector environment
        ↓
subject-specific state (NVDA/MU/AVGO/AMD/...)
        ↓
background sentiment + structural disagreement + volatility state
        ↓
intraday VWAP/RSI/volume trigger
        ↓
explicit execution simulation
```

For semiconductor research, QQQ and SOXX should be treated as permanent controls. The broad/sector layers answer whether the market is in a state where the short scalp tends to work; subject-level context answers which security may be the best expression of that state.

**Current research warning:** high `sentiment_fragility` is not a validated standalone bearish signal. Validation showed it can mix useful structural disagreement with execution-hostile volatility stress. Inspect `sentiment_component_spread` and `sentiment_volatility_stress` separately and validate across symbols/time periods.

## System schematic

```mermaid
flowchart TD
    P[Market data providers] --> C[Persistent raw OHLCV cache]
    C --> I[Intraday feature layer]
    C --> R[Daily regime layer]
    C --> S[Background sentiment layer]

    I --> T[Technical trigger]
    R --> G[Regime compatibility]
    S --> L[Sentiment level]
    S --> M[Sentiment momentum]
    S --> F[Sentiment fragility]
    S --> Q[Data provenance / quality]

    T --> E[Backtest execution engine]
    G --> E
    L --> E
    M --> E
    F --> E
    Q --> E

    E --> O[Trade records + summary metrics]
    O --> API[JSON API]
    API --> GUI[Future GUI / AI research client]
```

The intended hierarchy is:

1. **Background sentiment** — What does the market appear to believe about the asset over weeks to months?
2. **Sentiment transition/fragility** — Is that belief coherent and stable, or is it beginning to break?
3. **Regime** — Is the current daily market environment favorable to this kind of trade?
4. **Technical signal** — Is there a specific intraday entry now?
5. **Execution model** — What would have happened under explicit fills, slippage, stops, targets, and time limits?

No layer should silently substitute for another. A strong technical setup can exist inside a hostile sentiment background; the system should expose that disagreement rather than erase it.

## Persistent cache architecture

The existing raw OHLCV cache is Layer 0. v0.3.4 adds integrated reusable deterministic layers **without caching trading decisions**:

```text
L0 raw OHLCV cache
      ↓
L1 deterministic feature cache
      ↓
L2 daily context/regime/sentiment cache
      ↓
live strategy thresholds + live execution simulation
      ↓
L3 optional exact-result memoization
```

### L1 — deterministic features

Cache values that do not change when a researcher adjusts thresholds or execution settings: session VWAP, RSI14, volume ratio, moving averages/slopes, returns, EMA, ATR, realized volatility, 52-week-high distance, and persistence primitives.

### L2 — context

Cache deterministic subject/sector/market context keyed by the subject, sector benchmark, market benchmark, clean-data profile/source set, formula version, look-ahead rule, and digests of all input DataFrames. This includes relative returns and sentiment component/output columns.

### Never cache strategy decisions

Do not persist Boolean "bearish regime passed", entry-rule pass/fail, tuned threshold pass/fail, side, stop/target choices, or "take short" decisions. Thresholds and execution stay live so research hypotheses remain easy to change.

### Invalidation

Derived cache entries are content-addressed by deterministic DataFrame digests plus explicit semantic dimensions (`formula_version`, timeframe/session model, benchmark mapping, profile/sources). Changing input data or a formula version creates a new key rather than mutating old cached research state. Atomic writes prevent partial entries; unreadable entries degrade to cache misses.

### Railway storage

The merge package's default path resolution is:

1. `BKTSTR_DERIVED_CACHE_DIR`
2. `BKTSTR_CACHE_DIR/derived`
3. `RAILWAY_VOLUME_MOUNT_PATH/bktstr-cache/derived`
4. `/tmp/bktstr-cache/derived`

The persistent Railway volume should therefore carry both the raw cache and the derived cache in production. Set `BKTSTR_DERIVED_CACHE_ENABLED=false` to perform a cache-off equality control; the default is enabled. `BKTSTR_DERIVED_CACHE_DIR` can override the derived-cache path.

## Core execution model

BKTSTR evaluates entry rules on a completed bar and enters on the **next bar open**. This prevents same-bar-close look-ahead. Long and short underlying-equity trades are supported. Slippage is applied adversely. If both stop and target are touched within the same OHLC bar, BKTSTR assumes the stop was hit first, which is deliberately conservative.

By default, indicators and trades use regular US equity hours. Session VWAP resets each trading session. Cross rules are session-bounded so the first bar of a new session cannot create a synthetic cross against the previous day's last bar.

The current aggregate max-drawdown statistic is based on closed-trade equity rather than minute-by-minute mark-to-market equity. MFE and MAE are recorded per trade.

## Layer definitions

### Technical layer

The intraday layer currently provides session VWAP, RSI(14), and a rolling 20-bar volume ratio. Rules use a compact `field.operator:value` syntax and comma-separated rules are ANDed.

Examples:

```text
close.cross_below:vwap
rsi14.lt:50
volume_ratio20.gt:1.1
```

A typical short discovery trigger is:

```text
close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.1
```

### Daily regime layer

The regime layer is an intermediate-timescale filter. It uses completed daily data and can compare the subject with a benchmark.

Current fields include:

- `day_close`
- `day_sma20`
- `day_sma50`
- `day_sma20_slope5`
- `day_return20`
- `benchmark_return20`
- `relative_return20`

Example:

```text
regime=day_sma20_slope5.lt:0,relative_return20.lt:0
benchmark=SOXX
```

Regime rules are hard filters: if the regime condition is false, the technical setup cannot open a trade.

## Sentiment layer definitions

The sentiment layer is **price-implied background investor sentiment**, not a direct survey of investor opinions. In v0.3.3 the only active source is clean historical market price data. The layer uses daily OHLCV from the subject, a sector benchmark, and a broad-market benchmark.

For an NVDA study the normal mapping is:

```text
subject = NVDA
sector benchmark = SOXX
market benchmark = QQQ
```

The sentiment layer intentionally exposes three separate state variables:

- `sentiment_direction`: established background sentiment level, -1 bearish to +1 bullish.
- `sentiment_momentum`: direction in which that sentiment level is changing, -1 deteriorating to +1 improving.
- `sentiment_fragility`: instability/contradiction in the sentiment state, 0 coherent to 1 highly fragile.

This separation is important. A stock can remain structurally bullish while its leadership collapses and volatility expands. Averaging those observations into a single neutral number would hide a potentially important narrative transition.

### 1. Leadership component

**Weight in sentiment level: 35%.**

Leadership compares subject returns with both the sector and market over approximately three and six trading months:

```text
relative_return63_sector  = subject_return63  - sector_return63
relative_return126_sector = subject_return126 - sector_return126
relative_return63_market  = subject_return63  - market_return63
relative_return126_market = subject_return126 - market_return126
```

Each relative-return series is smoothly compressed to -1..+1 with a hyperbolic tangent transform. The 63-session series uses a 10 percentage-point scale and the 126-session series uses a 20 percentage-point scale. The four transformed values are averaged into `sentiment_leadership_score`.

Interpretation:

- Near +1: persistent leadership/outperformance.
- Near 0: broadly keeping pace.
- Near -1: persistent loss of leadership.

### 2. Trend component

**Weight in sentiment level: 30%.**

To preserve comparability with v0.3.1, v0.3.2 keeps the established slow-trend definition. It calculates 50-, 100-, and 200-session simple moving averages and measures each one's percentage change over 20 completed sessions:

```text
sma50_slope20
sma100_slope20
sma200_slope20
```

Those slopes are compressed to -1..+1 and averaged into `sentiment_trend_score`.

EMA values are now also exposed (`ema50`, `ema100`, `ema200`) for persistence/transition analysis, but v0.3.2 does not simultaneously replace the legacy trend formula. This isolates the persistence change for cleaner research comparison.

### 3. Peak-psychology component

**Weight in sentiment level: 20%.**

`distance_from_52w_high` measures the subject close against the highest close in the previous 252 sessions. The component maps approximately as follows:

| Distance from 252-session high | `sentiment_peak_score` |
| ---: | ---: |
| 0% | +1.00 |
| -5% | +0.75 |
| -10% | +0.50 |
| -20% | 0.00 |
| -30% | -0.50 |
| -40% or lower | -1.00 |

The intent is behavioral: persistent proximity to records often reinforces a winner narrative, while a large sustained drawdown can weaken that narrative.

### 4. Persistence component — v0.3.2

**Weight in sentiment level: 15%.**

v0.3.1 counted how many of the previous 20 sessions closed below SMA50. That field (`days_below_sma50`) remains available as a diagnostic, but it no longer drives the persistence component.

v0.3.2 uses two exponentially weighted measurements over a 40-session span.

#### Persistence occupancy

First define whether the subject is below EMA50:

```text
below_ema50 = 1 when close < EMA50, otherwise 0
```

Then calculate:

```text
persistence_occupancy = EWMA(below_ema50, span=40)
```

Range is 0..1. A high value means recent history has repeatedly spent time below the responsive trend anchor.

The directional occupancy score is:

```text
occupancy_score = 1 - 2 * persistence_occupancy
```

So 0% occupancy maps to +1 and 100% occupancy maps to -1.

#### Persistence pressure

BKTSTR computes 20-session Average True Range from daily high/low/close data and normalizes distance from EMA50 by volatility:

```text
normalized_ema50_distance = (close - EMA50) / ATR20
```

This matters because being $3 below an EMA is significant in a calm stock and less significant in a highly volatile stock.

That normalized distance is exponentially smoothed:

```text
persistence_pressure_raw = EWMA(normalized_ema50_distance, span=40)
pressure_score = tanh(persistence_pressure_raw)
```

Finally:

```text
sentiment_persistence_score = mean(occupancy_score, pressure_score)
```

This captures both **how persistently** price is below trend and **how far** below trend it tends to be, while adjusting for volatility.

### Sentiment level

The four component scores are combined using:

```text
leadership  35%
trend       30%
peak        20%
persistence 15%
```

The weighted mean over available components is `sentiment_direction` in the range -1..+1.

`sentiment_completeness` equals the sum of available component weights. Missing long-history features reduce completeness instead of being silently imputed.

`sentiment_confidence` incorporates completeness, absolute component magnitude, and absolute sentiment direction. Low agreement among strong components can therefore produce low confidence even when each input is individually large.

### Informational multipliers

For research, BKTSTR exposes symmetric bounded multipliers:

```text
adjustment = 0.5 * sentiment_direction * sentiment_confidence
sentiment_multiplier_long  = clip(1 + adjustment, 0.5, 1.5)
sentiment_multiplier_short = clip(1 - adjustment, 0.5, 1.5)
```

**These do not change position size in v0.3.3.** They are metadata only. Position sizing should not be altered until the layer proves predictive out of sample.

## Sentiment momentum

Momentum measures the change in the sentiment level itself:

```text
sentiment_momentum20 = clip(direction_today - direction_20_sessions_ago, -1, +1)
sentiment_momentum60 = clip(direction_today - direction_60_sessions_ago, -1, +1)
```

The combined score is:

```text
sentiment_momentum = 65% * momentum20 + 35% * momentum60
```

Weights are renormalized if one lookback is unavailable.

Interpretation:

- Positive: sentiment is improving.
- Near zero: sentiment level is stable.
- Negative: sentiment is deteriorating.

Momentum is intentionally separate from level. A strongly bullish asset can have sharply negative sentiment momentum during an early narrative break.

## Sentiment fragility

Fragility is **non-directional** and ranges from 0 to 1. High fragility means the sentiment state is internally contradictory, changing rapidly, experiencing volatility expansion, or some combination of those conditions.

### Component spread — 50% of fragility

`sentiment_component_spread` is the weighted standard deviation of the four sentiment components around the weighted `sentiment_direction`, clipped to 0..1.

Low spread means leadership, trend, peak psychology, and persistence broadly agree. High spread means the story is internally fractured.

### Volatility stress — 30% of fragility

BKTSTR exposes:

- `atr20_pct`: ATR20 divided by close, percent.
- `realized_vol20`: annualized standard deviation of daily returns over 20 sessions.
- `realized_vol60`: annualized standard deviation over 60 sessions.
- `volatility_ratio`: realized_vol20 / realized_vol60.

Two expansion measures are used:

```text
vol_ratio_stress = clip((volatility_ratio - 1) / 0.75, 0, 1)
atr_stress = clip((atr20_pct / median60(atr20_pct) - 1) / 0.75, 0, 1)
```

Their available-value mean is `sentiment_volatility_stress`.

A value near zero means short-horizon volatility is not elevated relative to its recent baseline. A value near one means volatility has expanded substantially.

### Transition speed — 20% of fragility

The third fragility ingredient is `abs(sentiment_momentum20)`. A rapid change in either direction can make the prevailing sentiment state less stable.

Final formula:

```text
sentiment_fragility =
    50% * component_spread
  + 30% * volatility_stress
  + 20% * abs(momentum20)
```

Available inputs are renormalized and the result is clipped to 0..1.

Fragility must never be interpreted as automatically bearish. High fragility plus bearish momentum and a bearish regime can strengthen a short thesis; high fragility plus improving momentum and bullish confirmation can describe an upside transition.

## Data provenance and quality tiers

The provenance system is designed to prevent lower-confidence data from entering a backtest invisibly.

| Tier | Label | Definition | v0.3.3 status |
| --- | --- | --- | --- |
| A | Clean | Objective point-in-time market data with deterministic transforms | **Enabled** |
| B | Structured | Reliable structured data requiring interpretation/revision discipline | Not yet enabled |
| C | Derived | Model-transformed narrative/text data | Not yet enabled |
| D | Experimental | Esoteric, low-confidence, or difficult-to-reconstruct data | Not yet enabled |

The source registry already reserves future source IDs:

- `price` — Tier A, available now.
- `options` — Tier B, unavailable in v0.3.2.
- `analyst` — Tier B, unavailable.
- `macro` — Tier B, unavailable.
- `news` — Tier C, unavailable/model-derived.
- `social` — Tier D, unavailable/model-derived and not currently marked point-in-time safe.

### Profiles and toggles

The v0.3.3 sentiment request accepts:

```text
sentiment_data_profile=clean
sentiment_sources=price
```

`clean` is the default and currently the only available profile. If a request asks for an unavailable source, the request fails explicitly. BKTSTR will not replace the missing source with another source and will not silently promote a lower-quality tier.

Every sentiment-enabled response includes provenance metadata such as:

```json
{
  "profile": "clean",
  "non_clean_data_used": false,
  "all_point_in_time_safe": true,
  "sources": [
    {
      "id": "price",
      "tier": "A",
      "point_in_time_safe": true,
      "model_derived": false,
      "available": true
    }
  ]
}
```

A future GUI should surface `non_clean_data_used` prominently whenever it becomes true.

## Look-ahead safety

Look-ahead safety is a hard requirement, not an optional display property.

For an intraday trading session on date D, BKTSTR attaches the latest completed sentiment row whose daily date is **strictly earlier than D**. Therefore a Tuesday intraday trade can use Monday's completed daily data but never Tuesday's eventual close/high/low.

Momentum, persistence, volatility, and fragility are all computed within the historical daily series before this strict prior-day attachment occurs.

Non-price sources added in the future must also be point-in-time reconstructable. For revision-prone macro or analyst data, the system should use the value actually published and known on the historical date, not a later revised value.

## v0.3.3 coverage behavior

v0.3.3 distinguishes optional historical warm-up from required backtest-period data. Missing optional warm-up must not convert an otherwise valid request into a 502. Instead BKTSTR uses available history, reduces completeness where appropriate, and reports:

```text
requested_warmup_start
coverage_start
coverage_end
warmup_degraded
subject / sector / market coverage
fallback_used
```

Missing required-period data remains a hard failure. Cache hits must preserve exactly the same coverage/provenance semantics as uncached computation.

## Agent/API control path

Some execution environments cannot reliably reach the Railway hostname directly. The proven agent path is:

```text
ChatGPT → Supabase.execute_sql → pg_net net.http_get → Railway BKTSTR → net._http_response → ChatGPT
```

See `AGENT_BACKTEST_RUNBOOK.md` for exact SQL, timeout/polling discipline, frozen NVDA parameters, percentage semantics, and standard QQQ/SOXX controls.

## API examples

### Sentiment only

```text
GET /api/v1/backtest?
symbol=NVDA&
start=2026-06-01&
end=2026-08-21&
timeframe=1m&
side=short&
entry=close.cross_below%3Avwap%2Crsi14.lt%3A50%2Cvolume_ratio20.gt%3A1.1&
sentiment=true&
sentiment_sector_benchmark=SOXX&
sentiment_market_benchmark=QQQ&
sentiment_data_profile=clean&
sentiment_sources=price
```

### Regime + sentiment

```text
regime=day_sma20_slope5.lt:0,relative_return20.lt:0
benchmark=SOXX
sentiment=true
sentiment_sector_benchmark=SOXX
sentiment_market_benchmark=QQQ
sentiment_data_profile=clean
```

The regime remains a hard trade filter. Sentiment outputs remain research metadata unless a later release explicitly introduces validated sizing behavior.

## GUI implementation contract

The machine-readable companion file is:

```text
docs/gui/sentiment-data-contract.json
```

Future GUI code should treat that contract and `/api/v1/capabilities` as the authoritative field vocabulary.

Recommended GUI panels:

### 1. Sentiment state card

Display three independent gauges:

- **Level**: `sentiment_direction` (-1..+1)
- **Momentum**: `sentiment_momentum` (-1..+1)
- **Fragility**: `sentiment_fragility` (0..1)

Do not collapse the three into one unlabeled color.

### 2. Component decomposition

Show four component bars:

- Leadership
- Trend
- Peak psychology
- Persistence

A disagreement visualization is especially important because `sentiment_component_spread` is itself meaningful.

### 3. Transition/volatility panel

Show:

- `persistence_occupancy`
- `persistence_pressure_raw`
- `volatility_ratio`
- `sentiment_volatility_stress`
- 20/60 sentiment momentum

### 4. Provenance badge

Always display the active data profile. If `non_clean_data_used=true`, display a visible warning/badge and list every active source with its quality tier. A user should be able to turn optional non-clean families on/off independently when those sources are implemented.

### 5. Research-vs-execution distinction

GUI labels must distinguish:

- informational multiplier
- actual configured `position_size`

In v0.3.3 the multiplier must never be displayed as though it changed P/L sizing.

### Suggested semantic labels

These labels are presentation guidance only; the raw numeric value remains authoritative.

**Sentiment direction**

- -1.00 to -0.60: strongly bearish
- -0.60 to -0.20: bearish
- -0.20 to +0.20: neutral/mixed
- +0.20 to +0.60: bullish
- +0.60 to +1.00: strongly bullish

**Fragility**

- 0.00 to 0.25: coherent/stable
- 0.25 to 0.50: mild tension
- 0.50 to 0.75: fragile
- 0.75 to 1.00: highly unstable

These thresholds should remain GUI labels, not trade rules, unless independently validated.

## Response field glossary

### Sentiment outputs

- `sentiment_direction`: weighted background sentiment level, -1..+1.
- `sentiment_confidence`: confidence in level interpretation, 0..1.
- `sentiment_completeness`: fraction of component weight with valid data, 0..1.
- `sentiment_multiplier_long`: informational long-side prior, 0.5..1.5.
- `sentiment_multiplier_short`: informational short-side prior, 0.5..1.5.
- `sentiment_momentum20`: 20-session change in sentiment direction, -1..+1.
- `sentiment_momentum60`: 60-session change, -1..+1.
- `sentiment_momentum`: weighted 20/60-session change, -1..+1.
- `sentiment_component_spread`: disagreement among level components, 0..1.
- `sentiment_volatility_stress`: short-vs-medium volatility expansion, 0..1.
- `sentiment_fragility`: combined non-directional instability, 0..1.

### Persistence/volatility diagnostics

- `ema50`, `ema100`, `ema200`: subject exponential moving averages.
- `atr20_pct`: ATR20 as percent of subject close.
- `realized_vol20`, `realized_vol60`: annualized realized volatility in percent.
- `volatility_ratio`: realized_vol20 / realized_vol60.
- `persistence_occupancy`: EWMA probability-like occupancy below EMA50, 0..1.
- `normalized_ema50_distance`: close-minus-EMA50 measured in ATR20 units.
- `persistence_pressure_raw`: EWMA of normalized EMA50 distance.

## Research discipline

The sentiment system is designed to create hypotheses, not certify them. Recommended workflow:

1. Define sentiment formulas before viewing validation results.
2. Treat heavily explored periods as training/discovery data.
3. Validate on untouched periods/symbols when provider history permits.
4. Keep non-clean data disabled during clean baseline testing.
5. When adding a new source family, test the clean model and augmented model side by side.
6. Never infer that a better in-sample P/L automatically justifies larger live position sizing.
7. Preserve all provenance metadata with research outputs.


### Current validation status (August 2026 research pass)

The following findings guide future experiments but are not production trade rules:

- NVDA Mar-Dec 2025 bearish-regime control: 30 trades, 40% wins, approximately -$2.27 EV/trade.
- NVDA Jun-Aug 2026 bearish-regime control: 7 trades, 85.7% wins, approximately +$6.09 EV/trade.
- Fragility threshold sweeps did not show reliable monotonicity.
- High-fragility NVDA and MU samples were strong but tiny; AVGO remained negative and AMD produced no qualifying high-fragility trades.
- AVGO's high-fragility state carried much greater volatility stress and multiple stop-outs, supporting separation of structural disagreement from volatility chaos.
- SOXX and QQQ both improved materially from 2025 to Jun-Aug 2026 under the same frozen scalp trigger, supporting the QQQ → SOXX → subject hierarchy.

Treat the heavily explored NVDA 2025 and Jun-Aug 2026 samples as discovery data. New claims require untouched periods and cross-symbol validation.

## v0.3.5 release identity and development workflow

v0.3.5 does not change trading formulas. It adds an explicit release identity so a production result can be tied back to the source and deterministic formula/cache contract that produced it. `/health` reports `version` plus `git_commit`, `git_branch`, `git_repo`, `deployment_id`, and optional `build_time`. Railway-sourced identity comes from `RAILWAY_GIT_COMMIT_SHA`, `RAILWAY_GIT_BRANCH`, `RAILWAY_GIT_REPO_OWNER`, `RAILWAY_GIT_REPO_NAME`, and `RAILWAY_DEPLOYMENT_ID`; local verification may override commit/build time with `BKTSTR_GIT_COMMIT` and `BKTSTR_BUILD_TIME`.

`/api/v1/capabilities` also publishes:

- intraday feature formula version;
- daily regime formula version;
- daily sentiment formula version;
- derived cache format version.

The development path is intentionally separated from the research/control plane:

```text
feature branch → GitHub CI → merge main → Railway auto-deploy
                                      ↓
                           Supabase pg_net acceptance
```

GitHub CI runs the full test suite, Python compile checks, a generated-file hygiene check, and the cache benchmark. Generated `__pycache__`, `.pyc/.pyo`, and `.pytest_cache` artifacts must never be tracked. After deployment, `scripts/production_acceptance.py` reruns the frozen NVDA Jun-Aug 2026 control twice and requires identical trading output plus warm derived-cache hits.

When direct GitHub access from an agent is unavailable, the **GitHub-through-Supabase** recovery bridge in `ops/supabase/GITHUB_BRIDGE.md` uses `pg_net` to resolve an exact commit/tree and retrieve source bodies from GitHub's raw-content host. Every recovered source body is retained with its Git blob SHA so integrity can be verified. This bridge is operational tooling only and never enters the backtest execution path.

## v0.5 strategy-neutral core contracts

v0.5 publishes domain contracts for research-variable metadata and the existing baseline strategy. It does not change the v0.3.5 runtime version, trading formulas, execution behavior, legacy endpoint, or production-acceptance defaults.

### Research variables and evidence tiers

Every variable has a stable ID and semantic version. Tier A is immutable point-in-time source data; Tier B is trusted structured point-in-time data or validated deterministic measurement data; Tier C is lower-trust model-derived evidence; and Tier D is experimental or difficult-to-reconstruct evidence. Current technical measurements, regime, sentiment, and fragility are Tier B variables that depend only on Tier A source variables.

Definitions and snapshots are immutable variables: consumers receive read-only values, lineage, digests, coverage, deterministic suggestion policy, and optional GUI metadata. Monotonic inheritance means a derived variable cannot claim a higher trust tier than any of its inputs. Consequently Tier C or Tier D evidence cannot influence a Tier A or Tier B variable.

`/api/v1/capabilities` builds `research_variables` metadata from registered definitions, including tiers, stable identities, dependencies, lineage, suggestion policy, and GUI metadata. This makes the registered contract—not a copied formula list—the source of truth for a future GUI.

### Baseline strategy contract

The existing baseline is the immutable `StrategyDefinition` `bktstr.bearish-regime-scalp`, executed by the strategy-neutral `bktstr.next-bar-open` execution model. Its registered parameter, variable-use, and filter metadata are published at `strategies.baseline` in `/api/v1/capabilities`; this publication does not add a second strategy or alter the legacy request payload.

Strategy filters declare one of gate, rank, or annotate behavior and cannot mutate research variables. A strategy must explicitly opt into Tier C or Tier D evidence, and lower-trust evidence remains unable to change Tier A or Tier B measurements.

### Missing data, suggestions, and forced runs

Missing required evidence fails with an explanation and a deterministic suggestion. Suggestions are diagnostics only: they never modify source data or variable snapshots, and there is no automatic backfill. Optional missing evidence may be omitted only when its registered filter is both optional and forceable and the caller explicitly confirms a forced run. Such a forced run is degraded and non-canonical; it cannot be presented as a canonical result.

The capability response publishes registered metadata only; it does not promise confirmation requirements or forced-run status. Run-specific information is split across run diagnostics, filter decisions and provenance, and the top-level StrategyRunResult degraded/canonical status when a registered optional, forceable filter is used; the current baseline has no registered filters.

## v0.6 research API

v0.6 makes the typed REST API BKTSTR's programmatic research interface. A
future MCP server is only an adapter over these same services; it does not add
agent-specific rules or a second experiment model. The complete machine-readable
contract is available at `GET /openapi.json`.

### Authentication and discovery

`GET /health` and `GET /api/v1/health` are unauthenticated deployment probes.
Every other `/api/v1/*` route requires one service bearer key:

```text
Authorization: Bearer <BKTSTR_API_KEY>
```

Start with `GET /api/v1/capabilities`. It publishes registered strategy and
research-variable metadata, available sources and timeframe limits, operation
names, execution policy, idempotency behavior, experiment states, and API/build
identity. Registry-derived v0.5 variable tiers, immutability, no-automatic-
backfill policy, and strategy evidence rules remain authoritative.

### Research operations and polling

Use high-level operations rather than client-supplied formulas:

- `POST /api/v1/backtests` runs one registered strategy configuration.
- `POST /api/v1/parameter-sweeps`, `POST /api/v1/compare`, and
  `POST /api/v1/regime-comparison` submit bounded research jobs.
- `GET /api/v1/backtests/{experiment_id}` is the typed backtest view.
- `GET /api/v1/experiments/{experiment_id}` is the canonical shared experiment
  envelope for polling any operation.

All submissions create an immutable experiment with canonical typed request,
result, and provenance artifacts on the Railway volume. A completed result
records the exact strategy configuration, dates, symbol, timeframe, selected
data source/version and coverage, slippage/execution assumptions, regime
settings, BKTSTR version and commit. Use the experiment ID when comparing or
reproducing research.

Every submitted operation accepts `execution: "auto" | "sync" | "async"`.
`auto` completes a bounded single backtest inline and queues parameter sweeps,
comparisons, and regime comparisons. `sync` either completes immediately or
returns `409 execution_not_available`; it is never silently converted to a
queue. `async` always returns a queued experiment. Poll until the immutable
envelope status is `completed` or `failed`:

```json
{
  "experiment_id": "exp_...",
  "operation": "parameter_sweep",
  "status": "queued",
  "execution": "async"
}
```

Mutating operations accept `Idempotency-Key`. Retrying the same key with the
same canonical typed request returns the original experiment; using it for a
different request returns `409 idempotency_conflict` rather than silently
duplicating a hypothesis.

### Market-data inspection and errors

`GET /api/v1/market-data` returns read-only normalized `timestamp`, `open`,
`high`, `low`, `close`, and `volume` rows. Supply `symbol`, `start`, `end`, and
`timeframe`, with optional `source`, `limit` (1 through 1000), and opaque
`cursor`. Use `next_cursor` unchanged for the following page. A cursor is bound
to the canonical market-data identity, so it cannot page a different symbol,
range, timeframe, or source. Responses never expose provider credentials or
provider raw response payloads.

Errors use one typed envelope with a stable `code`, human-readable `message`,
structured `details`, and `request_id`. Common client actions are: correct the
reported fields after `422 validation_error`; inspect input after `400
invalid_request`; authenticate after `401 unauthorized`; wait/poll after `202`;
adjust a forced inline request after `409 execution_not_available`; and retry a
provider failure only after evaluating the returned error code.

The former `GET /api/v1/backtest` endpoint is intentionally removed in v0.6 to
avoid a second execution path. It returns `410 legacy_endpoint_removed`, a
`Link: </openapi.json>; rel="alternate"` header, and a migration target of
`POST /api/v1/backtests`.

### Railway configuration

Set `BKTSTR_API_KEY` as the single bearer credential. Set
`BKTSTR_EXPERIMENT_DIR` to a directory on the Railway volume so SQLite records
and immutable artifacts survive a deployment. `BKTSTR_SYNC_MAX_CALENDAR_DAYS`
sets the inclusive maximum span for an inline sync backtest (default `31`), and
`BKTSTR_MAX_SWEEP_VARIANTS` caps parameter sweeps (default `500`).
`BKTSTR_LEGACY_BACKTEST_SUNSET` is migration metadata for clients of the
removed endpoint; it does not re-enable the old threaded server or a second
execution path.

## Known limitations

- v0.3.3 sentiment is price-implied, not literal investor-opinion measurement.
- Provider history limits can reduce completeness for long-lookback fields.
- The current sentiment weights are research priors, not statistically fitted production coefficients.
- The multiplier is informational only.
- Options, analyst, macro, news, and social sources are registered but not implemented.
- Historical options contracts are not backtested by the underlying-equity engine.
- Aggregate drawdown is still closed-trade equity rather than full mark-to-market.

## Versioning

This research branch advances sub-builds through `0.3.9`; the next release after `0.3.9` becomes `0.4.0`.
