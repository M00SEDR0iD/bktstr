from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import date, datetime
from enum import Enum
from itertools import product
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from bktstr import __version__
from bktstr.build_info import runtime_build_info
from bktstr.regime import REGIME_FIELDS
from bktstr.rules import parse_rules
from bktstr.service import BacktestRequest, execute_backtest
from bktstr.strategies import ResolvedStrategy, baseline_strategy_registry

from .data import normalize_market_request
from .experiments import ExperimentStatus, ExperimentStore
from .regimes import RegimeInput, normalize_regime_request


ParameterValue = float | int | str | bool | None
_PROTECTED_PARAMETERS = frozenset(
    {
        "execution_model",
        "execution_model_id",
        "execution_model_version",
        "schema_version",
        "strategy_id",
        "strategy_version",
    }
)
_REGIME_PARAMETERS = frozenset(
    {"regime_rules", "sentiment", "sentiment_data_profile", "sentiment_sources"}
)
_DIRECT_PARAMETERS = frozenset({"side", "entry_rules"})


def _immutable_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class BacktestInput:
    strategy_id: str
    strategy_version: str
    symbol: str
    start: date
    end: date
    timeframe: str
    side: str
    entry: str
    parameters: Mapping[str, ParameterValue] = field(default_factory=dict)
    regime: RegimeInput | None = None
    execution: str = "auto"
    source: str = "auto"

    def __post_init__(self) -> None:
        market = normalize_market_request(
            symbol=self.symbol,
            start=self.start,
            end=self.end,
            timeframe=self.timeframe,
            source=self.source,
        )
        if self.execution not in {"auto", "sync", "async"}:
            raise ValueError("execution must be auto, sync, or async")
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        protected = sorted(set(self.parameters) & _PROTECTED_PARAMETERS)
        if protected:
            raise ValueError(f"{protected[0]} is not overridable")
        ambiguous = sorted(set(self.parameters) & (_DIRECT_PARAMETERS | _REGIME_PARAMETERS))
        if ambiguous:
            raise ValueError(
                f"{ambiguous[0]} must use its dedicated typed request field"
            )

        definition = baseline_strategy_registry().require(
            self.strategy_id, self.strategy_version
        )
        default_rules = definition.parameter_definitions["regime_rules"].default
        regime = normalize_regime_request(self.regime, default_rules=default_rules)
        overrides = dict(self.parameters)
        overrides.update(
            {
                "side": self.side,
                "entry_rules": self.entry,
                "regime_rules": regime.rules if regime and regime.enabled else None,
                "sentiment": bool(regime and regime.enabled and regime.sentiment_enabled),
                "sentiment_data_profile": (
                    regime.sentiment_data_profile if regime else "clean"
                ),
                "sentiment_sources": regime.sentiment_sources if regime else ("price",),
            }
        )
        definition.resolve(overrides)
        object.__setattr__(self, "symbol", market.symbol)
        object.__setattr__(self, "start", market.start)
        object.__setattr__(self, "end", market.end)
        object.__setattr__(self, "source", market.source)
        object.__setattr__(self, "regime", regime)
        object.__setattr__(self, "parameters", _immutable_mapping(self.parameters))


@dataclass(frozen=True)
class BacktestMetrics:
    total_pnl: float | None
    total_return: float | None
    ev_per_trade: float | None
    win_rate: float | None
    profit_factor: float | None
    max_drawdown: float | None
    sharpe: float | None
    trade_count: int


@dataclass(frozen=True)
class ResearchTrade:
    entry_timestamp: datetime | None
    exit_timestamp: datetime | None
    entry_price: float | None
    exit_price: float | None
    holding_time_minutes: int | None
    realized_pnl: float | None
    return_pct: float | None
    mfe: float | None
    mae: float | None
    side: str | None
    exit_reason: str | None
    signal_values_at_entry: Mapping[str, Any]
    regime_variables: Mapping[str, Any]


@dataclass(frozen=True)
class BacktestConfiguration:
    strategy: Mapping[str, Any]
    market: Mapping[str, Any]
    regime: Mapping[str, Any]
    execution: Mapping[str, Any]


@dataclass(frozen=True)
class ResearchProvenance:
    strategy: Mapping[str, Any]
    market_data: Mapping[str, Any]
    execution_model: Mapping[str, Any]
    software: Mapping[str, Any]


