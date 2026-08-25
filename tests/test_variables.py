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


def test_hyphenated_strategy_filter_id_is_valid_for_refs_and_definitions():
    # Break caught: canonical strategy-owned filter IDs could fail variable registration.
    variable_id = "strategy.bearish-regime-scalp.filter.context-confirmation"
    reference = VariableRef(variable_id, "1.0.0", DataTier.C)
    definition = ResearchVariableDefinition(
        id=variable_id,
        version="1.0.0",
        kind=VariableKind.FILTER,
        tier=DataTier.C,
        column="context_confirmation",
        value_dtype="bool",
        frequency="1d",
        inputs=(VariableRef("sentiment.fragility", "1.0.0", DataTier.B),),
        plugin_id="test.context-filter",
        plugin_version="1.0.0",
        formula_version="test-v1",
    )

    assert definition.ref == reference


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
    assert diagnostic.suggested_reference is None
    assert diagnostic.applied is False


@pytest.mark.parametrize(
    ("policy", "expected_reference"),
    [
        (ReplicationSuggestionPolicy.neutral(0.0, "Neutral"), None),
        (ReplicationSuggestionPolicy.last_valid("Last valid"), None),
        (ReplicationSuggestionPolicy.historical_median("Median"), None),
        (ReplicationSuggestionPolicy.reference("market.reference.close", "Reference"), "market.reference.close"),
        (ReplicationSuggestionPolicy.no_safe_suggestion("No suggestion"), None),
    ],
)
def test_suggestion_policy_constructors_emit_only_declared_references(policy, expected_reference):
    diagnostic = policy.suggest(variable_id="sentiment.direction")
    assert diagnostic.suggested_reference == expected_reference


@pytest.mark.parametrize("kind", (VariableKind.MEASUREMENT, VariableKind.FILTER))
def test_tier_a_rejects_non_source_definitions(kind):
    with pytest.raises(ValueError, match="Tier A is reserved for source variables"):
        ResearchVariableDefinition(
            id="technical.invalid",
            version="1.0.0",
            kind=kind,
            tier=DataTier.A,
            column="invalid",
            value_dtype="float64",
            frequency="1d",
        )
