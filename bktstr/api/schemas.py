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


class ParameterSweepCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base: BacktestCreate
    grid: dict[str, list[ParameterValue]]
    objective: Literal[
        "ev_per_trade", "profit_factor", "sharpe", "max_drawdown", "total_pnl"
    ]
    execution: ExecutionMode = ExecutionMode.AUTO


class NamedVariantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    backtest: BacktestCreate


class CompareCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[str | NamedVariantCreate] = Field(min_length=2, max_length=20)
    execution: ExecutionMode = ExecutionMode.AUTO


class RegimeLabelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    start: date
    end: date
    rule: str | None = None


class RegimeComparisonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base: BacktestCreate
    labels: list[RegimeLabelCreate] = Field(min_length=2, max_length=12)
    disjoint_periods: bool = False
    execution: ExecutionMode = ExecutionMode.AUTO


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


class SweepVariantResponse(BaseModel):
    experiment_id: str
    parameters: dict[str, ParameterValue]
    score: float | None
    metrics: BacktestMetricsResponse
    provenance: ResearchProvenanceResponse


class ParameterSweepProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_experiment_id: str | None
    objective: Literal[
        "ev_per_trade", "profit_factor", "sharpe", "max_drawdown", "total_pnl"
    ]
    grid: dict[str, list[ParameterValue]]
    child_experiment_ids: list[str]


class ParameterSweepResult(BaseModel):
    objective: Literal[
        "ev_per_trade", "profit_factor", "sharpe", "max_drawdown", "total_pnl"
    ]
    variants: list[SweepVariantResponse]
    provenance: ParameterSweepProvenanceResponse


class ComparisonCandidateResponse(BaseModel):
    name: str
    experiment_id: str
    metrics: BacktestMetricsResponse
    provenance: ResearchProvenanceResponse


class ComparisonItemResponse(BaseModel):
    reference_experiment_id: str
    candidate_experiment_id: str
    changed_inputs: list[str]


class CompareProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_experiment_id: str | None
    candidate_experiment_ids: list[str]
    comparison_reference: str


class CompareResult(BaseModel):
    candidates: list[ComparisonCandidateResponse]
    items: list[ComparisonItemResponse]
    metric_deltas: dict[str, dict[str, float | None]]
    provenance: CompareProvenanceResponse


class RegimeComparisonItemResponse(BaseModel):
    label: str
    experiment_id: str
    metrics: BacktestMetricsResponse
    trades: list[ResearchTradeResponse]
    provenance: ResearchProvenanceResponse


class RegimeLabelProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    start: date
    end: date
    rule: str | None


class RegimeComparisonProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_experiment_id: str | None
    labels: list[RegimeLabelProvenanceResponse]
    disjoint_periods: bool
    child_experiment_ids: list[str]


class RegimeComparisonResult(BaseModel):
    items: list[RegimeComparisonItemResponse]
    comparison_matrix: dict[str, dict[str, float | int | None]]
    provenance: RegimeComparisonProvenanceResponse


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


class ParameterSweepExperimentResponse(ExperimentEnvelope):
    operation: Literal["parameter_sweep"]
    request: ParameterSweepCreate
    result: ParameterSweepResult | None = None
    provenance: ParameterSweepProvenanceResponse | None = None


class CompareExperimentResponse(ExperimentEnvelope):
    operation: Literal["compare"]
    request: CompareCreate
    result: CompareResult | None = None
    provenance: CompareProvenanceResponse | None = None


class RegimeComparisonExperimentResponse(ExperimentEnvelope):
    operation: Literal["regime_comparison"]
    request: RegimeComparisonCreate
    result: RegimeComparisonResult | None = None
    provenance: RegimeComparisonProvenanceResponse | None = None


class PendingExperimentResponse(ExperimentEnvelope):
    """Stable shared envelope for stored operations awaiting their public schema."""

    operation: Literal["pending"]
    stored_operation: str

    @classmethod
    def from_record(cls, record: ExperimentRecord) -> "PendingExperimentResponse":
        payload = ExperimentEnvelope.from_record(record).model_dump()
        payload["stored_operation"] = payload["operation"]
        payload["operation"] = "pending"
        return cls.model_validate(payload)


# Keep the canonical polling contract explicitly discriminated. Pending remains
# the safe representation for unknown future operations and old malformed rows.
ExperimentResponse = Annotated[
    Union[
        BacktestExperimentResponse,
        ParameterSweepExperimentResponse,
        CompareExperimentResponse,
        RegimeComparisonExperimentResponse,
        PendingExperimentResponse,
    ],
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