@dataclass(frozen=True)
class BacktestResearchResult:
    metrics: BacktestMetrics
    trades: tuple[ResearchTrade, ...]
    configuration: BacktestConfiguration
    provenance: ResearchProvenance


def _resolved_strategy(value: BacktestInput) -> ResolvedStrategy:
    definition = baseline_strategy_registry().require(
        value.strategy_id, value.strategy_version
    )
    overrides = dict(value.parameters)
    overrides.update(
        {
            "side": value.side,
            "entry_rules": value.entry,
            "regime_rules": (
                value.regime.rules if value.regime and value.regime.enabled else None
            ),
            "sentiment": bool(
                value.regime and value.regime.enabled and value.regime.sentiment_enabled
            ),
            "sentiment_data_profile": (
                value.regime.sentiment_data_profile if value.regime else "clean"
            ),
            "sentiment_sources": (
                value.regime.sentiment_sources if value.regime else ("price",)
            ),
        }
    )
    return definition.resolve(overrides)


def to_legacy_request(value: BacktestInput) -> BacktestRequest:
    if not isinstance(value, BacktestInput):
        raise TypeError("input must be a BacktestInput")
    resolved = _resolved_strategy(value)
    regime = value.regime if value.regime and value.regime.enabled else None
    return BacktestRequest.from_values(
        symbol=value.symbol,
        start=value.start.isoformat(),
        end=value.end.isoformat(),
        timeframe=value.timeframe,
        side=resolved.values["side"],
        entry=resolved.values["entry_rules"],
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
        regime=resolved.values["regime_rules"],
        benchmark=regime.benchmark if regime else None,
        sentiment=resolved.values["sentiment"],
        sentiment_sector_benchmark=(
            regime.sentiment_sector_benchmark if regime else None
        ),
        sentiment_market_benchmark=(
            regime.sentiment_market_benchmark if regime else None
        ),
        sentiment_data_profile=resolved.values["sentiment_data_profile"],
        sentiment_sources=resolved.values["sentiment_sources"],
    )


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _profit_factor(trades: tuple[Mapping[str, Any], ...]) -> float | None:
    pnls = [_number(item.get("pnl_dollars")) for item in trades]
    values = [item for item in pnls if item is not None]
    gross_loss = abs(sum(item for item in values if item < 0))
    if gross_loss == 0:
        return None
    return sum(item for item in values if item > 0) / gross_loss


def _sharpe(trades: tuple[Mapping[str, Any], ...]) -> float | None:
    returns = [_number(item.get("return_pct")) for item in trades]
    values = [item for item in returns if item is not None]
    if len(values) < 2:
        return None
    deviation = statistics.stdev(values)
    if deviation == 0:
        return None
    return statistics.mean(values) / deviation * math.sqrt(len(values))


def _entry_variable_names(entry_rules: str) -> frozenset[str]:
    names: set[str] = set()
    for rule in parse_rules(entry_rules):
        names.add(rule.left)
        if isinstance(rule.right, str):
            names.add(rule.right)
    return frozenset(names)


def _project_trade(item: Mapping[str, Any], *, entry_rules: str) -> ResearchTrade:
    signal_names = _entry_variable_names(entry_rules)
    signal_values = {
        key: item[key]
        for key in sorted(signal_names)
        if key in item and _number(item[key]) is not None
    }
    regime_values = {
        key: item[key]
        for key in sorted(REGIME_FIELDS)
        if key in item and _number(item[key]) is not None
    }
    hold = item.get("hold_minutes")
    return ResearchTrade(
        entry_timestamp=_timestamp(item.get("entry_time")),
        exit_timestamp=_timestamp(item.get("exit_time")),
        entry_price=_number(item.get("entry_price")),
        exit_price=_number(item.get("exit_price")),
        holding_time_minutes=(
            int(hold) if isinstance(hold, int) and not isinstance(hold, bool) else None
        ),
        realized_pnl=_number(item.get("pnl_dollars")),
        return_pct=_number(item.get("return_pct")),
        mfe=_number(item.get("mfe_pct")),
        mae=_number(item.get("mae_pct")),
        side=item.get("side") if isinstance(item.get("side"), str) else None,
        exit_reason=(
            item.get("exit_reason")
            if isinstance(item.get("exit_reason"), str)
            else None
        ),
        signal_values_at_entry=_immutable_mapping(signal_values),
        regime_variables=_immutable_mapping(regime_values),
    )


