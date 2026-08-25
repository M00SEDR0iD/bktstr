from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import httpx


ANCHOR_REQUEST = {
    "strategy": {
        "id": "bktstr.bearish-regime-scalp",
        "version": "1.0.0",
        "parameters": {"stop_pct": 1.0, "target_pct": 3.0},
    },
    "market": {
        "symbol": "NVDA",
        "start": "2026-08-17",
        "end": "2026-08-17",
        "timeframe": "1m",
        "source": "auto",
    },
    "side": "short",
    "entry": "close.cross_below:vwap",
    "regime": None,
    "execution": "auto",
    "include_trades": True,
}

RESEARCH_PATHS = {
    "/api/v1/backtests",
    "/api/v1/parameter-sweeps",
    "/api/v1/compare",
    "/api/v1/regime-comparison",
    "/api/v1/experiments/{experiment_id}",
    "/api/v1/market-data",
}


class AcceptanceError(RuntimeError):
    pass


def _deployment_attempts(wait_seconds: float, poll_seconds: float) -> int:
    if not math.isfinite(wait_seconds) or wait_seconds < 0:
        raise AcceptanceError("--deployment-wait-seconds must be finite and >= 0")
    if not math.isfinite(poll_seconds) or poll_seconds <= 0:
        raise AcceptanceError("--deployment-poll-seconds must be finite and > 0")
    if wait_seconds == 0:
        return 1
    return math.ceil(wait_seconds / poll_seconds) + 1


def _get_json(client: httpx.Client, path: str, *, params: dict[str, str] | None = None) -> dict:
    response = client.get(path, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise AcceptanceError(f"{path} did not return a JSON object")
    return payload


def _post_json(client: httpx.Client, path: str, body: dict) -> dict:
    response = client.post(path, json=body)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise AcceptanceError(f"{path} did not return a JSON object")
    return payload


def _wait_for_deployment(
    client: httpx.Client,
    expected_version: str,
    expected_commit: str | None,
    deployment_attempts: int,
    deployment_poll_seconds: float,
    sleeper,
) -> dict:
    last_version = None
    last_commit = None
    last_http_error = None

    for attempt in range(deployment_attempts):
        try:
            health = _get_json(client, "/health")
        except httpx.HTTPError as exc:
            last_http_error = str(exc)
        else:
            last_version = health.get("version")
            last_commit = health.get("git_commit")
            if last_version == expected_version and (
                expected_commit is None or last_commit == expected_commit
            ):
                return health

        if attempt + 1 < deployment_attempts:
            sleeper(deployment_poll_seconds)

    expected_identity = f"expected version {expected_version}"
    if expected_commit is not None:
        expected_identity += f" and expected commit {expected_commit}"
    message = (
        f"{expected_identity}; observed version {last_version}, "
        f"observed commit {last_commit}"
    )
    if last_http_error is not None:
        message += f"; last HTTP error: {last_http_error}"
    raise AcceptanceError(message)


def run_acceptance(
    base_url: str,
    expected_version: str = "0.6.0",
    *,
    api_key: str | None = None,
    expected_commit: str | None = None,
    deployment_attempts: int = 1,
    deployment_poll_seconds: float = 10.0,
    sleeper=time.sleep,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 300.0,
) -> dict[str, Any]:
    if not isinstance(api_key, str) or not api_key:
        raise AcceptanceError("a non-empty BKTSTR_API_KEY is required")
    if (
        isinstance(deployment_attempts, bool)
        or not isinstance(deployment_attempts, int)
        or deployment_attempts < 1
    ):
        raise AcceptanceError("deployment_attempts must be an integer >= 1")
    if (
        isinstance(deployment_poll_seconds, bool)
        or not isinstance(deployment_poll_seconds, (int, float))
        or not math.isfinite(deployment_poll_seconds)
        or deployment_poll_seconds < 0
    ):
        raise AcceptanceError("deployment_poll_seconds must be finite and >= 0")

    with httpx.Client(
        base_url=base_url.rstrip("/"),
        timeout=timeout_seconds,
        follow_redirects=True,
        transport=transport,
        headers={"Authorization": f"Bearer {api_key}"},
    ) as client:
        health = _wait_for_deployment(
            client,
            expected_version,
            expected_commit,
            deployment_attempts,
            deployment_poll_seconds,
            sleeper,
        )

        schema = _get_json(client, "/openapi.json")
        if not schema.get("openapi") or not RESEARCH_PATHS.issubset(set(schema.get("paths") or [])):
            raise AcceptanceError("OpenAPI is missing the v0.6 research contract")

        capabilities = _get_json(client, "/api/v1/capabilities")
        if capabilities.get("version") != expected_version:
            raise AcceptanceError("capabilities version does not match health")
        authentication = ((capabilities.get("api") or {}).get("authentication") or {})
        if authentication != {"scheme": "bearer", "header": "Authorization"}:
            raise AcceptanceError("capabilities do not publish bearer authentication")

        backtest = _post_json(client, "/api/v1/backtests", ANCHOR_REQUEST)

    if backtest.get("operation") != "backtest" or backtest.get("status") != "completed":
        raise AcceptanceError("bounded v0.6 backtest did not complete inline")
    if not isinstance(backtest.get("experiment_id"), str) or not backtest["experiment_id"]:
        raise AcceptanceError("completed backtest is missing an experiment_id")
    result = backtest.get("result")
    if not isinstance(result, dict) or not {"metrics", "trades", "configuration", "provenance"} <= set(result):
        raise AcceptanceError("completed backtest is missing reproducible research output")

    return {
        "status": "pass",
        "version": expected_version,
        "git_commit": health.get("git_commit"),
        "backtest": {
            "experiment_id": backtest["experiment_id"],
            "status": backtest["status"],
            "trade_count": result["metrics"].get("trade_count"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a deployed BKTSTR release against the locked NVDA anchor.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", default="0.6.0")
    parser.add_argument("--api-key", default=os.getenv("BKTSTR_API_KEY"))
    parser.add_argument("--expected-commit")
    parser.add_argument("--deployment-wait-seconds", type=float, default=0)
    parser.add_argument("--deployment-poll-seconds", type=float, default=10)
    parser.add_argument("--output")
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    args = parser.parse_args()
    try:
        deployment_attempts = _deployment_attempts(
            args.deployment_wait_seconds,
            args.deployment_poll_seconds,
        )
        report = run_acceptance(
            args.base_url,
            expected_version=args.expected_version,
            api_key=args.api_key,
            expected_commit=args.expected_commit,
            deployment_attempts=deployment_attempts,
            deployment_poll_seconds=args.deployment_poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
    except (AcceptanceError, httpx.HTTPError) as exc:
        report = {"status": "fail", "error": str(exc)}
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
        print(rendered, end="")
        if args.output:
            Path(args.output).write_text(rendered, encoding="utf-8")
        return 1
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
