# BKTSTR v0.5 Strategy-Neutral Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce immutable tiered research-variable and strategy contracts, migrate the current baseline through a strategy-neutral orchestrator, and prove identical normalized trading output.

**Architecture:** Stable IDs and versions address immutable research-variable definitions and snapshots. Registries resolve Tier A sources, Tier B measurements, and strategy-owned filters into a read-only `VariableSet`; an immutable `StrategyDefinition` then drives the existing execution model through a compatibility adapter. Existing indicator formulas, provider behavior, cache semantics, execution behavior, and the legacy HTTP response remain unchanged.

**Tech Stack:** Python 3.12, frozen dataclasses, enums, pandas, existing `DerivedFrameCache`, pytest 8.4.1, standard-library JSON/hashlib

**Spec:** `docs/superpowers/specs/2026-08-24-v05-strategy-neutral-core-design.md`

## Global Constraints

- Tier A contains immutable objective point-in-time raw or normalized source arrays.
- Tier B contains immutable trusted structured data and validated deterministic measurements; regime, sentiment, fragility, VWAP, RSI14, and volume ratio are explicitly Tier B.
- Tier B cannot depend on Tier C or Tier D.
- Tier propagation is monotonic: composition may preserve or lower trust, never raise it.
- Tier C/D processing cannot overwrite, rescale, backfill, reclassify, or otherwise alter Tier A/B artifacts.
- Filters emit immutable measurements and strategies explicitly use them as `gate`, `rank`, or `annotate`.
- Missing required data fails with a deterministic replication suggestion; v0.5 never applies or saves a backfill.
- Forced execution is limited to explicitly forceable optional filters and always produces a degraded, non-canonical result.
- A missing primary entry-signal variable, dependency cycle, illegal tier promotion, schema mismatch, formula mismatch, corrupt Tier A/B snapshot, or mutation attempt is never forceable.
- Strategy decisions, thresholds, accepted signals, sizing, and execution results are not stored in the research-variable cache.
- The current compatibility response, formulas, fills, slippage, stops, targets, sizing, causal timing, summaries, frozen values, and production acceptance remain unchanged.
- `bktstr/__init__.py` remains the canonical version source and stays at `0.3.5` until the separate v0.5 release-preparation change.
- Use focused tests during Tasks 1-7. Run the complete suite, compile check, consistency check, and benchmark only in Task 8.
- Do not commit credentials, caches, bytecode, generated manifests, local reports, or machine-specific output.
- Treat non-goals as excluded from v0.5 acceptance, not as automatic future commitments. Preserve only the explicit contract seams described by the spec; do not add speculative workflow or infrastructure.

---

## File Map

### New domain modules

- `bktstr/variables.py` — tier enums, display/suggestion metadata, immutable variable definitions/snapshots, `VariableSet`, digests, and diagnostic errors.
- `bktstr/variable_registry.py` — immutable registration, lookup, dependency validation, and tier-graph validation.
- `bktstr/variable_store.py` — adapter from the existing `DerivedFrameCache` to immutable variable snapshots.
- `bktstr/measurements.py` — registered Tier A/B definitions and adapters around existing technical, regime, sentiment, and fragility calculations.
- `bktstr/strategies.py` — strategy parameters, filter roles, immutable definitions, resolution, registry, and baseline registration.
- `bktstr/orchestrator.py` — strategy-neutral data/measurement/filter/execution flow and run-result provenance.

### New tests and fixtures

- `tests/v05_fixtures.py` — deterministic synthetic intraday/daily inputs and current baseline request.
- `tests/test_v05_equivalence.py` — canonical-output helpers and frozen legacy/new/cache equivalence.
- `tests/test_variables.py` — tier, immutability, digest, display, and suggestion contracts.
- `tests/test_variable_registry.py` — registration, dependency, cycle, and tier validation.
- `tests/test_variable_store.py` — snapshot-store cache hit/miss, digest, corruption, and defensive-copy behavior.
- `tests/test_measurements.py` — current calculations exposed as Tier B variables without formula changes.
- `tests/test_strategies.py` — definition resolution, override validation, filter roles, and baseline registration.
- `tests/test_orchestrator.py` — data flow, diagnostics, forced execution, provenance, and compatibility behavior.

