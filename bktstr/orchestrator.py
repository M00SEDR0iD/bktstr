from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import pandas as pd

from bktstr_cache.derived import CacheResult, CacheStatus, DerivedFrameCache

from .build_info import runtime_build_info
from .cache import CachedProvider
from .engine import BacktestConfig, run_backtest_on_bars
from .provenance import sentiment_provenance
from .regime import regime_uses_market_fields
from .strategies import (
    ResolvedStrategy,
    StrategyDefinition,
    StrategyRegistry,
    StrategyRunRequest,
)
from .variable_registry import VariableRegistry
from .variable_store import VariableSnapshotStore
from .variables import (
    DataTier,
    ReplicationSuggestionPolicy,
    ResearchVariableDefinition,
    ResearchVariableSnapshot,
    VariableContractError,
    VariableDiagnostic,
    VariableRef,
    VariableSet,
)

if TYPE_CHECKING:
    from .service import BacktestRequest


_OHLCV_COLUMNS = frozenset(("open", "high", "low", "close", "volume"))
_BUILD_IDENTITY_KEYS = (
    "git_commit",
    "git_branch",
    "git_repo",
    "deployment_id",
    "build_time",
)
_CORRUPTION_CODES = frozenset(
    (
        "invalid_snapshot_digest",
        "immutable_snapshot_corruption",
        "snapshot_corruption",
    )
)


@dataclass(frozen=True)
class OrchestratorDependencies:
    """Application-owned dependencies for one strategy-neutral run."""

    provider: CachedProvider
    provider_name: str
    variable_store: VariableSnapshotStore
    variable_registry: VariableRegistry
    strategy_registry: StrategyRegistry
    derived_cache_enabled: bool = True
    build_identity: Mapping[str, Any] = field(default_factory=runtime_build_info)

    def __post_init__(self) -> None:
        if not isinstance(self.provider_name, str) or not self.provider_name:
            raise ValueError("provider_name cannot be empty")
        if not isinstance(self.derived_cache_enabled, bool):
            raise TypeError("derived_cache_enabled must be bool")
        if not isinstance(self.build_identity, Mapping):
            raise TypeError("build_identity must be a mapping")


@dataclass(frozen=True)
class StrategyRunResult:
    resolved_strategy: ResolvedStrategy
    variables: VariableSet
    summary: Mapping[str, Any]
    trades: tuple[Mapping[str, Any], ...]
    data: Mapping[str, Any]
    provenance: Mapping[str, Any]
    diagnostics: tuple[VariableDiagnostic, ...] = ()
    degraded: bool = False
    canonical: bool = True


class StrategyRunError(RuntimeError):
    """A stable domain error containing safe, structured diagnostics."""

    def __init__(
        self,
        code: str,
        diagnostics: tuple[VariableDiagnostic, ...],
        *,
        provider_cause: BaseException | None = None,
    ) -> None:
        self.code = str(code)
        self.diagnostics = tuple(diagnostics)
        # Kept out of the domain message, diagnostics, and provenance.  The
        # legacy boundary alone may re-raise an HTTP provider error for its
        # established transport classifier.
        self.provider_cause = provider_cause
        variable_ids = ", ".join(item.variable_id for item in self.diagnostics)
        super().__init__(f"{self.code}: {variable_ids}")


@dataclass(frozen=True)
class _VariableMaterialization:
    """One immutable artifact actually consumed or produced during a run."""

    snapshot: ResearchVariableSnapshot
    purpose: str
    role: str
    symbol: str
    timeframe: str
    requested_start: date
    requested_end: date
    cache: Mapping[str, Any]


@dataclass(frozen=True)
class _ContractDetailIdentity:
    variable_id: str
    version: str | None
    tier: DataTier | None


@dataclass(frozen=True)
class _ContractDiagnosticTarget:
    definition: ResearchVariableDefinition | None
    variable_id: str
    variable: VariableRef | None
    attribution: Mapping[str, Any] | None = None


class _NoWriteDerivedFrameCache(DerivedFrameCache):
    """Preserve cache-key semantics while the public toggle disables persistence."""

    def get_or_compute(
        self,
        namespace: str,
        dimensions: Mapping[str, Any],
        inputs: Mapping[str, pd.DataFrame | str],
        compute,
    ) -> CacheResult:
        digests = self.input_digests(inputs)
        key = self.make_key(namespace, dimensions, digests)
        payload_path, metadata_path = self._paths(namespace, key)
        frame = compute()
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("compute callback must return a pandas DataFrame")
        return CacheResult(
            frame=frame,
            status=CacheStatus(
                hit=False,
                key=key,
                namespace=namespace,
                payload_path=payload_path,
                metadata_path=metadata_path,
                # v0.3's disabled branch exposed an explicit zero rather than
                # timing an operation it intentionally did not cache.
                elapsed_seconds=0.0,
            ),
        )


def _cache_status(status: CacheStatus) -> dict[str, Any]:
    return {
        "hit": bool(status.hit),
        "elapsed_seconds": round(float(status.elapsed_seconds), 6),
        "recovered_corruption": bool(status.recovered_corruption),
    }


