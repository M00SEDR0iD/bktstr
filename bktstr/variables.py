from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

import pandas as pd

from bktstr_cache.derived import canonical_json, dataframe_digest


_VARIABLE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


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


_TIER_ORDER = {DataTier.A: 0, DataTier.B: 1, DataTier.C: 2, DataTier.D: 3}


def inherited_tier(inputs: tuple[DataTier, ...], *, method_floor: DataTier) -> DataTier:
    return max((*inputs, method_floor), key=_TIER_ORDER.__getitem__)


class VariableContractError(ValueError):
    """Raised when a variable contract violates an immutable-domain invariant."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "variable_contract_error",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = _immutable_mapping(details or {})


def _immutable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _immutable_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_immutable_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_immutable_value(item) for item in value), key=canonical_json))
    return value


def _immutable_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): _immutable_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))})


def _require_identifier(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not _VARIABLE_ID_RE.fullmatch(value):
        raise VariableContractError(
            f"{label} must be a dot-separated stable identifier",
            code="invalid_identifier",
            details={label: value},
        )


def _require_version(value: str) -> None:
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        raise VariableContractError(
            "version must be a semantic version",
            code="invalid_version",
            details={"version": value},
        )


@dataclass(frozen=True)
class VariableRef:
    id: str
    version: str
    tier: DataTier

    def __post_init__(self) -> None:
        _require_identifier(self.id, label="id")
        _require_version(self.version)
        if not isinstance(self.tier, DataTier):
            raise VariableContractError("tier must be a DataTier", code="invalid_tier")


@dataclass(frozen=True)
class VariableDisplay:
    label: str
    description: str
    category: str
    preferred_chart: str = "line"
    color_hint: str | None = None
    strategy_owned: bool = False


@dataclass(frozen=True)
class VariableDiagnostic:
    code: str
    message: str
    variable_id: str
    variable: VariableRef | None = None
    affected_coverage: Mapping[str, Any] = field(default_factory=dict)
    affected_rules: tuple[str, ...] = ()
    suggestion_method: str | None = None
    suggested_value: Any | None = None
    suggested_reference: str | None = None
    suggestion_rationale: str | None = None
    applied: bool = False
    forceable: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_identifier(self.variable_id, label="variable_id")
        if self.variable is not None and self.variable.id != self.variable_id:
            raise VariableContractError(
                "diagnostic variable must match variable_id",
                code="diagnostic_variable_mismatch",
            )
        if self.applied:
            raise VariableContractError(
                "suggestions are diagnostics and cannot be applied",
                code="suggestion_applied",
            )
        object.__setattr__(self, "affected_coverage", _immutable_mapping(self.affected_coverage))
        object.__setattr__(self, "affected_rules", tuple(self.affected_rules))
        object.__setattr__(self, "details", _immutable_mapping(self.details))

    @property
    def variable_ref(self) -> VariableRef | None:
        return self.variable

    @property
    def suggestion_reference(self) -> str | None:
        return self.suggested_reference


@dataclass(frozen=True)
class ReplicationSuggestionPolicy:
    method: str
    value: Any | None = None
    reference: str | None = None
    rationale: str = ""

    @classmethod
    def neutral(cls, value: Any, rationale: str) -> "ReplicationSuggestionPolicy":
        return cls(method="neutral", value=value, rationale=rationale)

    @classmethod
    def last_valid(cls, rationale: str = "Use the last valid value for review only") -> "ReplicationSuggestionPolicy":
        return cls(method="last_valid", rationale=rationale)

    @classmethod
    def historical_median(
        cls, rationale: str = "Use the historical median for review only"
    ) -> "ReplicationSuggestionPolicy":
        return cls(method="historical_median", rationale=rationale)

    @classmethod
    def reference(cls, reference: str, rationale: str) -> "ReplicationSuggestionPolicy":
        return cls(method="reference", reference=reference, rationale=rationale)

    @classmethod
    def no_safe_suggestion(
        cls, rationale: str = "No safe deterministic suggestion is available"
    ) -> "ReplicationSuggestionPolicy":
        return cls(method="no_safe_suggestion", rationale=rationale)

    def suggest(
        self,
        *,
        variable_id: str,
        start: Any | None = None,
        end: Any | None = None,
        variable: VariableRef | None = None,
        affected_rules: tuple[str, ...] = (),
        forceable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> VariableDiagnostic:
        coverage = {key: value for key, value in {"start": start, "end": end}.items() if value is not None}
        return VariableDiagnostic(
            code="replication_suggestion",
            message=self.rationale,
            variable_id=variable_id,
            variable=variable,
            affected_coverage=coverage,
            affected_rules=affected_rules,
            suggestion_method=self.method,
            suggested_value=self.value,
            suggested_reference=self.reference,
            suggestion_rationale=self.rationale,
            applied=False,
            forceable=forceable,
            details=details or {},
        )


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

    def __post_init__(self) -> None:
        _require_identifier(self.id, label="id")
        _require_version(self.version)
        if not isinstance(self.kind, VariableKind):
            raise VariableContractError("kind must be a VariableKind", code="invalid_kind")
        if not isinstance(self.tier, DataTier):
            raise VariableContractError("tier must be a DataTier", code="invalid_tier")
        if not isinstance(self.column, str) or not self.column.strip():
            raise VariableContractError("column must be non-empty", code="invalid_column")
        if not isinstance(self.value_dtype, str) or not self.value_dtype.strip():
            raise VariableContractError("value_dtype must be non-empty", code="invalid_value_dtype")
        if not isinstance(self.frequency, str) or not self.frequency.strip():
            raise VariableContractError("frequency must be non-empty", code="invalid_frequency")
        if not isinstance(self.suggestion_policy, ReplicationSuggestionPolicy):
            raise VariableContractError("suggestion_policy must be a ReplicationSuggestionPolicy", code="invalid_suggestion_policy")

        inputs = tuple(self.inputs)
        if any(not isinstance(item, VariableRef) for item in inputs):
            raise VariableContractError("inputs must contain VariableRef values", code="invalid_input")
        if len({item.id for item in inputs}) != len(inputs):
            raise VariableContractError("inputs must have unique variable IDs", code="duplicate_input")
        object.__setattr__(self, "inputs", inputs)

        if self.expected_min is not None and self.expected_max is not None and self.expected_min > self.expected_max:
            raise VariableContractError(
                "expected_min cannot exceed expected_max",
                code="invalid_expected_range",
            )
        if self.tier is DataTier.B and any(item.tier in (DataTier.C, DataTier.D) for item in inputs):
            raise VariableContractError(
                "Tier B cannot depend on Tier C or Tier D",
                code="illegal_tier_dependency",
            )
        calculated_tier = inherited_tier(tuple(item.tier for item in inputs), method_floor=self.tier)
        if calculated_tier is not self.tier:
            raise VariableContractError(
                f"tier {self.tier.value} cannot improve inherited tier {calculated_tier.value}",
                code="illegal_tier_dependency",
            )

    @property
    def ref(self) -> VariableRef:
        return VariableRef(self.id, self.version, self.tier)

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
        return cls(
            id=id,
            version=version,
            kind=VariableKind.SOURCE,
            tier=tier,
            column=column,
            value_dtype=value_dtype,
            frequency=frequency,
            units=units,
            display=display,
        )


def snapshot_digest(
    definition: ResearchVariableDefinition,
    series: pd.Series,
    input_digests: tuple[str, ...] = (),
    provenance: Mapping[str, Any] | None = None,
) -> str:
    if not isinstance(series, pd.Series):
        raise TypeError("snapshot_digest requires a pandas Series")
    material = {
        "definition": {
            "id": definition.id,
            "version": definition.version,
            "tier": definition.tier.value,
        },
        "series_digest": dataframe_digest(series.to_frame(name=definition.column)),
        "input_digests": list(input_digests),
        "provenance": provenance or {},
    }
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchVariableSnapshot:
    definition: ResearchVariableDefinition
    _series: pd.Series = field(repr=False, compare=False)
    digest: str = ""
    input_digests: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)
    coverage: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.definition, ResearchVariableDefinition):
            raise VariableContractError("definition must be a ResearchVariableDefinition", code="invalid_definition")
        if not isinstance(self._series, pd.Series):
            raise VariableContractError("snapshot values must be a pandas Series", code="invalid_series")
        series = self._series.copy(deep=True)
        values = series.to_numpy(copy=False)
        if hasattr(values, "setflags"):
            values.setflags(write=False)
        object.__setattr__(self, "_series", series)
        object.__setattr__(self, "input_digests", tuple(self.input_digests))
        object.__setattr__(self, "provenance", _immutable_mapping(self.provenance))
        object.__setattr__(self, "coverage", _immutable_mapping(self.coverage))
        expected_digest = snapshot_digest(self.definition, series, self.input_digests, self.provenance)
        if self.digest and self.digest != expected_digest:
            raise VariableContractError("snapshot digest does not match content", code="invalid_snapshot_digest")
        object.__setattr__(self, "digest", expected_digest)

    @classmethod
    def create(
        cls,
        definition: ResearchVariableDefinition,
        series: pd.Series,
        *,
        input_digests: tuple[str, ...],
        provenance: Mapping[str, Any],
        coverage: Mapping[str, Any] | None = None,
    ) -> "ResearchVariableSnapshot":
        if not isinstance(series, pd.Series):
            raise TypeError("series must be a pandas Series")
        copied_series = series.copy(deep=True)
        normalized_provenance = _immutable_mapping(provenance)
        return cls(
            definition=definition,
            _series=copied_series,
            input_digests=tuple(input_digests),
            provenance=normalized_provenance,
            coverage=coverage or {},
        )

    @property
    def series(self) -> pd.Series:
        return self._series.copy(deep=True)

    @property
    def tier(self) -> DataTier:
        return self.definition.tier

    @property
    def ref(self) -> VariableRef:
        return self.definition.ref


@dataclass(frozen=True)
class VariableSet(Mapping[str, ResearchVariableSnapshot]):
    snapshots: tuple[ResearchVariableSnapshot, ...] | Mapping[str, ResearchVariableSnapshot] = ()
    _by_id: Mapping[str, ResearchVariableSnapshot] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        items = tuple(self.snapshots.values()) if isinstance(self.snapshots, Mapping) else tuple(self.snapshots)
        if any(not isinstance(snapshot, ResearchVariableSnapshot) for snapshot in items):
            raise VariableContractError("VariableSet values must be snapshots", code="invalid_snapshot")
        by_id: dict[str, ResearchVariableSnapshot] = {}
        for snapshot in items:
            variable_id = snapshot.definition.id
            if variable_id in by_id:
                raise VariableContractError(
                    f"variable ID {variable_id!r} is duplicated in VariableSet",
                    code="duplicate_variable_id",
                )
            by_id[variable_id] = snapshot
        object.__setattr__(self, "snapshots", items)
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))

    def __getitem__(self, key: str) -> ResearchVariableSnapshot:
        return self._by_id[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_id)

    def __len__(self) -> int:
        return len(self._by_id)