### Existing files

- Modify `bktstr/service.py` — retain `BacktestRequest`, provider selection, and compatibility payload formatting; delegate domain execution to the orchestrator.
- Modify `bktstr/server.py` — publish variable/strategy capability metadata without changing compatibility routing.
- Modify `bktstr/provenance.py` — expose artifact-tier semantics alongside the existing source registry.
- Modify `tests/test_service.py`, `tests/test_server.py`, and `tests/test_docs.py` — lock compatibility and capability contracts.
- Modify `docs/BKTSTR_SYSTEM_MANUAL.md`, `docs/roadmap/v1-release-plan.md`, and `CHANGELOG.md` — document v0.5 contracts and mark v0.5 active without changing the runtime version.

---

### Task 1: Freeze the Legacy Baseline and Canonical Comparison

**Files:**
- Create: `tests/v05_fixtures.py`
- Create: `tests/test_v05_equivalence.py`

**Interfaces:**
- Produces: `intraday_fixture() -> pd.DataFrame`, `daily_fixture(start: date, end: date, base: float, slope: float) -> pd.DataFrame`, `baseline_request() -> BacktestRequest`, and `canonical_trading_output(result: Mapping[str, Any]) -> bytes`.
- Consumed by: Tasks 5, 7, and 8.

- [ ] **Step 1: Add deterministic fixture builders**

Create `tests/v05_fixtures.py` with the fixed intraday bars already used by `tests/test_v034_cache_integration.py`, a deterministic business-day daily-bar builder, and the exact current baseline request:

```python
from datetime import date

import pandas as pd

from bktstr.service import BacktestRequest


def intraday_fixture() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            "2026-08-17 09:30:00",
            "2026-08-17 09:31:00",
            "2026-08-17 09:32:00",
        ],
        tz="America/New_York",
    )
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 98.0],
            "high": [101.0, 101.0, 99.0],
            "low": [99.0, 98.0, 96.0],
            "close": [101.0, 99.0, 97.0],
            "volume": [1000.0, 1000.0, 1000.0],
        },
        index=index,
    )


def daily_fixture(start: date, end: date, base: float, slope: float) -> pd.DataFrame:
    index = pd.date_range(start=start, end=end, freq="B", tz="America/New_York")
    close = [base + offset * slope for offset in range(len(index))]
    return pd.DataFrame(
        {
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "volume": [1000.0] * len(index),
        },
        index=index,
    )


def baseline_request() -> BacktestRequest:
    return BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-17",
        end="2026-08-17",
        timeframe="1m",
        side="short",
        entry="close.lt:1000",
        regime="day_sma20_slope5.lt:999,relative_return20.lt:999",
        benchmark="SOXX",
        sentiment=True,
        sentiment_sector_benchmark="SOXX",
        sentiment_market_benchmark="QQQ",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=1,
        slippage_bps=0,
    )
```

- [ ] **Step 2: Add canonical trading-output tests before new contracts exist**

Create `tests/test_v05_equivalence.py` with a canonical serializer that includes only `summary` and `trades`, plus a frozen current-engine assertion:

```python
import json
from typing import Any, Mapping

from bktstr.engine import BacktestConfig, run_backtest_on_bars

from tests.v05_fixtures import intraday_fixture


def canonical_trading_output(result: Mapping[str, Any]) -> bytes:
    return json.dumps(
        {"summary": result["summary"], "trades": result["trades"]},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def test_legacy_engine_fixture_remains_frozen():
    result = run_backtest_on_bars(
        intraday_fixture(),
        BacktestConfig(
            side="short",
            entry_rules="close.cross_below:vwap",
            stop_pct=10,
            target_pct=10,
            max_hold_minutes=1,
            slippage_bps=0,
        ),
    )
    assert result["summary"] == {
        "trades": 1,
        "wins": 1,
        "losses": 0,
        "win_rate_pct": 100.0,
        "total_pnl_dollars": 10.204082,
        "expected_pnl_per_trade": 10.204082,
        "average_return_pct": 1.020408,
        "max_drawdown_pct": 0.0,
        "ending_equity": 10010.204082,
    }
    assert result["trades"][0]["entry_price"] == 98.0
    assert result["trades"][0]["exit_price"] == 97.0
    assert result["trades"][0]["exit_reason"] == "end_of_data"
```