def _regime_configuration(value: RegimeInput | None) -> Mapping[str, Any]:
    if value is None or not value.enabled:
        return _immutable_mapping({"enabled": False})
    return _immutable_mapping(
        {
            "enabled": True,
            "rules": value.rules,
            "benchmark": value.benchmark,
            "sentiment_enabled": value.sentiment_enabled,
            "sentiment_sector_benchmark": value.sentiment_sector_benchmark,
            "sentiment_market_benchmark": value.sentiment_market_benchmark,
            "sentiment_data_profile": value.sentiment_data_profile,
            "sentiment_sources": value.sentiment_sources,
        }
    )


def project_research_result(
    value: BacktestInput, legacy_result: Mapping[str, Any]
) -> BacktestResearchResult:
    if not isinstance(value, BacktestInput):
        raise TypeError("input must be a BacktestInput")
    if not isinstance(legacy_result, Mapping):
        raise TypeError("legacy_result must be a mapping")
    resolved = _resolved_strategy(value)
    request = to_legacy_request(value)
    summary = legacy_result.get("summary", {})
    data = legacy_result.get("data", {})
    raw_trades = tuple(legacy_result.get("trades", ()))
    if not isinstance(summary, Mapping) or not isinstance(data, Mapping):
        raise ValueError("legacy result summary and data must be mappings")
    if not all(isinstance(item, Mapping) for item in raw_trades):
        raise ValueError("legacy result trades must be mappings")

    trade_count = summary.get("trades")
    if not isinstance(trade_count, int) or isinstance(trade_count, bool):
        trade_count = len(raw_trades)
    total_pnl = _number(summary.get("total_pnl_dollars"))
    total_return = (
        total_pnl / request.starting_capital * 100.0
        if total_pnl is not None and request.starting_capital != 0
        else None
    )
    trades = tuple(
        _project_trade(item, entry_rules=request.entry) for item in raw_trades
    )
    metrics = BacktestMetrics(
        total_pnl=total_pnl,
        total_return=total_return,
        ev_per_trade=_number(summary.get("expected_pnl_per_trade")),
        win_rate=_number(summary.get("win_rate_pct")),
        profit_factor=_profit_factor(raw_trades),
        max_drawdown=_number(summary.get("max_drawdown_pct")),
        sharpe=_sharpe(raw_trades),
        trade_count=trade_count,
    )
    strategy_configuration = _immutable_mapping(dict(resolved.values))
    market_configuration = _immutable_mapping(
        {
            "symbol": value.symbol,
            "start": value.start.isoformat(),
            "end": value.end.isoformat(),
            "timeframe": value.timeframe,
            "source": value.source,
        }
    )
    execution_configuration = _immutable_mapping(
        {
            "mode": value.execution,
            "model_id": resolved.execution_model_id,
            "model_version": resolved.execution_model_version,
            "slippage_bps": request.slippage_bps,
            "position_size": request.position_size,
            "starting_capital": request.starting_capital,
        }
    )
    configuration = BacktestConfiguration(
        strategy=_immutable_mapping(
            {
                "id": resolved.strategy_id,
                "version": resolved.strategy_version,
                "schema_version": resolved.schema_version,
                "parameters": strategy_configuration,
            }
        ),
        market=market_configuration,
        regime=_regime_configuration(value.regime),
        execution=execution_configuration,
    )
    provider = data.get("provider") if isinstance(data.get("provider"), str) else None
    provenance = ResearchProvenance(
        strategy=configuration.strategy,
        market_data=_immutable_mapping(
            {
                "source": provider,
                "requested_source": value.source,
                "version": data.get("version") or data.get("data_version"),
                "coverage": {
                    "requested_start": value.start.isoformat(),
                    "requested_end": value.end.isoformat(),
                    "bars": data.get("bars"),
                },
                "cache": data.get("cache"),
            }
        ),
        execution_model=_immutable_mapping(
            {
                "id": resolved.execution_model_id,
                "version": resolved.execution_model_version,
                "slippage_bps": request.slippage_bps,
            }
        ),
        software=_immutable_mapping(
            {"bktstr_version": __version__, **runtime_build_info()}
        ),
    )
    return BacktestResearchResult(
        metrics=metrics,
        trades=trades,
        configuration=configuration,
        provenance=provenance,
    )


