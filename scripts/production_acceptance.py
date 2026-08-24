from __future__ import annotations

import argparse
import json
import math
from typing import Any

import httpx


ANCHOR_PARAMS = {
    "symbol": "NVDA",
    "start": "2026-06-01",
    "end": "2026-08-21",
    "timeframe": "1m",
    "side": "short",
    "entry": "close.cross_below:vwap,rsi14.lt:50,volume_ratio20.gt:1.1",
    "regime": "day_sma20_slope5.lt:0,relative_return20.lt:0",
    "benchmark": "SOXX",
    "sentiment": "true",
    "sentiment_sector_benchmark": "SOXX",
    "sentiment_market_benchmark": "QQQ",
    "sentiment_data_profile": "clean",
    "sentiment_sources": "price",
    "stop_pct": "1",
    "target_pct": "3",
    "max_hold_minutes": "240",
    "position_size": "1000",
    "starting_capital": "10000",
    "slippage_bps": "2",
    "entry_start_time": "12:30",
    "entry_end_time": "16:00",
    "trade_limit": "1000",
}

EXPECTED_ANCHOR = {
    "trades": 7,
    "wins": 6,
    "losses": 1,
    "total_pnl_dollars": 42.604714,
    "expected_pnl_per_trade": 6.086388,
}

DERIVED_NAMESPACES = {"intraday", "regime", "sentiment"}
CAPABILITY_NAMESPACES = {"intraday_features", "daily_regime", "daily_sentiment"}


class AcceptanceError(RuntimeError):
    pass


def _get_json(client: httpx.Client, path: str, *, params: dict[str, str] | None = None) -> dict:
    response = client.get(path, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise AcceptanceError(f"{path} did not return a JSON object")
    return payload


def _canonical_trading_output(result: dict) -> dict:
    sentiment = (result.get("data") or {}).get("sentiment") or {}
    return {
        "request": result.get("request"),
        "summary": result.get("summary"),
        "trades": result.get("trades"),
        "trades_total": result.get("trades_total"),
        "trades_returned": result.get("trades_returned"),
        "trades_truncated": result.get("trades_truncated"),
        "provenance": sentiment.get("provenance"),
    }


def _validate_anchor(summary: dict) -> None:
    for field in ("trades", "wins", "losses"):
        if summary.get(field) != EXPECTED_ANCHOR[field]:
            raise AcceptanceError(
                f"anchor {field} drifted: expected {EXPECTED_ANCHOR[field]!r}, got {summary.get(field)!r}"
            )
    for field in ("total_pnl_dollars", "expected_pnl_per_trade"):
        value = summary.get(field)
        if not isinstance(value, (int, float)) or not math.isclose(
            float(value), float(EXPECTED_ANCHOR[field]), rel_tol=0.0, abs_tol=1e-9
        ):
            raise AcceptanceError(
                f"anchor {field} drifted: expected {EXPECTED_ANCHOR[field]!r}, got {value!r}"
            )


def _second_run_hits(result: dict) -> dict[str, bool]:
    derived = (result.get("data") or {}).get("derived_cache") or {}
    if derived.get("enabled") is not True:
        raise AcceptanceError("derived cache is not enabled")
    hits = {
        name: bool((derived.get(name) or {}).get("hit"))
        for name in sorted(DERIVED_NAMESPACES)
    }
    missing = [name for name, hit in hits.items() if not hit]
    if missing:
        raise AcceptanceError(f"derived cache miss on second run: {', '.join(missing)}")
    return hits


def run_acceptance(
    base_url: str,
    expected_version: str = "0.3.5",
    *,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    with httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=timeout_seconds,
        follow_redirects=True,
        transport=transport,
    ) as client:
        health = _get_json(client, "/health")
        version = health.get("version")
        if version != expected_version:
            raise AcceptanceError(f"expected version {expected_version}, got {version}")

        capabilities = _get_json(client, "/api/v1/capabilities")
        if capabilities.get("version") != expected_version:
            raise AcceptanceError("capabilities version does not match health")
        derived_contract = ((capabilities.get("cache") or {}).get("derived") or {})
        namespaces = set(derived_contract.get("namespaces") or [])
        if not CAPABILITY_NAMESPACES.issubset(namespaces):
            raise AcceptanceError("capabilities are missing derived-cache namespaces")
        if derived_contract.get("strategy_decisions_cached") is not False:
            raise AcceptanceError("strategy decisions must not be cached")

        first = _get_json(client, "/api/v1/backtest", params=ANCHOR_PARAMS)
        second = _get_json(client, "/api/v1/backtest", params=ANCHOR_PARAMS)

    if _canonical_trading_output(first) != _canonical_trading_output(second):
        raise AcceptanceError("trading output changed between identical runs")

    summary = second.get("summary") or {}
    _validate_anchor(summary)
    hits = _second_run_hits(second)
    return {
        "status": "pass",
        "version": expected_version,
        "git_commit": health.get("git_commit"),
        "anchor": {key: summary.get(key) for key in EXPECTED_ANCHOR},
        "second_run_derived_hits": hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a deployed BKTSTR release against the locked NVDA anchor.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", default="0.3.5")
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    args = parser.parse_args()
    try:
        report = run_acceptance(
            args.base_url,
            expected_version=args.expected_version,
            timeout_seconds=args.timeout_seconds,
        )
    except (AcceptanceError, httpx.HTTPError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