- [ ] **Step 3: Run the focused baseline tests**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_v05_equivalence.py -v
```

Expected: PASS on the unchanged legacy engine.

- [ ] **Step 4: Commit the frozen fixture**

```powershell
git add tests/v05_fixtures.py tests/test_v05_equivalence.py
git commit -m "test(core): freeze v0.3.5 baseline output"
```

---

### Task 2: Add Immutable Research-Variable Contracts

**Files:**
- Create: `bktstr/variables.py`
- Create: `tests/test_variables.py`

**Interfaces:**
- Produces: `DataTier`, `VariableKind`, `FilterRole`, `VariableRef`, `VariableDisplay`, `ReplicationSuggestionPolicy`, `ResearchVariableDefinition`, `ResearchVariableSnapshot`, `VariableSet`, `VariableDiagnostic`, `VariableContractError`, `inherited_tier`, and `snapshot_digest`.
- Consumed by: Tasks 3-7.

- [ ] **Step 1: Write failing tier, immutability, and suggestion tests**

Create `tests/test_variables.py` covering these exact behaviors:

```python
import pandas as pd
import pytest

from bktstr.variables import (
    DataTier,
    ReplicationSuggestionPolicy,
    ResearchVariableDefinition,
    ResearchVariableSnapshot,
    VariableKind,
    VariableRef,
    inherited_tier,
)


def test_tier_inheritance_never_improves_trust():
    assert inherited_tier((DataTier.A,), method_floor=DataTier.B) is DataTier.B
    assert inherited_tier((DataTier.B, DataTier.C), method_floor=DataTier.B) is DataTier.C
    assert inherited_tier((DataTier.A, DataTier.D), method_floor=DataTier.B) is DataTier.D


def test_tier_b_definition_rejects_lower_trust_inputs():
    with pytest.raises(ValueError, match="Tier B cannot depend on Tier C or Tier D"):
        ResearchVariableDefinition(
            id="sentiment.invalid",
            version="1.0.0",
            kind=VariableKind.MEASUREMENT,
            tier=DataTier.B,
            column="sentiment_invalid",
            value_dtype="float64",
            frequency="1d",
            inputs=(VariableRef("evidence.news", "1.0.0", DataTier.C),),
            plugin_id="invalid",
            plugin_version="1.0.0",
            formula_version="invalid-v1",
        )


def test_snapshot_returns_a_defensive_series_copy():
    definition = ResearchVariableDefinition.source(
        id="market.subject.close",
        version="1.0.0",
        tier=DataTier.A,
        column="close",
        value_dtype="float64",
        frequency="1m",
    )
    snapshot = ResearchVariableSnapshot.create(
        definition,
        pd.Series([100.0, 101.0], index=pd.date_range("2026-08-17", periods=2, freq="min", tz="UTC")),
        input_digests=(),
        provenance={"provider": "fixture"},
    )
    copy = snapshot.series
    copy.iloc[0] = -1.0
    assert snapshot.series.iloc[0] == 100.0


def test_neutral_suggestion_is_deterministic_and_never_applied():
    policy = ReplicationSuggestionPolicy.neutral(0.0, "Use a neutral score for review only")
    diagnostic = policy.suggest(variable_id="sentiment.direction", start="2026-08-01", end="2026-08-02")
    assert diagnostic.suggested_value == 0.0
    assert diagnostic.applied is False
```

- [ ] **Step 2: Run the tests and verify the missing-module failure**

Run:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_variables.py -v
```

Expected: collection FAIL because `bktstr.variables` does not exist.

- [ ] **Step 3: Implement the contracts with frozen dataclasses**

Implement in `bktstr/variables.py`:

```python
class DataTier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class VariableKind(str, Enum):
    SOURCE = "source"
    MEASUREMENT = "measurement"
    FILTER = "filter"


class FilterRole(str, Enum):
    GATE = "gate"
    RANK = "rank"
    ANNOTATE = "annotate"


def inherited_tier(inputs: tuple[DataTier, ...], *, method_floor: DataTier) -> DataTier:
    order = {DataTier.A: 0, DataTier.B: 1, DataTier.C: 2, DataTier.D: 3}
    return max((*inputs, method_floor), key=order.__getitem__)
```

