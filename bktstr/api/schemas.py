from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bktstr.services.experiments import ExecutionMode, ExperimentRecord, ExperimentStatus


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
