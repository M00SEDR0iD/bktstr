from dataclasses import FrozenInstanceError, replace
from datetime import date

import pytest

from bktstr.strategies import (
    StrategyDefinition,
    StrategyFilterDefinition,
    StrategyParameter,
    StrategyRegistry,
    StrategyRunRequest,
    StrategyVariableUse,
    baseline_strategy_definition,
    baseline_strategy_registry,
)
from bktstr.variables import DataTier, FilterRole, VariableRef


def _definition(
    *,
    variable_uses: tuple[StrategyVariableUse, ...] = (),
    filters: tuple[StrategyFilterDefinition, ...] = (),
    evidence_tier_opt_ins: tuple[DataTier, ...] = (),
) -> StrategyDefinition:
    return StrategyDefinition(
        id="test.strategy",
        schema_version="1.0.0",
        version="1.0.0",
        name="Test strategy",
        description="Strategy contract fixture",
        instrument_roles=("subject",),
        timeframe="1m",
        calendar="XNYS",
        timezone="America/New_York",
        parameters=(StrategyParameter("threshold", float, 1.0, minimum=0.0),),
        variable_uses=variable_uses,
        filters=filters,
        execution_model_id="test.execution",
        execution_model_version="1.0.0",
        evidence_tier_opt_ins=evidence_tier_opt_ins,
    )


def test_baseline_resolves_current_execution_defaults():
    # Break caught: migration could silently change risk, sizing, or fill assumptions.
    definition = baseline_strategy_definition()
    resolved = definition.resolve({})

    assert resolved.strategy_id == "bktstr.bearish-regime-scalp"
    assert resolved.strategy_version == "1.0.0"
    assert resolved.execution_model_id == "bktstr.next-bar-open"
    assert resolved.execution_model_version == "1.0.0"
    assert resolved.values["side"] == "short"
    assert resolved.values["entry_rules"] == (
        "close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10"
    )
    assert resolved.values["regime_rules"] == (
        "day_sma20_slope5.lt:0,relative_return20.lt:0"
    )
    assert resolved.values["stop_pct"] == 1.0
    assert resolved.values["target_pct"] == 3.0
    assert resolved.values["max_hold_minutes"] == 240
    assert resolved.values["position_size"] == 1000.0
    assert resolved.values["starting_capital"] == 10000.0
    assert resolved.values["slippage_bps"] == 2.0
    assert resolved.values["regular_hours_only"] is True
    assert resolved.values["same_day_only"] is True


def test_baseline_declares_roles_and_only_tier_a_b_requirements():
    # Break caught: the baseline could omit a control role or silently consume C/D evidence.
    definition = baseline_strategy_definition()
    variable_ids = {use.variable.id for use in definition.variable_uses}

    assert definition.instrument_roles == ("subject", "sector", "market")
    assert {
        "technical.vwap",
        "technical.rsi14",
        "technical.volume_ratio20",
        "regime.day_sma20_slope5",
        "regime.relative_return20",
        "sentiment.direction",
        "sentiment.fragility",
    } <= variable_ids
    assert {use.variable.tier for use in definition.variable_uses} == {
        DataTier.B
    }
    assert definition.evidence_tier_opt_ins == ()


def test_resolution_accepts_only_declared_overridable_typed_values():
    # Break caught: arbitrary or ill-typed values could bypass the strategy schema.
    definition = baseline_strategy_definition()

    resolved = definition.resolve(
        {"stop_pct": 2.5, "max_hold_minutes": 30, "side": "long"}
    )
    assert resolved.values["stop_pct"] == 2.5
    assert resolved.values["max_hold_minutes"] == 30
    assert resolved.values["side"] == "long"

    with pytest.raises(ValueError, match="undeclared strategy parameter"):
        definition.resolve({"unknown": 1})
    with pytest.raises(TypeError, match="stop_pct must be float"):
        definition.resolve({"stop_pct": "2.5"})
    with pytest.raises(ValueError, match="stop_pct must be greater than 0.0"):
        definition.resolve({"stop_pct": 0.0})
    with pytest.raises(ValueError, match="side must be one of"):
        definition.resolve({"side": "flat"})


def test_resolution_rejects_override_of_declared_fixed_parameter():
    # Break caught: registration-only assumptions could be changed at run time.
    fixed = StrategyParameter("fixed", int, 1, overridable=False)
    definition = replace(
        _definition(),
        parameters=(fixed,),
    )

    with pytest.raises(ValueError, match="fixed is not overridable"):
        definition.resolve({"fixed": 2})