Use frozen dataclasses for the remaining named interfaces. `ResearchVariableSnapshot.create` must deep-copy the input series, calculate a SHA-256 digest from the definition reference, one-column `dataframe_digest`, ordered input digests, and normalized provenance, and expose `.series` as a deep copy. `VariableSet` must implement `Mapping[str, ResearchVariableSnapshot]` and reject duplicate IDs. `ResearchVariableDefinition.__post_init__` must validate IDs/versions, expected ranges, unique inputs, calculated tier, and the Tier B dependency prohibition.

Use these public fields so later tasks share one concrete contract:

```python
@dataclass(frozen=True)
class VariableRef:
    id: str
    version: str
    tier: DataTier


@dataclass(frozen=True)
class VariableDisplay:
    label: str
    description: str
    category: str
    preferred_chart: str = "line"
    color_hint: str | None = None
    strategy_owned: bool = False


@dataclass(frozen=True)
class ResearchVariableDefinition:
    id: str
    version: str
    kind: VariableKind
    tier: DataTier
    column: str
    value_dtype: str
    frequency: str
    inputs: tuple[VariableRef, ...] = ()
    plugin_id: str | None = None
    plugin_version: str | None = None
    formula_version: str | None = None
    units: str | None = None
    expected_min: float | None = None
    expected_max: float | None = None
    suggestion_policy: ReplicationSuggestionPolicy = field(
        default_factory=ReplicationSuggestionPolicy.no_safe_suggestion
    )
    display: VariableDisplay | None = None

    @classmethod
    def source(
        cls,
        *,
        id: str,
        version: str,
        tier: DataTier,
        column: str,
        value_dtype: str,
        frequency: str,
        units: str | None = None,
        display: VariableDisplay | None = None,
    ) -> "ResearchVariableDefinition":
        # Return a SOURCE definition with no plugin, formula, or inputs.
```

`ReplicationSuggestionPolicy` stores `method`, optional `value`/`reference`, and `rationale`; its constructors return immutable policies. `VariableDiagnostic` stores `code`, `message`, variable reference, affected coverage/rules, suggestion method/value/reference/rationale, `applied=False`, `forceable`, and structured details. `ResearchVariableSnapshot` stores the definition, private copied series, digest, ordered input digests, normalized provenance, and coverage. `VariableSet` is keyed by stable variable ID and rejects two versions of the same ID in one set.

Suggestion policies must support `neutral`, `last_valid`, `historical_median`, `reference`, and `no_safe_suggestion`; they return diagnostics only and never modify a series.

- [ ] **Step 4: Run the focused tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_variables.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit the variable contracts**

```powershell
git add bktstr/variables.py tests/test_variables.py
git commit -m "feat(core): add tiered research variables"
```

---

### Task 3: Add the Immutable Variable Registry and Dependency Validation

**Files:**
- Create: `bktstr/variable_registry.py`
- Create: `tests/test_variable_registry.py`

**Interfaces:**
- Consumes: Task 2 variable definitions and errors.
- Produces: `VariableRegistry.register`, `VariableRegistry.get`, `VariableRegistry.require`, `VariableRegistry.validate_dependencies`, and `VariableRegistry.definitions`.

- [ ] **Step 1: Write failing registry tests**

Cover duplicate registration, exact-version lookup, missing variables, cycles, lower-tier dependencies, and a valid A-to-B graph:

```python
def test_registry_rejects_cycle_and_duplicate_identity():
    registry = VariableRegistry()
    registry.register(source_definition("market.close"))
    with pytest.raises(VariableContractError, match="already registered"):
        registry.register(source_definition("market.close"))


def test_registry_validates_a_to_b_graph():
    registry = VariableRegistry()
    registry.register(source_definition("market.close"))
    registry.register(measurement_definition("technical.rsi14", inputs=(ref("market.close"),)))
    ordered = registry.validate_dependencies((ref("technical.rsi14"),))
    assert [item.id for item in ordered] == ["market.close", "technical.rsi14"]
```

Build cycle fixtures by creating definitions through a test-only helper that bypasses registration order but not `validate_dependencies`.

