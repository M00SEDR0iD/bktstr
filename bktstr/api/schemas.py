from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
