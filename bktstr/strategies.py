from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any

from .measurements import baseline_variable_registry
from .variables import DataTier, FilterRole, VariableRef, inherited_tier


_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_-]*)+$")
_PARAMETER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_LOWER_TRUST_TIERS = frozenset((DataTier.C, DataTier.D))


def _immutable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _immutable_value(item)
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            }
        )
    if isinstance(value, list | tuple):
        return tuple(_immutable_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_immutable_value(item) for item in value), key=repr))
    return value


def _immutable_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    frozen = _immutable_value(value)
    assert isinstance(frozen, Mapping)
    return frozen


def _require_identifier(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} must be a dot-separated stable identifier")


def _require_version(value: str, *, label: str = "version") -> None:
    if not isinstance(value, str) or not _VERSION_RE.fullmatch(value):
        raise ValueError(f"{label} must be a semantic version")


def _matches_type(value: Any, expected: type) -> bool:
    if expected in (bool, int, float):
        return type(value) is expected
    return isinstance(value, expected)


@dataclass(frozen=True)
class StrategyParameter:
    name: str
    value_type: type
    default: Any
    minimum: int | float | None = None
    maximum: int | float | None = None
    choices: tuple[Any, ...] = ()
    overridable: bool = True
    allow_none: bool = False
    minimum_exclusive: bool = False
    maximum_exclusive: bool = False
    ui_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _PARAMETER_RE.fullmatch(self.name):
            raise ValueError("parameter name must be a stable snake-case identifier")
        if not isinstance(self.value_type, type):
            raise TypeError("value_type must be a Python type")
        if not isinstance(self.overridable, bool) or not isinstance(self.allow_none, bool):
            raise TypeError("parameter flags must be bool")
        if not isinstance(self.minimum_exclusive, bool) or not isinstance(
            self.maximum_exclusive, bool
        ):
            raise TypeError("parameter bound flags must be bool")
        object.__setattr__(self, "choices", tuple(_immutable_value(self.choices)))
        object.__setattr__(self, "ui_metadata", _immutable_mapping(self.ui_metadata))
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("parameter minimum cannot exceed maximum")
            if self.minimum == self.maximum and (
                self.minimum_exclusive or self.maximum_exclusive
            ):
                raise ValueError("exclusive parameter bounds cannot be equal")
        object.__setattr__(self, "default", self.validate(self.default))

    def validate(self, value: Any) -> Any:
        if value is None:
            if not self.allow_none:
                raise TypeError(f"{self.name} must be {self.value_type.__name__}")
            return None
        if not _matches_type(value, self.value_type):
            raise TypeError(f"{self.name} must be {self.value_type.__name__}")
        if self.choices and value not in self.choices:
            raise ValueError(f"{self.name} must be one of {self.choices!r}")
        if self.minimum is not None:
            invalid = (
                value <= self.minimum
                if self.minimum_exclusive
                else value < self.minimum
            )
            if invalid:
                relation = (
                    "greater than"
                    if self.minimum_exclusive
                    else "greater than or equal to"
                )
                raise ValueError(f"{self.name} must be {relation} {self.minimum}")
        if self.maximum is not None:
            invalid = (
                value >= self.maximum
                if self.maximum_exclusive
                else value > self.maximum
            )
            if invalid:
                relation = (
                    "less than"
                    if self.maximum_exclusive
                    else "less than or equal to"
                )
                raise ValueError(f"{self.name} must be {relation} {self.maximum}")
        return _immutable_value(value)


@dataclass(frozen=True)
class StrategyVariableUse:
    variable: VariableRef
    role: FilterRole
    rule: str | None
    forceable: bool

    def __post_init__(self) -> None:
        if not isinstance(self.variable, VariableRef):
            raise TypeError("variable must be a VariableRef")
        if not isinstance(self.role, FilterRole):
            raise TypeError("role must be a FilterRole")
        if self.rule is not None and (
            not isinstance(self.rule, str) or not self.rule.strip()
        ):
            raise ValueError("rule must be a non-empty string or None")
        if self.role is FilterRole.GATE and self.rule is None:
            raise ValueError("gate variable use requires a rule")
        if not isinstance(self.forceable, bool):
            raise TypeError("forceable must be bool")
        if self.forceable:
            raise ValueError("direct variable uses cannot be forceable")


