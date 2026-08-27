from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from bktstr.api.lifecycle import experiment_retry_after, experiment_status_url
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


class CapabilityModel(BaseModel):
    """Closed building block for the public discovery contract."""

    model_config = ConfigDict(extra="forbid")


class BearerAuthenticationCapabilities(CapabilityModel):
    scheme: Literal["bearer"]
    header: Literal["Authorization"]


class IntegerRangeCapabilities(CapabilityModel):
    minimum: int
    maximum: int


class ApiLimitsCapabilities(CapabilityModel):
    market_data_page_size: IntegerRangeCapabilities


class ApiCapabilities(CapabilityModel):
    openapi_url: str
    authentication: BearerAuthenticationCapabilities
    operations: list[str]
    limits: ApiLimitsCapabilities


class IdempotencyCapabilities(CapabilityModel):
    header: Literal["Idempotency-Key"]
    behavior: str


class ExecutionPolicyCapabilities(CapabilityModel):
    auto_inline: list[str]
    auto_queues: list[str]
    sync_max_calendar_days: int
    sync_refusal_code: Literal["execution_not_available"]


class ExperimentCapabilities(CapabilityModel):
    states: list[ExperimentStatus]
    execution_modes: list[ExecutionMode]
    idempotency: IdempotencyCapabilities
    execution_policy: ExecutionPolicyCapabilities


class RuleSyntaxCapabilities(CapabilityModel):
    examples: list[str]
    combine: str
    operators: list[str]


class RegimeCapabilities(CapabilityModel):
    parameter: str
    benchmark_parameter: str
    fields: list[str]
    sentiment_fields_require: str
    operators: list[str]
    lookahead_guard: str


class SentimentProfileCapabilities(CapabilityModel):
    label: str
    allowed_tiers: list[str]
    default_sources: list[str]


class TierDescriptionCapabilities(CapabilityModel):
    label: str
    description: str


class ArtifactTierCapabilities(CapabilityModel):
    tier: str
    description: str


class ProvenanceSourceCapabilities(CapabilityModel):
    id: str
    tier: str
    description: str
    point_in_time_safe: bool
    model_derived: bool
    available: bool


class DataProfilesCapabilities(CapabilityModel):
    default: str
    available_profiles: dict[str, SentimentProfileCapabilities]
    tiers: dict[str, TierDescriptionCapabilities]
    artifact_tiers: dict[str, ArtifactTierCapabilities]
    sources: dict[str, ProvenanceSourceCapabilities]


class SentimentCapabilities(CapabilityModel):
    enabled_parameter: str
    sector_benchmark_parameter: str
    market_benchmark_parameter: str
    direction_range: list[float]
    confidence_range: list[float]
    momentum_range: list[float]
    fragility_range: list[float]
    multiplier_range: list[float]
    raw_features: list[str]
    component_scores: list[str]
    outputs: list[str]
    component_weights: dict[str, float]
    multipliers_are_informational: bool
    filterable_fields: list[str]
    coverage_fields: list[str]
    optional_warmup_behavior: str
    data_profile_parameter: str
    sources_parameter: str
    data_profiles: DataProfilesCapabilities
    lookahead_guard: str


class ExecutionModelCapabilities(CapabilityModel):
    entry: str
    same_bar_stop_target: str
    slippage: str
    default_regular_hours_only: bool
    default_same_day_only: bool
    entry_window: str


class ProviderCapabilities(CapabilityModel):
    massive: str
    yahoo: str


class BuildCapabilities(CapabilityModel):
    git_commit: str | None = None
    git_branch: str | None = None
    git_repo: str | None = None
    deployment_id: str | None = None
    build_time: str | None = None


class ReleaseCapabilities(CapabilityModel):
    build: BuildCapabilities
    feature_formula_versions: dict[str, str]
    derived_cache_format_version: str


class RawCacheCapabilities(CapabilityModel):
    type: str
    persistent_when: str
    default_path: str


class DerivedCacheCapabilities(CapabilityModel):
    type: str
    namespaces: list[str]
    toggle: str
    default_enabled: bool
    override_path_variable: str
    strategy_decisions_cached: bool


class CacheCapabilities(RawCacheCapabilities):
    raw: RawCacheCapabilities
    derived: DerivedCacheCapabilities


class VariableReferenceCapabilities(CapabilityModel):
    id: str
    version: str
    tier: str


class VariableLineageCapabilities(CapabilityModel):
    plugin_id: str | None = None
    plugin_version: str | None = None
    formula_version: str | None = None


class SuggestionPolicyCapabilities(CapabilityModel):
    method: str
    rationale: str


