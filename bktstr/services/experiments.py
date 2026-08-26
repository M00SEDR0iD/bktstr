from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping
from uuid import uuid4

import httpx

from .validation import SemanticValidationError


_WORKER_LEASE_NAME = "experiment-worker"
_ARTIFACT_RECONCILE_LIMIT = 25


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


class ExecutionNotAvailableError(ValueError):
    """Raised when a client requests inline execution outside the safe policy."""

    code = "execution_not_available"

    def __init__(self, message: str = "This operation cannot run synchronously.") -> None:
        super().__init__(message)


class ExperimentOperationError(RuntimeError):
    """An expected operation failure safe to persist in an experiment envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True)
class ExecutionPolicy:
    """Select synchronous execution only for bounded individual backtests."""

    sync_max_calendar_days: int = 31

    def __post_init__(self) -> None:
        if self.sync_max_calendar_days < 1:
            raise ValueError("sync_max_calendar_days must be at least 1.")

    @classmethod
    def from_environment(cls) -> "ExecutionPolicy":
        configured = os.getenv("BKTSTR_SYNC_MAX_CALENDAR_DAYS")
        return cls(sync_max_calendar_days=int(configured) if configured is not None else 31)

    def choose(
        self,
        operation: str,
        execution: ExecutionMode | str,
        *,
        calendar_days: int | None,
    ) -> ExecutionMode:
        try:
            requested = ExecutionMode(execution)
        except ValueError as exc:
            raise ValueError(f"Unsupported execution mode: {execution!r}") from exc

        can_run_inline = (
            operation == "backtest"
            and calendar_days is not None
            and 0 <= calendar_days <= self.sync_max_calendar_days
        )
        if requested is ExecutionMode.ASYNC:
            return ExecutionMode.ASYNC
        if requested is ExecutionMode.SYNC:
            if can_run_inline:
                return ExecutionMode.SYNC
            raise ExecutionNotAvailableError()
        return ExecutionMode.SYNC if can_run_inline else ExecutionMode.ASYNC


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    operation: str
    status: ExperimentStatus
    execution: ExecutionMode
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    request: Mapping[str, Any]
    result: Mapping[str, Any] | None
    error: Mapping[str, Any] | None
    provenance: Mapping[str, Any] | None
    parent_experiment_id: str | None = None


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
                    idempotency_key TEXT,
                    parent_experiment_id TEXT,
                    artifact_generation TEXT,
                    artifact_published_generation TEXT,
                    worker_owner_id TEXT
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(experiments)")
            }
            if "parent_experiment_id" not in columns:
                connection.execute(
                    "ALTER TABLE experiments ADD COLUMN parent_experiment_id TEXT"
                )
            if "artifact_generation" not in columns:
                connection.execute(
                    "ALTER TABLE experiments ADD COLUMN artifact_generation TEXT"
                )
            if "artifact_published_generation" not in columns:
                connection.execute(
                    "ALTER TABLE experiments ADD COLUMN artifact_published_generation TEXT"
                )
            if "worker_owner_id" not in columns:
                connection.execute(
                    "ALTER TABLE experiments ADD COLUMN worker_owner_id TEXT"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_leases (
                    lease_name TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL
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
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS experiments_artifact_publication
                ON experiments(
                    artifact_published_generation,
                    artifact_generation,
                    created_at,
                    experiment_id
                )
                WHERE artifact_generation IS NOT NULL
                """
            )
        self.reconcile_artifacts(limit=_ARTIFACT_RECONCILE_LIMIT)

    def acquire_worker_lease(
        self,
        owner_id: str,
        *,
        lease_duration_seconds: float,
        now: datetime | None = None,
    ) -> bool:
        if not owner_id:
            raise ValueError("worker lease owner_id is required")
        if lease_duration_seconds <= 0:
            raise ValueError("worker lease duration must be positive")
        current = now or _timestamp()
        expires_at = current + timedelta(seconds=lease_duration_seconds)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            lease = connection.execute(
                "SELECT owner_id, expires_at FROM worker_leases WHERE lease_name = ?",
                (_WORKER_LEASE_NAME,),
            ).fetchone()
            if (
                lease is not None
                and lease["owner_id"] != owner_id
                and _decode_timestamp(lease["expires_at"]) > current
            ):
                connection.execute("COMMIT")
                return False
            connection.execute(
                """
                INSERT INTO worker_leases (lease_name, owner_id, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(lease_name) DO UPDATE SET
                    owner_id = excluded.owner_id,
                    expires_at = excluded.expires_at
                """,
                (
                    _WORKER_LEASE_NAME,
                    owner_id,
                    _encode_timestamp(expires_at),
                ),
            )
            connection.execute("COMMIT")
        return True

    def renew_worker_lease(
        self,
        owner_id: str,
        *,
        lease_duration_seconds: float,
        now: datetime | None = None,
    ) -> bool:
        if lease_duration_seconds <= 0:
            raise ValueError("worker lease duration must be positive")
        current = now or _timestamp()
        expires_at = current + timedelta(seconds=lease_duration_seconds)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE worker_leases SET expires_at = ?
                WHERE lease_name = ? AND owner_id = ?
                """,
                (_encode_timestamp(expires_at), _WORKER_LEASE_NAME, owner_id),
            )
        return cursor.rowcount == 1

    def owns_worker_lease(
        self, owner_id: str, *, now: datetime | None = None
    ) -> bool:
        current = now or _timestamp()
        with self._connect() as connection:
            lease = connection.execute(
                "SELECT owner_id, expires_at FROM worker_leases WHERE lease_name = ?",
                (_WORKER_LEASE_NAME,),
            ).fetchone()
        return bool(
            lease is not None
            and lease["owner_id"] == owner_id
            and _decode_timestamp(lease["expires_at"]) > current
        )

    def release_worker_lease(self, owner_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM worker_leases WHERE lease_name = ? AND owner_id = ?",
                (_WORKER_LEASE_NAME, owner_id),
            )
        return cursor.rowcount == 1

    @staticmethod
    def _write_json(destination: Path, canonical_json: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(canonical_json.encode("utf-8"))
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _artifact_files(row: sqlite3.Row) -> dict[str, str]:
        files = {"request.json": row["request_json"]}
        for filename, column in (
            ("result.json", "result_json"),
            ("provenance.json", "provenance_json"),
            ("error.json", "error_json"),
        ):
            if row[column] is not None:
                files[filename] = row[column]
        return files

    @classmethod
    def _generation_for(cls, row: sqlite3.Row) -> str:
        files = cls._artifact_files(row)
        digest = hashlib.sha256(
            _canonical_json(
                {
                    "status": row["status"],
                    "files": {
                        name: hashlib.sha256(contents.encode("utf-8")).hexdigest()
                        for name, contents in sorted(files.items())
                    },
                }
            ).encode("utf-8")
        ).hexdigest()
        # Keep the generation portable as a directory name on Railway and local
        # Windows development volumes; the manifest still records file digests.
        return digest

    @classmethod
    def _manifest_for(cls, row: sqlite3.Row) -> dict[str, Any]:
        files = cls._artifact_files(row)
        return {
            "generation": row["artifact_generation"],
            "status": row["status"],
            "files": {
                name: hashlib.sha256(contents.encode("utf-8")).hexdigest()
                for name, contents in sorted(files.items())
            },
        }

    def _generation_is_valid(self, row: sqlite3.Row) -> bool:
        generation = row["artifact_generation"]
        if not isinstance(generation, str) or not generation:
            return False
        generation_dir = (
            self.artifacts_root
            / row["experiment_id"]
            / "generations"
            / generation
        )
        files = self._artifact_files(row)
        try:
            entries = tuple(generation_dir.iterdir())
            if {entry.name for entry in entries} != set(files):
                return False
            if any(not entry.is_file() for entry in entries):
                return False
            return all(
                (generation_dir / filename).read_text(encoding="utf-8") == contents
                for filename, contents in files.items()
            )
        except (OSError, UnicodeDecodeError):
            return False

    def _validated_manifest(self, row: sqlite3.Row) -> Mapping[str, Any] | None:
        generation = row["artifact_generation"]
        if not isinstance(generation, str) or not generation:
            return None
        artifact_dir = self.artifacts_root / row["experiment_id"]
        try:
            manifest = json.loads(
                (artifact_dir / "manifest.json").read_text(encoding="utf-8")
            )
            if manifest != self._manifest_for(row):
                return None
            if not self._generation_is_valid(row):
                return None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return manifest

    def _set_artifact_generation(
        self, connection: sqlite3.Connection, experiment_id: str
    ) -> sqlite3.Row:
        row = self._load_row(connection, experiment_id)
        generation = self._generation_for(row)
        connection.execute(
            "UPDATE experiments SET artifact_generation = ? WHERE experiment_id = ?",
            (generation, experiment_id),
        )
        return self._load_row(connection, experiment_id)

    def _publish_artifact_generation(self, experiment_id: str) -> None:
        """Publish the authoritative generation while serializing lifecycle writers."""
        staging: Path | None = None
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._load_row(connection, experiment_id)
                generation = row["artifact_generation"]
                if not isinstance(generation, str) or not generation:
                    connection.execute("COMMIT")
                    return
                files = self._artifact_files(row)
                artifact_dir = self.artifacts_root / experiment_id
                staging = (
                    self.artifacts_root
                    / ".staging"
                    / f"{experiment_id}.{uuid4().hex}"
                )
                for filename, contents in files.items():
                    self._write_json(staging / filename, contents)
                generation_dir = artifact_dir / "generations" / generation
                generation_dir.parent.mkdir(parents=True, exist_ok=True)
                if generation_dir.exists() and not self._generation_is_valid(row):
                    replaced = generation_dir.with_name(
                        f".{generation}.replaced.{uuid4().hex}"
                    )
                    os.replace(generation_dir, replaced)
                    try:
                        os.replace(staging, generation_dir)
                    except Exception:
                        os.replace(replaced, generation_dir)
                        raise
                    staging = None
                    try:
                        for child in sorted(replaced.rglob("*"), reverse=True):
                            if child.is_file():
                                child.unlink()
                            elif child.is_dir():
                                child.rmdir()
                        replaced.rmdir()
                    except OSError:
                        # The valid generation is already atomically published;
                        # stale replaced directories are never referenced.
                        pass
                elif not generation_dir.exists():
                    os.replace(staging, generation_dir)
                    staging = None
                self._write_json(
                    artifact_dir / "manifest.json",
                    _canonical_json(self._manifest_for(row)),
                )
                connection.execute(
                    """
                    UPDATE experiments SET artifact_published_generation = ?
                    WHERE experiment_id = ? AND artifact_generation = ?
                    """,
                    (generation, experiment_id, generation),
                )
                connection.execute("COMMIT")
        finally:
            if staging is not None and staging.exists():
                for child in sorted(staging.rglob("*"), reverse=True):
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                staging.rmdir()

    def _best_effort_publish(self, experiment_id: str) -> bool:
        try:
            self._publish_artifact_generation(experiment_id)
        except Exception:
            return False
        return True

    def reconcile_artifacts(
        self,
        experiment_id: str | None = None,
        *,
        limit: int = _ARTIFACT_RECONCILE_LIMIT,
    ) -> int:
        """Repair stale projections from SQLite without re-running experiments."""
        if limit < 1:
            raise ValueError("artifact reconciliation limit must be positive")
        with self._connect() as connection:
            if experiment_id is None:
                rows = connection.execute(
                    """
                    SELECT * FROM experiments
                    WHERE artifact_generation IS NOT NULL
                      AND (
                        artifact_published_generation IS NULL
                        OR artifact_published_generation != artifact_generation
                      )
                    ORDER BY created_at, experiment_id
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = [self._load_row(connection, experiment_id)]
        repaired = 0
        for row in rows:
            dirty = row["artifact_published_generation"] != row["artifact_generation"]
            invalid = self._validated_manifest(row) is None
            if (dirty or invalid) and self._best_effort_publish(row["experiment_id"]):
                with self._connect() as connection:
                    current = self._load_row(connection, row["experiment_id"])
                if (
                    current["artifact_published_generation"]
                    == current["artifact_generation"]
                    and self._validated_manifest(current) is not None
                ):
                    repaired += 1
        return repaired

    def load_artifact_manifest(self, experiment_id: str) -> Mapping[str, Any]:
        """Return only a manifest validated against authoritative SQLite state."""
        self.reconcile_artifacts(experiment_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_row(connection, experiment_id)
            manifest = self._validated_manifest(row)
            connection.execute("COMMIT")
        if manifest is None:
            raise OSError(
                f"Artifact projection for experiment {experiment_id} is unavailable."
            )
        return _freeze(dict(manifest))

    @staticmethod
    def _record(row: sqlite3.Row) -> ExperimentRecord:
        return ExperimentRecord(
            experiment_id=row["experiment_id"],
            operation=row["operation"],
            status=ExperimentStatus(row["status"]),
            execution=ExecutionMode(row["execution"]),
            created_at=_decode_timestamp(row["created_at"]),  # type: ignore[arg-type]
            started_at=_decode_timestamp(row["started_at"]),
            completed_at=_decode_timestamp(row["completed_at"]),
            request=_frozen_json(row["request_json"]) or MappingProxyType({}),
            result=_frozen_json(row["result_json"]),
            error=_frozen_json(row["error_json"]),
            provenance=_frozen_json(row["provenance_json"]),
            parent_experiment_id=row["parent_experiment_id"],
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
        parent_experiment_id: str | None = None,
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
                if parent_experiment_id is not None:
                    self._load_row(connection, parent_experiment_id)
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
                        experiment_id, operation, status, execution, created_at, request_json,
                        idempotency_key, parent_experiment_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        experiment_id,
                        operation,
                        ExperimentStatus.QUEUED.value,
                        execution_value,
                        _encode_timestamp(now),
                        request_json,
                        idempotency_key,
                        parent_experiment_id,
                    ),
                )
                row = self._set_artifact_generation(connection, experiment_id)
                connection.execute("COMMIT")
            self._best_effort_publish(experiment_id)
            return self._record(row), True
        except Exception:
            # A failed transaction must not leave this connection holding a lock.
            raise

    def create_and_claim_experiment(
        self,
        operation: str,
        request: Mapping[str, Any],
        execution: ExecutionMode | str = ExecutionMode.SYNC,
        idempotency_key: str | None = None,
        parent_experiment_id: str | None = None,
    ) -> tuple[ExperimentRecord, bool]:
        """Atomically persist and reserve a synchronous experiment for its caller."""
        if not operation:
            raise ValueError("Experiment operation is required.")
        if idempotency_key == "":
            raise ValueError("Idempotency keys cannot be empty.")
        request_json = _canonical_json(request)
        execution_value = self._execution_value(execution)
        if execution_value != ExecutionMode.SYNC.value:
            raise ValueError("Only synchronous experiments can be created and claimed together.")
        now = _timestamp()
        experiment_id = f"exp_{uuid4().hex}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if parent_experiment_id is not None:
                self._load_row(connection, parent_experiment_id)
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
                    experiment_id, operation, status, execution, created_at, started_at,
                    request_json, idempotency_key, parent_experiment_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    operation,
                    ExperimentStatus.RUNNING.value,
                    execution_value,
                    _encode_timestamp(now),
                    _encode_timestamp(now),
                    request_json,
                    idempotency_key,
                    parent_experiment_id,
                ),
            )
            record = self._set_artifact_generation(connection, experiment_id)
            connection.execute("COMMIT")
        self._best_effort_publish(experiment_id)
        return self._record(record), True

    def load_experiment(self, experiment_id: str) -> ExperimentRecord:
        with self._connect() as connection:
            return self._record(self._load_row(connection, experiment_id))

    def claim_next(
        self,
        owner_id: str | None = None,
        *,
        now: datetime | None = None,
    ) -> ExperimentRecord | None:
        current = now or _timestamp()
        temporary_owner = owner_id is None
        owner = owner_id or f"one-shot-{uuid4().hex}"
        if temporary_owner and not self.acquire_worker_lease(
            owner, lease_duration_seconds=30, now=current
        ):
            return None
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                lease = connection.execute(
                    "SELECT owner_id, expires_at FROM worker_leases WHERE lease_name = ?",
                    (_WORKER_LEASE_NAME,),
                ).fetchone()
                if (
                    lease is None
                    or lease["owner_id"] != owner
                    or _decode_timestamp(lease["expires_at"]) <= current
                ):
                    connection.execute("COMMIT")
                    return None
                row = connection.execute(
                    "SELECT * FROM experiments WHERE status = ? ORDER BY created_at, experiment_id LIMIT 1",
                    (ExperimentStatus.QUEUED.value,),
                ).fetchone()
                if row is None:
                    connection.execute("COMMIT")
                    return None
                connection.execute(
                    """
                    UPDATE experiments
                    SET status = ?, started_at = ?, worker_owner_id = ?
                    WHERE experiment_id = ?
                    """,
                    (
                        ExperimentStatus.RUNNING.value,
                        _encode_timestamp(current),
                        owner,
                        row["experiment_id"],
                    ),
                )
                claimed = self._set_artifact_generation(
                    connection, row["experiment_id"]
                )
                connection.execute("COMMIT")
            self._best_effort_publish(claimed["experiment_id"])
            return self._record(claimed)
        finally:
            if temporary_owner:
                self.release_worker_lease(owner)

    def claim(self, experiment_id: str) -> ExperimentRecord:
        """Claim one particular queued row for synchronous execution."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_row(connection, experiment_id)
            if ExperimentStatus(row["status"]) is not ExperimentStatus.QUEUED:
                raise ExperimentStateError(f"Experiment {experiment_id} is not queued.")
            now = _timestamp()
            connection.execute(
                "UPDATE experiments SET status = ?, started_at = ? WHERE experiment_id = ?",
                (ExperimentStatus.RUNNING.value, _encode_timestamp(now), experiment_id),
            )
            claimed = self._set_artifact_generation(connection, experiment_id)
            connection.execute("COMMIT")
        self._best_effort_publish(experiment_id)
        return self._record(claimed)

    def recover_incomplete(
        self,
        owner_id: str | None = None,
        *,
        now: datetime | None = None,
    ) -> int:
        """Return records abandoned by a prior process to the durable queue."""
        current = now or _timestamp()
        temporary_owner = owner_id is None
        owner = owner_id or f"recovery-{uuid4().hex}"
        if temporary_owner and not self.acquire_worker_lease(
            owner, lease_duration_seconds=30, now=current
        ):
            return 0
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                lease = connection.execute(
                    "SELECT owner_id, expires_at FROM worker_leases WHERE lease_name = ?",
                    (_WORKER_LEASE_NAME,),
                ).fetchone()
                if (
                    lease is None
                    or lease["owner_id"] != owner
                    or _decode_timestamp(lease["expires_at"]) <= current
                ):
                    connection.execute("COMMIT")
                    return 0
                running_ids = [
                    row["experiment_id"]
                    for row in connection.execute(
                        """
                        SELECT experiment_id FROM experiments
                        WHERE status = ? AND execution != ?
                          AND (worker_owner_id IS NULL OR worker_owner_id != ?)
                        """,
                        (
                            ExperimentStatus.RUNNING.value,
                            ExecutionMode.SYNC.value,
                            owner,
                        ),
                    )
                ]
                cursor = connection.execute(
                    """
                    UPDATE experiments
                    SET status = ?, started_at = NULL, worker_owner_id = NULL
                    WHERE status = ? AND execution != ?
                      AND (worker_owner_id IS NULL OR worker_owner_id != ?)
                    """,
                    (
                        ExperimentStatus.QUEUED.value,
                        ExperimentStatus.RUNNING.value,
                        ExecutionMode.SYNC.value,
                        owner,
                    ),
                )
                for experiment_id in running_ids:
                    self._set_artifact_generation(connection, experiment_id)
                connection.execute("COMMIT")
            for experiment_id in running_ids:
                self._best_effort_publish(experiment_id)
            return cursor.rowcount
        finally:
            if temporary_owner:
                self.release_worker_lease(owner)

    def complete(
        self,
        experiment_id: str,
        result: Mapping[str, Any],
        provenance: Mapping[str, Any],
        *,
        owner_id: str | None = None,
    ) -> ExperimentRecord:
        result_json = _canonical_json(result)
        provenance_json = _canonical_json(provenance)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_row(connection, experiment_id)
            status = ExperimentStatus(row["status"])
            if status in (ExperimentStatus.COMPLETED, ExperimentStatus.FAILED):
                raise ExperimentStateError(f"Experiment {experiment_id} is terminal and cannot be completed.")
            if owner_id is not None and row["worker_owner_id"] != owner_id:
                raise ExperimentStateError(
                    f"Experiment {experiment_id} is not owned by worker {owner_id}."
                )
            if status is ExperimentStatus.QUEUED:
                connection.execute(
                    "UPDATE experiments SET status = ?, started_at = ? WHERE experiment_id = ?",
                    (ExperimentStatus.RUNNING.value, _encode_timestamp(_timestamp()), experiment_id),
                )
            completed_at = _timestamp()
            connection.execute(
                """
                UPDATE experiments
                SET status = ?, completed_at = ?, result_json = ?, provenance_json = ?,
                    worker_owner_id = NULL
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
            completed = self._set_artifact_generation(connection, experiment_id)
            connection.execute("COMMIT")
        self._best_effort_publish(experiment_id)
        return self._record(completed)

    def fail(
        self,
        experiment_id: str,
        error: Mapping[str, Any],
        *,
        owner_id: str | None = None,
    ) -> ExperimentRecord:
        error_json = _canonical_json(error)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._load_row(connection, experiment_id)
            status = ExperimentStatus(row["status"])
            if status is not ExperimentStatus.RUNNING:
                raise ExperimentStateError(
                    f"Experiment {experiment_id} must be running before it can fail."
                )
            if owner_id is not None and row["worker_owner_id"] != owner_id:
                raise ExperimentStateError(
                    f"Experiment {experiment_id} is not owned by worker {owner_id}."
                )
            completed_at = _timestamp()
            connection.execute(
                """
                UPDATE experiments
                SET status = ?, completed_at = ?, error_json = ?, worker_owner_id = NULL
                WHERE experiment_id = ?
                """,
                (ExperimentStatus.FAILED.value, _encode_timestamp(completed_at), error_json, experiment_id),
            )
            failed = self._set_artifact_generation(connection, experiment_id)
            connection.execute("COMMIT")
        self._best_effort_publish(experiment_id)
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


