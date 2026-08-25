from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Mapping

from bktstr import __version__
from bktstr.build_info import runtime_build_info
from bktstr.regime import REGIME_FIELDS
from bktstr.rules import parse_rules
from bktstr.service import BacktestRequest, execute_backtest
from bktstr.strategies import ResolvedStrategy, baseline_strategy_registry

from .data import normalize_market_request
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


__all__ = [
    "BacktestConfiguration",
    "BacktestInput",
    "BacktestMetrics",
    "BacktestResearchResult",
    "ResearchProvenance",
    "ResearchTrade",
    "project_research_result",
    "run_backtest",
    "to_legacy_request",
]
