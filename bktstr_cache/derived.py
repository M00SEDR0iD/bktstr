from __future__ import annotations

import hashlib
import json
import os
import pickle
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

CACHE_FORMAT_VERSION = "derived-frame-cache-v1"


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, set):
        return sorted((_normalize(v) for v in value), key=lambda x: json.dumps(x, sort_keys=True))
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(_normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def dataframe_digest(frame: pd.DataFrame) -> str:
    """Return a deterministic SHA-256 digest of DataFrame schema, index, and values."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("dataframe_digest requires a pandas DataFrame")

    hasher = hashlib.sha256()
    schema = {
        "columns": [str(c) for c in frame.columns],
        "dtypes": [str(dtype) for dtype in frame.dtypes],
        "index_type": type(frame.index).__name__,
        "index_name": _normalize(frame.index.name),
        "rows": len(frame),
    }
    hasher.update(canonical_json(schema).encode("utf-8"))
    if len(frame):
        row_hashes = pd.util.hash_pandas_object(frame, index=True, categorize=True).values
        hasher.update(row_hashes.tobytes())
    return hasher.hexdigest()


def default_cache_root() -> Path:
    explicit = os.getenv("BKTSTR_DERIVED_CACHE_DIR")
    if explicit:
        return Path(explicit)
    raw_cache = os.getenv("BKTSTR_CACHE_DIR")
    if raw_cache:
        return Path(raw_cache) / "bktstr-cache" / "derived"
    volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    if volume:
        return Path(volume) / "bktstr-cache" / "derived"
    return Path("/tmp/bktstr-cache/derived")


def _safe_namespace(namespace: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", namespace.strip()).strip("-.")
    if not cleaned:
        raise ValueError("namespace must contain at least one safe character")
    return cleaned


@dataclass(frozen=True)
class CacheStatus:
    hit: bool
    key: str
    namespace: str
    payload_path: Path
    metadata_path: Path
    elapsed_seconds: float
    recovered_corruption: bool = False


@dataclass(frozen=True)
class CacheResult:
    frame: pd.DataFrame
    status: CacheStatus


class DerivedFrameCache:
    """Persistent cache for deterministic DataFrame computations.

    The caller owns the formulas. This class only fingerprints inputs/dimensions,
    stores the computed DataFrame, and returns it on an exact future match.
    """

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else default_cache_root()

    @staticmethod
    def input_digests(inputs: Mapping[str, pd.DataFrame | str]) -> dict[str, str]:
        digests: dict[str, str] = {}
        for name, value in sorted(inputs.items()):
            if isinstance(value, pd.DataFrame):
                digests[str(name)] = dataframe_digest(value)
            elif isinstance(value, str) and value:
                digests[str(name)] = value
            else:
                raise TypeError(f"cache input {name!r} must be a DataFrame or non-empty digest string")
        return digests

    @staticmethod
    def make_key(namespace: str, dimensions: Mapping[str, Any], input_digests: Mapping[str, str]) -> str:
        material = {
            "cache_format_version": CACHE_FORMAT_VERSION,
            "namespace": namespace,
            "dimensions": _normalize(dimensions),
            "input_digests": _normalize(input_digests),
        }
        return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()

    def _paths(self, namespace: str, key: str) -> tuple[Path, Path]:
        ns_dir = self.root / _safe_namespace(namespace) / key[:2]
        return ns_dir / f"{key}.pkl.gz", ns_dir / f"{key}.json"

    def get_or_compute(
        self,
        namespace: str,
        dimensions: Mapping[str, Any],
        inputs: Mapping[str, pd.DataFrame | str],
        compute: Callable[[], pd.DataFrame],
    ) -> CacheResult:
        started = time.perf_counter()
        digests = self.input_digests(inputs)
        key = self.make_key(namespace, dimensions, digests)
        payload_path, metadata_path = self._paths(namespace, key)
        recovered_corruption = False

        if payload_path.exists() and metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if (
                    metadata.get("key") != key
                    or metadata.get("cache_format_version") != CACHE_FORMAT_VERSION
                    or metadata.get("input_digests") != digests
                    or metadata.get("dimensions") != _normalize(dimensions)
                ):
                    raise ValueError("cache metadata mismatch")
                frame = pd.read_pickle(payload_path, compression="gzip")
                if not isinstance(frame, pd.DataFrame):
                    raise TypeError("cached payload is not a DataFrame")
                return CacheResult(
                    frame=frame,
                    status=CacheStatus(
                        hit=True,
                        key=key,
                        namespace=namespace,
                        payload_path=payload_path,
                        metadata_path=metadata_path,
                        elapsed_seconds=time.perf_counter() - started,
                    ),
                )
            except Exception:
                recovered_corruption = True
                payload_path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)

        frame = compute()
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("compute callback must return a pandas DataFrame")

        payload_path.parent.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        temp_payload = payload_path.with_name(f".{payload_path.name}.{token}.tmp")
        temp_metadata = metadata_path.with_name(f".{metadata_path.name}.{token}.tmp")
        metadata = {
            "cache_format_version": CACHE_FORMAT_VERSION,
            "key": key,
            "namespace": namespace,
            "dimensions": _normalize(dimensions),
            "input_digests": digests,
            "rows": len(frame),
            "columns": [str(c) for c in frame.columns],
            "created_unix": time.time(),
        }

        try:
            frame.to_pickle(temp_payload, compression="gzip", protocol=pickle.HIGHEST_PROTOCOL)
            temp_metadata.write_text(json.dumps(metadata, sort_keys=True, indent=2), encoding="utf-8")
            os.replace(temp_payload, payload_path)
            os.replace(temp_metadata, metadata_path)
        finally:
            temp_payload.unlink(missing_ok=True)
            temp_metadata.unlink(missing_ok=True)

        return CacheResult(
            frame=frame,
            status=CacheStatus(
                hit=False,
                key=key,
                namespace=namespace,
                payload_path=payload_path,
                metadata_path=metadata_path,
                elapsed_seconds=time.perf_counter() - started,
                recovered_corruption=recovered_corruption,
            ),
        )