async def run_backtest(value: BacktestInput) -> BacktestResearchResult:
    request = to_legacy_request(value)
    legacy_result = await execute_backtest(request)
    return project_research_result(value, legacy_result)


SWEEP_OBJECTIVES = frozenset(
    {"ev_per_trade", "profit_factor", "sharpe", "max_drawdown", "total_pnl"}
)


def _canonical_scalar(value: ParameterValue) -> str:
    if not isinstance(value, str | int | float | bool) and value is not None:
        raise TypeError("sweep candidates must be JSON scalar values")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("sweep candidates must be finite")
    return json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":"))


def _sweep_limit() -> int:
    configured = os.getenv("BKTSTR_MAX_SWEEP_VARIANTS")
    limit = int(configured) if configured is not None else 500
    if limit < 1:
        raise ValueError("BKTSTR_MAX_SWEEP_VARIANTS must be at least 1")
    return limit


@dataclass(frozen=True)
class ParameterSweepInput:
    base: BacktestInput
    grid: Mapping[str, Sequence[ParameterValue]]
    objective: str
    execution: str = "auto"

    def __post_init__(self) -> None:
        if not isinstance(self.base, BacktestInput):
            raise TypeError("base must be a BacktestInput")
        if self.execution not in {"auto", "sync", "async"}:
            raise ValueError("execution must be auto, sync, or async")
        if self.objective not in SWEEP_OBJECTIVES:
            raise ValueError(
                f"objective must be one of {tuple(sorted(SWEEP_OBJECTIVES))!r}"
            )
        if not isinstance(self.grid, Mapping) or not self.grid:
            raise ValueError("parameter sweep grid cannot be empty")

        definitions = baseline_strategy_registry().require(
            self.base.strategy_id, self.base.strategy_version
        ).parameter_definitions
        normalized: dict[str, tuple[ParameterValue, ...]] = {}
        variant_count = 1
        for name in sorted(self.grid):
            definition = definitions.get(name)
            if (
                definition is None
                or not definition.overridable
                or name in _PROTECTED_PARAMETERS | _DIRECT_PARAMETERS | _REGIME_PARAMETERS
            ):
                raise ValueError(f"{name} is not a registered overridable sweep parameter")
            candidates = tuple(self.grid[name])
            if not candidates:
                raise ValueError(f"grid candidates for {name} cannot be empty")
            validated: list[tuple[str, ParameterValue]] = []
            seen: set[str] = set()
            for candidate in candidates:
                canonical = _canonical_scalar(candidate)
                if canonical in seen:
                    raise ValueError(f"{name} has a duplicate canonical candidate")
                seen.add(canonical)
                validated.append((canonical, definition.validate(candidate)))
            normalized[name] = tuple(
                candidate for _, candidate in sorted(validated, key=lambda item: item[0])
            )
            variant_count *= len(candidates)

        limit = _sweep_limit()
        if variant_count > limit:
            raise ValueError(f"parameter sweep may contain at most {limit} variants")
        object.__setattr__(self, "grid", _immutable_mapping(normalized))


@dataclass(frozen=True)
class SweepVariantResult:
    experiment_id: str
    parameters: Mapping[str, ParameterValue]
    score: float | None
    metrics: BacktestMetrics


@dataclass(frozen=True)
class ParameterSweepResult:
    objective: str
    variants: tuple[SweepVariantResult, ...]
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class NamedVariantInput:
    name: str
    backtest: BacktestInput

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("variant name cannot be empty")
        if not isinstance(self.backtest, BacktestInput):
            raise TypeError("variant backtest must be a BacktestInput")
        object.__setattr__(self, "name", self.name.strip())


ComparisonCandidateInput = str | NamedVariantInput


@dataclass(frozen=True)
class CompareInput:
    candidates: Sequence[ComparisonCandidateInput]
    execution: str = "auto"

    def __post_init__(self) -> None:
        candidates = tuple(self.candidates)
        if not 2 <= len(candidates) <= 20:
            raise ValueError("compare requires two through twenty candidates")
        if self.execution not in {"auto", "sync", "async"}:
            raise ValueError("execution must be auto, sync, or async")
        identities: list[str] = []
        for candidate in candidates:
            if isinstance(candidate, str):
                if not candidate.startswith("exp_"):
                    raise ValueError("comparison experiment IDs must start with exp_")
                identities.append(candidate)
            elif isinstance(candidate, NamedVariantInput):
                identities.append(f"name:{candidate.name}")
            else:
                raise TypeError(
                    "comparison candidates must be experiment IDs or named variants"
                )
        if len(set(identities)) != len(identities):
            raise ValueError("comparison candidates must be unique")
        object.__setattr__(self, "candidates", candidates)


