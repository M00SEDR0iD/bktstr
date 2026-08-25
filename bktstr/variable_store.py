from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

import pandas as pd

from bktstr.variables import (
    DataTier,
    ResearchVariableDefinition,
    ResearchVariableSnapshot,
    VariableContractError,
    VariableSet,
    inherited_tier,
)
from bktstr_cache.derived import CacheResult, CacheStatus, DerivedFrameCache


@dataclass(frozen=True)
class VariableStoreResult:
    variables: VariableSet
    status: CacheStatus
    legacy_frame: pd.DataFrame


class VariableSnapshotStore:
    """Materialize deterministic research outputs as immutable snapshots."""

    def __init__(self, cache: DerivedFrameCache):
        if not isinstance(cache, DerivedFrameCache):
            raise TypeError("cache must be a DerivedFrameCache")
        self._cache = cache

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
        definitions = _validate_definitions(definitions)
        _validate_snapshot_inputs(definitions, inputs)
        cache_inputs = _cache_inputs(inputs)
        input_digests = DerivedFrameCache.input_digests(cache_inputs)
        cache_dimensions = {
            "caller_dimensions": dimensions,
            "definitions": [_definition_identity(item) for item in sorted(definitions, key=lambda item: (item.id, item.version))],
        }

        def checked_compute() -> pd.DataFrame:
            return _validate_output(compute(), definitions)

        cached = self._cache.get_or_compute(
            namespace=namespace,
            dimensions=cache_dimensions,
            inputs=cache_inputs,
            compute=checked_compute,
        )
        try:
            frame = _validate_output(cached.frame, definitions)
        except ValueError:
            if not cached.status.hit:
                raise
            cached.status.payload_path.unlink(missing_ok=True)
            cached.status.metadata_path.unlink(missing_ok=True)
            recomputed = self._cache.get_or_compute(
                namespace=namespace,
                dimensions=cache_dimensions,
                inputs=cache_inputs,
                compute=checked_compute,
            )
            cached = CacheResult(
                frame=recomputed.frame,
                status=replace(recomputed.status, recovered_corruption=True),
            )
            frame = _validate_output(cached.frame, definitions)

        lineage = tuple(input_digests[name] for name in sorted(input_digests))
        snapshots = VariableSet(
            tuple(
                ResearchVariableSnapshot.create(
                    item,
                    frame[item.column],
                    input_digests=lineage,
                    provenance=provenance,
                    coverage=_series_coverage(frame[item.column]),
                )
                for item in definitions
            )
        )
        return VariableStoreResult(
            variables=snapshots,
            status=cached.status,
            legacy_frame=frame.copy(deep=True),
        )


def _definition_identity(definition: ResearchVariableDefinition) -> dict[str, str | None]:
    return {
        "id": definition.id,
        "version": definition.version,
        "tier": definition.tier.value,
        "column": definition.column,
        "plugin_id": definition.plugin_id,
        "plugin_version": definition.plugin_version,
        "formula_version": definition.formula_version,
    }


def _validate_definitions(
    definitions: tuple[ResearchVariableDefinition, ...],
) -> tuple[ResearchVariableDefinition, ...]:
    if not isinstance(definitions, tuple) or any(
        not isinstance(item, ResearchVariableDefinition) for item in definitions
    ):
        raise TypeError("definitions must be a tuple of ResearchVariableDefinition values")
    if not definitions:
        raise ValueError("definitions must not be empty")

    ids = [item.id for item in definitions]
    duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
    if duplicate_ids:
        raise ValueError(f"duplicate variable IDs: {', '.join(duplicate_ids)}")

    columns = [item.column for item in definitions]
    duplicate_columns = sorted({item for item in columns if columns.count(item) > 1})
    if duplicate_columns:
        raise ValueError(f"duplicate declared output columns: {', '.join(duplicate_columns)}")

    for definition in definitions:
        input_tiers = tuple(item.tier for item in definition.inputs)
        if definition.tier is DataTier.B and any(
            tier in (DataTier.C, DataTier.D) for tier in input_tiers
        ):
            raise VariableContractError(
                "Tier B cannot depend on Tier C or Tier D",
                code="illegal_tier_dependency",
                details={"variable_id": definition.id},
            )
        calculated_tier = inherited_tier(input_tiers, method_floor=definition.tier)
        if calculated_tier is not definition.tier:
            raise VariableContractError(
                f"tier {definition.tier.value} cannot improve inherited tier {calculated_tier.value}",
                code="illegal_tier_dependency",
                details={"variable_id": definition.id},
            )
    return definitions


