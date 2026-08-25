import pytest

from bktstr.variable_registry import VariableRegistry
from bktstr.variables import (
    DataTier,
    ResearchVariableDefinition,
    VariableContractError,
    VariableKind,
    VariableRef,
)


def ref(variable_id: str, tier: DataTier = DataTier.A, version: str = "1.0.0") -> VariableRef:
    return VariableRef(variable_id, version, tier)


def source_definition(variable_id: str, version: str = "1.0.0") -> ResearchVariableDefinition:
    return ResearchVariableDefinition.source(
        id=variable_id,
        version=version,
        tier=DataTier.A,
        column=variable_id.replace(".", "_"),
        value_dtype="float64",
        frequency="1d",
    )


def measurement_definition(
    variable_id: str,
    *,
    inputs: tuple[VariableRef, ...] = (),
    tier: DataTier = DataTier.B,
) -> ResearchVariableDefinition:
    return ResearchVariableDefinition(
        id=variable_id,
        version="1.0.0",
        kind=VariableKind.MEASUREMENT,
        tier=tier,
        column=variable_id.replace(".", "_"),
        value_dtype="float64",
        frequency="1d",
        inputs=inputs,
        plugin_id="test.measurement",
        plugin_version="1.0.0",
        formula_version="test-v1",
    )


def unsafe_inputs(
    definition: ResearchVariableDefinition, inputs: tuple[VariableRef, ...]
) -> ResearchVariableDefinition:
    """Create an invalid graph fixture without bypassing registry validation."""
    object.__setattr__(definition, "inputs", inputs)
    return definition


def test_registry_rejects_duplicate_identity_and_exposes_read_only_definitions():
    # Break caught: replacing an exact registered identity would rewrite history.
    registry = VariableRegistry()
    close = source_definition("market.close")
    registry.register(close)

    with pytest.raises(VariableContractError, match="already registered") as error:
        registry.register(close)

    assert error.value.code == "duplicate_variable_identity"
    assert error.value.details == {"id": "market.close", "version": "1.0.0"}
    with pytest.raises(TypeError):
        registry.definitions[("market.close", "1.0.0")] = close  # type: ignore[index]


def test_registry_looks_up_exact_versions_and_reports_missing_identity():
    # Break caught: resolving by ID alone could silently substitute another version.
    registry = VariableRegistry()
    close_v1 = source_definition("market.close", version="1.0.0")
    close_v2 = source_definition("market.close", version="2.0.0")
    registry.register(close_v1)
    registry.register(close_v2)

    assert registry.get(ref("market.close", version="1.0.0")) is close_v1
    assert registry.get(ref("market.close", version="3.0.0")) is None
    with pytest.raises(VariableContractError) as error:
        registry.require(ref("market.close", version="3.0.0"))

    assert error.value.code == "unknown_variable"
    assert error.value.details == {"id": "market.close", "version": "3.0.0"}


def test_registry_validates_a_to_b_graph_in_dependency_order():
    # Break caught: consumers preceding their inputs causes evaluation before data exists.
    registry = VariableRegistry()
    registry.register(source_definition("market.close"))
    registry.register(
        measurement_definition("technical.rsi14", inputs=(ref("market.close"),))
    )

    ordered = registry.validate_dependencies((ref("technical.rsi14", DataTier.B),))

    assert [item.id for item in ordered] == ["market.close", "technical.rsi14"]


def test_registry_rejects_dependency_cycle_deterministically():
    # Break caught: cyclic variables would recurse forever or yield an unstable order.
    registry = VariableRegistry()
    alpha = measurement_definition(
        "technical.alpha", inputs=(ref("technical.beta", DataTier.B),)
    )
    beta = measurement_definition(
        "technical.beta", inputs=(ref("technical.alpha", DataTier.B),)
    )
    registry.register(alpha)
    registry.register(beta)

    with pytest.raises(VariableContractError) as error:
        registry.validate_dependencies((ref("technical.alpha", DataTier.B),))

    assert error.value.code == "dependency_cycle"
    assert error.value.details == {
        "cycle": (
            ("technical.alpha", "1.0.0"),
            ("technical.beta", "1.0.0"),
            ("technical.alpha", "1.0.0"),
        )
    }


def test_registry_rejects_tier_b_dependency_on_tier_c():
    # Break caught: a forged low-trust input could be relabeled as foundational Tier B data.
    registry = VariableRegistry()
    experimental = measurement_definition("evidence.experimental", tier=DataTier.C)
    trusted = unsafe_inputs(
        measurement_definition("technical.invalid"),
        (ref("evidence.experimental", DataTier.C),),
    )
    registry.register(experimental)
    registry.register(trusted)

    with pytest.raises(VariableContractError) as error:
        registry.validate_dependencies((ref("technical.invalid", DataTier.B),))

    assert error.value.code == "illegal_tier_dependency"
    assert error.value.details == {
        "dependency": ("evidence.experimental", "1.0.0"),
        "dependency_tier": "C",
        "variable": ("technical.invalid", "1.0.0"),
        "variable_tier": "B",
    }