@dataclass(frozen=True)
class ComparisonCandidate:
    name: str
    experiment_id: str
    metrics: BacktestMetrics
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class ComparisonItem:
    reference_experiment_id: str
    candidate_experiment_id: str
    changed_inputs: tuple[str, ...]


@dataclass(frozen=True)
class CompareResult:
    candidates: tuple[ComparisonCandidate, ...]
    items: tuple[ComparisonItem, ...]
    metric_deltas: Mapping[str, Mapping[str, float | None]]
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class RegimeLabelInput:
    label: str
    start: date
    end: date
    rule: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("regime comparison label cannot be empty")
        if not isinstance(self.start, date) or not isinstance(self.end, date):
            raise TypeError("regime label dates must be date values")
        if self.start > self.end:
            raise ValueError("regime label start cannot be after end")
        if self.rule is not None and (
            not isinstance(self.rule, str) or not self.rule.strip()
        ):
            raise ValueError("regime label rule must be a non-empty string or None")
        object.__setattr__(self, "label", self.label.strip())
        object.__setattr__(self, "rule", self.rule.strip() if self.rule else None)


@dataclass(frozen=True)
class RegimeComparisonInput:
    base: BacktestInput
    labels: Sequence[RegimeLabelInput]
    disjoint_periods: bool = False
    execution: str = "auto"

    def __post_init__(self) -> None:
        if not isinstance(self.base, BacktestInput):
            raise TypeError("base must be a BacktestInput")
        labels = tuple(self.labels)
        if not 2 <= len(labels) <= 12:
            raise ValueError("regime comparison requires two through twelve labels")
        if not all(isinstance(item, RegimeLabelInput) for item in labels):
            raise TypeError("labels must contain RegimeLabelInput values")
        if len({item.label for item in labels}) != len(labels):
            raise ValueError("regime comparison labels must be unique")
        if type(self.disjoint_periods) is not bool:
            raise TypeError("disjoint_periods must be bool")
        if self.execution not in {"auto", "sync", "async"}:
            raise ValueError("execution must be auto, sync, or async")
        if self.disjoint_periods:
            by_start = sorted(labels, key=lambda item: (item.start, item.end, item.label))
            if any(
                current.start <= previous.end
                for previous, current in zip(by_start, by_start[1:])
            ):
                raise ValueError("regime comparison periods cannot overlap")
        for item in labels:
            if item.rule is not None:
                base_regime = self.base.regime or RegimeInput(enabled=True)
                normalize_regime_request(replace(base_regime, enabled=True, rules=item.rule))
        object.__setattr__(self, "labels", labels)


@dataclass(frozen=True)
class RegimeComparisonItem:
    label: str
    experiment_id: str
    metrics: BacktestMetrics
    trades: tuple[ResearchTrade, ...]
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class RegimeComparisonResult:
    items: tuple[RegimeComparisonItem, ...]
    comparison_matrix: Mapping[str, Mapping[str, float | int | None]]
    provenance: Mapping[str, Any]


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def backtest_input_mapping(value: BacktestInput) -> Mapping[str, Any]:
    regime = value.regime
    return {
        "strategy": {
            "id": value.strategy_id,
            "version": value.strategy_version,
            "parameters": dict(value.parameters),
        },
        "market": {
            "symbol": value.symbol,
            "start": value.start.isoformat(),
            "end": value.end.isoformat(),
            "timeframe": value.timeframe,
            "source": value.source,
        },
        "side": value.side,
        "entry": value.entry,
        "regime": (
            None
            if regime is None
            else {
                "enabled": regime.enabled,
                "rules": regime.rules,
                "benchmark": regime.benchmark,
                "sentiment_enabled": regime.sentiment_enabled,
                "sentiment_sector_benchmark": regime.sentiment_sector_benchmark,
                "sentiment_market_benchmark": regime.sentiment_market_benchmark,
                "sentiment_data_profile": regime.sentiment_data_profile,
                "sentiment_sources": list(regime.sentiment_sources),
            }
        ),
        "execution": value.execution,
        "include_trades": True,
    }