class VariableGuiCapabilities(CapabilityModel):
    label: str
    description: str
    category: str
    preferred_chart: str
    color_hint: str | None = None
    strategy_owned: bool


class ResearchVariableDefinitionCapabilities(CapabilityModel):
    id: str
    version: str
    kind: str
    tier: str
    column: str
    value_dtype: str
    frequency: str
    units: str | None = None
    inputs: list[VariableReferenceCapabilities]
    lineage: VariableLineageCapabilities
    suggestion_policy: SuggestionPolicyCapabilities
    gui: VariableGuiCapabilities | None = None


class ResearchVariableTierCapabilities(CapabilityModel):
    immutable: bool
    examples: list[str]
    definitions: list[ResearchVariableDefinitionCapabilities]


class MissingDataCapabilities(CapabilityModel):
    behavior: str
    suggestions_applied: bool


class ResearchVariablesCapabilities(CapabilityModel):
    tiers: dict[str, ResearchVariableTierCapabilities]
    automatic_backfill: bool
    missing_data: MissingDataCapabilities


class StrategyParameterCapabilities(CapabilityModel):
    name: str
    type: str
    default: Any
    minimum: float | int | None = None
    maximum: float | int | None = None
    choices: list[Any]
    overridable: bool
    allow_none: bool
    ui_metadata: dict[str, Any]


class StrategyVariableUseCapabilities(CapabilityModel):
    id: str
    version: str
    tier: str
    role: str
    rule: str | None = None
    forceable: bool


class StrategyFilterCapabilities(StrategyVariableUseCapabilities):
    optional: bool


class StrategyCapabilities(CapabilityModel):
    id: str
    version: str
    schema_version: str
    name: str
    description: str
    instrument_roles: list[str]
    timeframe: str
    calendar: str
    timezone: str
    execution_model: str
    execution_model_version: str
    parameters: list[StrategyParameterCapabilities]
    variable_uses: list[StrategyVariableUseCapabilities]
    filters: list[StrategyFilterCapabilities]
    evidence_tier_opt_ins: list[str]


class StrategiesCapabilities(CapabilityModel):
    baseline: StrategyCapabilities


class CapabilityResponse(CapabilityModel):
    """Fully typed API and registered v0.5 capability discovery payload."""

    service: Literal["bktstr"]
    version: str
    timeframes: list[str]
    sides: list[str]
    api: ApiCapabilities
    experiments: ExperimentCapabilities
    rule_syntax: RuleSyntaxCapabilities
    regime: RegimeCapabilities
    sentiment: SentimentCapabilities
    execution_model: ExecutionModelCapabilities
    providers: ProviderCapabilities
    release: ReleaseCapabilities
    cache: CacheCapabilities
    research_variables: ResearchVariablesCapabilities
    strategies: StrategiesCapabilities


class MarketDataBarResponse(BaseModel):
    """One provider-independent normalized OHLCV bar."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataResponse(BaseModel):
    """A bounded page of safe raw market data inspection output."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    symbol: str
    start: date
    end: date
    timeframe: str
    source: str
    bars: list[MarketDataBarResponse]
    next_cursor: str | None = None


class StrategyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    parameters: dict[str, ParameterValue] = Field(default_factory=dict)


class MarketTimeframe(StrEnum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"


class AutomaticSource(StrEnum):
    AUTO = "auto"


class MarketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    start: date
    end: date
    timeframe: MarketTimeframe = Field(
        default=MarketTimeframe.ONE_MINUTE,
        description=(
            "Globally valid market-data timeframe. The selected strategy may "
            "narrow this set; the baseline strategy requires 1m."
        ),
    )
    source: AutomaticSource = AutomaticSource.AUTO


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
    available_start: date | None
    available_end: date | None
    observations: int
    bars: int


class CacheUsageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit_days: int
    miss_days: int
    fetched_ranges: int


class MarketDataProvenanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    requested_source: str
    version: str | int | None
    snapshot_id: str
    coverage: MarketDataCoverageResponse
    cache: CacheUsageResponse


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
    governed_dependencies: list[dict[str, Any]] = Field(default_factory=list)
    attachments: dict[str, dict[str, Any]] = Field(default_factory=dict)


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
    status_url: str = Field(
        description="Canonical experiment status URL. GET this URL to retrieve the current experiment status."
    )
    retry_after_seconds: int | None = Field(
        description=(
            "Seconds to wait before GETting status_url again while the experiment is "
            "nonterminal; null after it completes or fails."
        )
    )
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
            status_url=experiment_status_url(record),
            retry_after_seconds=experiment_retry_after(record),
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