- [ ] **Step 2: Run and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_variable_registry.py -v
```

Expected: collection FAIL because `bktstr.variable_registry` does not exist.

- [ ] **Step 3: Implement deterministic registry validation**

Store definitions under `(id, version)`. Registration is append-only; an existing identity with equal content is still rejected so callers cannot assume replacement semantics. Dependency validation performs a stable topological traversal, returns dependencies before consumers, and raises `VariableContractError` with codes `unknown_variable`, `dependency_cycle`, or `illegal_tier_dependency` plus structured details.

- [ ] **Step 4: Run the focused tests and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_variable_registry.py tests/test_variables.py -v
git add bktstr/variable_registry.py tests/test_variable_registry.py
git commit -m "feat(core): register immutable variable graphs"
```

---

### Task 4: Adapt the Derived Cache into a Variable Snapshot Store

**Files:**
- Create: `bktstr/variable_store.py`
- Create: `tests/test_variable_store.py`

**Interfaces:**
- Consumes: `DerivedFrameCache`, definitions, snapshots, and `VariableSet`.
- Produces: `VariableStoreResult` and `VariableSnapshotStore.resolve -> VariableStoreResult`.

- [ ] **Step 1: Write failing cache-adapter tests**

Define `VariableSnapshotStore.resolve` with this signature:

```python
def resolve(
    self,
    *,
    namespace: str,
    definitions: tuple[ResearchVariableDefinition, ...],
    dimensions: Mapping[str, Any],
    inputs: Mapping[str, pd.DataFrame | ResearchVariableSnapshot],
    provenance: Mapping[str, Any],
    compute: Callable[[], pd.DataFrame],
) -> VariableStoreResult:
    raise NotImplementedError
```

Tests must prove a cold miss then warm hit invokes `compute` once, snapshots expose individual arrays by stable ID, input changes change digests, formula versions change keys, mutation of returned series does not affect later reads, and corrupt payloads are recomputed with `recovered_corruption=True`.

- [ ] **Step 2: Run and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_variable_store.py -v
```

Expected: collection FAIL because `bktstr.variable_store` does not exist.

- [ ] **Step 3: Implement the store adapter**

Convert snapshot inputs to their content digests and DataFrame inputs through the existing cache digest path. Include sorted definition identities, tiers, columns, plugin/formula versions, and caller dimensions in cache dimensions. Require every declared output column and reject unexpected duplicate columns. Convert the cached frame into independent immutable snapshots and return existing `CacheStatus` metadata without caching strategy decisions.

- [ ] **Step 4: Run focused cache tests and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_variable_store.py tests/test_derived_cache.py -v
git add bktstr/variable_store.py tests/test_variable_store.py
git commit -m "feat(cache): store immutable research variables"
```

---

### Task 5: Register Existing Calculations as Tier B Measurements

**Files:**
- Create: `bktstr/measurements.py`
- Create: `tests/test_measurements.py`
- Modify: `bktstr/provenance.py`

**Interfaces:**
- Consumes: Tasks 2-4 plus unchanged functions in `engine.py`, `regime.py`, and `sentiment.py`.
- Produces: `baseline_variable_registry()`, `source_definitions(role)`, `intraday_definitions()`, `regime_definitions()`, `sentiment_definitions()`, and adapters returning `VariableStoreResult`.

- [ ] **Step 1: Write failing classification and formula-parity tests**

Tests must assert:

```python
def test_current_measurements_are_registered_tier_b():
    registry = baseline_variable_registry()
    for variable_id in [
        "technical.vwap",
        "technical.rsi14",
        "technical.volume_ratio20",
        "regime.relative_return20",
        "sentiment.direction",
        "sentiment.fragility",
    ]:
        assert registry.require(variable_id).tier is DataTier.B


def test_intraday_adapter_preserves_existing_formula(tmp_path):
    expected = prepare_bars_for_backtest(intraday_fixture(), regular_hours_only=True)
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))
    actual = compute_intraday_variables(
        store=store,
        raw_bars=intraday_fixture(),
        symbol="NVDA",
        timeframe="1m",
        regular_hours_only=True,
    ).legacy_frame
    pd.testing.assert_frame_equal(actual, expected)
```