@dataclass(frozen=True)
class StrategyFilterDefinition:
    id: str
    version: str
    output: VariableRef
    inputs: tuple[VariableRef, ...]
    role: FilterRole
    rule: str | None
    tier: DataTier
    forceable: bool
    optional: bool = False

    def __post_init__(self) -> None:
        _require_identifier(self.id, label="filter id")
        _require_version(self.version)
        if not isinstance(self.output, VariableRef):
            raise TypeError("filter output must be a VariableRef")
        if not self.output.id.startswith("strategy."):
            raise ValueError("filter output must be strategy-owned")
        object.__setattr__(self, "inputs", tuple(self.inputs))
        if not self.inputs or not all(isinstance(item, VariableRef) for item in self.inputs):
            raise ValueError("filter inputs must contain VariableRef values")
        if not isinstance(self.role, FilterRole):
            raise TypeError("filter role must be a FilterRole")
        if self.rule is not None and (
            not isinstance(self.rule, str) or not self.rule.strip()
        ):
            raise ValueError("filter rule must be a non-empty string or None")
        if self.role is FilterRole.GATE and self.rule is None:
            raise ValueError("gate filter requires a rule")
        if not isinstance(self.tier, DataTier) or self.output.tier is not self.tier:
            raise ValueError("filter output tier must match filter tier")
        if inherited_tier(
            tuple(item.tier for item in self.inputs), method_floor=self.tier
        ) is not self.tier:
            raise ValueError("filter tier cannot improve inherited trust")
        if not isinstance(self.forceable, bool):
            raise TypeError("filter forceable must be bool")
        if not isinstance(self.optional, bool):
            raise TypeError("filter optional must be bool")
        if self.forceable and not self.optional:
            raise ValueError("forceable filter must be optional")


@dataclass(frozen=True)
class ResolvedStrategy:
    strategy_id: str
    strategy_version: str
    schema_version: str
    values: Mapping[str, Any]
    execution_model_id: str
    execution_model_version: str

    def __post_init__(self) -> None:
        _require_identifier(self.strategy_id, label="strategy id")
        _require_version(self.strategy_version, label="strategy version")
        _require_version(self.schema_version, label="schema version")
        _require_identifier(self.execution_model_id, label="execution model id")
        _require_version(self.execution_model_version, label="execution model version")
        object.__setattr__(self, "values", _immutable_mapping(self.values))


