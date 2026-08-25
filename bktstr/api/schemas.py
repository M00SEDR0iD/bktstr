from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from bktstr.services.experiments import ExecutionMode, ExperimentRecord, ExperimentStatus


ParameterValue = float | int | str | bool | None
StrategyParameterValue = ParameterValue | list[str]


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    error: ApiError


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["bktstr"]
    version: str
    git_commit: str | None = None
    git_branch: str | None = None
    git_repo: str | None = None
    deployment_id: str | None = None
    build_time: str | None = None


class CapabilityResponse(BaseModel):
    """Registered public capabilities; unmodeled registry sections are preserved."""

    model_config = ConfigDict(extra="allow")

    service: Literal["bktstr"]
    version: str
    timeframes: list[str]
    sides: list[str]


class StrategyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    parameters: dict[str, ParameterValue] = Field(default_factory=dict)


class MarketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    start: date
    end: date
    timeframe: str = "1m"
    source: str = "auto"


class RegimeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    rules: str | None = None
    benchmark: str | None = None
    sentiment_enabled: bool = False
    sentiment_sector_benchmark: str | None = None
    sentiment_market_benchmark: str | None = None
    sentiment_data_profile: str = "clean"
    sentiment_sources: list[str] = Field(default_factory=lambda: ["price"])


class BacktestCreate(BaseModel):
    """One registered strategy evaluated over one normalized market range."""

    model_config = ConfigDict(extra="forbid")

    strategy: StrategyCreate
    market: MarketCreate
    side: str = "short"
    entry: str = "close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.10"
    regime: RegimeCreate | None = None
    execution: ExecutionMode = ExecutionMode.AUTO
    include_trades: bool = True


class BacktestMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_pnl: float | None
    total_return: float | None
    ev_per_trade: float | None
    win_rate: float | None
    profit_factor: float | None
    max_drawdown: float | None
    sharpe: float | None
    trade_count: int


class ResearchTradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    signal_values_at_entry: dict[str, Any]
    regime_variables: dict[str, Any]


class StrategyConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    schema_version: str
    parameters: dict[str, StrategyParameterValue]


class MarketConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    start: date
    end: date
    timeframe: str
    source: str


class RegimeConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    rules: str | None = None
    benchmark: str | None = None
    sentiment_enabled: bool = False
    sentiment_sector_benchmark: str | None = None
    sentiment_market_benchmark: str | None = None
    sentiment_data_profile: str | None = None
    sentiment_sources: list[str] | None = None


class ExecutionConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ExecutionMode
    model_id: str
    model_version: str
    slippage_bps: float
    position_size: float
    starting_capital: float


class BacktestConfigurationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy: StrategyConfigurationResponse
    market: MarketConfigurationResponse
    regime: RegimeConfigurationResponse
    execution: ExecutionConfigurationResponse


class MarketDataCoverageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_start: date
    requested_end: date
    bars: int | None


class CacheUsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit_days: int
    miss_days: int
    fetched_ranges: int


class MarketDataProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None
    requested_source: str
    version: str | int | None
    coverage: MarketDataCoverageResponse
    cache: CacheUsageResponse | None = None


class ExecutionModelProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    slippage_bps: float


class SoftwareProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bktstr_version: str
    git_commit: str | None = None
    git_branch: str | None = None
    git_repo: str | None = None
    deployment_id: str | None = None
    build_time: str | None = None


class ResearchProvenanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy: StrategyConfigurationResponse
    market_data: MarketDataProvenanceResponse
    execution_model: ExecutionModelProvenanceResponse
    software: SoftwareProvenanceResponse


class BacktestResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metrics: BacktestMetricsResponse
    trades: list[ResearchTradeResponse]
    configuration: BacktestConfigurationResponse
    provenance: ResearchProvenanceResponse


class ExperimentError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ExperimentEnvelope(BaseModel):
    """The shared typed lifecycle envelope around an operation-specific result."""

    experiment_id: str
    operation: str
    status: ExperimentStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution: ExecutionMode
    request: dict[str, Any]
    result: dict[str, Any] | None = None
    error: ExperimentError | None = None
    provenance: dict[str, Any] | None = None

    @classmethod
    def from_record(cls, record: ExperimentRecord) -> "ExperimentEnvelope":
        return cls(
            experiment_id=record.experiment_id,
            operation=record.operation,
            status=record.status,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            execution=record.execution,
            request=_thaw(record.request),
            result=_thaw(record.result),
            error=ExperimentError.model_validate(_thaw(record.error)) if record.error else None,
            provenance=_thaw(record.provenance),
        )


class BacktestExperimentResponse(ExperimentEnvelope):
    operation: Literal["backtest"]
    request: BacktestCreate
    result: BacktestResult | None = None
    provenance: ResearchProvenanceResponse | None = None


# Keep the canonical polling contract explicitly discriminated even while v0.6
# exposes only backtests. Task 6 extends this Union with its typed operations.
ExperimentResponse = Annotated[
    Union[BacktestExperimentResponse],
    Field(discriminator="operation"),
]


def _thaw(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: _thaw(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