Add equivalent parity checks for `build_daily_regime`, `build_daily_sentiment`, prior-day attachment, and the existing formula-version constants.

- [ ] **Step 2: Run and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_measurements.py -v
```

Expected: collection FAIL because `bktstr.measurements` does not exist.

- [ ] **Step 3: Register definitions without moving formulas**

Map stable IDs to existing column names. Source definitions are Tier A; every current deterministic technical/regime/sentiment output is Tier B with method floor B and only Tier A dependencies. Adapters call the existing functions and snapshot store, then expose `legacy_frame` with the original column names so rule evaluation and execution remain unchanged.

Update `capability_provenance()` to publish separate `artifact_tiers` descriptions while retaining the existing source IDs and source-tier metadata. Do not relabel the Tier A `price` source as Tier B; only its derived measurements are Tier B.

- [ ] **Step 4: Run focused calculation tests and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_measurements.py tests/test_regime.py tests/test_sentiment.py tests/test_engine.py -v
git add bktstr/measurements.py bktstr/provenance.py tests/test_measurements.py
git commit -m "feat(core): register baseline measurements"
```

---

### Task 6: Add Strategy, Filter, and Baseline Definitions

**Files:**
- Create: `bktstr/strategies.py`
- Create: `tests/test_strategies.py`

**Interfaces:**
- Consumes: variable references, registry, and `BacktestConfig` field semantics.
- Produces: `StrategyParameter`, `StrategyVariableUse`, `StrategyFilterDefinition`, `StrategyDefinition`, `ResolvedStrategy`, `StrategyRunRequest`, `StrategyRegistry`, `baseline_strategy_definition`, and `baseline_strategy_registry`.

- [ ] **Step 1: Write failing strategy-resolution tests**

Cover exact strategy/version lookup, immutable definitions, default resolution, typed/range-checked overrides, undeclared override rejection, filter roles, C/D opt-in, and forbidden direct mutation semantics:

```python
def test_baseline_resolves_current_execution_defaults():
    definition = baseline_strategy_definition()
    resolved = definition.resolve({})
    assert resolved.strategy_id == "bktstr.bearish-regime-scalp"
    assert resolved.execution_model_id == "bktstr.next-bar-open"
    assert resolved.values["stop_pct"] == 1.0
    assert resolved.values["target_pct"] == 3.0
    assert resolved.values["position_size"] == 1000.0
    assert resolved.values["slippage_bps"] == 2.0


def test_filter_role_is_explicit_and_does_not_mutate_variables():
    use = StrategyVariableUse(
        variable=VariableRef("sentiment.fragility", "1.0.0", DataTier.B),
        role=FilterRole.ANNOTATE,
        rule=None,
        forceable=False,
    )
    assert use.role is FilterRole.ANNOTATE
```

- [ ] **Step 2: Run and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_strategies.py -v
```

Expected: collection FAIL because `bktstr.strategies` does not exist.

- [ ] **Step 3: Implement immutable strategy resolution**

Use frozen dataclasses and an append-only registry. Parameters declare Python type, default, optional bounds/choices, and overridability. `StrategyDefinition.resolve` returns a complete immutable mapping and never mutates the definition. The baseline permits the current legacy fields as overrides and registers subject, sector, and market instrument roles; Tier B technical/context requirements; the current entry/regime rules; and execution model `bktstr.next-bar-open` version `1.0.0`.

`StrategyFilterDefinition` declares stable identity, owned output reference, input references, role, rule, tier, and `forceable`. Validate inherited tier and require explicit opt-in for C/D.

- [ ] **Step 4: Run focused tests and commit**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_strategies.py tests/test_variables.py -v
git add bktstr/strategies.py tests/test_strategies.py
git commit -m "feat(core): define versioned strategies"
```

---

### Task 7: Add the Strategy-Neutral Orchestrator and Legacy Adapter

**Files:**
- Create: `bktstr/orchestrator.py`
- Create: `tests/test_orchestrator.py`
- Modify: `bktstr/service.py`
- Modify: `tests/test_service.py`
- Modify: `tests/test_v05_equivalence.py`