@dataclass(frozen=True)
class StrategyDefinition:
    id: str
    schema_version: str
    version: str
    name: str
    description: str
    instrument_roles: tuple[str, ...]
    timeframe: str
    calendar: str
    timezone: str
    parameters: tuple[StrategyParameter, ...]
    variable_uses: tuple[StrategyVariableUse, ...]
    filters: tuple[StrategyFilterDefinition, ...]
    execution_model_id: str
    execution_model_version: str
    evidence_tier_opt_ins: tuple[DataTier, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.id, label="strategy id")
        _require_version(self.schema_version, label="schema version")
        _require_version(self.version, label="strategy version")
        _require_identifier(self.execution_model_id, label="execution model id")
        _require_version(self.execution_model_version, label="execution model version")
        if not self.name.strip() or not self.description.strip():
            raise ValueError("strategy name and description cannot be empty")
        object.__setattr__(self, "instrument_roles", tuple(self.instrument_roles))
        if not self.instrument_roles or any(
            not isinstance(role, str) or not _PARAMETER_RE.fullmatch(role)
            for role in self.instrument_roles
        ):
            raise ValueError("instrument roles must be stable identifiers")
        if len(set(self.instrument_roles)) != len(self.instrument_roles):
            raise ValueError("instrument roles must be unique")
        for label, value in (
            ("timeframe", self.timeframe),
            ("calendar", self.calendar),
            ("timezone", self.timezone),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{label} cannot be empty")
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(self, "variable_uses", tuple(self.variable_uses))
        object.__setattr__(self, "filters", tuple(self.filters))
        object.__setattr__(self, "evidence_tier_opt_ins", tuple(self.evidence_tier_opt_ins))
        if not all(isinstance(item, StrategyParameter) for item in self.parameters):
            raise TypeError("parameters must contain StrategyParameter values")
        if not all(isinstance(item, StrategyVariableUse) for item in self.variable_uses):
            raise TypeError("variable_uses must contain StrategyVariableUse values")
        if not all(isinstance(item, StrategyFilterDefinition) for item in self.filters):
            raise TypeError("filters must contain StrategyFilterDefinition values")
        parameter_names = tuple(item.name for item in self.parameters)
        if len(set(parameter_names)) != len(parameter_names):
            raise ValueError("strategy parameter names must be unique")
        variable_identities = tuple(
            (item.variable.id, item.variable.version) for item in self.variable_uses
        )
        if len(set(variable_identities)) != len(variable_identities):
            raise ValueError("strategy variable uses must have unique identities")
        filter_identities = tuple((item.id, item.version) for item in self.filters)
        if len(set(filter_identities)) != len(filter_identities):
            raise ValueError("strategy filters must have unique identities")
        opt_ins = self.evidence_tier_opt_ins
        if len(set(opt_ins)) != len(opt_ins) or any(
            tier not in _LOWER_TRUST_TIERS for tier in opt_ins
        ):
            raise ValueError("evidence tier opt-ins may contain Tier C and Tier D once each")
        for item in self.variable_uses:
            if item.variable.tier in _LOWER_TRUST_TIERS:
                raise ValueError(
                    "Tier C/D evidence must use a strategy-owned filter"
                )
        # Owned outputs use strategy.<full strategy id>.filter.<output name>.
        output_namespace = f"strategy.{self.id}.filter."
        for item in self.filters:
            if not item.output.id.startswith(output_namespace):
                raise ValueError(
                    f"filter output must use namespace {output_namespace}"
                )
            for reference in item.inputs:
                if (
                    reference.tier in _LOWER_TRUST_TIERS
                    and not reference.id.startswith(output_namespace)
                ):
                    raise ValueError(
                        "lower-trust filter input must use namespace "
                        f"{output_namespace}"
                    )
            for reference in (*item.inputs, item.output):
                if (
                    reference.tier in _LOWER_TRUST_TIERS
                    and reference.tier not in opt_ins
                ):
                    raise ValueError(
                        f"{reference.id} requires explicit Tier "
                        f"{reference.tier.value} opt-in"
                    )

    @property
    def parameter_definitions(self) -> Mapping[str, StrategyParameter]:
        return MappingProxyType({item.name: item for item in self.parameters})

    def resolve(self, overrides: Mapping[str, Any]) -> ResolvedStrategy:
        if not isinstance(overrides, Mapping):
            raise TypeError("strategy overrides must be a mapping")
        definitions = self.parameter_definitions
        unknown = sorted(set(overrides) - set(definitions))
        if unknown:
            raise ValueError(f"undeclared strategy parameter: {unknown[0]}")
        values: dict[str, Any] = {}
        for parameter in self.parameters:
            if parameter.name in overrides:
                if not parameter.overridable:
                    raise ValueError(f"{parameter.name} is not overridable")
                value = parameter.validate(overrides[parameter.name])
            else:
                value = parameter.default
            values[parameter.name] = value
        return ResolvedStrategy(
            strategy_id=self.id,
            strategy_version=self.version,
            schema_version=self.schema_version,
            values=values,
            execution_model_id=self.execution_model_id,
            execution_model_version=self.execution_model_version,
        )


@dataclass(frozen=True)
class StrategyRunRequest:
    strategy_id: str
    strategy_version: str
    instruments: Mapping[str, str]
    start: date
    end: date
    timeframe: str
    overrides: Mapping[str, Any] = field(default_factory=dict)
    confirm_degraded: bool = False

    def __post_init__(self) -> None:
        _require_identifier(self.strategy_id, label="strategy id")
        _require_version(self.strategy_version, label="strategy version")
        if not isinstance(self.instruments, Mapping) or not self.instruments:
            raise ValueError("instruments must contain role bindings")
        for role, symbol in self.instruments.items():
            if not isinstance(role, str) or not _PARAMETER_RE.fullmatch(role):
                raise ValueError("instrument role must be a stable identifier")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("instrument symbol cannot be empty")
        if type(self.start) is not date or type(self.end) is not date:
            raise TypeError("start and end must be dates")
        if self.end < self.start:
            raise ValueError("end must be on or after start")
        if not isinstance(self.timeframe, str) or not self.timeframe:
            raise ValueError("timeframe cannot be empty")
        if not isinstance(self.overrides, Mapping):
            raise TypeError("overrides must be a mapping")
        if not isinstance(self.confirm_degraded, bool):
            raise TypeError("confirm_degraded must be bool")
        object.__setattr__(self, "instruments", _immutable_mapping(self.instruments))
        object.__setattr__(self, "overrides", _immutable_mapping(self.overrides))


class StrategyRegistry:
    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str], StrategyDefinition] = {}

    @property
    def definitions(self) -> Mapping[tuple[str, str], StrategyDefinition]:
        return MappingProxyType(self._definitions)

    def register(self, definition: StrategyDefinition) -> None:
        if not isinstance(definition, StrategyDefinition):
            raise TypeError("definition must be a StrategyDefinition")
        identity = (definition.id, definition.version)
        if identity in self._definitions:
            raise ValueError(
                f"strategy {definition.id!r} version {definition.version!r} is already registered"
            )
        self._definitions[identity] = definition

    def get(self, strategy_id: str, version: str) -> StrategyDefinition | None:
        return self._definitions.get((strategy_id, version))

    def require(self, strategy_id: str, version: str) -> StrategyDefinition:
        definition = self.get(strategy_id, version)
        if definition is None:
            raise ValueError(f"unknown strategy {strategy_id!r} version {version!r}")
        return definition


