from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4


class ExperimentStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionMode(StrEnum):
    AUTO = "auto"
    SYNC = "sync"
    ASYNC = "async"


class ExperimentStateError(ValueError):
    """Raised when a requested lifecycle transition would rewrite history."""


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused for different research input."""


class ExperimentNotFoundError(KeyError):
    """Raised when an experiment identifier is not present in this store."""


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    operation: str
    status: ExperimentStatus
    execution: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    request: Mapping[str, Any]
    result: Mapping[str, Any] | None
    error: Mapping[str, Any] | None
    provenance: Mapping[str, Any] | None


def experiment_root() -> Path:
    """Return the configured durable root, preferring an explicit local override."""
    configured = os.getenv("BKTSTR_EXPERIMENT_DIR")
    if configured:
        return Path(configured)
    railway_volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if railway_volume:
        return Path(railway_volume) / "bktstr-experiments"
    return Path("/tmp/bktstr-experiments")


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Experiment artifacts must contain canonical JSON without NaN or infinity.") from exc


def _frozen_json(value: str | None) -> Mapping[str, Any] | None:
    if value is None:
        return None
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("Experiment JSON values must be objects.")
    return _freeze(decoded)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _encode_timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _decode_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ExperimentStore:
    """A SQLite index plus canonical artifacts for immutable research records."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else experiment_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts_root = self.root / "artifacts"
        self.artifacts_root.mkdir(exist_ok=True)
        self.database_path = self.root / "experiments.sqlite3"
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    experiment_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error_json TEXT,
                    provenance_json TEXT,
                    idempotency_key TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS experiments_operation_idempotency_key
                ON experiments(operation, idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )

    def _artifact_path(self, experiment_id: str, filename: str) -> Path:
        return self.artifacts_root / experiment_id / filename

    def _write_artifact(self, experiment_id: str, filename: str, canonical_json: str) -> None:
        destination = self._artifact_path(experiment_id, filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{filename}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(canonical_json.encode("utf-8"))
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _record(row: sqlite3.Row) -> ExperimentRecord:
        return ExperimentRecord(
            experiment_id=row["experiment_id"],
            operation=row["operation"],
            status=ExperimentStatus(row["status"]),
            execution=row["execution"],
            created_at=_decode_timestamp(row["created_at"]),  # type: ignore[arg-type]
            started_at=_decode_timestamp(row["started_at"]),
            completed_at=_decode_timestamp(row["completed_at"]),
            request=_frozen_json(row["request_json"]) or MappingProxyType({}),
            result=_frozen_json(row["result_json"]),
            error=_frozen_json(row["error_json"]),
            provenance=_frozen_json(row["provenance_json"]),
        )

    @staticmethod
    def _execution_value(execution: ExecutionMode | str) -> str:
        try:
            return ExecutionMode(execution).value
        except ValueError as exc:
            raise ValueError(f"Unsupported execution mode: {execution!r}") from exc

    def _load_row(self, connection: sqlite3.Connection, experiment_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        if row is None:
            raise ExperimentNotFoundError(experiment_id)
        return row

    def create_experiment(
        self,
        operation: str,
        request: Mapping[str, Any],
        execution: ExecutionMode | str = ExecutionMode.AUTO,
        idempotency_key: str | None = None,
    ) -> tuple[ExperimentRecord, bool]:
        if not operation:
            raise ValueError("Experiment operation is required.")
        if idempotency_key == "":
            raise ValueError("Idempotency keys cannot be empty.")
        request_json = _canonical_json(request)
        execution_value = self._execution_value(execution)
        now = _timestamp()
        experiment_id = f"exp_{uuid4().hex}"
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                if idempotency_key is not None:
                    existing = connection.execute(
                        "SELECT * FROM experiments WHERE operation = ? AND idempotency_key = ?",
                        (operation, idempotency_key),
                    ).fetchone()
                    if existing is not None:
                        if existing["request_json"] != request_json:
                            raise IdempotencyConflictError(
                                "This idempotency key was already used with a different request."
                            )
                        connection.execute("COMMIT")
                        return self._record(existing), False
                connection.execute(
                    """
                    INSERT INTO experiments (
                        experiment_id, operation, status, execution, created_at, request_json, idempotency_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        experiment_id,
                        operation,
                        ExperimentStatus.QUEUED.value,
                        execution_value,
                        _encode_timestamp(now),
                        request_json,
                        idempotency_key,
                    ),
                )
                self._write_artifact(experiment_id, "request.json", request_json)
                row = self._load_row(connection, experiment_id)
                connection.execute("COMMIT")
                return self._record(row), True
        except Exception:
            # A failed transaction must not leave this connection holding a lock.
            raise

    def load_experiment(self, experiment_id: str) -> ExperimentRecord:
        with self._connect() as connection:
            return self._record(self._load_row(connection, experiment_id))

    def claim_next(self) -> ExperimentRecord | None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM experiments WHERE status = ? ORDER BY created_at, experiment_id LIMIT 1",
                (ExperimentStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            now = _timestamp()
            connection.execute(
                "UPDATE experiments SET status = ?, started_at = ? WHERE experiment_id = ?",
                (ExperimentStatus.RUNNING.value, _encode_timestamp(now), row["experiment_id"]),
            )
            claimed = self._load_row(connection, row["experiment_id"])
            connection.execute("COMMIT")
            return self._record(claimed)

    def complete(
        self,
        experiment_id: str,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
    ) -> ExperimentRecord:
        result_json = _canonical_json(result)
        provenance_json = _canonical_json(provenance)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_row(connection, experiment_id)
            status = ExperimentStatus(row["status"])
            if status in (ExperimentStatus.COMPLETED, ExperimentStatus.FAILED):
                raise ExperimentStateError(f"Experiment {experiment_id} is terminal and cannot be completed.")
            if status is ExperimentStatus.QUEUED:
                connection.execute(
                    "UPDATE experiments SET status = ?, started_at = ? WHERE experiment_id = ?",
                    (ExperimentStatus.RUNNING.value, _encode_timestamp(_timestamp()), experiment_id),
                )
            completed_at = _timestamp()
            self._write_artifact(experiment_id, "result.json", result_json)
            self._write_artifact(experiment_id, "provenance.json", provenance_json)
            connection.execute(
                """
                UPDATE experiments
                SET status = ?, completed_at = ?, result_json = ?, provenance_json = ?
                WHERE experiment_id = ?
                """,
                (
                    ExperimentStatus.COMPLETED.value,
                    _encode_timestamp(completed_at),
                    result_json,
                    provenance_json,
                    experiment_id,
                ),
            )
            completed = self._load_row(connection, experiment_id)
            connection.execute("COMMIT")
            return self._record(completed)

    def fail(self, experiment_id: str, error: Mapping[str, Any]) -> ExperimentRecord:
        error_json = _canonical_json(error)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_row(connection, experiment_id)
            status = ExperimentStatus(row["status"])
            if status is not ExperimentStatus.RUNNING:
                raise ExperimentStateError(
                    f"Experiment {experiment_id} must be running before it can fail."
                )
            completed_at = _timestamp()
            self._write_artifact(experiment_id, "error.json", error_json)
            connection.execute(
                """
                UPDATE experiments
                SET status = ?, completed_at = ?, error_json = ?
                WHERE experiment_id = ?
                """,
                (ExperimentStatus.FAILED.value, _encode_timestamp(completed_at), error_json, experiment_id),
            )
            failed = self._load_row(connection, experiment_id)
            connection.execute("COMMIT")
            return self._record(failed)


def create_experiment(*args: Any, store: ExperimentStore | None = None, **kwargs: Any) -> tuple[ExperimentRecord, bool]:
    return (store or ExperimentStore()).create_experiment(*args, **kwargs)


def load_experiment(experiment_id: str, *, store: ExperimentStore | None = None) -> ExperimentRecord:
    return (store or ExperimentStore()).load_experiment(experiment_id)


def claim_next(*, store: ExperimentStore | None = None) -> ExperimentRecord | None:
    return (store or ExperimentStore()).claim_next()


def complete(
    experiment_id: str,
    result: Mapping[str, Any],
    provenance: Mapping[str, Any],
    *,
    store: ExperimentStore | None = None,
) -> ExperimentRecord:
    return (store or ExperimentStore()).complete(experiment_id, result, provenance)


def fail(
    experiment_id: str,
    error: Mapping[str, Any],
    *,
    store: ExperimentStore | None = None,
) -> ExperimentRecord:
    return (store or ExperimentStore()).fail(experiment_id, error)
