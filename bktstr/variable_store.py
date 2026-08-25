from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

import pandas as pd

from bktstr.variables import (
    ResearchVariableDefinition,
    ResearchVariableSnapshot,
    VariableSet,
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

    ids = [item.id for item in definitions]
    duplicate_ids = sorted({item for item in ids if ids.count(item) > 1})
    if duplicate_ids:
        raise ValueError(f"duplicate variable IDs: {', '.join(duplicate_ids)}")

    columns = [item.column for item in definitions]
    duplicate_columns = sorted({item for item in columns if columns.count(item) > 1})
    if duplicate_columns:
        raise ValueError(f"duplicate declared output columns: {', '.join(duplicate_columns)}")
    return definitions


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
    return frame


__all__ = ["VariableSnapshotStore", "VariableStoreResult"]
