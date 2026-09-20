# Local strategy configuration

Task 1 adds a Python/file interface for deterministic minute-bar research. The
HTTP API continues to expose the existing baseline; there is no strategy upload
endpoint. See the [example](../examples/strategies/macro-context-v1.json).

```python
import asyncio
from bktstr.strategy_config import load_strategy
from bktstr.runtime import run_configured_strategy

manifest = load_strategy("examples/strategies/macro-context-v1.json")
result = asyncio.run(run_configured_strategy(manifest))
print(manifest.digest)
```

Loading and compilation are offline. Running acquires historical market data
through the existing provider/cache pipeline and requires its usual credentials.
The example contains illustrative research inputs, not measured performance.
Despite its future-facing filename, it enables no macro or model filter.

## Supported contract

All objects reject unknown fields. Numeric values reject booleans and nonfinite
numbers. Money is in the instrument's account currency (USD for this equity/ETF
scope); `stop_pct` and `target_pct` use percentage points (1 means 1 percent),
`slippage_bps` uses basis points, and holding limits use minutes. Position size
retains the existing engine's per-trade notional sizing semantics; this is not a
portfolio exposure or buying-power enforcement feature.

- Supply schema version `1.0.0`, a dot-separated strategy ID, a semantic strategy
  version, hypothesis, falsification, and explicit `subject` symbol. The example
  uses the neutral `bktstr.minute-strategy` identity. Custom identities are allowed;
  the baseline identity cannot be redefined.
- Use one-minute bars, XNYS, America/New_York, regular hours and same-day exits.
  Entry time bounds are optional local exchange times.
- Entry rules and technical gates support `open`, `high`, `low`, `close`, `volume`,
  `vwap`, `rsi14`, and `volume_ratio20`. Operators are `lt`, `lte`, `gt`, `gte`,
  `eq`, `cross_above`, and `cross_below`. Commas mean AND.
- Regime gates support registered daily regime measurements. Relative/benchmark
  rules require an explicit `benchmark` symbol. Macro, model, sentiment, ranking,
  and annotation filters are not supported by this configuration interface yet.
  Daily regime rules use comparison operators only, not crossings.
- `evaluation.start` and `end` select the historical run. `variant_budget` records
  research intent; cross-experiment enforcement and held-out comparisons are Task 5.
- `model_policy` must be disabled. An optional pinned Jev identifier and question
  are fingerprinted planning metadata and do not affect trades.
- Paper documents must declare `paper_limits`; execution rejects paper mode until
  Task 6. Historical documents do not need paper limits.
- Compilation accepts a semantic execution version so planned assumptions can be
  fingerprinted. Running currently accepts only `bktstr.next-bar-open@1.0.0`.
  Unimplemented modes and versions fail before provider selection.

## Reproducibility

The compiler normalizes defaults, numeric units, dates, and rule syntax, then
hashes canonical JSON with SHA-256. JSON object key order does not affect the
digest; array order is retained. The manifest's document and existing strategy
contracts are immutable. Runtime recompiles its canonical source before use.
Result provenance includes the complete normalized document and digest.

Changing rules, risk settings, model questions, or execution assumptions changes
the digest. Increment the strategy version when revising a theory. Local loading
does not maintain a persistent identity/version registry: cross-run revision
enforcement and durable experiment integration remain later work.
