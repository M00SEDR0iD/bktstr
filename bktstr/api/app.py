from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from typing import Any, AsyncIterator
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from bktstr import __version__
from bktstr.server import health_payload
from bktstr.services.experiments import (
    ExecutionNotAvailableError,
    ExperimentNotFoundError,
    ExperimentStore,
    ExperimentWorker,
    IdempotencyConflictError,
)
from bktstr.services.validation import SemanticValidationError

from .routes import api_router, experiment_operations
from .schemas import ApiError, ErrorResponse, HealthResponse, NamedVariantCreate


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", f"req_{uuid4().hex}")


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error = ApiError(
        code=code,
        message=message,
        details=details or {},
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=status_code, content={"error": error.model_dump()}, headers=headers)


def _validation_error_fields(exc: RequestValidationError) -> list[str]:
    union_branch_types = {
        branch.__name__
        for branch in (
            str,
            int,
            float,
            bool,
            bytes,
            list,
            dict,
            tuple,
            type(None),
            NamedVariantCreate,
        )
    }
    candidates: list[str] = []
    for error in exc.errors():
        location = tuple(
            str(part)
            for part in error.get("loc", ())
            if part not in {"body", "query", "path", "header"}
            and str(part) not in union_branch_types
        )
        path = ".".join(location)
        if path and path not in candidates:
            candidates.append(path)
    fields = [
        path
        for path in candidates
        if not any(
            other != path and other.startswith(f"{path}.") for other in candidates
        )
    ]
    return fields or ["request"]


@asynccontextmanager
async def experiment_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Recover durable work before one in-process worker begins polling it."""
    store = ExperimentStore()
    worker = ExperimentWorker(store, experiment_operations(store))
    worker.recover_incomplete()
    stop_event = threading.Event()
    worker_thread = threading.Thread(
        target=worker.run_forever,
        args=(stop_event,),
        daemon=True,
        name="bktstr-experiment-worker",
    )
    app.state.experiment_store = worker.store
    app.state.experiment_worker = worker
    app.state.experiment_worker_stop_event = stop_event
    worker_thread.start()
    try:
        yield
    finally:
        stop_event.set()
        worker_thread.join()


def create_app() -> FastAPI:
    app = FastAPI(title="BKTSTR Research API", version=__version__, lifespan=experiment_lifespan)

    @app.middleware("http")
    async def assign_request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any:
        request.state.request_id = f"req_{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return _error_response(
            request,
            exc.status_code,
            detail.get("code", "http_error"),
            detail.get("message", str(exc.detail)),
            detail.get("details", {}),
            dict(exc.headers or {}),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            request,
            422,
            "validation_error",
            "Request validation failed.",
            {"fields": _validation_error_fields(exc)},
        )

    @app.exception_handler(SemanticValidationError)
    async def handle_semantic_validation_error(
        request: Request, exc: SemanticValidationError
    ) -> JSONResponse:
        return _error_response(
            request,
            400,
            "invalid_request",
            str(exc),
            {"fields": list(exc.fields)},
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        return _error_response(
            request,
            400,
            "invalid_request",
            str(exc),
            {"fields": ["request"]},
        )

    @app.exception_handler(IdempotencyConflictError)
    async def handle_idempotency_conflict(
        request: Request, exc: IdempotencyConflictError
    ) -> JSONResponse:
        return _error_response(request, 409, "idempotency_conflict", str(exc))

    @app.exception_handler(ExecutionNotAvailableError)
    async def handle_execution_refusal(
        request: Request, exc: ExecutionNotAvailableError
    ) -> JSONResponse:
        return _error_response(request, 409, exc.code, str(exc))

    @app.exception_handler(ExperimentNotFoundError)
    async def handle_missing_experiment(
        request: Request, _: ExperimentNotFoundError
    ) -> JSONResponse:
        return _error_response(
            request, 404, "experiment_not_found", "The requested experiment was not found."
        )

    @app.exception_handler(httpx.HTTPError)
    async def handle_provider_error(request: Request, exc: httpx.HTTPError) -> JSONResponse:
        return _error_response(request, 502, "market_data_http_error", "Market-data provider request failed.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, _: Exception) -> JSONResponse:
        return _error_response(request, 500, "internal_error", "An unexpected server error occurred.")

    @app.get("/health", response_model=HealthResponse, responses={500: {"model": ErrorResponse}})
    def root_health() -> dict:
        return health_payload()

    app.include_router(api_router, prefix="/api/v1")
    return app