**Interfaces:**
- Consumes: all Tasks 1-6 and existing provider/cache/execution interfaces.
- Produces: `OrchestratorDependencies`, `StrategyRunResult`, `execute_strategy_run`, `legacy_request_to_strategy_run`, and the unchanged `execute_backtest(request) -> dict` compatibility interface.

- [ ] **Step 1: Write failing orchestration and diagnostic tests**

Add tests that require:

- exact baseline strategy resolution and variable dependency trace;
- Tier A acquisition before Tier B calculation;
- current regime/sentiment prior-day attachment;
- missing-data failure containing ID, tier, coverage, affected rules, and deterministic suggestion;
- forced omission only for a declared forceable optional filter with confirmation;
- forced output marked `degraded=True`, `canonical=False`, and filter `not_evaluated`;
- missing primary signal input and immutable snapshot corruption remain non-forceable;
- provider secrets never appear in diagnostics or provenance.

Define the result contract:

```python
@dataclass(frozen=True)
class StrategyRunResult:
    resolved_strategy: ResolvedStrategy
    variables: VariableSet
    summary: Mapping[str, Any]
    trades: tuple[Mapping[str, Any], ...]
    data: Mapping[str, Any]
    provenance: Mapping[str, Any]
    diagnostics: tuple[VariableDiagnostic, ...] = ()
    degraded: bool = False
    canonical: bool = True
```

- [ ] **Step 2: Run and verify failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_orchestrator.py -v
```

Expected: collection FAIL because `bktstr.orchestrator` does not exist.

- [ ] **Step 3: Move orchestration behind domain contracts**

`OrchestratorDependencies` receives the cached provider, provider name, variable store, registries, cache toggle, and build identity. `execute_strategy_run` follows the spec's ordered flow and calls existing calculation and execution functions without changing them.

Refactor `service.execute_backtest` to:

1. select and wrap the existing provider exactly as before;
2. convert `BacktestRequest` with `legacy_request_to_strategy_run`;
3. create dependencies using the same raw and derived cache roots/toggles;
4. call `execute_strategy_run`;
5. serialize `StrategyRunResult` into the exact existing request/data/summary/trades payload.

Keep `BacktestRequest.from_values`, `provider_name_for_request`, and public error messages compatible. Do not add new query parameters in v0.5.

- [ ] **Step 4: Add legacy/new and cache-mode equivalence tests**

Using `tests.v05_fixtures`, monkeypatch the Massive provider exactly as existing service tests do. Execute the compatibility adapter with `execute_backtest(request)` and execute the new domain path directly with `execute_strategy_run(legacy_request_to_strategy_run(request), dependencies)` using the same provider, cache roots, and registries. Serialize the domain result through the same compatibility serializer, then assert:

```python
assert canonical_trading_output(new_result) == canonical_trading_output(legacy_result)
assert new_result["summary"] == legacy_result["summary"]
assert new_result["trades"] == legacy_result["trades"]
```

Run the new path with `BKTSTR_DERIVED_CACHE_ENABLED=false` and `true`; assert canonical trading bytes are equal and second-run variable-cache statuses are hits. The frozen Task 1 engine result and existing service tests remain the independent behavior references; do not retain a temporary legacy implementation.

- [ ] **Step 5: Run focused integration tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_orchestrator.py tests/test_service.py tests/test_v05_equivalence.py tests/test_v034_cache_integration.py -v
```

Expected: PASS with identical normalized output.

- [ ] **Step 6: Commit the orchestrator migration**

```powershell
git add bktstr/orchestrator.py bktstr/service.py tests/test_orchestrator.py tests/test_service.py tests/test_v05_equivalence.py
git commit -m "feat(core): run baseline through strategy contracts"
```

---

### Task 8: Publish Capabilities, Documentation, and Final Verification