def _execute_child_backtest(
    value: BacktestInput,
    *,
    store: ExperimentStore,
    parent_experiment_id: str | None,
) -> tuple[str, BacktestResearchResult]:
    child_input = replace(value, execution="sync")
    record, created = store.create_and_claim_experiment(
        "backtest",
        backtest_input_mapping(child_input),
        "sync",
        None,
        parent_experiment_id,
    )
    if not created:
        raise RuntimeError("child backtests do not reuse idempotency records")
    try:
        result = asyncio.run(run_backtest(child_input))
        payload = _json_value(result)
        store.complete(record.experiment_id, payload, payload["provenance"])
    except Exception:
        store.fail(
            record.experiment_id,
            {
                "code": "child_backtest_failed",
                "message": "The linked child backtest failed.",
                "details": {},
            },
        )
        raise
    return record.experiment_id, result


def run_parameter_sweep(
    value: ParameterSweepInput,
    *,
    store: ExperimentStore,
    parent_experiment_id: str | None = None,
) -> ParameterSweepResult:
    if not isinstance(value, ParameterSweepInput):
        raise TypeError("input must be a ParameterSweepInput")
    names = tuple(value.grid)
    variants: list[SweepVariantResult] = []
    for candidates in product(*(value.grid[name] for name in names)):
        parameters = dict(value.base.parameters)
        parameters.update(zip(names, candidates))
        child_id, result = _execute_child_backtest(
            replace(value.base, parameters=parameters),
            store=store,
            parent_experiment_id=parent_experiment_id,
        )
        variants.append(
            SweepVariantResult(
                experiment_id=child_id,
                parameters=_immutable_mapping(dict(zip(names, candidates))),
                score=getattr(result.metrics, value.objective),
                metrics=result.metrics,
            )
        )
    provenance = _immutable_mapping(
        {
            "parent_experiment_id": parent_experiment_id,
            "objective": value.objective,
            "grid": {name: list(value.grid[name]) for name in names},
            "child_experiment_ids": [item.experiment_id for item in variants],
        }
    )
    return ParameterSweepResult(value.objective, tuple(variants), provenance)


