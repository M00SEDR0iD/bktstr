from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from bktstr.server import CAPABILITIES, health_payload
from bktstr.services.backtest import BacktestInput, run_backtest
from bktstr.services.experiments import (
    ExperimentNotFoundError,
    ExperimentRecord,
    ExperimentStatus,
    ExperimentStore,
    submit,
)
from bktstr.services.regimes import RegimeInput

from .auth import require_api_key
from .schemas import (
    BacktestCreate,
    BacktestExperimentResponse,
    BacktestResult,
    CapabilityResponse,
    ErrorResponse,
    ExperimentEnvelope,
    HealthResponse,
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
    return CAPABILITIES


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


def experiment_operations() -> dict:
    """Return operation handlers shared by inline submission and the durable worker."""
    return {"backtest": _execute_backtest_experiment}


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
        experiment_operations(),
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
    response_model=ExperimentEnvelope,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_experiment(
    experiment_id: str,
    request: Request,
    _: Annotated[None, Depends(require_api_key)],
) -> ExperimentEnvelope:
    return ExperimentEnvelope.from_record(_load_experiment(request, experiment_id))


@api_router.get(
    "/backtest",
    response_model=ErrorResponse,
    status_code=410,
    responses={401: {"model": ErrorResponse}},
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
