from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

import bktstr.orchestrator as orchestrator
from bktstr.cache import BarCache, CachedProvider
from bktstr.measurements import baseline_variable_registry
from bktstr.orchestrator import (
    OrchestratorDependencies,
    StrategyRunError,
    execute_strategy_run,
    legacy_request_to_strategy_run,
)
from bktstr.regime import build_daily_regime
from bktstr.sentiment import build_daily_sentiment
from bktstr.service import BacktestRequest
from bktstr.strategies import (
    StrategyFilterDefinition,
    StrategyRegistry,
    baseline_strategy_definition,
)
from bktstr.variable_store import VariableSnapshotStore
from bktstr.variables import (
    DataTier,
    FilterRole,
    ResearchVariableDefinition,
    VariableContractError,
    VariableRef,
)
from bktstr_cache.derived import DerivedFrameCache
from tests.v05_fixtures import daily_fixture, intraday_fixture


class FixtureProvider:
    """External-data boundary fake with realistic Tier A frames."""

    def __init__(
        self,
        *,
        empty_intraday: bool = False,
        secret: str = "fixture-secret",
        event_log: list[str] | None = None,
    ) -> None:
        self.empty_intraday = empty_intraday
        self.secret = secret
        self.event_log = event_log
        self.calls: list[tuple[str, date, date, str]] = []

    async def fetch_bars(
        self, symbol: str, start: date, end: date, timeframe: str = "1m"
    ) -> pd.DataFrame:
        self.calls.append((symbol, start, end, timeframe))
        if self.event_log is not None:
            self.event_log.append(f"tier_a:{symbol}:{timeframe}")
        if timeframe == "1d":
            return _daily_bars(symbol, start, end)
        if self.empty_intraday:
            return intraday_fixture().iloc[0:0]
        return intraday_fixture()


class ExplodingProvider(FixtureProvider):
    async def fetch_bars(
        self, symbol: str, start: date, end: date, timeframe: str = "1m"
    ) -> pd.DataFrame:
        raise RuntimeError(f"provider rejected request with credential {self.secret}")