def _coverage_bounds(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return None, None
    if frame.index.tz is None:
        local = frame.index.tz_localize("UTC").tz_convert("America/New_York")
    else:
        local = frame.index.tz_convert("America/New_York")
    return local[0].date().isoformat(), local[-1].date().isoformat()


def _coverage(
    frame: pd.DataFrame, *, requested_start: date, requested_end: date
) -> dict[str, str | int | None]:
    available_start, available_end = _coverage_bounds(frame)
    return {
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "available_start": available_start,
        "available_end": available_end,
        "observations": int(len(frame)),
    }


def _definition_trace(
    definition: ResearchVariableDefinition,
) -> dict[str, str | None]:
    return {
        "id": definition.id,
        "version": definition.version,
        "kind": definition.kind.value,
        "tier": definition.tier.value,
        "column": definition.column,
        "value_dtype": definition.value_dtype,
        "frequency": definition.frequency,
        "plugin_id": definition.plugin_id,
        "plugin_version": definition.plugin_version,
        "formula_version": definition.formula_version,
    }


def _source_materializations(
    *,
    definitions: tuple[ResearchVariableDefinition, ...],
    frame: pd.DataFrame,
    purpose: str,
    role: str,
    symbol: str,
    timeframe: str,
    requested_start: date,
    requested_end: date,
    cache: Mapping[str, Any],
    provider_name: str,
) -> tuple[_VariableMaterialization, ...]:
    coverage = _coverage(
        frame, requested_start=requested_start, requested_end=requested_end
    )
    materializations: list[_VariableMaterialization] = []
    for definition in definitions:
        if definition.column not in frame.columns:
            continue
        snapshot = ResearchVariableSnapshot.create(
            definition,
            frame[definition.column],
            input_digests=(),
            provenance={
                "provider": provider_name,
                "purpose": purpose,
                "role": role,
                "symbol": symbol,
                "timeframe": timeframe,
            },
            coverage=coverage,
        )
        materializations.append(
            _VariableMaterialization(
                snapshot=snapshot,
                purpose=purpose,
                role=role,
                symbol=symbol,
                timeframe=timeframe,
                requested_start=requested_start,
                requested_end=requested_end,
                cache=dict(cache),
            )
        )
    return tuple(materializations)


def _measurement_materializations(
    *,
    variables: VariableSet,
    cache: CacheStatus,
    purpose: str,
    role: str,
    symbol: str,
    timeframe: str,
    requested_start: date,
    requested_end: date,
    include_tier_a: bool = False,
) -> tuple[_VariableMaterialization, ...]:
    return tuple(
        _VariableMaterialization(
            snapshot=snapshot,
            purpose=purpose,
            role=role,
            symbol=symbol,
            timeframe=timeframe,
            requested_start=requested_start,
            requested_end=requested_end,
            cache=_cache_status(cache),
        )
        for snapshot in variables.snapshots
        if include_tier_a or snapshot.tier is not DataTier.A
    )


def _materialization_trace(
    materialization: _VariableMaterialization,
) -> dict[str, Any]:
    snapshot = materialization.snapshot
    coverage = {
        "requested_start": materialization.requested_start.isoformat(),
        "requested_end": materialization.requested_end.isoformat(),
        **dict(snapshot.coverage),
    }
    scope = {
        "purpose": materialization.purpose,
        "role": materialization.role,
        "symbol": materialization.symbol,
        "timeframe": materialization.timeframe,
    }
    return {
        "artifact_id": (
            f"{snapshot.definition.id}@{materialization.purpose}:"
            f"{materialization.role}:{materialization.timeframe}:"
            f"{materialization.requested_start.isoformat()}:"
            f"{materialization.requested_end.isoformat()}"
        ),
        "definition": _definition_trace(snapshot.definition),
        "digest": snapshot.digest,
        "coverage": coverage,
        "cache": dict(materialization.cache),
        "scope": scope,
    }


def _safe_build_identity(identity: Mapping[str, Any]) -> dict[str, str | None]:
    return {
        key: str(identity[key]) if identity.get(key) is not None else None
        for key in _BUILD_IDENTITY_KEYS
        if key in identity
    }


def _store_for_run(dependencies: OrchestratorDependencies) -> VariableSnapshotStore:
    if dependencies.derived_cache_enabled:
        return dependencies.variable_store
    cache = getattr(dependencies.variable_store, "_cache", None)
    if not isinstance(cache, DerivedFrameCache):
        return dependencies.variable_store
    return VariableSnapshotStore(_NoWriteDerivedFrameCache(cache.root))


def _definition_for(
    registry: VariableRegistry, variable_id: str
) -> ResearchVariableDefinition:
    return registry.require(variable_id)


def _reference_from_contract_details(
    details: Mapping[str, Any]
) -> _ContractDetailIdentity | None:
    """Recover an error's structured identity without requiring registry membership."""

    def valid_variable_id(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        try:
            VariableRef(value, "0.0.0", DataTier.A)
        except VariableContractError:
            return None
        return value

    def tier(value: Any) -> DataTier | None:
        if isinstance(value, DataTier):
            return value
        if isinstance(value, str):
            try:
                return DataTier(value)
            except ValueError:
                return None
        return None

    def identity_from_value(
        value: Any, *, fallback_tier: Any = None
    ) -> _ContractDetailIdentity | None:
        if isinstance(value, ResearchVariableDefinition):
            return _ContractDetailIdentity(
                value.id,
                value.version,
                value.tier,
            )
        if isinstance(value, VariableRef):
            return _ContractDetailIdentity(value.id, value.version, value.tier)
        if isinstance(value, Mapping):
            variable_id = valid_variable_id(value.get("id"))
            if variable_id is None:
                return None
            version = value.get("version")
            return _ContractDetailIdentity(
                variable_id,
                version if isinstance(version, str) else None,
                tier(value.get("tier")) or tier(fallback_tier),
            )
        if isinstance(value, str):
            variable_id = valid_variable_id(value)
            return (
                _ContractDetailIdentity(variable_id, None, tier(fallback_tier))
                if variable_id is not None
                else None
            )
        if isinstance(value, tuple) and value and isinstance(value[0], str):
            variable_id = valid_variable_id(value[0])
            if variable_id is None:
                return None
            version = value[1] if len(value) >= 2 and isinstance(value[1], str) else None
            explicit_tier = value[2] if len(value) >= 3 else fallback_tier
            return _ContractDetailIdentity(
                variable_id,
                version,
                tier(explicit_tier),
            )
        return None

    direct = identity_from_value(details)
    if direct is not None:
        return direct
    for key in ("variable", "definition", "variable_id", "id", "dependency"):
        detail_tier = details.get(f"{key}_tier")
        if key == "variable":
            detail_tier = detail_tier or details.get("variable_tier")
        if key == "dependency":
            detail_tier = detail_tier or details.get("dependency_tier")
        value = details.get(key)
        if key == "variable_id" and isinstance(value, str):
            value = {
                "id": value,
                "version": details.get("version"),
                "tier": details.get("tier"),
            }
        identity = identity_from_value(value, fallback_tier=detail_tier)
        if identity is not None:
            return identity
    cycle = details.get("cycle")
    if isinstance(cycle, tuple):
        for item in cycle:
            identity = identity_from_value(item)
            if identity is not None:
                return identity
    return None


def _stable_registered_definition(
    registry: VariableRegistry,
    identity: _ContractDetailIdentity,
) -> ResearchVariableDefinition | None:
    candidates = tuple(
        definition
        for (variable_id, version), definition in registry.definitions.items()
        if variable_id == identity.variable_id
        and (identity.version is None or version == identity.version)
        and (identity.tier is None or definition.tier is identity.tier)
    )
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item.version, item.tier.value))


def _explicit_contract_reference(
    identity: _ContractDetailIdentity,
) -> VariableRef | None:
    if identity.version is None or identity.tier is None:
        return None
    try:
        return VariableRef(identity.variable_id, identity.version, identity.tier)
    except VariableContractError:
        return None


