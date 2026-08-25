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
    snapshot_digest,
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


def test_suggestion_policy_freezes_nested_values_at_construction():
    # Break caught: a caller could mutate a list or mapping after registration
    # and silently change the policy's future replication suggestions.
    supplied = {
        "weights": [1.0, {"fallbacks": ["historical_median"]}],
    }
    policy = ReplicationSuggestionPolicy.neutral(supplied, "Review only")

    supplied["weights"].append(2.0)
    supplied["weights"][1]["fallbacks"].append("last_valid")
    diagnostic = policy.suggest(variable_id="sentiment.direction")

    assert diagnostic.suggested_value["weights"] == (
        1.0,
        {"fallbacks": ("historical_median",)},
    )
    with pytest.raises(TypeError):
        diagnostic.suggested_value["weights"] = ()


def test_snapshot_freezes_nested_provenance_and_preserves_digest():
    # Break caught: mutating caller-owned nested provenance could change the
    # material represented by an already issued immutable snapshot digest.
    definition = ResearchVariableDefinition.source(
        id="market.subject.close",
        version="1.0.0",
        tier=DataTier.A,
        column="close",
        value_dtype="float64",
        frequency="1m",
    )
    supplied = {
        "provider": {
            "name": "fixture",
            "sources": ["primary"],
        }
    }
    snapshot = ResearchVariableSnapshot.create(
        definition,
        pd.Series(
            [100.0, 101.0],
            index=pd.date_range("2026-08-17", periods=2, freq="min", tz="UTC"),
        ),
        input_digests=("source-digest",),
        provenance=supplied,
    )
    original_digest = snapshot.digest

    supplied["provider"]["name"] = "mutated"
    supplied["provider"]["sources"].append("secondary")

    assert snapshot.provenance["provider"] == {
        "name": "fixture",
        "sources": ("primary",),
    }
    assert snapshot.digest == original_digest
    assert snapshot_digest(
        definition,
        snapshot.series,
        snapshot.input_digests,
        snapshot.provenance,
    ) == original_digest
    with pytest.raises(TypeError):
        snapshot.provenance["provider"]["name"] = "mutated again"


def test_immutable_contracts_reject_unsupported_mutable_values():
    # Break caught: an unsupported mutable object could bypass recursive
    # freezing and mutate policy or provenance content after construction.
    with pytest.raises(TypeError, match="unsupported mutable value type: bytearray"):
        ReplicationSuggestionPolicy.neutral(bytearray(b"mutable"), "Review only")

    definition = ResearchVariableDefinition.source(
        id="market.subject.close",
        version="1.0.0",
        tier=DataTier.A,
        column="close",
        value_dtype="float64",
        frequency="1m",
    )
    with pytest.raises(TypeError, match="unsupported mutable value type: bytearray"):
        ResearchVariableSnapshot.create(
            definition,
            pd.Series(
                [100.0],
                index=pd.date_range("2026-08-17", periods=1, freq="min", tz="UTC"),
            ),
            input_digests=(),
            provenance={"payload": bytearray(b"mutable")},
        )


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