def _daily_bars(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Return the same date-indexed provider history regardless of fetch chunking."""
    frame = daily_fixture(
        date(2024, 1, 1),
        date(2027, 12, 31),
        {"NVDA": 300.0, "SOXX": 200.0, "QQQ": 500.0}[symbol],
        {"NVDA": -0.2, "SOXX": 0.1, "QQQ": 0.05}[symbol],
    )
    return frame.loc[(frame.index.date >= start) & (frame.index.date <= end)].copy()


def _dependencies(
    tmp_path: Path,
    upstream: FixtureProvider,
    *,
    strategy_registry: StrategyRegistry | None = None,
    variable_registry=None,
    derived_cache_enabled: bool = True,
) -> OrchestratorDependencies:
    return OrchestratorDependencies(
        provider=CachedProvider(
            upstream,
            BarCache(tmp_path / "raw"),
            provider_name="fixture",
            today_fn=lambda: date(2026, 8, 25),
        ),
        provider_name="fixture",
        variable_store=VariableSnapshotStore(DerivedFrameCache(tmp_path / "derived")),
        variable_registry=variable_registry or baseline_variable_registry(),
        strategy_registry=strategy_registry or _baseline_registry(),
        derived_cache_enabled=derived_cache_enabled,
        build_identity={"git_commit": "fixture-commit"},
    )


def _baseline_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(baseline_strategy_definition())
    return registry


def _request(*, with_context: bool = False, confirm_degraded: bool = False):
    request = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-17",
        end="2026-08-17",
        timeframe="1m",
        side="short",
        entry="close.lt:1000" if with_context else "close.cross_below:vwap",
        regime=("day_sma20_slope5.lt:999,relative_return20.lt:999" if with_context else None),
        benchmark="SOXX" if with_context else None,
        sentiment=with_context,
        sentiment_sector_benchmark="SOXX" if with_context else None,
        sentiment_market_benchmark="QQQ" if with_context else None,
        stop_pct=10.0,
        target_pct=10.0,
        max_hold_minutes=1,
        slippage_bps=0.0,
    )
    return replace(legacy_request_to_strategy_run(request), confirm_degraded=confirm_degraded)


def _run(request, dependencies: OrchestratorDependencies):
    return asyncio.run(execute_strategy_run(request, dependencies))


def test_baseline_run_resolves_exact_strategy_and_records_tiered_dependency_trace(
    tmp_path: Path,
):
    # Break caught: the compatibility baseline could bypass its versioned strategy or lose B-to-A lineage.
    result = _run(_request(), _dependencies(tmp_path, FixtureProvider()))

    assert result.resolved_strategy.strategy_id == "bktstr.bearish-regime-scalp"
    assert result.resolved_strategy.strategy_version == "1.0.0"
    assert result.resolved_strategy.values["entry_rules"] == "close.cross_below:vwap"
    assert result.degraded is False
    assert result.canonical is True
    trace = {item["id"]: item for item in result.provenance["dependency_trace"]}
    assert trace["market.subject.close"]["tier"] == "A"
    assert trace["technical.vwap"]["tier"] == "B"
    assert trace["technical.vwap"]["dependencies"] == (
        "market.subject.high",
        "market.subject.low",
        "market.subject.close",
        "market.subject.volume",
    )
    assert result.variables["technical.vwap"].tier is DataTier.B
    assert result.variables["technical.vwap"].series.index.equals(intraday_fixture().index)


def test_trace_records_actual_tier_a_artifacts_with_coverage_and_cache(
    tmp_path: Path,
):
    # Break caught: daily inputs could be represented only by an empty registry entry instead of their actual immutable acquisition.
    result = _run(_request(with_context=True), _dependencies(tmp_path, FixtureProvider()))
    trace = {item["id"]: item for item in result.provenance["dependency_trace"]}

    subject_sources = trace["market.subject.close"]["materializations"]
    intraday_source = next(
        item
        for item in subject_sources
        if item["scope"]["purpose"] == "intraday" and item["scope"]["timeframe"] == "1m"
    )
    assert intraday_source["artifact_id"] == (
        "market.subject.close@intraday:subject:1m:2026-08-17:2026-08-17"
    )
    assert intraday_source["definition"] == {
        "id": "market.subject.close",
        "version": "1.0.0",
        "kind": "source",
        "tier": "A",
        "column": "close",
        "value_dtype": "float64",
        "frequency": "bar",
        "plugin_id": None,
        "plugin_version": None,
        "formula_version": None,
    }
    assert len(intraday_source["digest"]) == 64
    assert intraday_source["coverage"] == {
        "requested_start": "2026-08-17",
        "requested_end": "2026-08-17",
        "available_start": "2026-08-17",
        "available_end": "2026-08-17",
        "observations": 3,
    }
    assert set(intraday_source["cache"]) == {
        "hit_days",
        "miss_days",
        "fetched_ranges",
    }
    assert result.variables["market.subject.close"].coverage == {
        "available_start": "2026-08-17",
        "available_end": "2026-08-17",
        "observations": 3,
    }
    # Every raw Tier A column actually acquired is a traceable artifact, even
    # when it is not a direct input of the selected Tier B formula.
    subject_open = trace["market.subject.open"]["materializations"]
    intraday_input = next(
        item
        for item in subject_open
        if item["scope"]["purpose"] == "intraday_features"
    )
    assert intraday_input["digest"] == result.variables["market.subject.open"].digest
    assert intraday_input["coverage"] == {
        "requested_start": "2026-08-17",
        "requested_end": "2026-08-17",
        "available_start": "2026-08-17",
        "available_end": "2026-08-17",
        "observations": 3,
    }
    assert intraday_input["cache"] == result.data["derived_cache"]["intraday"]
    assert tuple(item["scope"]["purpose"] for item in subject_open) == (
        "intraday",
        "regime",
        "sentiment",
        "intraday_features",
    )
    assert tuple(item["scope"]["timeframe"] for item in subject_open) == (
        "1m",
        "1d",
        "1d",
        "1m",
    )
    assert trace["market.sector.high"]["materializations"][0]["scope"] == {
        "purpose": "sentiment",
        "role": "sector",
        "symbol": "SOXX",
        "timeframe": "1d",
    }

    regime_benchmark = next(
        item
        for item in trace["market.benchmark.close"]["materializations"]
        if item["scope"]["purpose"] == "regime"
    )
    assert regime_benchmark["scope"] == {
        "purpose": "regime",
        "role": "benchmark",
        "symbol": "SOXX",
        "timeframe": "1d",
    }
    assert regime_benchmark["coverage"] == {
        "requested_start": "2026-04-19",
        "requested_end": "2026-08-17",
        "available_start": "2026-04-20",
        "available_end": "2026-08-17",
        "observations": 86,
    }

    sentiment_market = next(
        item
        for item in trace["market.market.close"]["materializations"]
        if item["scope"]["purpose"] == "sentiment"
    )
    assert sentiment_market["scope"] == {
        "purpose": "sentiment",
        "role": "market",
        "symbol": "QQQ",
        "timeframe": "1d",
    }
    assert sentiment_market["coverage"] == {
        "requested_start": "2025-05-14",
        "requested_end": "2026-08-17",
        "available_start": "2025-05-14",
        "available_end": "2026-08-17",
        "observations": 329,
    }

    technical = trace["technical.vwap"]["materializations"]
    assert technical == (
        {
            "artifact_id": "technical.vwap@intraday_features:subject:1m:2026-08-17:2026-08-17",
            "definition": {
                "id": "technical.vwap",
                "version": "1.0.0",
                "kind": "measurement",
                "tier": "B",
                "column": "vwap",
                "value_dtype": "float64",
                "frequency": "intraday",
                "plugin_id": "bktstr.technical",
                "plugin_version": "1.0.0",
                "formula_version": "intraday-v1",
            },
            "digest": result.variables["technical.vwap"].digest,
            "coverage": {
                "requested_start": "2026-08-17",
                "requested_end": "2026-08-17",
                "available_start": "2026-08-17",
                "available_end": "2026-08-17",
                "observations": 3,
            },
            "cache": result.data["derived_cache"]["intraday"],
            "scope": {
                "purpose": "intraday_features",
                "role": "subject",
                "symbol": "NVDA",
                "timeframe": "1m",
            },
        },
    )


@pytest.mark.parametrize(
    ("field", "replacement_value", "expected_code"),
    (
        ("formula_version", "tampered-formula-v9", "formula_mismatch"),
        ("column", "tampered_vwap", "schema_mismatch"),
        ("tier", DataTier.C, "schema_mismatch"),
    ),
)
def test_materialized_definition_must_match_injected_registry_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    replacement_value: object,
    expected_code: str,
):
    # Break caught: trace could claim a registry definition different from the one calculated.
    registry = baseline_variable_registry()
    actual = registry.require("technical.vwap")
    registry._definitions[(actual.id, actual.version)] = replace(
        actual, **{field: replacement_value}
    )

    def engine_must_not_run(*args, **kwargs):
        raise AssertionError("canonical engine executed after definition mismatch")

    monkeypatch.setattr(orchestrator, "run_backtest_on_bars", engine_must_not_run)
    with pytest.raises(StrategyRunError) as raised:
        _run(
            _request(),
            _dependencies(tmp_path, FixtureProvider(), variable_registry=registry),
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == expected_code
    assert diagnostic.variable_id == "technical.vwap"
    assert diagnostic.variable == actual.ref
    assert diagnostic.forceable is False
    assert diagnostic.details == {
        "failure_class": "registry_definition",
        "mismatched_fields": (field,),
    }


def test_graph_failure_attributes_the_offending_registry_variable(tmp_path: Path):
    # Break caught: a graph error could be blamed on the fixed primary-signal placeholder.
    strategies, input_ref = _optional_filter_strategy(forceable=True, optional=True)
    registry = _registry_with_unavailable_filter_input(input_ref)
    offending = registry.require(input_ref)
    registry._definitions[(offending.id, offending.version)] = replace(
        offending,
        inputs=(offending.ref,),
    )

    with pytest.raises(StrategyRunError) as raised:
        _run(
            _request(),
            _dependencies(
                tmp_path,
                FixtureProvider(),
                strategy_registry=strategies,
                variable_registry=registry,
            ),
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "dependency_cycle"
    assert diagnostic.variable_id == input_ref.id
    assert diagnostic.variable == offending.ref
    assert diagnostic.forceable is False


def test_contract_failure_attributes_definition_named_in_error_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: a schema/formula contract failure could still use a fixed adapter placeholder.
    expected = baseline_variable_registry().require("technical.rsi14")

    def fail_with_named_definition(*args, **kwargs):
        raise VariableContractError(
            "generated schema differs from the registered variable",
            code="schema_mismatch",
            details={"definition": expected},
        )

    monkeypatch.setattr(VariableSnapshotStore, "resolve", fail_with_named_definition)
    with pytest.raises(StrategyRunError) as raised:
        _run(_request(), _dependencies(tmp_path, FixtureProvider()))

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "schema_mismatch"
    assert diagnostic.variable_id == "technical.rsi14"
    assert diagnostic.variable == expected.ref
    assert diagnostic.forceable is False


@pytest.mark.parametrize(
    ("details", "expected_id", "expected_version", "expected_variable"),
    (
        (
            {
                "dependency": {
                    "id": "strategy.bktstr.bearish-regime-scalp.filter.unregistered-input",
                    "version": "9.9.9",
                    "tier": "C",
                }
            },
            "strategy.bktstr.bearish-regime-scalp.filter.unregistered-input",
            "9.9.9",
            VariableRef(
                "strategy.bktstr.bearish-regime-scalp.filter.unregistered-input",
                "9.9.9",
                DataTier.C,
            ),
        ),
        (
            {
                "id": "strategy.bktstr.bearish-regime-scalp.filter.versioned-unregistered",
                "version": "9.9.9",
            },
            "strategy.bktstr.bearish-regime-scalp.filter.versioned-unregistered",
            "9.9.9",
            None,
        ),
        (
            {
                "id": "technical.rsi14",
                "version": "1.0.0",
                "tier": "C",
            },
            "technical.rsi14",
            "1.0.0",
            VariableRef("technical.rsi14", "1.0.0", DataTier.C),
        ),
        (
            {
                "variable_id": "strategy.bktstr.bearish-regime-scalp.filter.variable-id-unregistered",
                "version": "9.9.9",
                "tier": "C",
            },
            "strategy.bktstr.bearish-regime-scalp.filter.variable-id-unregistered",
            "9.9.9",
            VariableRef(
                "strategy.bktstr.bearish-regime-scalp.filter.variable-id-unregistered",
                "9.9.9",
                DataTier.C,
            ),
        ),
    ),
)
def test_contract_failure_preserves_unregistered_structured_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    details: dict[str, object],
    expected_id: str,
    expected_version: str,
    expected_variable: VariableRef | None,
):
    # Break caught: an unavailable strategy/filter dependency could be relabeled as the primary signal.
    def fail_with_unregistered_dependency(*args, **kwargs):
        raise VariableContractError(
            "dependency is not registered",
            code="unknown_variable",
            details=details,
        )

    monkeypatch.setattr(
        VariableSnapshotStore, "resolve", fail_with_unregistered_dependency
    )
    with pytest.raises(StrategyRunError) as raised:
        _run(_request(), _dependencies(tmp_path, FixtureProvider()))

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "unknown_variable"
    assert diagnostic.variable_id == expected_id
    assert diagnostic.variable == expected_variable
    assert diagnostic.details["attribution"] == {
        "id": expected_id,
        "version": expected_version,
        "tier": expected_variable.tier.value if expected_variable else None,
        "registered": False,
    }
    assert diagnostic.forceable is False


def test_contract_failure_with_ambiguous_id_only_details_uses_stable_registered_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: handling an original contract error could raise a second ambiguous-version error.
    registry = baseline_variable_registry()
    first = registry.require("technical.rsi14")
    registry.register(replace(first, version="2.0.0"))

    def fail_with_ambiguous_id(*args, **kwargs):
        raise VariableContractError(
            "the adapter named an ambiguous variable ID",
            code="schema_mismatch",
            details={"id": "technical.rsi14"},
        )

    monkeypatch.setattr(VariableSnapshotStore, "resolve", fail_with_ambiguous_id)
    with pytest.raises(StrategyRunError) as raised:
        _run(
            _request(),
            _dependencies(tmp_path, FixtureProvider(), variable_registry=registry),
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "schema_mismatch"
    assert diagnostic.variable_id == "technical.rsi14"
    assert diagnostic.variable == VariableRef("technical.rsi14", "1.0.0", DataTier.B)
    assert diagnostic.details["attribution"] == {
        "id": "technical.rsi14",
        "version": "1.0.0",
        "tier": "B",
        "registered": True,
    }
    assert diagnostic.forceable is False


def test_contract_failure_prefers_exact_version_from_ambiguous_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: a supplied version could be discarded while resolving an otherwise ambiguous ID.
    registry = baseline_variable_registry()
    first = registry.require("technical.rsi14")
    registry.register(replace(first, version="2.0.0"))

    def fail_with_exact_version(*args, **kwargs):
        raise VariableContractError(
            "the adapter named a versioned variable ID",
            code="schema_mismatch",
            details={"id": "technical.rsi14", "version": "2.0.0"},
        )

    monkeypatch.setattr(VariableSnapshotStore, "resolve", fail_with_exact_version)
    with pytest.raises(StrategyRunError) as raised:
        _run(
            _request(),
            _dependencies(tmp_path, FixtureProvider(), variable_registry=registry),
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.variable == VariableRef("technical.rsi14", "2.0.0", DataTier.B)
    assert diagnostic.details["attribution"] == {
        "id": "technical.rsi14",
        "version": "2.0.0",
        "tier": "B",
        "registered": True,
    }


def test_contract_failure_from_variable_store_details_prefers_exact_registered_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: VariableSnapshotStore's undeclared-input identity lost its sibling version/tier.
    registry = baseline_variable_registry()
    first = registry.require("technical.rsi14")
    registry.register(replace(first, version="2.0.0"))

    def fail_with_variable_store_identity(*args, **kwargs):
        raise VariableContractError(
            "snapshot input is not declared by an output definition",
            code="undeclared_input",
            details={
                "variable_id": "technical.rsi14",
                "version": "2.0.0",
                "tier": "B",
            },
        )

    monkeypatch.setattr(
        VariableSnapshotStore, "resolve", fail_with_variable_store_identity
    )
    with pytest.raises(StrategyRunError) as raised:
        _run(
            _request(),
            _dependencies(tmp_path, FixtureProvider(), variable_registry=registry),
        )

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "undeclared_input"
    assert diagnostic.variable_id == "technical.rsi14"
    assert diagnostic.variable == VariableRef("technical.rsi14", "2.0.0", DataTier.B)
    assert diagnostic.details["attribution"] == {
        "id": "technical.rsi14",
        "version": "2.0.0",
        "tier": "B",
        "registered": True,
    }
    assert diagnostic.forceable is False


def test_all_tier_a_acquisitions_finish_before_first_tier_b_adapter_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: a staged provenance label could claim ordering the real calls did not have.
    events: list[str] = []
    original_resolve = VariableSnapshotStore.resolve

    def record_measurement(self, *args, **kwargs):
        events.append(f"tier_b:{kwargs['namespace']}")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(VariableSnapshotStore, "resolve", record_measurement)
    _run(
        _request(with_context=True),
        _dependencies(tmp_path, FixtureProvider(event_log=events)),
    )

    first_tier_b = next(
        index for index, event in enumerate(events) if event.startswith("tier_b:")
    )
    tier_a_indexes = [
        index for index, event in enumerate(events) if event.startswith("tier_a:")
    ]
    assert len(tier_a_indexes) == 6
    assert max(tier_a_indexes) < first_tier_b
    assert events[first_tier_b] == "tier_b:intraday_features"


def test_context_variables_attached_from_strictly_prior_day_snapshots(tmp_path: Path):
    # Break caught: regime or sentiment could leak same-day daily data into an intraday signal.
    result = _run(_request(with_context=True), _dependencies(tmp_path, FixtureProvider()))

    regime_subject = _daily_bars(
        "NVDA", date(2026, 8, 17) - timedelta(days=120), date(2026, 8, 17)
    )
    regime_benchmark = _daily_bars(
        "SOXX", date(2026, 8, 17) - timedelta(days=120), date(2026, 8, 17)
    )
    expected_regime = build_daily_regime(regime_subject, regime_benchmark)
    sentiment_subject = _daily_bars(
        "NVDA", date(2026, 8, 17) - timedelta(days=460), date(2026, 8, 17)
    )
    sentiment_sector = _daily_bars(
        "SOXX", date(2026, 8, 17) - timedelta(days=460), date(2026, 8, 17)
    )
    sentiment_market = _daily_bars(
        "QQQ", date(2026, 8, 17) - timedelta(days=460), date(2026, 8, 17)
    )
    expected_sentiment = build_daily_sentiment(
        sentiment_subject, sentiment_sector, sentiment_market
    )

    assert result.variables["regime.day_close"].series.iloc[0] == pytest.approx(
        expected_regime.loc[pd.Timestamp("2026-08-14"), "day_close"]
    )
    assert result.variables["sentiment.direction"].series.iloc[0] == pytest.approx(
        expected_sentiment.loc[pd.Timestamp("2026-08-14"), "sentiment_direction"]
    )
    assert result.provenance["attachments"]["regime"]["availability"] == "prior_day"
    assert result.provenance["attachments"]["sentiment"]["availability"] == "prior_day"


def test_missing_primary_signal_data_has_deterministic_nonforceable_diagnostic(
    tmp_path: Path,
):
    # Break caught: an absent primary signal could be silently backfilled or forced into a canonical run.
    dependencies = _dependencies(tmp_path, FixtureProvider(empty_intraday=True))

    with pytest.raises(StrategyRunError) as raised:
        _run(_request(confirm_degraded=True), dependencies)

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "missing_coverage"
    assert diagnostic.variable_id == "market.subject.close"
    assert diagnostic.variable is not None and diagnostic.variable.tier is DataTier.A
    assert diagnostic.affected_coverage == {
        "available_end": None,
        "available_start": None,
        "required_end": "2026-08-17",
        "required_start": "2026-08-17",
    }
    assert diagnostic.affected_rules == ("close.cross_below:vwap",)
    assert diagnostic.suggestion_method == "no_safe_suggestion"
    assert diagnostic.applied is False
    assert diagnostic.forceable is False


def _optional_filter_strategy(*, forceable: bool, optional: bool) -> tuple[StrategyRegistry, object]:
    definition = baseline_strategy_definition()
    input_ref = VariableRef(
        "strategy.bktstr.bearish-regime-scalp.filter.context-input",
        "1.0.0",
        DataTier.C,
    )
    evidence_filter = StrategyFilterDefinition(
        id="bktstr.context-confirmation",
        version="1.0.0",
        output=VariableRef(
            "strategy.bktstr.bearish-regime-scalp.filter.context-confirmation",
            "1.0.0",
            DataTier.C,
        ),
        inputs=(input_ref,),
        role=FilterRole.ANNOTATE,
        rule="context_input.gte:0.5",
        tier=DataTier.C,
        forceable=forceable,
        optional=optional,
    )
    registry = StrategyRegistry()
    registry.register(
        replace(
            definition,
            filters=(evidence_filter,),
            evidence_tier_opt_ins=(DataTier.C,),
        )
    )
    return registry, input_ref


def _registry_with_unavailable_filter_input(input_ref: VariableRef):
    registry = baseline_variable_registry()
    registry.register(
        ResearchVariableDefinition.source(
            id=input_ref.id,
            version=input_ref.version,
            tier=input_ref.tier,
            column="context_input",
            value_dtype="float64",
            frequency="1m",
        )
    )
    return registry


def test_force_omits_only_declared_optional_forceable_filter_after_confirmation(
    tmp_path: Path,
):
    # Break caught: a lower-trust unavailable filter could be silently ignored without an explicit degraded decision.
    strategies, input_ref = _optional_filter_strategy(forceable=True, optional=True)
    dependencies = _dependencies(
        tmp_path,
        FixtureProvider(),
        strategy_registry=strategies,
        variable_registry=_registry_with_unavailable_filter_input(input_ref),
    )

    with pytest.raises(StrategyRunError) as unconfirmed:
        _run(_request(), dependencies)
    assert unconfirmed.value.diagnostics[0].forceable is True

    forced = _run(_request(confirm_degraded=True), dependencies)
    assert forced.degraded is True
    assert forced.canonical is False
    assert forced.diagnostics[0].applied is False
    assert forced.diagnostics[0].forceable is True
    decision = forced.provenance["filters"][0]
    assert decision == {
        "id": "bktstr.context-confirmation",
        "role": "annotate",
        "status": "not_evaluated",
        "tier": "C",
        "version": "1.0.0",
        "confirmation": True,
        "outcome": "omitted",
        "observed_value": None,
        "rule": "context_input.gte:0.5",
        "threshold": (
            {"field": "context_input", "operator": "gte", "value": 0.5},
        ),
        "inputs": (
            {
                "id": "strategy.bktstr.bearish-regime-scalp.filter.context-input",
                "version": "1.0.0",
                "tier": "C",
                "digest": None,
            },
        ),
        "backfill": {"attempted": False, "applied": False},
    }


def test_confirmation_cannot_omit_a_required_filter(tmp_path: Path):
    # Break caught: confirmation could make a required filter forceable despite its immutable definition.
    strategies, input_ref = _optional_filter_strategy(forceable=False, optional=True)
    dependencies = _dependencies(
        tmp_path,
        FixtureProvider(),
        strategy_registry=strategies,
        variable_registry=_registry_with_unavailable_filter_input(input_ref),
    )

    with pytest.raises(StrategyRunError) as raised:
        _run(_request(confirm_degraded=True), dependencies)

    assert raised.value.diagnostics[0].forceable is False
    assert raised.value.diagnostics[0].variable_id.endswith("context-confirmation")


def test_immutable_snapshot_corruption_is_nonforceable_and_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: corruption could be treated as an optional data gap or expose cache implementation details.
    secret = "corrupt-provider-token"

    def corrupt_snapshot(*args, **kwargs):
        raise VariableContractError(
            f"immutable snapshot corruption near {secret}",
            code="invalid_snapshot_digest",
        )

    monkeypatch.setattr(VariableSnapshotStore, "resolve", corrupt_snapshot)
    with pytest.raises(StrategyRunError) as raised:
        _run(_request(confirm_degraded=True), _dependencies(tmp_path, FixtureProvider(secret=secret)))

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "immutable_snapshot_corruption"
    assert diagnostic.forceable is False
    assert secret not in str(raised.value)
    assert secret not in repr(diagnostic)


def test_provider_secrets_never_appear_in_diagnostics_or_provenance(tmp_path: Path):
    # Break caught: provider exceptions or object metadata could leak credentials into durable run evidence.
    secret = "provider-secret-never-publish"
    successful = _run(_request(), _dependencies(tmp_path / "success", FixtureProvider(secret=secret)))
    assert secret not in repr(successful.provenance)

    with pytest.raises(StrategyRunError) as raised:
        _run(_request(), _dependencies(tmp_path / "failure", ExplodingProvider(secret=secret)))

    assert secret not in str(raised.value)
    assert all(secret not in repr(item) for item in raised.value.diagnostics)
