from __future__ import annotations

from pathlib import Path

from bktstr_cache.result_cache import JsonResultCache


def test_json_result_cache_hits_on_identical_dimensions(tmp_path: Path):
    cache = JsonResultCache(tmp_path)
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"summary": {"trades": 7, "ev": 6.086388}}

    dims = {"engine_version": "0.3.3", "symbol": "NVDA", "entry": ["vwap", "rsi", "volume"]}
    first = cache.get_or_compute(dims, compute)
    second = cache.get_or_compute(dims, compute)

    assert first.status.hit is False
    assert second.status.hit is True
    assert calls == 1
    assert second.value["summary"]["trades"] == 7


def test_json_result_cache_invalidates_when_request_changes(tmp_path: Path):
    cache = JsonResultCache(tmp_path)
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"calls": calls}

    a = cache.get_or_compute({"symbol": "NVDA", "stop_pct": 1}, compute)
    b = cache.get_or_compute({"symbol": "NVDA", "stop_pct": 2}, compute)

    assert calls == 2
    assert a.status.key != b.status.key


def test_json_result_cache_recovers_from_corruption(tmp_path: Path):
    cache = JsonResultCache(tmp_path)
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"ok": True, "call": calls}

    first = cache.get_or_compute({"symbol": "NVDA"}, compute)
    first.status.payload_path.write_bytes(b"bad-gzip")
    second = cache.get_or_compute({"symbol": "NVDA"}, compute)

    assert calls == 2
    assert second.status.hit is False
    assert second.status.recovered_corruption is True
    assert second.value["call"] == 2