def _contract_target(
    *,
    registry: VariableRegistry,
    fallback_variable_id: str,
    error: VariableContractError,
) -> _ContractDiagnosticTarget:
    identity = _reference_from_contract_details(error.details)
    if identity is None:
        fallback = _definition_for(registry, fallback_variable_id)
        return _ContractDiagnosticTarget(fallback, fallback.id, fallback.ref)
    registered = _stable_registered_definition(registry, identity)
    explicit = _explicit_contract_reference(identity)
    reference = explicit or (registered.ref if registered is not None else None)
    resolved_version = (
        reference.version if reference is not None else identity.version
    )
    resolved_tier = reference.tier.value if reference is not None else (
        identity.tier.value if identity.tier is not None else None
    )
    return _ContractDiagnosticTarget(
        definition=registered,
        variable_id=identity.variable_id,
        variable=reference,
        attribution={
            "id": identity.variable_id,
            "version": resolved_version,
            "tier": resolved_tier,
            "registered": registered is not None,
        },
    )


def _definition_mismatched_fields(
    actual: ResearchVariableDefinition,
    registered: ResearchVariableDefinition,
) -> tuple[str, ...]:
    return tuple(
        item.name
        for item in fields(ResearchVariableDefinition)
        if getattr(actual, item.name) != getattr(registered, item.name)
    )


def _validate_generated_definitions(
    *,
    registry: VariableRegistry,
    definitions: tuple[ResearchVariableDefinition, ...],
    affected_rules: tuple[str, ...],
) -> None:
    """Ensure generated definitions are exactly the definitions governance approved."""

    seen: dict[tuple[str, str], ResearchVariableDefinition] = {}
    seen_by_id: dict[str, ResearchVariableDefinition] = {}
    for actual in definitions:
        identity = (actual.id, actual.version)
        prior = seen.get(identity)
        if prior is not None and prior != actual:
            _raise_diagnostic(
                "schema_mismatch",
                _diagnostic(
                    code="schema_mismatch",
                    definition=actual,
                    variable=actual.ref,
                    affected_coverage={},
                    affected_rules=affected_rules,
                    forceable=False,
                    details={
                        "failure_class": "materialization_definition",
                        "mismatched_fields": _definition_mismatched_fields(
                            actual, prior
                        ),
                    },
                ),
            )
        prior_by_id = seen_by_id.get(actual.id)
        if prior_by_id is not None and prior_by_id != actual:
            _raise_diagnostic(
                "schema_mismatch",
                _diagnostic(
                    code="schema_mismatch",
                    definition=actual,
                    variable=actual.ref,
                    affected_coverage={},
                    affected_rules=affected_rules,
                    forceable=False,
                    details={
                        "failure_class": "materialization_definition",
                        "mismatched_fields": _definition_mismatched_fields(
                            actual, prior_by_id
                        ),
                    },
                ),
            )
        seen[identity] = actual
        seen_by_id[actual.id] = actual

    for actual in seen.values():
        registered = registry.get(actual.ref)
        if registered is None:
            _raise_diagnostic(
                "unknown_variable",
                _diagnostic(
                    code="unknown_variable",
                    definition=actual,
                    variable=actual.ref,
                    affected_coverage={},
                    affected_rules=affected_rules,
                    forceable=False,
                    details={"failure_class": "registry_definition"},
                ),
            )
        mismatched_fields = _definition_mismatched_fields(actual, registered)
        if not mismatched_fields:
            continue
        code = (
            "formula_mismatch"
            if mismatched_fields == ("formula_version",)
            else "schema_mismatch"
        )
        _raise_diagnostic(
            code,
            _diagnostic(
                code=code,
                definition=actual,
                variable=actual.ref,
                affected_coverage={},
                affected_rules=affected_rules,
                forceable=False,
                details={
                    "failure_class": "registry_definition",
                    "mismatched_fields": mismatched_fields,
                },
            ),
        )


def _validate_materialized_definitions(
    *,
    registry: VariableRegistry,
    materializations: tuple[_VariableMaterialization, ...],
    affected_rules: tuple[str, ...],
) -> None:
    """Recheck the definitions carried by every actual immutable artifact."""

    _validate_generated_definitions(
        registry=registry,
        definitions=tuple(item.snapshot.definition for item in materializations),
        affected_rules=affected_rules,
    )


def _diagnostic(
    *,
    code: str,
    definition: ResearchVariableDefinition | None,
    variable: VariableRef | None,
    variable_id: str | None = None,
    affected_coverage: Mapping[str, Any],
    affected_rules: tuple[str, ...],
    forceable: bool,
    details: Mapping[str, Any] | None = None,
) -> VariableDiagnostic:
    resolved_variable_id = variable.id if variable is not None else variable_id
    if resolved_variable_id is None:
        raise ValueError("diagnostic requires a variable ID")
    policy = (
        definition.suggestion_policy
        if definition is not None
        else ReplicationSuggestionPolicy.no_safe_suggestion()
    )
    suggested = policy.suggest(
        variable_id=resolved_variable_id,
        variable=variable,
        affected_rules=affected_rules,
        forceable=forceable,
        details=details or {},
    )
    return replace(
        suggested,
        code=code,
        message=(
            f"{code} for {resolved_variable_id} (Tier {variable.tier.value})"
            if variable is not None
            else f"{code} for {resolved_variable_id}"
        ),
        affected_coverage=dict(affected_coverage),
    )


def _raise_diagnostic(
    code: str,
    diagnostic: VariableDiagnostic,
    *,
    provider_cause: BaseException | None = None,
) -> None:
    if provider_cause is None:
        raise StrategyRunError(code, (diagnostic,))
    raise StrategyRunError(
        code,
        (diagnostic,),
        provider_cause=provider_cause,
    ) from None


def _missing_coverage(
    *,
    registry: VariableRegistry,
    variable_id: str,
    required_start: date,
    required_end: date,
    frame: pd.DataFrame,
    affected_rules: tuple[str, ...],
    forceable: bool = False,
    details: Mapping[str, Any] | None = None,
) -> None:
    definition = _definition_for(registry, variable_id)
    available_start, available_end = _coverage_bounds(frame)
    _raise_diagnostic(
        "missing_coverage",
        _diagnostic(
            code="missing_coverage",
            definition=definition,
            variable=definition.ref,
            affected_coverage={
                "required_start": required_start.isoformat(),
                "required_end": required_end.isoformat(),
                "available_start": available_start,
                "available_end": available_end,
            },
            affected_rules=affected_rules,
            forceable=forceable,
            details=details,
        ),
    )


def _contract_failure(
    *,
    registry: VariableRegistry,
    variable_id: str,
    error: VariableContractError,
    affected_rules: tuple[str, ...],
) -> None:
    target = _contract_target(
        registry=registry,
        fallback_variable_id=variable_id,
        error=error,
    )
    code = (
        "immutable_snapshot_corruption"
        if error.code in _CORRUPTION_CODES or "snapshot" in error.code
        else str(error.code)
    )
    _raise_diagnostic(
        code,
        _diagnostic(
            code=code,
            definition=target.definition,
            variable=target.variable,
            variable_id=target.variable_id,
            affected_coverage={},
            affected_rules=affected_rules,
            forceable=False,
            details={
                "failure_class": "variable_contract",
                **(
                    {"attribution": target.attribution}
                    if target.attribution is not None
                    else {}
                ),
            },
        ),
    )


