from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bktstr.variable_store import VariableSnapshotStore
from bktstr.variables import (
    DataTier,
    ResearchVariableDefinition,
    ResearchVariableSnapshot,
    VariableContractError,
    VariableKind,
    VariableRef,
)
from bktstr_cache.derived import DerivedFrameCache


def definition(
    *,
    variable_id: str = "technical.alpha",
    version: str = "1.0.0",
    column: str = "alpha",
    plugin_version: str = "1.0.0",
    formula_version: str = "alpha-v1",
    inputs: tuple[VariableRef, ...] = (),
) -> ResearchVariableDefinition:
    return ResearchVariableDefinition(
        id=variable_id,
        version=version,
        kind=VariableKind.MEASUREMENT,
        tier=DataTier.B,
        column=column,
        value_dtype="float64",
        frequency="1m",
        plugin_id="technical",
        plugin_version=plugin_version,
        formula_version=formula_version,
        inputs=inputs,
    )


def input_frame(last_value: float = 3.0) -> pd.DataFrame:
    return pd.DataFrame(
        {"close": [1.0, 2.0, last_value]},
        index=pd.date_range("2026-08-20", periods=3, freq="min", tz="UTC"),
    )


def alpha_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"alpha": [10.0, 20.0, 30.0]},
        index=input_frame().index,
    )


def test_cold_miss_then_warm_hit_exposes_snapshots_by_stable_id(tmp_path: Path):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))
    alpha = definition()
    beta = definition(variable_id="technical.beta", column="beta", formula_version="beta-v1")
    calls = 0
    expected = pd.DataFrame(
        {"alpha": [10.0, 20.0, 30.0], "beta": [1.0, 4.0, 9.0]},
        index=input_frame().index,
    )

    def compute() -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return expected.copy(deep=True)

    first = store.resolve(
        namespace="technical",
        definitions=(beta, alpha),
        dimensions={"symbol": "NVDA", "timeframe": "1m"},
        inputs={"raw": input_frame()},
        provenance={"provider": "fixture"},
        compute=compute,
    )
    second = store.resolve(
        namespace="technical",
        definitions=(alpha, beta),
        dimensions={"timeframe": "1m", "symbol": "NVDA"},
        inputs={"raw": input_frame().copy(deep=True)},
        provenance={"provider": "fixture"},
        compute=compute,
    )

    assert first.status.hit is False
    assert second.status.hit is True
    assert first.status.key == second.status.key
    assert calls == 1
    assert tuple(first.variables) == ("technical.beta", "technical.alpha")
    assert second.variables["technical.alpha"].series.tolist() == [10.0, 20.0, 30.0]
    assert second.variables["technical.beta"].series.tolist() == [1.0, 4.0, 9.0]
    pd.testing.assert_frame_equal(second.legacy_frame, expected)


def test_mutating_returned_series_does_not_change_later_reads(tmp_path: Path):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))
    alpha = definition()
    result = store.resolve(
        namespace="technical",
        definitions=(alpha,),
        dimensions={"symbol": "NVDA"},
        inputs={"raw": input_frame()},
        provenance={},
        compute=alpha_frame,
    )

    returned = result.variables["technical.alpha"].series
    returned.iloc[0] = -999.0

    assert result.variables["technical.alpha"].series.iloc[0] == 10.0


def test_changed_dataframe_and_snapshot_inputs_change_content_addresses(tmp_path: Path):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))
    source_definition = ResearchVariableDefinition.source(
        id="market.subject.close",
        version="1.0.0",
        tier=DataTier.A,
        column="close",
        value_dtype="float64",
        frequency="1m",
    )
    alpha = definition(inputs=(source_definition.ref,))

    def source_snapshot(last_value: float) -> ResearchVariableSnapshot:
        return ResearchVariableSnapshot.create(
            source_definition,
            input_frame(last_value)["close"],
            input_digests=(),
            provenance={"provider": "fixture"},
        )

    def resolve(raw_last: float, snapshot_last: float):
        return store.resolve(
            namespace="technical",
            definitions=(alpha,),
            dimensions={"symbol": "NVDA"},
            inputs={"raw": input_frame(raw_last), "source": source_snapshot(snapshot_last)},
            provenance={},
            compute=alpha_frame,
        )

    baseline = resolve(3.0, 3.0)
    changed_frame = resolve(4.0, 3.0)
    changed_snapshot = resolve(3.0, 4.0)

    assert len({baseline.status.key, changed_frame.status.key, changed_snapshot.status.key}) == 3
    assert baseline.variables["technical.alpha"].digest != changed_frame.variables["technical.alpha"].digest
    assert baseline.variables["technical.alpha"].digest != changed_snapshot.variables["technical.alpha"].digest


def test_undeclared_lower_tier_snapshot_is_rejected_before_compute(tmp_path: Path):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))
    tier_c_definition = ResearchVariableDefinition.source(
        id="evidence.news.score",
        version="1.0.0",
        tier=DataTier.C,
        column="news_score",
        value_dtype="float64",
        frequency="1m",
    )
    tier_c_snapshot = ResearchVariableSnapshot.create(
        tier_c_definition,
        pd.Series([0.1, 0.2, 0.3], index=input_frame().index),
        input_digests=(),
        provenance={"provider": "fixture"},
    )
    calls = 0

    def compute() -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return alpha_frame()

    with pytest.raises(VariableContractError, match="not declared"):
        store.resolve(
            namespace="technical",
            definitions=(definition(),),
            dimensions={},
            inputs={"evidence": tier_c_snapshot},
            provenance={},
            compute=compute,
        )

    assert calls == 0


