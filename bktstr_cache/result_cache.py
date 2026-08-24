from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .derived import canonical_json, default_cache_root

RESULT_CACHE_FORMAT_VERSION = "json-result-cache-v1"


@dataclass(frozen=True)
class JsonCacheStatus:
    hit: bool
    key: str
    payload_path: Path
    elapsed_seconds: float
    recovered_corruption: bool = False


@dataclass(frozen=True)
class JsonCacheResult:
    value: Any
    status: JsonCacheStatus


class JsonResultCache:
    """Optional exact-result memoization for JSON-serializable backtest results."""

    def __init__(self, root: str | Path | None = None):
        base = Path(root) if root is not None else default_cache_root()
        self.root = base / "exact-results"

    @staticmethod
    def make_key(dimensions: Mapping[str, Any]) -> str:
        material = {
            "cache_format_version": RESULT_CACHE_FORMAT_VERSION,
            "dimensions": dimensions,
        }
        return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()

    def get_or_compute(self, dimensions: Mapping[str, Any], compute: Callable[[], Any]) -> JsonCacheResult:
        started = time.perf_counter()
        key = self.make_key(dimensions)
        payload_path = self.root / key[:2] / f"{key}.json.gz"
        recovered_corruption = False

        if payload_path.exists():
            try:
                with gzip.open(payload_path, "rt", encoding="utf-8") as handle:
                    envelope = json.load(handle)
                if envelope.get("key") != key or envelope.get("cache_format_version") != RESULT_CACHE_FORMAT_VERSION:
                    raise ValueError("result cache metadata mismatch")
                return JsonCacheResult(
                    value=envelope["value"],
                    status=JsonCacheStatus(
                        hit=True,
                        key=key,
                        payload_path=payload_path,
                        elapsed_seconds=time.perf_counter() - started,
                    ),
                )
            except Exception:
                recovered_corruption = True
                payload_path.unlink(missing_ok=True)

        value = compute()
        envelope = {
            "cache_format_version": RESULT_CACHE_FORMAT_VERSION,
            "key": key,
            "dimensions": dimensions,
            "value": value,
            "created_unix": time.time(),
        }
        # Validate JSON serializability before touching the cache.
        serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":"))

        payload_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = payload_path.with_name(f".{payload_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with gzip.open(temp_path, "wt", encoding="utf-8") as handle:
                handle.write(serialized)
            os.replace(temp_path, payload_path)
        finally:
            temp_path.unlink(missing_ok=True)

        return JsonCacheResult(
            value=value,
            status=JsonCacheStatus(
                hit=False,
                key=key,
                payload_path=payload_path,
                elapsed_seconds=time.perf_counter() - started,
                recovered_corruption=recovered_corruption,
            ),
        )
