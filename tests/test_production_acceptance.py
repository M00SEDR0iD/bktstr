from importlib import import_module
import json

import httpx
import pytest


def _module():
    try:
        return import_module("scripts.production_acceptance")
    except ModuleNotFoundError:
        pytest.fail("scripts.production_acceptance is not implemented")


def _anchor_result(*, hits: bool, pnl: float = 42.604714) -> dict:
    return {
        "request": {"symbol": "NVDA", "side": "short"},
        "data": {
            "derived_cache": {
                "enabled": True,
                "intraday": {"hit": hits, "elapsed_seconds": 0.01, "recovered_corruption": False},
                "regime": {"hit": hits, "elapsed_seconds": 0.001, "recovered_corruption": False},
                "sentiment": {"hit": hits, "elapsed_seconds": 0.002, "recovered_corruption": False},
            },
            "sentiment": {
                "provenance": {
                    "profile": "clean",
                    "non_clean_data_used": False,
                    "all_point_in_time_safe": True,
                }
            },
        },
        "summary": {
            "trades": 7,
            "wins": 6,
            "losses": 1,
            "total_pnl_dollars": pnl,
            "expected_pnl_per_trade": 6.086388,
        },
        "trades": [
            {"entry_time": "2026-06-16T15:09:00-04:00", "pnl_dollars": 7.543021},
            {"entry_time": "2026-06-17T14:01:00-04:00", "pnl_dollars": 9.5951},
        ],
        "trades_total": 7,
        "trades_returned": 7,
        "trades_truncated": False,
    }


def _transport(*, version: str = "0.3.5", second_hits: bool = True, second_pnl: float = 42.604714):
    backtest_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal backtest_calls
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "service": "bktstr", "version": version}, request=request)
        if request.url.path == "/api/v1/capabilities":
            return httpx.Response(
                200,
                json={
                    "version": version,
                    "cache": {
                        "derived": {
                            "namespaces": ["intraday_features", "daily_regime", "daily_sentiment"],
                            "strategy_decisions_cached": False,
                        }
                    },
                },
                request=request,
            )
        if request.url.path == "/api/v1/backtest":
            backtest_calls += 1
            payload = _anchor_result(
                hits=(second_hits if backtest_calls == 2 else False),
                pnl=(second_pnl if backtest_calls == 2 else 42.604714),
            )
            return httpx.Response(200, json=payload, request=request)
        return httpx.Response(404, request=request)

    return httpx.MockTransport(handler)


def test_run_acceptance_validates_anchor_and_second_run_hits():
    module = _module()
    report = module.run_acceptance("https://bktstr.example", transport=_transport())

    assert report["status"] == "pass"
    assert report["version"] == "0.3.5"
    assert report["anchor"]["trades"] == 7
    assert report["second_run_derived_hits"] == {
        "intraday": True,
        "regime": True,
        "sentiment": True,
    }


def test_run_acceptance_rejects_trade_output_drift():
    module = _module()
    with pytest.raises(module.AcceptanceError, match="trading output changed"):
        module.run_acceptance("https://bktstr.example", transport=_transport(second_pnl=41.0))


def test_run_acceptance_requires_second_run_derived_hits():
    module = _module()
    with pytest.raises(module.AcceptanceError, match="derived cache miss"):
        module.run_acceptance("https://bktstr.example", transport=_transport(second_hits=False))


def test_run_acceptance_rejects_wrong_version():
    module = _module()
    with pytest.raises(module.AcceptanceError, match="expected version 0.3.5"):
        module.run_acceptance("https://bktstr.example", transport=_transport(version="0.3.4"))
