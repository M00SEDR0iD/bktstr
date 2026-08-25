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


@pytest.mark.parametrize(
    ("variable_id", "tier"),
    (("evidence.news", DataTier.C), ("evidence.social", DataTier.D)),
)
def test_tier_c_d_evidence_cannot_be_a_direct_variable_use_even_with_opt_in(
    variable_id: str, tier: DataTier
):
    # Break caught: opt-in could authorize raw C/D evidence without filter lineage.
    evidence = StrategyVariableUse(
        variable=VariableRef(variable_id, "1.0.0", tier),
        role=FilterRole.ANNOTATE,
        rule=None,
        forceable=False,
    )

    with pytest.raises(
        ValueError, match="Tier C/D evidence must use a strategy-owned filter"
    ):
        _definition(
            variable_uses=(evidence,), evidence_tier_opt_ins=(tier,)
        )


@pytest.mark.parametrize(
    ("role", "rule"),
    (
        (FilterRole.GATE, "value.gte:0.5"),
        (FilterRole.RANK, None),
        (FilterRole.ANNOTATE, None),
    ),
)
def test_direct_variable_uses_are_never_forceable(role: FilterRole, rule: str | None):
    # Break caught: a required entry/rank/annotation input could be omitted by force.
    with pytest.raises(ValueError, match="direct variable uses cannot be forceable"):
        StrategyVariableUse(
            variable=VariableRef("technical.rsi14", "1.0.0", DataTier.B),
            role=role,
            rule=rule,
            forceable=True,
        )


def test_forceable_filter_must_be_explicitly_optional():
    # Break caught: a required filter could be omitted by setting only forceable=True.
    with pytest.raises(ValueError, match="forceable filter must be optional"):
        StrategyFilterDefinition(
            id="test.context-filter",
            version="1.0.0",
            output=VariableRef(
                "strategy.test.strategy.filter.context", "1.0.0", DataTier.C
            ),
            inputs=(VariableRef("evidence.news", "1.0.0", DataTier.C),),
            role=FilterRole.ANNOTATE,
            rule=None,
            tier=DataTier.C,
            forceable=True,
        )


def test_owned_optional_tier_c_filter_requires_and_accepts_explicit_opt_in():
    # Break caught: a valid lower-trust filter could bypass opt-in or lack optionality.
    evidence_filter = StrategyFilterDefinition(
        id="test.context-filter",
        version="1.0.0",
        output=VariableRef(
            "strategy.test.strategy.filter.context", "1.0.0", DataTier.C
        ),
        inputs=(
            VariableRef(
                "strategy.test.strategy.filter.upstream", "1.0.0", DataTier.C
            ),
        ),
        role=FilterRole.ANNOTATE,
        rule=None,
        tier=DataTier.C,
        forceable=True,
        optional=True,
    )

    with pytest.raises(ValueError, match="requires explicit Tier C opt-in"):
        _definition(filters=(evidence_filter,))

    opted_in = _definition(
        filters=(evidence_filter,), evidence_tier_opt_ins=(DataTier.C,)
    )
    assert opted_in.filters == (evidence_filter,)
    assert evidence_filter.optional is True


@pytest.mark.parametrize(
    "input_id",
    (
        "strategy.other.filter.upstream",
        "evidence.news",
    ),
)
def test_strategy_rejects_foreign_or_unowned_lower_tier_filter_input(
    input_id: str,
):
    # Break caught: opt-in could authorize C/D input lineage outside filter ownership.
    evidence_filter = StrategyFilterDefinition(
        id="test.context-filter",
        version="1.0.0",
        output=VariableRef(
            "strategy.test.strategy.filter.context", "1.0.0", DataTier.C
        ),
        inputs=(VariableRef(input_id, "1.0.0", DataTier.C),),
        role=FilterRole.ANNOTATE,
        rule=None,
        tier=DataTier.C,
        forceable=False,
    )

    with pytest.raises(ValueError, match="lower-trust filter input must use namespace"):
        _definition(
            filters=(evidence_filter,), evidence_tier_opt_ins=(DataTier.C,)
        )


def test_canonical_baseline_strategy_owns_hyphenated_filter_namespace():
    # Break caught: the baseline's raw strategy ID could not address its owned filter.
    evidence_filter = StrategyFilterDefinition(
        id="bktstr.context-confirmation",
        version="1.0.0",
        output=VariableRef(
            "strategy.bktstr.bearish-regime-scalp.filter.context-confirmation",
            "1.0.0",
            DataTier.C,
        ),
        inputs=(VariableRef("sentiment.fragility", "1.0.0", DataTier.B),),
        role=FilterRole.ANNOTATE,
        rule=None,
        tier=DataTier.C,
        forceable=True,
        optional=True,
    )

    definition = replace(
        baseline_strategy_definition(),
        filters=(evidence_filter,),
        evidence_tier_opt_ins=(DataTier.C,),
    )
    assert definition.filters == (evidence_filter,)


def test_strategy_rejects_filter_output_owned_by_another_strategy():
    # Break caught: one strategy could attach and relabel another strategy's output.
    foreign_filter = StrategyFilterDefinition(
        id="foreign.context-filter",
        version="1.0.0",
        output=VariableRef("strategy.foreign.filter.context", "1.0.0", DataTier.B),
        inputs=(VariableRef("sentiment.fragility", "1.0.0", DataTier.B),),
        role=FilterRole.ANNOTATE,
        rule=None,
        tier=DataTier.B,
        forceable=False,
    )

    with pytest.raises(ValueError, match="filter output must use namespace"):
        _definition(filters=(foreign_filter,))


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
