from __future__ import annotations

from fastapi import Response

from bktstr.services.experiments import ExperimentRecord, ExperimentStatus


POLL_RETRY_SECONDS = 2
_NONTERMINAL = frozenset({ExperimentStatus.QUEUED, ExperimentStatus.RUNNING})


def experiment_status_url(record: ExperimentRecord) -> str:
    return f"/api/v1/experiments/{record.experiment_id}"


def experiment_retry_after(record: ExperimentRecord) -> int | None:
    return POLL_RETRY_SECONDS if record.status in _NONTERMINAL else None


def apply_experiment_headers(
    response: Response,
    record: ExperimentRecord,
    *,
    include_location: bool,
) -> None:
    if include_location:
        response.headers["Location"] = experiment_status_url(record)
    retry_after = experiment_retry_after(record)
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)


__all__ = [
    "POLL_RETRY_SECONDS",
    "apply_experiment_headers",
    "experiment_retry_after",
    "experiment_status_url",
]