def _provider_failure(
    *,
    registry: VariableRegistry,
    variable_id: str,
    required_start: date,
    required_end: date,
    affected_rules: tuple[str, ...],
    provider_cause: BaseException | None = None,
) -> None:
    definition = _definition_for(registry, variable_id)
    _raise_diagnostic(
        "provider_failure",
        _diagnostic(
            code="provider_failure",
            definition=definition,
            variable=definition.ref,
            affected_coverage={
                "required_start": required_start.isoformat(),
                "required_end": required_end.isoformat(),
                "available_start": None,
                "available_end": None,
            },
            affected_rules=affected_rules,
            forceable=False,
            details={"failure_class": "provider"},
        ),
        provider_cause=provider_cause,
    )


async def _fetch_tier_a(
    *,
    dependencies: OrchestratorDependencies,
    variable_id: str,
    symbol: str,
    start: date,
    end: date,
    timeframe: str,
    affected_rules: tuple[str, ...],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        frame = await dependencies.provider.fetch_bars(symbol, start, end, timeframe)
    except Exception as error:
        _provider_failure(
            registry=dependencies.variable_registry,
            variable_id=variable_id,
            required_start=start,
            required_end=end,
            affected_rules=affected_rules,
            provider_cause=error,
        )
    if not isinstance(frame, pd.DataFrame):
        _provider_failure(
            registry=dependencies.variable_registry,
            variable_id=variable_id,
            required_start=start,
            required_end=end,
            affected_rules=affected_rules,
        )
    if frame.empty:
        _missing_coverage(
            registry=dependencies.variable_registry,
            variable_id=variable_id,
            required_start=start,
            required_end=end,
            frame=frame,
            affected_rules=affected_rules,
        )
    if not _OHLCV_COLUMNS.issubset(frame.columns):
        definition = _definition_for(dependencies.variable_registry, variable_id)
        _raise_diagnostic(
            "schema_mismatch",
            _diagnostic(
                code="schema_mismatch",
                definition=definition,
                variable=definition.ref,
                affected_coverage={},
                affected_rules=affected_rules,
                forceable=False,
                details={"failure_class": "schema"},
            ),
        )
    return frame, dict(dependencies.provider.last_stats)


async def _fetch_sentiment_daily(
    provider: CachedProvider,
    symbol: str,
    requested_start: date,
    required_start: date,
    end: date,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    fallback_used = False
    try:
        frame = await provider.fetch_bars(symbol, requested_start, end, "1d")
        cache_stats = dict(provider.last_stats)
    except httpx.HTTPStatusError:
        if requested_start >= required_start:
            raise
        fallback_used = True
        await provider.fetch_bars(symbol, required_start, end, "1d")
        cache_stats = dict(provider.last_stats)
        frame, cached_stats = provider.read_cached_bars(symbol, requested_start, end, "1d")
        cache_stats = {**cache_stats, **cached_stats}
    coverage_start, coverage_end = _coverage_bounds(frame)
    return frame, {
        "requested_start": requested_start.isoformat(),
        "required_start": required_start.isoformat(),
        "coverage_start": coverage_start,
        "coverage_end": coverage_end,
        "fallback_used": fallback_used,
        "daily_bars": int(len(frame)),
        "cache": cache_stats,
    }


async def _fetch_sentiment_tier_a(
    *,
    dependencies: OrchestratorDependencies,
    variable_id: str,
    symbol: str,
    requested_start: date,
    required_start: date,
    end: date,
    affected_rules: tuple[str, ...],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        return await _fetch_sentiment_daily(
            dependencies.provider,
            symbol,
            requested_start,
            required_start,
            end,
        )
    except Exception as error:
        _provider_failure(
            registry=dependencies.variable_registry,
            variable_id=variable_id,
            required_start=requested_start,
            required_end=end,
            affected_rules=affected_rules,
            provider_cause=error,
        )


def _merge_variables(*variable_sets: VariableSet) -> VariableSet:
    snapshots = {}
    for variable_set in variable_sets:
        for snapshot in variable_set.snapshots:
            snapshots[snapshot.definition.id] = snapshot
    return VariableSet(tuple(snapshots.values()))


def _variable_ids_for_rules(spec: str | None) -> tuple[str, ...]:
    if not spec:
        return ()
    from .rules import parse_rules

    fields_to_ids = {
        "open": "market.subject.open",
        "high": "market.subject.high",
        "low": "market.subject.low",
        "close": "market.subject.close",
        "volume": "market.subject.volume",
        "vwap": "technical.vwap",
        "rsi14": "technical.rsi14",
        "volume_ratio20": "technical.volume_ratio20",
    }
    ids: list[str] = []
    for rule in parse_rules(spec):
        fields = (rule.left, rule.right) if isinstance(rule.right, str) else (rule.left,)
        for item in fields:
            variable_id = fields_to_ids.get(item)
            if variable_id is not None and variable_id not in ids:
                ids.append(variable_id)
    return tuple(ids)


def _regime_variable_ids(spec: str | None) -> tuple[str, ...]:
    if not spec:
        return ()
    from .rules import parse_rules

    ids: list[str] = []
    for rule in parse_rules(spec):
        fields = (rule.left, rule.right) if isinstance(rule.right, str) else (rule.left,)
        for item in fields:
            if item.startswith("sentiment_"):
                variable_id = f"sentiment.{item.removeprefix('sentiment_')}"
            elif item.startswith("day_") or item in {
                "benchmark_return20",
                "relative_return20",
            }:
                variable_id = f"regime.{item}"
            else:
                continue
            if variable_id not in ids:
                ids.append(variable_id)
    return tuple(ids)


def _require_usable_rule_values(
    *,
    registry: VariableRegistry,
    variables: VariableSet,
    variable_ids: tuple[str, ...],
    bars: pd.DataFrame,
    request: StrategyRunRequest,
    rule: str,
) -> None:
    for variable_id in variable_ids:
        snapshot = variables.get(variable_id)
        if snapshot is not None:
            series = snapshot.series
        else:
            definition = registry.require(variable_id)
            series = bars.get(definition.column, pd.Series(dtype=float))
        if not series.empty and series.notna().any():
            continue
        _missing_coverage(
            registry=registry,
            variable_id=variable_id,
            required_start=request.start,
            required_end=request.end,
            frame=bars,
            affected_rules=(rule,),
        )


def _filter_diagnostic(
    definition: StrategyDefinition,
    filter_definition,
    request: StrategyRunRequest,
) -> VariableDiagnostic:
    return _diagnostic(
        code="missing_filter_input",
        definition=None,
        variable=filter_definition.output,
        affected_coverage={
            "required_start": request.start.isoformat(),
            "required_end": request.end.isoformat(),
            "available_start": None,
            "available_end": None,
        },
        affected_rules=(filter_definition.rule or filter_definition.id,),
        forceable=filter_definition.optional and filter_definition.forceable,
        details={
            "filter_id": filter_definition.id,
            "strategy_id": definition.id,
            "omission_effect": "filter would not be evaluated",
        },
    )


def _filter_input_lineage(
    filter_definition, variables: VariableSet
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "id": reference.id,
            "version": reference.version,
            "tier": reference.tier.value,
            "digest": (
                variables[reference.id].digest
                if reference.id in variables
                else None
            ),
        }
        for reference in filter_definition.inputs
    )


def _filter_thresholds(rule: str | None) -> tuple[Mapping[str, Any], ...]:
    if rule is None:
        return ()
    from .rules import parse_rules

    try:
        parsed = parse_rules(rule)
    except ValueError:
        # Preserve existing strategy-definition compatibility: parsing a rule is
        # diagnostic provenance here, not a new execution-time validation point.
        return ({"expression": rule},)
    return tuple(
        {
            "field": item.left,
            "operator": item.op,
            "value": item.right,
        }
        for item in parsed
    )


def _observed_filter_value(snapshot: ResearchVariableSnapshot | None) -> Any | None:
    if snapshot is None:
        return None
    observed = snapshot.series.dropna()
    if observed.empty:
        return None
    value = observed.iloc[-1]
    return value.item() if hasattr(value, "item") else value


def _filter_decision(
    *,
    filter_definition,
    request: StrategyRunRequest,
    variables: VariableSet,
    available: bool,
) -> Mapping[str, Any]:
    output = variables.get(filter_definition.output.id)
    status = "evaluated" if available else "not_evaluated"
    return {
        "id": filter_definition.id,
        "version": filter_definition.version,
        "tier": filter_definition.tier.value,
        "role": filter_definition.role.value,
        "status": status,
        "outcome": "evaluated" if available else "omitted",
        "confirmation": bool(request.confirm_degraded),
        "inputs": _filter_input_lineage(filter_definition, variables),
        "observed_value": _observed_filter_value(output) if available else None,
        "rule": filter_definition.rule,
        "threshold": _filter_thresholds(filter_definition.rule),
        "backfill": {"attempted": False, "applied": False},
    }


def _evaluate_filters(
    *,
    definition: StrategyDefinition,
    request: StrategyRunRequest,
    variables: VariableSet,
) -> tuple[tuple[VariableDiagnostic, ...], tuple[Mapping[str, Any], ...], bool]:
    diagnostics: list[VariableDiagnostic] = []
    decisions: list[Mapping[str, Any]] = []
    degraded = False
    for filter_definition in definition.filters:
        # V0.5 has no registered production C/D filter adapters. A declared filter
        # therefore remains unavailable unless a future adapter materializes its
        # immutable output; it cannot alter the A/B execution frame here.
        available = filter_definition.output.id in variables
        if available:
            decisions.append(
                _filter_decision(
                    filter_definition=filter_definition,
                    request=request,
                    variables=variables,
                    available=True,
                )
            )
            continue
        diagnostic = _filter_diagnostic(definition, filter_definition, request)
        if not (
            request.confirm_degraded
            and filter_definition.optional
            and filter_definition.forceable
        ):
            _raise_diagnostic("non_forceable_degraded_execution", diagnostic)
        diagnostics.append(diagnostic)
        degraded = True
        decisions.append(
            _filter_decision(
                filter_definition=filter_definition,
                request=request,
                variables=variables,
                available=False,
            )
        )
    return tuple(diagnostics), tuple(decisions), degraded


def _dependency_trace(
    definitions: tuple[ResearchVariableDefinition, ...],
    materializations: tuple[_VariableMaterialization, ...],
) -> tuple[Mapping[str, Any], ...]:
    # The graph roots express calculated dependencies, while materializations
    # express every source column actually acquired (including execution-only
    # columns such as subject open).  The latter are appended exactly once so a
    # reused variable ID is disambiguated by its scoped artifacts, not by a
    # duplicate top-level record.
    traced_definitions = list(definitions)
    definitions_by_id = {definition.id: definition for definition in definitions}
    for materialization in materializations:
        actual = materialization.snapshot.definition
        if actual.id not in definitions_by_id:
            traced_definitions.append(actual)
            definitions_by_id[actual.id] = actual
    by_id: dict[str, list[_VariableMaterialization]] = {}
    for materialization in materializations:
        by_id.setdefault(materialization.snapshot.definition.id, []).append(
            materialization
        )
    trace: list[Mapping[str, Any]] = []
    for definition in traced_definitions:
        records = tuple(
            _materialization_trace(item) for item in by_id.get(definition.id, ())
        )
        digests: str | tuple[str, ...] | None
        coverages: Mapping[str, Any] | tuple[Mapping[str, Any], ...]
        if len(records) == 1:
            digests = records[0]["digest"]
            coverages = records[0]["coverage"]
        elif records:
            digests = tuple(item["digest"] for item in records)
            coverages = tuple(item["coverage"] for item in records)
        else:
            digests = None
            coverages = {}
        trace.append(
            {
                "id": definition.id,
                "version": definition.version,
                "tier": definition.tier.value,
                "kind": definition.kind.value,
                "formula_version": definition.formula_version,
                "dependencies": tuple(item.id for item in definition.inputs),
                "digest": digests,
                "coverage": coverages,
                "materializations": records,
            }
        )
    return tuple(trace)


def legacy_request_to_strategy_run(request: BacktestRequest) -> StrategyRunRequest:
    """Losslessly map the legacy request surface onto the registered baseline."""

    # Import-time construction is intentionally avoided here: this adapter keeps
    # service.py independent of domain execution imports until a request runs.
    from .strategies import baseline_strategy_definition

    baseline = baseline_strategy_definition()
    instruments: dict[str, str] = {"subject": request.symbol}
    if request.benchmark:
        instruments["benchmark"] = request.benchmark
    if request.sentiment_sector_benchmark:
        instruments["sector"] = request.sentiment_sector_benchmark
    if request.sentiment_market_benchmark:
        instruments["market"] = request.sentiment_market_benchmark
    return StrategyRunRequest(
        strategy_id=baseline.id,
        strategy_version=baseline.version,
        instruments=instruments,
        start=request.start,
        end=request.end,
        timeframe=request.timeframe,
        overrides={
            "side": request.side,
            "entry_rules": request.entry,
            "regime_rules": request.regime,
            "stop_pct": request.stop_pct,
            "target_pct": request.target_pct,
            "max_hold_minutes": request.max_hold_minutes,
            "position_size": request.position_size,
            "starting_capital": request.starting_capital,
            "slippage_bps": request.slippage_bps,
            "regular_hours_only": request.regular_hours_only,
            "same_day_only": request.same_day_only,
            "entry_start_time": request.entry_start_time,
            "entry_end_time": request.entry_end_time,
            "sentiment": request.sentiment,
            "sentiment_data_profile": request.sentiment_data_profile,
            "sentiment_sources": tuple(request.sentiment_sources),
        },
    )


async def execute_strategy_run(
    request: StrategyRunRequest, dependencies: OrchestratorDependencies
) -> StrategyRunResult:
    """Run a resolved strategy through governed data acquisition and unchanged execution."""

    if not isinstance(request, StrategyRunRequest):
        raise TypeError("request must be a StrategyRunRequest")
    if not isinstance(dependencies, OrchestratorDependencies):
        raise TypeError("dependencies must be OrchestratorDependencies")

    definition = dependencies.strategy_registry.require(
        request.strategy_id, request.strategy_version
    )
    resolved = definition.resolve(request.overrides)
    stages: list[str] = ["strategy_resolved"]
    entry_rules = resolved.values["entry_rules"]
    regime_rules = resolved.values["regime_rules"]
    sentiment_enabled = bool(resolved.values["sentiment"])

    subject = request.instruments.get("subject")
    if subject is None:
        raise ValueError("strategy run requires a subject instrument")
    needs_regime = bool(regime_rules and regime_uses_market_fields(regime_rules))
    sector = request.instruments.get("sector")
    market = request.instruments.get("market")
    benchmark = request.instruments.get("benchmark")
    benchmark_regime_ids = {
        "regime.benchmark_return20",
        "regime.relative_return20",
    }
    if benchmark is None and benchmark_regime_ids.intersection(
        _regime_variable_ids(regime_rules)
    ):
        # The domain strategy declares sector rather than the legacy-only
        # benchmark role. Legacy requests that reference benchmark fields are
        # already required to supply that explicit binding before adaptation.
        benchmark = sector
    if sentiment_enabled and (not sector or not market):
        raise ValueError("sentiment strategy run requires sector and market instruments")

    (
        attach_regime_variables,
        attach_sentiment_variables,
        compute_intraday_variables,
        compute_regime_variables,
        compute_sentiment_variables,
        intraday_definitions,
        regime_definitions,
        sentiment_definitions,
        source_definitions,
    ) = _measurement_adapters()
    generated_definitions = [
        *source_definitions("subject"),
        *intraday_definitions(),
    ]
    if needs_regime:
        generated_definitions.extend(source_definitions("subject"))
        if benchmark:
            generated_definitions.extend(source_definitions("benchmark"))
        generated_definitions.extend(
            regime_definitions(include_benchmark=bool(benchmark))
        )
    if sentiment_enabled:
        generated_definitions.extend(source_definitions("subject"))
        generated_definitions.extend(source_definitions("sector"))
        generated_definitions.extend(source_definitions("market"))
        generated_definitions.extend(sentiment_definitions())
    _validate_generated_definitions(
        registry=dependencies.variable_registry,
        definitions=tuple(generated_definitions),
        affected_rules=tuple(item for item in (entry_rules, regime_rules) if item),
    )

    # The registry graph is validated only after its concrete generated
    # definitions have been checked, so a tampered tier/schema never masquerades
    # as a governed dependency graph.
    try:
        dependencies.variable_registry.validate_dependencies(
            tuple(item.variable for item in definition.variable_uses)
        )
        for filter_definition in definition.filters:
            dependencies.variable_registry.validate_dependencies(filter_definition.inputs)
    except VariableContractError as error:
        _contract_failure(
            registry=dependencies.variable_registry,
            variable_id="market.subject.close",
            error=error,
            affected_rules=(entry_rules,),
        )
    stages.append("variable_graph_validated")

    # Tier A acquisition is deliberately complete before any Tier B calculation.
    raw_bars, intraday_cache = await _fetch_tier_a(
        dependencies=dependencies,
        variable_id="market.subject.close",
        symbol=subject,
        start=request.start,
        end=request.end,
        timeframe=request.timeframe,
        affected_rules=(entry_rules,),
    )

    regime_subject_daily = regime_benchmark_daily = None
    regime_warmup_start: date | None = None
    regime_data = None
    if needs_regime:
        regime_warmup_start = request.start - timedelta(days=120)
        regime_subject_daily, subject_cache = await _fetch_tier_a(
            dependencies=dependencies,
            variable_id="market.subject.close",
            symbol=subject,
            start=regime_warmup_start,
            end=request.end,
            timeframe="1d",
            affected_rules=(regime_rules,),
        )
        benchmark_cache = None
        if benchmark:
            regime_benchmark_daily, benchmark_cache = await _fetch_tier_a(
                dependencies=dependencies,
                variable_id="market.benchmark.close",
                symbol=benchmark,
                start=regime_warmup_start,
                end=request.end,
                timeframe="1d",
                affected_rules=(regime_rules,),
            )
        regime_data = {
            "subject": subject,
            "subject_daily_bars": int(len(regime_subject_daily)),
            "subject_cache": subject_cache,
            "benchmark": benchmark,
            "benchmark_daily_bars": int(len(regime_benchmark_daily))
            if regime_benchmark_daily is not None
            else 0,
            "benchmark_cache": benchmark_cache,
            "warmup_start": regime_warmup_start.isoformat(),
        }

    sentiment_subject_daily = sentiment_sector_daily = sentiment_market_daily = None
    sentiment_warmup_start: date | None = None
    sentiment_coverages = None
    if sentiment_enabled:
        sentiment_warmup_start = request.start - timedelta(days=460)
        sentiment_rules = (regime_rules or "sentiment",)
        sentiment_subject_daily, subject_coverage = await _fetch_sentiment_tier_a(
            dependencies=dependencies,
            variable_id="market.subject.close",
            symbol=subject,
            requested_start=sentiment_warmup_start,
            required_start=request.start,
            end=request.end,
            affected_rules=sentiment_rules,
        )
        sentiment_sector_daily, sector_coverage = await _fetch_sentiment_tier_a(
            dependencies=dependencies,
            variable_id="market.sector.close",
            symbol=sector,
            requested_start=sentiment_warmup_start,
            required_start=request.start,
            end=request.end,
            affected_rules=sentiment_rules,
        )
        sentiment_market_daily, market_coverage = await _fetch_sentiment_tier_a(
            dependencies=dependencies,
            variable_id="market.market.close",
            symbol=market,
            requested_start=sentiment_warmup_start,
            required_start=request.start,
            end=request.end,
            affected_rules=sentiment_rules,
        )
        daily_sets = (
            ("market.subject.close", sentiment_subject_daily),
            ("market.sector.close", sentiment_sector_daily),
            ("market.market.close", sentiment_market_daily),
        )
        for variable_id, frame in daily_sets:
            if frame.empty:
                _missing_coverage(
                    registry=dependencies.variable_registry,
                    variable_id=variable_id,
                    required_start=sentiment_warmup_start,
                    required_end=request.end,
                    frame=frame,
                    affected_rules=(regime_rules or "sentiment",),
                )
        sentiment_coverages = (subject_coverage, sector_coverage, market_coverage)
    stages.append("tier_a_acquired")

    store = _store_for_run(dependencies)
    materializations: list[_VariableMaterialization] = list(
        _source_materializations(
            definitions=source_definitions("subject"),
            frame=raw_bars,
            purpose="intraday",
            role="subject",
            symbol=subject,
            timeframe=request.timeframe,
            requested_start=request.start,
            requested_end=request.end,
            cache=intraday_cache,
            provider_name=dependencies.provider_name,
        )
    )
    if needs_regime:
        assert regime_warmup_start is not None
        materializations.extend(
            _source_materializations(
                definitions=source_definitions("subject"),
                frame=regime_subject_daily,
                purpose="regime",
                role="subject",
                symbol=subject,
                timeframe="1d",
                requested_start=regime_warmup_start,
                requested_end=request.end,
                cache=subject_cache,
                provider_name=dependencies.provider_name,
            )
        )
        if regime_benchmark_daily is not None:
            materializations.extend(
                _source_materializations(
                    definitions=source_definitions("benchmark"),
                    frame=regime_benchmark_daily,
                    purpose="regime",
                    role="benchmark",
                    symbol=benchmark,
                    timeframe="1d",
                    requested_start=regime_warmup_start,
                    requested_end=request.end,
                    cache=benchmark_cache or {},
                    provider_name=dependencies.provider_name,
                )
            )
    if sentiment_enabled:
        assert sentiment_warmup_start is not None
        materializations.extend(
            _source_materializations(
                definitions=source_definitions("subject"),
                frame=sentiment_subject_daily,
                purpose="sentiment",
                role="subject",
                symbol=subject,
                timeframe="1d",
                requested_start=sentiment_warmup_start,
                requested_end=request.end,
                cache=subject_coverage["cache"],
                provider_name=dependencies.provider_name,
            )
        )
        materializations.extend(
            _source_materializations(
                definitions=source_definitions("sector"),
                frame=sentiment_sector_daily,
                purpose="sentiment",
                role="sector",
                symbol=sector,
                timeframe="1d",
                requested_start=sentiment_warmup_start,
                requested_end=request.end,
                cache=sector_coverage["cache"],
                provider_name=dependencies.provider_name,
            )
        )
        materializations.extend(
            _source_materializations(
                definitions=source_definitions("market"),
                frame=sentiment_market_daily,
                purpose="sentiment",
                role="market",
                symbol=market,
                timeframe="1d",
                requested_start=sentiment_warmup_start,
                requested_end=request.end,
                cache=market_coverage["cache"],
                provider_name=dependencies.provider_name,
            )
        )
    try:
        intraday_result = compute_intraday_variables(
            store=store,
            raw_bars=raw_bars,
            symbol=subject,
            timeframe=request.timeframe,
            regular_hours_only=resolved.values["regular_hours_only"],
        )
    except VariableContractError as error:
        _contract_failure(
            registry=dependencies.variable_registry,
            variable_id="technical.vwap",
            error=error,
            affected_rules=(entry_rules,),
        )
    bars = intraday_result.legacy_frame
    variable_sets = [intraday_result.variables]
    materializations.extend(
        _measurement_materializations(
            variables=intraday_result.variables,
            cache=intraday_result.status,
            purpose="intraday_features",
            role="subject",
            symbol=subject,
            timeframe=request.timeframe,
            requested_start=request.start,
            requested_end=request.end,
            include_tier_a=True,
        )
    )
    derived_stats: dict[str, Any] = {
        "enabled": dependencies.derived_cache_enabled,
        "intraday": _cache_status(intraday_result.status),
    }
    attachments: dict[str, Mapping[str, Any]] = {}
    active_definitions: list[ResearchVariableDefinition] = list(intraday_definitions())

    if needs_regime:
        try:
            regime_result = compute_regime_variables(
                store=store,
                subject_daily=regime_subject_daily,
                benchmark_daily=regime_benchmark_daily,
                subject=subject,
                benchmark=benchmark,
            )
            regime_attachment = attach_regime_variables(
                store=store,
                intraday=bars,
                daily_regime=regime_result.legacy_frame,
                symbol=subject,
                timeframe=request.timeframe,
            )
        except VariableContractError as error:
            _contract_failure(
                registry=dependencies.variable_registry,
                variable_id="regime.day_close",
                error=error,
                affected_rules=(regime_rules,),
            )
        bars = regime_attachment.legacy_frame
        variable_sets.extend((regime_result.variables, regime_attachment.variables))
        assert regime_warmup_start is not None
        materializations.extend(
            _measurement_materializations(
                variables=regime_result.variables,
                cache=regime_result.status,
                purpose="daily_regime",
                role="subject",
                symbol=subject,
                timeframe="1d",
                requested_start=regime_warmup_start,
                requested_end=request.end,
            )
        )
        materializations.extend(
            _measurement_materializations(
                variables=regime_attachment.variables,
                cache=regime_attachment.status,
                purpose="intraday_regime_attachment",
                role="subject",
                symbol=subject,
                timeframe=request.timeframe,
                requested_start=request.start,
                requested_end=request.end,
            )
        )
        derived_stats["regime"] = _cache_status(regime_result.status)
        attachments["regime"] = {
            "availability": "prior_day",
            "cache": _cache_status(regime_attachment.status),
        }
        active_definitions.extend(
            regime_definitions(include_benchmark=regime_benchmark_daily is not None)
        )

    if sentiment_enabled:
        try:
            sentiment_result = compute_sentiment_variables(
                store=store,
                subject_daily=sentiment_subject_daily,
                sector_daily=sentiment_sector_daily,
                market_daily=sentiment_market_daily,
                subject=subject,
                sector_benchmark=sector,
                market_benchmark=market,
                data_profile=resolved.values["sentiment_data_profile"],
                sources=resolved.values["sentiment_sources"],
            )
            sentiment_attachment = attach_sentiment_variables(
                store=store,
                intraday=bars,
                daily_sentiment=sentiment_result.legacy_frame,
                symbol=subject,
                timeframe=request.timeframe,
            )
        except VariableContractError as error:
            _contract_failure(
                registry=dependencies.variable_registry,
                variable_id="sentiment.direction",
                error=error,
                affected_rules=(regime_rules or "sentiment",),
            )
        bars = sentiment_attachment.legacy_frame
        variable_sets.extend((sentiment_result.variables, sentiment_attachment.variables))
        assert sentiment_warmup_start is not None
        materializations.extend(
            _measurement_materializations(
                variables=sentiment_result.variables,
                cache=sentiment_result.status,
                purpose="daily_sentiment",
                role="subject",
                symbol=subject,
                timeframe="1d",
                requested_start=sentiment_warmup_start,
                requested_end=request.end,
            )
        )
        materializations.extend(
            _measurement_materializations(
                variables=sentiment_attachment.variables,
                cache=sentiment_attachment.status,
                purpose="intraday_sentiment_attachment",
                role="subject",
                symbol=subject,
                timeframe=request.timeframe,
                requested_start=request.start,
                requested_end=request.end,
            )
        )
        derived_stats["sentiment"] = _cache_status(sentiment_result.status)
        attachments["sentiment"] = {
            "availability": "prior_day",
            "cache": _cache_status(sentiment_attachment.status),
        }
        active_definitions.extend(sentiment_definitions())

    variables = _merge_variables(*variable_sets)
    stages.append("tier_b_calculated")
    _validate_materialized_definitions(
        registry=dependencies.variable_registry,
        materializations=tuple(materializations),
        affected_rules=tuple(
            item for item in (entry_rules, regime_rules) if item
        ),
    )
    try:
        trace_definitions = dependencies.variable_registry.validate_dependencies(
            tuple(item.ref for item in active_definitions)
        )
    except VariableContractError as error:
        _contract_failure(
            registry=dependencies.variable_registry,
            variable_id="market.subject.close",
            error=error,
            affected_rules=tuple(
                item for item in (entry_rules, regime_rules) if item
            ),
        )
    _require_usable_rule_values(
        registry=dependencies.variable_registry,
        variables=variables,
        variable_ids=_variable_ids_for_rules(entry_rules),
        bars=bars,
        request=request,
        rule=entry_rules,
    )
    _require_usable_rule_values(
        registry=dependencies.variable_registry,
        variables=variables,
        variable_ids=_regime_variable_ids(regime_rules),
        bars=bars,
        request=request,
        rule=regime_rules or "",
    )
    diagnostics, filter_decisions, degraded = _evaluate_filters(
        definition=definition, request=request, variables=variables
    )
    stages.append("filters_evaluated")

    execution = run_backtest_on_bars(
        bars,
        BacktestConfig(
            side=resolved.values["side"],
            entry_rules=entry_rules,
            regime_rules=regime_rules,
            stop_pct=resolved.values["stop_pct"],
            target_pct=resolved.values["target_pct"],
            max_hold_minutes=resolved.values["max_hold_minutes"],
            position_size=resolved.values["position_size"],
            starting_capital=resolved.values["starting_capital"],
            slippage_bps=resolved.values["slippage_bps"],
            regular_hours_only=resolved.values["regular_hours_only"],
            same_day_only=resolved.values["same_day_only"],
            entry_start_time=resolved.values["entry_start_time"],
            entry_end_time=resolved.values["entry_end_time"],
            features_precomputed=True,
        ),
    )
    stages.extend(("signals_evaluated", "execution_completed"))

    data: dict[str, Any] = {
        "bars": int(len(raw_bars)),
        "provider": dependencies.provider_name,
        "cache": intraday_cache,
        "derived_cache": derived_stats,
    }
    if regime_data is not None:
        data["regime"] = regime_data
    if sentiment_enabled and sentiment_coverages is not None:
        subject_coverage, sector_coverage, market_coverage = sentiment_coverages
        starts = [item["coverage_start"] for item in sentiment_coverages]
        ends = [item["coverage_end"] for item in sentiment_coverages]
        common_coverage_start = max(starts) if all(starts) else None
        common_coverage_end = min(ends) if all(ends) else None
        data["sentiment"] = {
            "subject": subject,
            "sector_benchmark": sector,
            "market_benchmark": market,
            "warmup_start": (request.start - timedelta(days=460)).isoformat(),
            "requested_warmup_start": (request.start - timedelta(days=460)).isoformat(),
            "coverage_start": common_coverage_start,
            "coverage_end": common_coverage_end,
            "warmup_degraded": any(
                item["fallback_used"] for item in sentiment_coverages
            )
            or common_coverage_start is None,
            "coverage": {
                "subject": subject_coverage,
                "sector": sector_coverage,
                "market": market_coverage,
            },
            "subject_daily_bars": int(len(sentiment_subject_daily)),
            "sector_daily_bars": int(len(sentiment_sector_daily)),
            "market_daily_bars": int(len(sentiment_market_daily)),
            "subject_cache": subject_coverage["cache"],
            "sector_cache": sector_coverage["cache"],
            "market_cache": market_coverage["cache"],
            "multipliers_are_informational": True,
            "provenance": sentiment_provenance(
                resolved.values["sentiment_data_profile"],
                resolved.values["sentiment_sources"],
            ),
        }

    return StrategyRunResult(
        resolved_strategy=resolved,
        variables=variables,
        summary=execution["summary"],
        trades=tuple(execution["trades"]),
        data=data,
        provenance={
            "strategy": {
                "id": resolved.strategy_id,
                "version": resolved.strategy_version,
                "schema_version": resolved.schema_version,
                "execution_model_id": resolved.execution_model_id,
                "execution_model_version": resolved.execution_model_version,
            },
            "provider": {"name": dependencies.provider_name},
            "build": _safe_build_identity(dependencies.build_identity),
            "stages": tuple(stages),
            "dependency_trace": _dependency_trace(
                trace_definitions, tuple(materializations)
            ),
            "attachments": attachments,
            "filters": filter_decisions,
        },
        diagnostics=diagnostics,
        degraded=degraded,
        canonical=not degraded,
    )


def _measurement_adapters():
    """Delay the legacy formula adapters to keep service/module imports acyclic."""

    from .measurements import (
        attach_regime_variables,
        attach_sentiment_variables,
        compute_intraday_variables,
        compute_regime_variables,
        compute_sentiment_variables,
        intraday_definitions,
        regime_definitions,
        sentiment_definitions,
        source_definitions,
    )

    return (
        attach_regime_variables,
        attach_sentiment_variables,
        compute_intraday_variables,
        compute_regime_variables,
        compute_sentiment_variables,
        intraday_definitions,
        regime_definitions,
        sentiment_definitions,
        source_definitions,
    )


__all__ = [
    "OrchestratorDependencies",
    "StrategyRunError",
    "StrategyRunResult",
    "execute_strategy_run",
    "legacy_request_to_strategy_run",
]