OperationHandler = Callable[[ExperimentRecord], tuple[Mapping[str, Any], Mapping[str, Any]]]


class ExperimentWorker:
    """Execute durable experiments from SQLite without making HTTP the lifecycle authority."""

    def __init__(
        self,
        store: ExperimentStore,
        operations: Mapping[str, OperationHandler],
        *,
        poll_interval_seconds: float = 0.1,
        owner_id: str | None = None,
        lease_duration_seconds: float = 30.0,
        heartbeat_interval_seconds: float | None = None,
        clock: Callable[[], datetime] = _timestamp,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive.")
        if lease_duration_seconds <= 0:
            raise ValueError("lease_duration_seconds must be positive.")
        heartbeat_interval = (
            heartbeat_interval_seconds
            if heartbeat_interval_seconds is not None
            else lease_duration_seconds / 3
        )
        if heartbeat_interval <= 0 or heartbeat_interval >= lease_duration_seconds:
            raise ValueError(
                "heartbeat_interval_seconds must be positive and shorter than the lease."
            )
        self.store = store
        self.operations = dict(operations)
        self.poll_interval_seconds = poll_interval_seconds
        self.owner_id = owner_id or f"worker-{uuid4().hex}"
        self.lease_duration_seconds = lease_duration_seconds
        self.heartbeat_interval_seconds = heartbeat_interval
        self.clock = clock
        self._has_lease = False
        self._lease_lost = threading.Event()

    def _ensure_lease(self) -> tuple[bool, bool]:
        current = self.clock()
        if self._has_lease and self.store.renew_worker_lease(
            self.owner_id,
            lease_duration_seconds=self.lease_duration_seconds,
            now=current,
        ):
            return True, False
        self._has_lease = self.store.acquire_worker_lease(
            self.owner_id,
            lease_duration_seconds=self.lease_duration_seconds,
            now=current,
        )
        if self._has_lease:
            self._lease_lost.clear()
            return True, True
        return False, False

    def _heartbeat(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(self.heartbeat_interval_seconds):
            try:
                renewed = self.store.renew_worker_lease(
                    self.owner_id,
                    lease_duration_seconds=self.lease_duration_seconds,
                    now=self.clock(),
                )
            except Exception:
                renewed = False
            if not renewed:
                self._has_lease = False
                self._lease_lost.set()
                return

    def _start_heartbeat(self) -> tuple[threading.Event, threading.Thread]:
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._heartbeat,
            args=(stop_event,),
            daemon=True,
            name=f"bktstr-lease-{self.owner_id}",
        )
        thread.start()
        return stop_event, thread

    def release_lease(self) -> bool:
        released = self.store.release_worker_lease(self.owner_id)
        self._has_lease = False
        return released

    def recover_incomplete(self) -> int:
        owned, _ = self._ensure_lease()
        if not owned:
            return 0
        return self.store.recover_incomplete(self.owner_id, now=self.clock())

    def _fail_survivably(
        self, record: ExperimentRecord, error: Mapping[str, Any]
    ) -> ExperimentRecord:
        try:
            return self.store.fail(
                record.experiment_id,
                error,
                owner_id=(
                    None
                    if record.execution is ExecutionMode.SYNC
                    else self.owner_id
                ),
            )
        except ExperimentStateError:
            # Another owner may have terminalized or recovered this row while a
            # stale handler was returning. Its authoritative SQLite state wins.
            return self.store.load_experiment(record.experiment_id)

    def _execute(self, record: ExperimentRecord) -> ExperimentRecord:
        operation = self.operations.get(record.operation)
        if operation is None:
            return self._fail_survivably(
                record,
                {
                    "code": "operation_not_registered",
                    "message": "No handler is registered for this experiment operation.",
                    "details": {"operation": record.operation},
                },
            )
        try:
            result, provenance = operation(record)
        except ExperimentOperationError as exc:
            return self._fail_survivably(
                record,
                {"code": exc.code, "message": str(exc), "details": exc.details},
            )
        except SemanticValidationError as exc:
            return self._fail_survivably(
                record,
                {
                    "code": "invalid_request",
                    "message": str(exc),
                    "details": {"fields": list(exc.fields)},
                },
            )
        except ValueError as exc:
            return self._fail_survivably(
                record,
                {"code": "invalid_request", "message": str(exc), "details": {}},
            )
        except httpx.HTTPError:
            return self._fail_survivably(
                record,
                {
                    "code": "market_data_http_error",
                    "message": "Market-data provider request failed.",
                    "details": {},
                },
            )
        except Exception:
            return self._fail_survivably(
                record,
                {
                    "code": "operation_failed",
                    "message": "The experiment operation failed.",
                    "details": {},
                },
            )
        try:
            return self.store.complete(
                record.experiment_id,
                result,
                provenance,
                owner_id=(
                    None
                    if record.execution is ExecutionMode.SYNC
                    else self.owner_id
                ),
            )
        except ExperimentStateError:
            return self.store.load_experiment(record.experiment_id)
        except Exception:
            return self._fail_survivably(
                record,
                {
                    "code": "result_persistence_failed",
                    "message": "Experiment result persistence failed.",
                    "details": {},
                },
            )

    def _run_one_owned(self) -> ExperimentRecord | None:
        self.store.reconcile_artifacts(limit=_ARTIFACT_RECONCILE_LIMIT)
        record = self.store.claim_next(self.owner_id, now=self.clock())
        return None if record is None else self._execute(record)

    def run_one(self) -> ExperimentRecord | None:
        owned, acquired = self._ensure_lease()
        if not owned:
            return None
        if acquired:
            self.store.recover_incomplete(self.owner_id, now=self.clock())
        heartbeat_stop, heartbeat_thread = self._start_heartbeat()
        try:
            return self._run_one_owned()
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join()
            self.release_lease()

    def run(self, experiment_id: str) -> ExperimentRecord:
        return self._execute(self.store.claim(experiment_id))

    def run_claimed(self, record: ExperimentRecord) -> ExperimentRecord:
        if record.status is not ExperimentStatus.RUNNING:
            raise ExperimentStateError(f"Experiment {record.experiment_id} is not running.")
        return self._execute(record)

    def run_forever(self, stop_event: threading.Event) -> None:
        try:
            while not stop_event.is_set():
                try:
                    owned, acquired = self._ensure_lease()
                except Exception:
                    owned, acquired = False, False
                if not owned:
                    stop_event.wait(self.poll_interval_seconds)
                    continue
                if acquired:
                    self.store.recover_incomplete(self.owner_id, now=self.clock())
                heartbeat_stop, heartbeat_thread = self._start_heartbeat()
                try:
                    while not stop_event.is_set() and not self._lease_lost.is_set():
                        try:
                            record = self._run_one_owned()
                        except Exception:
                            # A lifecycle/storage race must never terminate the
                            # durable poller; ownership is rechecked next loop.
                            record = None
                        if record is None:
                            stop_event.wait(self.poll_interval_seconds)
                finally:
                    heartbeat_stop.set()
                    heartbeat_thread.join()
                    self.release_lease()
        finally:
            if self._has_lease:
                self.release_lease()


def submit(
    store: ExperimentStore,
    operations: Mapping[str, OperationHandler],
    operation: str,
    request: Mapping[str, Any],
    *,
    execution: ExecutionMode | str = ExecutionMode.AUTO,
    calendar_days: int | None,
    idempotency_key: str | None = None,
    policy: ExecutionPolicy | None = None,
) -> ExperimentRecord:
    """Create an experiment, completing only a safely bounded one inline."""
    selected = (policy or ExecutionPolicy.from_environment()).choose(
        operation, execution, calendar_days=calendar_days
    )
    if selected is ExecutionMode.SYNC:
        record, created = store.create_and_claim_experiment(
            operation, request, selected, idempotency_key
        )
        if created:
            return ExperimentWorker(store, operations).run_claimed(record)
        return record
    record, _ = store.create_experiment(operation, request, selected, idempotency_key)
    return record


def recover_incomplete(*, store: ExperimentStore | None = None) -> int:
    return (store or ExperimentStore()).recover_incomplete()