def _validate_snapshot_inputs(
    definitions: tuple[ResearchVariableDefinition, ...],
    inputs: Mapping[str, pd.DataFrame | ResearchVariableSnapshot],
) -> None:
    declared_refs = {
        item
        for definition in definitions
        for item in definition.inputs
    }
    snapshots = tuple(
        value for value in inputs.values() if isinstance(value, ResearchVariableSnapshot)
    )
    for snapshot in snapshots:
        if snapshot.ref not in declared_refs:
            raise VariableContractError(
                f"snapshot input {snapshot.definition.id!r} is not declared by an output definition",
                code="undeclared_input",
                details={
                    "variable_id": snapshot.definition.id,
                    "version": snapshot.definition.version,
                    "tier": snapshot.tier.value,
                },
            )

    actual_tiers = tuple(snapshot.tier for snapshot in snapshots)
    for definition in definitions:
        calculated_tier = inherited_tier(actual_tiers, method_floor=definition.tier)
        if calculated_tier is not definition.tier:
            raise VariableContractError(
                f"tier {definition.tier.value} cannot improve actual input tier {calculated_tier.value}",
                code="illegal_tier_dependency",
                details={"variable_id": definition.id},
            )


def _cache_inputs(
    inputs: Mapping[str, pd.DataFrame | ResearchVariableSnapshot],
) -> dict[str, pd.DataFrame | str]:
    normalized: dict[str, pd.DataFrame | str] = {}
    for name, value in inputs.items():
        if isinstance(value, ResearchVariableSnapshot):
            normalized[str(name)] = value.digest
        elif isinstance(value, pd.DataFrame):
            normalized[str(name)] = value
        else:
            raise TypeError(
                f"variable store input {name!r} must be a DataFrame or ResearchVariableSnapshot"
            )
    return normalized


def _validate_output(
    frame: pd.DataFrame,
    definitions: tuple[ResearchVariableDefinition, ...],
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("compute callback must return a pandas DataFrame")

    duplicate_columns = [str(item) for item in frame.columns[frame.columns.duplicated()].unique()]
    if duplicate_columns:
        raise ValueError(f"duplicate output columns: {', '.join(sorted(duplicate_columns))}")

    missing_columns = sorted(item.column for item in definitions if item.column not in frame.columns)
    if missing_columns:
        raise ValueError(f"missing declared output columns: {', '.join(missing_columns)}")

    declared_columns = {item.column for item in definitions}
    undeclared_columns = sorted(str(item) for item in frame.columns if item not in declared_columns)
    if undeclared_columns:
        raise ValueError(f"undeclared output columns: {', '.join(undeclared_columns)}")
    return frame


def _series_coverage(series: pd.Series) -> dict[str, str | int | None]:
    """Record the observed date coverage without declaring incomplete frames invalid."""

    if series.empty or not isinstance(series.index, pd.DatetimeIndex):
        return {
            "available_start": None,
            "available_end": None,
            "observations": int(len(series)),
        }
    index = series.index
    if index.tz is None:
        local = index.tz_localize("UTC").tz_convert("America/New_York")
    else:
        local = index.tz_convert("America/New_York")
    return {
        "available_start": local[0].date().isoformat(),
        "available_end": local[-1].date().isoformat(),
        "observations": int(len(series)),
    }


__all__ = ["VariableSnapshotStore", "VariableStoreResult"]