**Files:**
- Modify: `bktstr/server.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_docs.py`
- Modify: `docs/BKTSTR_SYSTEM_MANUAL.md`
- Modify: `docs/roadmap/v1-release-plan.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: final variable, strategy, orchestrator, diagnostic, and provenance contracts.
- Produces: serialized capability metadata and v0.5 implementation documentation.

- [ ] **Step 1: Write failing capability/documentation assertions**

Require capabilities to publish:

```python
assert CAPABILITIES["research_variables"]["tiers"]["B"]["immutable"] is True
assert set(CAPABILITIES["research_variables"]["tiers"]["B"]["examples"]) >= {
    "regime", "sentiment", "fragility"
}
assert CAPABILITIES["strategies"]["baseline"]["id"] == "bktstr.bearish-regime-scalp"
assert CAPABILITIES["strategies"]["baseline"]["execution_model"] == "bktstr.next-bar-open"
assert CAPABILITIES["research_variables"]["automatic_backfill"] is False
```

Add documentation tests requiring the manual to define A-D, classify regime/sentiment/fragility as Tier B, explain immutable variables and monotonic inheritance, and document failure/suggestion/forced-run behavior.

- [ ] **Step 2: Run and verify focused failure**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_server.py tests/test_docs.py -v
```

Expected: FAIL because the new capability/documentation fields are absent.

- [ ] **Step 3: Publish capabilities and durable documentation**

Build capability dictionaries from registered definitions rather than duplicating formulas. Preserve every existing capability key. Update the system manual with the approved tier, variable, strategy, missing-data, and GUI-metadata contracts. In the release plan, mark v0.4.0 `Completed` and v0.5.0 `Active`. Add the strategy-neutral core contracts under `CHANGELOG.md` Unreleased. Do not change `__version__`, README current release, production-acceptance defaults, or runtime health version.

- [ ] **Step 4: Run focused documentation tests**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/test_server.py tests/test_docs.py -v
& '.\.venv\Scripts\python.exe' scripts/check_release_consistency.py
```

Expected: PASS and `Release consistency checks passed.`

- [ ] **Step 5: Commit capability and documentation changes**

```powershell
git add bktstr/server.py tests/test_server.py tests/test_docs.py docs/BKTSTR_SYSTEM_MANUAL.md docs/roadmap/v1-release-plan.md CHANGELOG.md
git commit -m "docs(core): publish strategy-neutral contracts"
```

- [ ] **Step 6: Run the one complete local verification gate**

```powershell
& '.\.venv\Scripts\python.exe' -m pytest
& '.\.venv\Scripts\python.exe' -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests
& '.\.venv\Scripts\python.exe' scripts/check_release_consistency.py
& '.\.venv\Scripts\python.exe' benchmarks/benchmark_cache.py
git diff --check main...HEAD
git status --short --branch
```

Expected:

- all tests pass with only the four existing NumPy timedelta deprecation warnings;
- compilation and consistency exit 0;
- benchmark reports one compute call, a cold miss, then a warm hit;
- diff check is empty and the tree is clean.

- [ ] **Step 7: Review the branch against v0.5 acceptance**

Confirm:

- every current measurement is Tier B and depends only on Tier A;
- no formula or execution function changed except orchestration call boundaries;
- A/B mutation and tier promotion fail in tests;
- missing-data suggestions never alter data;
- forced results cannot be canonical;
- legacy/new normalized trades and summaries are exactly equal;
- cache-on/cache-off trading bytes are exactly equal;
- no GUI, database, FastAPI, automatic backfill, C/D production source, or second strategy was added.

---

## Final Acceptance Checklist

- [ ] Tier A-D and monotonic propagation are executable contracts.
- [ ] Tier A/B definitions and snapshots are immutable.
- [ ] Regime, sentiment, fragility, and current technical measurements are registered Tier B variables.
- [ ] Research variables are addressable by stable ID/version and expose simple read-only arrays.
- [ ] Definitions and snapshots carry lineage, digests, suggestion policy, and GUI metadata.
- [ ] Strategy filters declare gate/rank/annotate behavior and cannot mutate variables.
- [ ] Missing evidence fails with an explanation and deterministic suggestion; no automatic backfill exists.
- [ ] Forced optional-filter omission requires confirmation and produces degraded non-canonical output.
- [ ] The baseline is an immutable `StrategyDefinition` executed by a strategy-neutral orchestrator.
- [ ] The legacy endpoint and payload remain compatible.
- [ ] Legacy/new normalized trade bytes and summaries are equal.
- [ ] Cache-on/cache-off trading output is equal.
- [ ] Existing production acceptance, formulas, execution behavior, and runtime version remain unchanged.
- [ ] Full pytest, compile, release consistency, cache benchmark, diff check, and CI pass.