def _metrics_from_record_result(result: Mapping[str, Any]) -> BacktestMetrics:
    metrics = result.get("metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError("completed backtest result is missing typed metrics")
    return BacktestMetrics(
        total_pnl=_number(metrics.get("total_pnl")),
        total_return=_number(metrics.get("total_return")),
        ev_per_trade=_number(metrics.get("ev_per_trade")),
        win_rate=_number(metrics.get("win_rate")),
        profit_factor=_number(metrics.get("profit_factor")),
        max_drawdown=_number(metrics.get("max_drawdown")),
        sharpe=_number(metrics.get("sharpe")),
        trade_count=(
            metrics["trade_count"]
            if isinstance(metrics.get("trade_count"), int)
            and not isinstance(metrics.get("trade_count"), bool)
            else 0
        ),
    )


def _changed_paths(left: Any, right: Any, prefix: str = "") -> tuple[str, ...]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        paths: list[str] = []
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in left or key not in right:
                paths.append(path)
            else:
                paths.extend(_changed_paths(left[key], right[key], path))
        return tuple(paths)
    if isinstance(left, (tuple, list)) and isinstance(right, (tuple, list)):
        paths = []
        for index in range(max(len(left), len(right))):
            path = f"{prefix}[{index}]"
            if index >= len(left) or index >= len(right):
                paths.append(path)
            else:
                paths.extend(_changed_paths(left[index], right[index], path))
        return tuple(paths)
    return () if left == right else (prefix,)


def compare_experiments(
    value: CompareInput | Sequence[ComparisonCandidateInput],
    *,
    store: ExperimentStore,
    parent_experiment_id: str | None = None,
) -> CompareResult:
    request = value if isinstance(value, CompareInput) else CompareInput(value)
    resolved: list[tuple[str, Any]] = []
    for candidate in request.candidates:
        if isinstance(candidate, NamedVariantInput):
            child_id, _ = _execute_child_backtest(
                candidate.backtest,
                store=store,
                parent_experiment_id=parent_experiment_id,
            )
            resolved.append((candidate.name, store.load_experiment(child_id)))
        else:
            resolved.append((candidate, store.load_experiment(candidate)))

    candidates: list[ComparisonCandidate] = []
    for name, record in resolved:
        if (
            record.operation != "backtest"
            or record.status is not ExperimentStatus.COMPLETED
            or record.result is None
        ):
            raise ValueError("compare requires completed backtest experiments")
        provenance = record.provenance or record.result.get("provenance") or {}
        candidates.append(
            ComparisonCandidate(
                name=name,
                experiment_id=record.experiment_id,
                metrics=_metrics_from_record_result(record.result),
                provenance=_immutable_mapping(provenance),
            )
        )

    reference_record = resolved[0][1]
    items = tuple(
        ComparisonItem(
            reference_experiment_id=reference_record.experiment_id,
            candidate_experiment_id=record.experiment_id,
            changed_inputs=_changed_paths(reference_record.request, record.request),
        )
        for _, record in resolved[1:]
    )
    metric_names = tuple(field.name for field in fields(BacktestMetrics))
    metric_deltas: dict[str, Mapping[str, float | None]] = {}
    reference_metrics = candidates[0].metrics
    for metric_name in metric_names:
        reference_value = getattr(reference_metrics, metric_name)
        deltas: dict[str, float | None] = {}
        for candidate in candidates[1:]:
            candidate_value = getattr(candidate.metrics, metric_name)
            deltas[candidate.experiment_id] = (
                float(candidate_value) - float(reference_value)
                if candidate_value is not None and reference_value is not None
                else None
            )
        metric_deltas[metric_name] = _immutable_mapping(deltas)
    provenance = _immutable_mapping(
        {
            "parent_experiment_id": parent_experiment_id,
            "candidate_experiment_ids": [item.experiment_id for item in candidates],
            "comparison_reference": candidates[0].experiment_id,
        }
    )
    return CompareResult(
        tuple(candidates), tuple(items), _immutable_mapping(metric_deltas), provenance
    )


def run_regime_comparison(
    value: RegimeComparisonInput,
    *,
    store: ExperimentStore,
    parent_experiment_id: str | None = None,
) -> RegimeComparisonResult:
    if not isinstance(value, RegimeComparisonInput):
        raise TypeError("input must be a RegimeComparisonInput")
    items: list[RegimeComparisonItem] = []
    for label in value.labels:
        regime = value.base.regime
        if label.rule is not None:
            regime = replace(regime or RegimeInput(enabled=True), enabled=True, rules=label.rule)
        child_id, result = _execute_child_backtest(
            replace(
                value.base,
                start=label.start,
                end=label.end,
                regime=regime,
            ),
            store=store,
            parent_experiment_id=parent_experiment_id,
        )
        items.append(
            RegimeComparisonItem(
                label=label.label,
                experiment_id=child_id,
                metrics=result.metrics,
                trades=result.trades,
                provenance=_immutable_mapping(_json_value(result.provenance)),
            )
        )
    comparison_matrix = {
        metric.name: _immutable_mapping(
            {item.label: getattr(item.metrics, metric.name) for item in items}
        )
        for metric in fields(BacktestMetrics)
    }
    label_provenance = [
        {
            "label": item.label,
            "start": item.start.isoformat(),
            "end": item.end.isoformat(),
            "rule": item.rule,
        }
        for item in value.labels
    ]
    provenance = _immutable_mapping(
        {
            "parent_experiment_id": parent_experiment_id,
            "labels": label_provenance,
            "disjoint_periods": value.disjoint_periods,
            "child_experiment_ids": [item.experiment_id for item in items],
        }
    )
    return RegimeComparisonResult(
        tuple(items), _immutable_mapping(comparison_matrix), provenance
    )


__all__ = [
    "BacktestConfiguration",
    "BacktestInput",
    "BacktestMetrics",
    "BacktestResearchResult",
    "CompareInput",
    "CompareResult",
    "ComparisonCandidate",
    "ComparisonItem",
    "NamedVariantInput",
    "ParameterSweepInput",
    "ParameterSweepResult",
    "RegimeComparisonInput",
    "RegimeComparisonItem",
    "RegimeComparisonResult",
    "RegimeLabelInput",
    "ResearchProvenance",
    "ResearchTrade",
    "SweepVariantResult",
    "backtest_input_mapping",
    "compare_experiments",
    "project_research_result",
    "run_backtest",
    "run_parameter_sweep",
    "run_regime_comparison",
    "to_legacy_request",
]