_ENTRY_RULES = "close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10"
_REGIME_RULES = "day_sma20_slope5.lt:0,relative_return20.lt:0"


def _baseline_parameters() -> tuple[StrategyParameter, ...]:
    return (
        StrategyParameter("side", str, "short", choices=("long", "short")),
        StrategyParameter("entry_rules", str, _ENTRY_RULES),
        StrategyParameter("regime_rules", str, _REGIME_RULES, allow_none=True),
        StrategyParameter("stop_pct", float, 1.0, minimum=0.0, minimum_exclusive=True),
        StrategyParameter("target_pct", float, 3.0, minimum=0.0, minimum_exclusive=True),
        StrategyParameter("max_hold_minutes", int, 240, minimum=1),
        StrategyParameter(
            "position_size", float, 1000.0, minimum=0.0, minimum_exclusive=True
        ),
        StrategyParameter(
            "starting_capital", float, 10000.0, minimum=0.0, minimum_exclusive=True
        ),
        StrategyParameter("slippage_bps", float, 2.0, minimum=0.0),
        StrategyParameter("regular_hours_only", bool, True),
        StrategyParameter("same_day_only", bool, True),
        StrategyParameter("entry_start_time", str, "12:30", allow_none=True),
        StrategyParameter("entry_end_time", str, "16:00", allow_none=True),
        StrategyParameter("sentiment", bool, True),
        StrategyParameter(
            "sentiment_data_profile", str, "clean", choices=("clean",)
        ),
        StrategyParameter("sentiment_sources", tuple, ("price",)),
    )


def _baseline_variable_uses() -> tuple[StrategyVariableUse, ...]:
    rules = {
        "technical.vwap": "close.cross_below:vwap",
        "technical.rsi14": "rsi14.lt:50",
        "technical.volume_ratio20": "volume_ratio20.gt:1.10",
        "regime.day_sma20_slope5": "day_sma20_slope5.lt:0",
        "regime.relative_return20": "relative_return20.lt:0",
    }
    definitions = baseline_variable_registry().definitions.values()
    return tuple(
        StrategyVariableUse(
            variable=definition.ref,
            role=FilterRole.GATE if definition.id in rules else FilterRole.ANNOTATE,
            rule=rules.get(definition.id),
            forceable=False,
        )
        for definition in definitions
        if definition.tier is DataTier.B
    )


def baseline_strategy_definition() -> StrategyDefinition:
    return StrategyDefinition(
        id="bktstr.bearish-regime-scalp",
        schema_version="1.0.0",
        version="1.0.0",
        name="BKTSTR bearish regime scalp",
        description=(
            "Short intraday VWAP, RSI, and volume setup conditioned on completed daily "
            "sector-relative regime data, with price-implied sentiment annotations."
        ),
        instrument_roles=("subject", "sector", "market"),
        timeframe="1m",
        calendar="XNYS",
        timezone="America/New_York",
        parameters=_baseline_parameters(),
        variable_uses=_baseline_variable_uses(),
        filters=(),
        execution_model_id="bktstr.next-bar-open",
        execution_model_version="1.0.0",
        evidence_tier_opt_ins=(),
    )


def baseline_strategy_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(baseline_strategy_definition())
    return registry


__all__ = [
    "ResolvedStrategy",
    "StrategyDefinition",
    "StrategyFilterDefinition",
    "StrategyParameter",
    "StrategyRegistry",
    "StrategyRunRequest",
    "StrategyVariableUse",
    "baseline_strategy_definition",
    "baseline_strategy_registry",
]
