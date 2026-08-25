from __future__ import annotations

import asyncio
from datetime import date
from typing import Annotated, Any, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import ValidationError

from bktstr.server import capabilities_payload, health_payload
from bktstr.services.backtest import (
    BacktestInput,
    CompareInput,
    NamedVariantInput,
    ParameterSweepInput,
    RegimeComparisonInput,
    RegimeLabelInput,
    compare_experiments,
    run_backtest,
    run_parameter_sweep,
    run_regime_comparison,
)
from bktstr.services.experiments import (
    ExperimentNotFoundError,
    ExperimentRecord,
    ExperimentStatus,
    ExperimentStore,
    submit,
)
from bktstr.services.regimes import RegimeInput
from bktstr.services.data import inspect_market_data

from .auth import require_api_key
from .schemas import (
    BacktestCreate,
    BacktestExperimentResponse,
    BacktestResult,
    CapabilityResponse,
    CompareCreate,
    CompareExperimentResponse,
    CompareResult,
    ErrorResponse,
    ExperimentResponse,
    HealthResponse,
    MarketDataResponse,
    NamedVariantCreate,
    ParameterSweepCreate,
    ParameterSweepExperimentResponse,
    ParameterSweepResult,
    PendingExperimentResponse,
    RegimeComparisonCreate,
    RegimeComparisonExperimentResponse,
    RegimeComparisonResult,
)


api_router = APIRouter()


@api_router.get("/health", response_model=HealthResponse, responses={500: {"model": ErrorResponse}})
def versioned_health() -> dict:
    return health_payload()


