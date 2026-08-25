from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from bktstr.server import CAPABILITIES, health_payload

from .auth import require_api_key
from .schemas import CapabilityResponse, ErrorResponse, HealthResponse


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