def test_forged_tier_b_definition_cannot_consume_tier_c_snapshot(tmp_path: Path):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))
    tier_c_definition = ResearchVariableDefinition.source(
        id="evidence.news.score",
        version="1.0.0",
        tier=DataTier.C,
        column="news_score",
        value_dtype="float64",
        frequency="1m",
    )
    tier_c_snapshot = ResearchVariableSnapshot.create(
        tier_c_definition,
        pd.Series([0.1, 0.2, 0.3], index=input_frame().index),
        input_digests=(),
        provenance={},
    )
    forged_output = definition()
    object.__setattr__(forged_output, "inputs", (tier_c_definition.ref,))

    with pytest.raises(VariableContractError) as exc_info:
        store.resolve(
            namespace="technical",
            definitions=(forged_output,),
            dimensions={},
            inputs={"evidence": tier_c_snapshot},
            provenance={},
            compute=alpha_frame,
        )

    assert exc_info.value.code == "illegal_tier_dependency"


@pytest.mark.parametrize(
    ("changed_definition",),
    [
        (definition(variable_id="technical.beta"),),
        (definition(version="1.1.0"),),
        (definition(formula_version="alpha-v2"),),
        (definition(plugin_version="2.0.0"),),
    ],
    ids=("stable-id", "definition-version", "formula-version", "plugin-version"),
)
def test_definition_identity_and_formula_versions_change_cache_keys(tmp_path: Path, changed_definition):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))

    original = store.resolve(
        namespace="technical",
        definitions=(definition(),),
        dimensions={"symbol": "NVDA"},
        inputs={"raw": input_frame()},
        provenance={},
        compute=alpha_frame,
    )
    changed = store.resolve(
        namespace="technical",
        definitions=(changed_definition,),
        dimensions={"symbol": "NVDA"},
        inputs={"raw": input_frame()},
        provenance={},
        compute=alpha_frame,
    )

    assert original.status.key != changed.status.key
    assert changed.status.hit is False


def test_missing_or_duplicate_declared_output_columns_are_rejected(tmp_path: Path):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))
    alpha = definition()

    with pytest.raises(ValueError, match="missing declared output columns: alpha"):
        store.resolve(
            namespace="technical",
            definitions=(alpha,),
            dimensions={},
            inputs={"raw": input_frame()},
            provenance={},
            compute=lambda: input_frame(),
        )

    duplicate = pd.DataFrame(
        [[10.0, 11.0]],
        columns=["alpha", "alpha"],
        index=input_frame().index[:1],
    )
    with pytest.raises(ValueError, match="duplicate output columns: alpha"):
        store.resolve(
            namespace="duplicate",
            definitions=(alpha,),
            dimensions={},
            inputs={"raw": input_frame()},
            provenance={},
            compute=lambda: duplicate,
        )


def test_undeclared_output_columns_are_rejected_before_persistence(tmp_path: Path):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))

    with pytest.raises(ValueError, match="undeclared output columns: accepted_signal"):
        store.resolve(
            namespace="technical",
            definitions=(definition(),),
            dimensions={},
            inputs={"raw": input_frame()},
            provenance={},
            compute=lambda: pd.DataFrame(
                {
                    "alpha": [10.0, 20.0, 30.0],
                    "accepted_signal": [False, True, False],
                },
                index=input_frame().index,
            ),
        )

    assert list(tmp_path.rglob("*.pkl.gz")) == []


def test_empty_definition_set_is_rejected_before_compute(tmp_path: Path):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))
    calls = 0

    def compute() -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return input_frame()

    with pytest.raises(ValueError, match="definitions must not be empty"):
        store.resolve(
            namespace="technical",
            definitions=(),
            dimensions={},
            inputs={"raw": input_frame()},
            provenance={},
            compute=compute,
        )

    assert calls == 0


def test_corrupt_payload_is_recomputed_and_reported(tmp_path: Path):
    store = VariableSnapshotStore(DerivedFrameCache(tmp_path))
    alpha = definition()
    calls = 0

    def compute() -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return alpha_frame()

    first = store.resolve(
        namespace="technical",
        definitions=(alpha,),
        dimensions={"symbol": "NVDA"},
        inputs={"raw": input_frame()},
        provenance={},
        compute=compute,
    )
    pd.DataFrame(
        {"wrong_column": [1.0, 2.0, 3.0]},
        index=input_frame().index,
    ).to_pickle(first.status.payload_path, compression="gzip")

    recovered = store.resolve(
        namespace="technical",
        definitions=(alpha,),
        dimensions={"symbol": "NVDA"},
        inputs={"raw": input_frame()},
        provenance={},
        compute=compute,
    )

    assert calls == 2
    assert recovered.status.hit is False
    assert recovered.status.recovered_corruption is True
    assert recovered.variables["technical.alpha"].series.tolist() == [10.0, 20.0, 30.0]