@api_router.get(
    "/capabilities",
    response_model=CapabilityResponse,
    responses={401: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def capabilities(_: Annotated[None, Depends(require_api_key)]) -> dict:
    return capabilities_payload()


@api_router.get(
    "/market-data",
    response_model=MarketDataResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_market_data(
    symbol: Annotated[str, Query(min_length=1, max_length=15)],
    start: date,
    end: date,
    timeframe: str = "1m",
    source: str = "auto",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    _: Annotated[None, Depends(require_api_key)] = None,
) -> MarketDataResponse:
    page = await inspect_market_data(
        symbol=symbol,
        start=start,
        end=end,
        timeframe=timeframe,
        source=source,
        limit=limit,
        cursor=cursor,
    )
    return MarketDataResponse.model_validate(page, from_attributes=True)


def _backtest_input(request: BacktestCreate) -> BacktestInput:
    regime = request.regime
    return BacktestInput(
        strategy_id=request.strategy.id,
        strategy_version=request.strategy.version,
        symbol=request.market.symbol,
        start=request.market.start,
        end=request.market.end,
        timeframe=request.market.timeframe,
        source=request.market.source,
        side=request.side,
        entry=request.entry,
        parameters=request.strategy.parameters,
        regime=(
            None
            if regime is None
            else RegimeInput(
                enabled=regime.enabled,
                rules=regime.rules,
                benchmark=regime.benchmark,
                sentiment_enabled=regime.sentiment_enabled,
                sentiment_sector_benchmark=regime.sentiment_sector_benchmark,
                sentiment_market_benchmark=regime.sentiment_market_benchmark,
                sentiment_data_profile=regime.sentiment_data_profile,
                sentiment_sources=tuple(regime.sentiment_sources),
            )
        ),
        execution=request.execution.value,
    )


def _execute_backtest_experiment(
    record: ExperimentRecord,
) -> tuple[dict, dict]:
    request = BacktestCreate.model_validate(record.request)
    result = BacktestResult.model_validate(
        asyncio.run(run_backtest(_backtest_input(request))), from_attributes=True
    )
    if not request.include_trades:
        result = result.model_copy(update={"trades": []})
    payload = result.model_dump(mode="json")
    return payload, payload["provenance"]


def _parameter_sweep_input(request: ParameterSweepCreate) -> ParameterSweepInput:
    return ParameterSweepInput(
        base=_backtest_input(request.base),
        grid=request.grid,
        objective=request.objective,
        execution=request.execution.value,
    )


def _compare_input(request: CompareCreate) -> CompareInput:
    return CompareInput(
        candidates=tuple(
            NamedVariantInput(candidate.name, _backtest_input(candidate.backtest))
            if isinstance(candidate, NamedVariantCreate)
            else candidate
            for candidate in request.candidates
        ),
        execution=request.execution.value,
    )


def _regime_comparison_input(
    request: RegimeComparisonCreate,
) -> RegimeComparisonInput:
    return RegimeComparisonInput(
        base=_backtest_input(request.base),
        labels=tuple(
            RegimeLabelInput(item.label, item.start, item.end, item.rule)
            for item in request.labels
        ),
        disjoint_periods=request.disjoint_periods,
        execution=request.execution.value,
    )


def _execute_parameter_sweep_experiment(
    record: ExperimentRecord, store: ExperimentStore
) -> tuple[dict, dict]:
    request = ParameterSweepCreate.model_validate(record.request)
    result = ParameterSweepResult.model_validate(
        run_parameter_sweep(
            _parameter_sweep_input(request),
            store=store,
            parent_experiment_id=record.experiment_id,
        ),
        from_attributes=True,
    )
    payload = result.model_dump(mode="json")
    return payload, payload["provenance"]


def _execute_compare_experiment(
    record: ExperimentRecord, store: ExperimentStore
) -> tuple[dict, dict]:
    request = CompareCreate.model_validate(record.request)
    result = CompareResult.model_validate(
        compare_experiments(
            _compare_input(request),
            store=store,
            parent_experiment_id=record.experiment_id,
        ),
        from_attributes=True,
    )
    payload = result.model_dump(mode="json")
    return payload, payload["provenance"]


def _execute_regime_comparison_experiment(
    record: ExperimentRecord, store: ExperimentStore
) -> tuple[dict, dict]:
    request = RegimeComparisonCreate.model_validate(record.request)
    result = RegimeComparisonResult.model_validate(
        run_regime_comparison(
            _regime_comparison_input(request),
            store=store,
            parent_experiment_id=record.experiment_id,
        ),
        from_attributes=True,
    )
    payload = result.model_dump(mode="json")
    return payload, payload["provenance"]


def experiment_operations(store: ExperimentStore | None = None) -> dict:
    """Return operation handlers shared by inline submission and the durable worker."""
    operations = {"backtest": _execute_backtest_experiment}
    if store is not None:
        operations.update(
            {
                "parameter_sweep": lambda record: _execute_parameter_sweep_experiment(
                    record, store
                ),
                "compare": lambda record: _execute_compare_experiment(record, store),
                "regime_comparison": lambda record: _execute_regime_comparison_experiment(
                    record, store
                ),
            }
        )
    return operations


def _experiment_store(request: Request) -> ExperimentStore:
    return request.app.state.experiment_store


@api_router.post(
    "/backtests",
    response_model=BacktestExperimentResponse,
    responses={
        202: {"model": BacktestExperimentResponse},
        401: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
def create_backtest(
    body: BacktestCreate,
    request: Request,
    response: Response,
    _: Annotated[None, Depends(require_api_key)],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            pattern=r"^[\x21-\x7e]+$",
        ),
    ] = None,
) -> BacktestExperimentResponse:
    canonical_request = body.model_dump(mode="json")
    record = submit(
        _experiment_store(request),
        experiment_operations(_experiment_store(request)),
        "backtest",
        canonical_request,
        execution=body.execution,
        calendar_days=(body.market.end - body.market.start).days + 1,
        idempotency_key=idempotency_key,
    )
    response.status_code = (
        202
        if record.status in {ExperimentStatus.QUEUED, ExperimentStatus.RUNNING}
        else 200
    )
    return BacktestExperimentResponse.from_record(record)


IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        pattern=r"^[\x21-\x7e]+$",
    ),
]


ResearchEnvelope = TypeVar(
    "ResearchEnvelope",
    ParameterSweepExperimentResponse,
    CompareExperimentResponse,
    RegimeComparisonExperimentResponse,
)


def _submit_research_operation(
    *,
    body: Any,
    request: Request,
    response: Response,
    operation: str,
    response_type: type[ResearchEnvelope],
    idempotency_key: str | None,
) -> ResearchEnvelope:
    store = _experiment_store(request)
    record = submit(
        store,
        experiment_operations(store),
        operation,
        body.model_dump(mode="json"),
        execution=body.execution,
        calendar_days=None,
        idempotency_key=idempotency_key,
    )
    response.status_code = (
        202
        if record.status in {ExperimentStatus.QUEUED, ExperimentStatus.RUNNING}
        else 200
    )
    return response_type.from_record(record)


@api_router.post(
    "/parameter-sweeps",
    response_model=ParameterSweepExperimentResponse,
    responses={
        202: {"model": ParameterSweepExperimentResponse},
        401: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def create_parameter_sweep(
    body: ParameterSweepCreate,
    request: Request,
    response: Response,
    _: Annotated[None, Depends(require_api_key)],
    idempotency_key: IdempotencyKey = None,
) -> ParameterSweepExperimentResponse:
    _parameter_sweep_input(body)
    return _submit_research_operation(
        body=body,
        request=request,
        response=response,
        operation="parameter_sweep",
        response_type=ParameterSweepExperimentResponse,
        idempotency_key=idempotency_key,
    )


@api_router.post(
    "/compare",
    response_model=CompareExperimentResponse,
    responses={
        202: {"model": CompareExperimentResponse},
        401: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def create_comparison(
    body: CompareCreate,
    request: Request,
    response: Response,
    _: Annotated[None, Depends(require_api_key)],
    idempotency_key: IdempotencyKey = None,
) -> CompareExperimentResponse:
    _compare_input(body)
    return _submit_research_operation(
        body=body,
        request=request,
        response=response,
        operation="compare",
        response_type=CompareExperimentResponse,
        idempotency_key=idempotency_key,
    )


@api_router.post(
    "/regime-comparison",
    response_model=RegimeComparisonExperimentResponse,
    responses={
        202: {"model": RegimeComparisonExperimentResponse},
        401: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def create_regime_comparison(
    body: RegimeComparisonCreate,
    request: Request,
    response: Response,
    _: Annotated[None, Depends(require_api_key)],
    idempotency_key: IdempotencyKey = None,
) -> RegimeComparisonExperimentResponse:
    _regime_comparison_input(body)
    return _submit_research_operation(
        body=body,
        request=request,
        response=response,
        operation="regime_comparison",
        response_type=RegimeComparisonExperimentResponse,
        idempotency_key=idempotency_key,
    )


def _load_experiment(request: Request, experiment_id: str) -> ExperimentRecord:
    return _experiment_store(request).load_experiment(experiment_id)


@api_router.get(
    "/backtests/{experiment_id}",
    response_model=BacktestExperimentResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_backtest(
    experiment_id: str,
    request: Request,
    _: Annotated[None, Depends(require_api_key)],
) -> BacktestExperimentResponse:
    record = _load_experiment(request, experiment_id)
    if record.operation != "backtest":
        raise ExperimentNotFoundError(experiment_id)
    return BacktestExperimentResponse.from_record(record)


@api_router.get(
    "/experiments/{experiment_id}",
    response_model=ExperimentResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_experiment(
    experiment_id: str,
    request: Request,
    _: Annotated[None, Depends(require_api_key)],
) -> ExperimentResponse:
    record = _load_experiment(request, experiment_id)
    response_types = {
        "backtest": BacktestExperimentResponse,
        "parameter_sweep": ParameterSweepExperimentResponse,
        "compare": CompareExperimentResponse,
        "regime_comparison": RegimeComparisonExperimentResponse,
    }
    response_type = response_types.get(record.operation)
    if response_type is not None:
        try:
            return response_type.from_record(record)
        except ValidationError:
            pass
    return PendingExperimentResponse.from_record(record)


@api_router.get(
    "/backtest",
    response_model=ErrorResponse,
    status_code=410,
    responses={
        401: {"model": ErrorResponse},
        410: {
            "model": ErrorResponse,
            "description": "The legacy endpoint was removed; use the typed replacement.",
            "headers": {
                "Link": {
                    "description": "OpenAPI documentation for the replacement endpoint.",
                    "schema": {"type": "string"},
                }
            },
        },
    },
)
def removed_legacy_backtest(
    _: Annotated[None, Depends(require_api_key)],
) -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_endpoint_removed",
            "message": "Use POST /api/v1/backtests with the typed request body.",
            "details": {"replacement": "/api/v1/backtests"},
        },
        headers={"Link": '</openapi.json>; rel="alternate"'},
    )
