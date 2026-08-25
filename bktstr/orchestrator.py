from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
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
    ReplicationSuggestionPolicy,
    ResearchVariableDefinition,
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

    def __init__(self, code: str, diagnostics: tuple[VariableDiagnostic, ...]) -> None:
        self.code = str(code)
        self.diagnostics = tuple(diagnostics)
        variable_ids = ", ".join(item.variable_id for item in self.diagnostics)
        super().__init__(f"{self.code}: {variable_ids}")


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


def _diagnostic(
    *,
    code: str,
    definition: ResearchVariableDefinition | None,
    variable: VariableRef,
    affected_coverage: Mapping[str, Any],
    affected_rules: tuple[str, ...],
    forceable: bool,
    details: Mapping[str, Any] | None = None,
) -> VariableDiagnostic:
    policy = (
        definition.suggestion_policy
        if definition is not None
        else ReplicationSuggestionPolicy.no_safe_suggestion()
    )
    suggested = policy.suggest(
        variable_id=variable.id,
        variable=variable,
        affected_rules=affected_rules,
        forceable=forceable,
        details=details or {},
    )
    return replace(
        suggested,
        code=code,
        message=f"{code} for {variable.id} (Tier {variable.tier.value})",
        affected_coverage=dict(affected_coverage),
    )


def _raise_diagnostic(code: str, diagnostic: VariableDiagnostic) -> None:
    raise StrategyRunError(code, (diagnostic,))


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
    definition = _definition_for(registry, variable_id)
    code = (
        "immutable_snapshot_corruption"
        if error.code in _CORRUPTION_CODES or "snapshot" in error.code
        else str(error.code)
    )
    _raise_diagnostic(
        code,
        _diagnostic(
            code=code,
            definition=definition,
            variable=definition.ref,
            affected_coverage={},
            affected_rules=affected_rules,
            forceable=False,
            details={"failure_class": "variable_contract"},
        ),
    )


def _provider_failure(
    *,
    registry: VariableRegistry,
    variable_id: str,
    required_start: date,
    required_end: date,
    affected_rules: tuple[str, ...],
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
    except Exception:
        _provider_failure(
            registry=dependencies.variable_registry,
            variable_id=variable_id,
            required_start=start,
            required_end=end,
            affected_rules=affected_rules,
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
                {
                    "id": filter_definition.id,
                    "version": filter_definition.version,
                    "tier": filter_definition.tier.value,
                    "role": filter_definition.role.value,
                    "status": "evaluated",
                    "inputs": tuple(item.id for item in filter_definition.inputs),
                }
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
            {
                "id": filter_definition.id,
                "version": filter_definition.version,
                "tier": filter_definition.tier.value,
                "role": filter_definition.role.value,
                "status": "not_evaluated",
                "inputs": tuple(item.id for item in filter_definition.inputs),
            }
        )
    return tuple(diagnostics), tuple(decisions), degraded


def _dependency_trace(
    definitions: tuple[ResearchVariableDefinition, ...], variables: VariableSet
) -> tuple[Mapping[str, Any], ...]:
    trace: list[Mapping[str, Any]] = []
    for definition in definitions:
        snapshot = variables.get(definition.id)
        trace.append(
            {
                "id": definition.id,
                "version": definition.version,
                "tier": definition.tier.value,
                "kind": definition.kind.value,
                "formula_version": definition.formula_version,
                "dependencies": tuple(item.id for item in definition.inputs),
                "digest": snapshot.digest if snapshot is not None else None,
                "coverage": dict(snapshot.coverage) if snapshot is not None else {},
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

    # The registry validation is governance-only and happens before acquisition.
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

    subject = request.instruments.get("subject")
    if subject is None:
        raise ValueError("strategy run requires a subject instrument")
    needs_regime = bool(regime_rules and regime_uses_market_fields(regime_rules))
    # The compatibility adapter preserves the legacy distinction: a sentiment
    # sector is not a regime benchmark unless the request explicitly supplies one.
    benchmark = request.instruments.get("benchmark")
    sector = request.instruments.get("sector")
    market = request.instruments.get("market")
    if sentiment_enabled and (not sector or not market):
        raise ValueError("sentiment strategy run requires sector and market instruments")

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
    regime_data = None
    if needs_regime:
        warmup_start = request.start - timedelta(days=120)
        regime_subject_daily, subject_cache = await _fetch_tier_a(
            dependencies=dependencies,
            variable_id="market.subject.close",
            symbol=subject,
            start=warmup_start,
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
                start=warmup_start,
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
            "warmup_start": warmup_start.isoformat(),
        }

    sentiment_subject_daily = sentiment_sector_daily = sentiment_market_daily = None
    sentiment_coverages = None
    if sentiment_enabled:
        warmup_start = request.start - timedelta(days=460)
        try:
            sentiment_subject_daily, subject_coverage = await _fetch_sentiment_daily(
                dependencies.provider, subject, warmup_start, request.start, request.end
            )
            sentiment_sector_daily, sector_coverage = await _fetch_sentiment_daily(
                dependencies.provider, sector, warmup_start, request.start, request.end
            )
            sentiment_market_daily, market_coverage = await _fetch_sentiment_daily(
                dependencies.provider, market, warmup_start, request.start, request.end
            )
        except Exception:
            _provider_failure(
                registry=dependencies.variable_registry,
                variable_id="market.subject.close",
                required_start=warmup_start,
                required_end=request.end,
                affected_rules=(regime_rules or "sentiment",),
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
                    required_start=warmup_start,
                    required_end=request.end,
                    frame=frame,
                    affected_rules=(regime_rules or "sentiment",),
                )
        sentiment_coverages = (subject_coverage, sector_coverage, market_coverage)
    stages.append("tier_a_acquired")

    (
        attach_regime_variables,
        attach_sentiment_variables,
        compute_intraday_variables,
        compute_regime_variables,
        compute_sentiment_variables,
        intraday_definitions,
        regime_definitions,
        sentiment_definitions,
    ) = _measurement_adapters()
    store = _store_for_run(dependencies)
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
        derived_stats["sentiment"] = _cache_status(sentiment_result.status)
        attachments["sentiment"] = {
            "availability": "prior_day",
            "cache": _cache_status(sentiment_attachment.status),
        }
        active_definitions.extend(sentiment_definitions())

    variables = _merge_variables(*variable_sets)
    stages.append("tier_b_calculated")
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

    trace_definitions = dependencies.variable_registry.validate_dependencies(
        tuple(item.ref for item in active_definitions)
    )

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
            "dependency_trace": _dependency_trace(trace_definitions, variables),
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
    )


__all__ = [
    "OrchestratorDependencies",
    "StrategyRunError",
    "StrategyRunResult",
    "execute_strategy_run",
    "legacy_request_to_strategy_run",
]