def test_parameter_defaults_are_defensively_frozen():
    # Break caught: a mutable default could rewrite future resolved strategy values.
    supplied = {"nested": {"threshold": 1}}
    parameter = StrategyParameter("settings", dict, supplied)
    supplied["nested"]["threshold"] = 99

    assert parameter.default == {"nested": {"threshold": 1}}
    with pytest.raises(TypeError):
        parameter.default["nested"]["threshold"] = 2


def test_definitions_resolved_values_and_run_requests_are_immutable():
    # Break caught: a caller could mutate historical strategy or run identity in place.
    definition = baseline_strategy_definition()
    resolved = definition.resolve({})
    request = StrategyRunRequest(
        strategy_id=definition.id,
        strategy_version=definition.version,
        instruments={"subject": "NVDA", "sector": "SOXX", "market": "QQQ"},
        start=date(2026, 8, 17),
        end=date(2026, 8, 18),
        timeframe="1m",
        overrides={"stop_pct": 2.0},
    )

    with pytest.raises(FrozenInstanceError):
        definition.name = "Changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        resolved.values["stop_pct"] = 99.0  # type: ignore[index]
    with pytest.raises(TypeError):
        request.instruments["subject"] = "AMD"  # type: ignore[index]
    with pytest.raises(TypeError):
        request.overrides["stop_pct"] = 99.0  # type: ignore[index]


def test_filter_role_is_explicit_and_does_not_mutate_variables():
    # Break caught: filter interpretation could be implicit or rewrite its input reference.
    variable = VariableRef("sentiment.fragility", "1.0.0", DataTier.B)
    use = StrategyVariableUse(
        variable=variable,
        role=FilterRole.ANNOTATE,
        rule=None,
        forceable=False,
    )

    assert use.role is FilterRole.ANNOTATE
    assert use.variable is variable
    with pytest.raises(FrozenInstanceError):
        use.variable = VariableRef(  # type: ignore[misc]
            "sentiment.direction", "1.0.0", DataTier.B
        )


def test_filter_tier_inherits_weakest_input_and_method_floor():
    # Break caught: a Tier C dependency could be mislabeled as a Tier B filter output.
    with pytest.raises(ValueError, match="filter tier cannot improve inherited trust"):
        StrategyFilterDefinition(
            id="test.context-filter",
            version="1.0.0",
            output=VariableRef("strategy.test.filter.context", "1.0.0", DataTier.B),
            inputs=(VariableRef("evidence.news", "1.0.0", DataTier.C),),
            role=FilterRole.GATE,
            rule="value.gte:0.5",
            tier=DataTier.B,
            forceable=False,
        )


def test_tier_c_d_variables_require_explicit_strategy_opt_in():
    # Break caught: lower-trust evidence could enter a strategy without visible consent.
    evidence = StrategyVariableUse(
        variable=VariableRef("evidence.news", "1.0.0", DataTier.C),
        role=FilterRole.ANNOTATE,
        rule=None,
        forceable=True,
    )

    with pytest.raises(ValueError, match="requires explicit Tier C opt-in"):
        _definition(variable_uses=(evidence,))

    opted_in = _definition(
        variable_uses=(evidence,), evidence_tier_opt_ins=(DataTier.C,)
    )
    assert opted_in.evidence_tier_opt_ins == (DataTier.C,)


def test_strategy_registry_is_append_only_and_looks_up_exact_versions():
    # Break caught: ID-only lookup or replacement could rewrite historical definitions.
    registry = StrategyRegistry()
    v1 = _definition()
    v2 = replace(v1, version="2.0.0")
    registry.register(v1)
    registry.register(v2)

    assert registry.require("test.strategy", "1.0.0") is v1
    assert registry.require("test.strategy", "2.0.0") is v2
    assert registry.get("test.strategy", "3.0.0") is None
    with pytest.raises(ValueError, match="already registered"):
        registry.register(v1)
    with pytest.raises(TypeError):
        registry.definitions[("test.strategy", "1.0.0")] = v2  # type: ignore[index]


def test_baseline_registry_contains_only_the_exact_baseline_version():
    # Break caught: baseline lookup could float to an unrequested version.
    registry = baseline_strategy_registry()

    definition = registry.require("bktstr.bearish-regime-scalp", "1.0.0")
    assert definition.version == "1.0.0"
    assert registry.get("bktstr.bearish-regime-scalp", "2.0.0") is None
