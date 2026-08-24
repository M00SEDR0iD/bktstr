from importlib import import_module
import json
import sys

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


def _transport(
    *,
    version: str = "0.3.5",
    health_commits: list[str] | None = None,
    second_hits: bool = True,
    second_pnl: float = 42.604714,
):
    backtest_calls = 0
    health_calls = 0
    commits = health_commits or ["test-commit"]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal backtest_calls, health_calls
        if request.url.path == "/health":
            commit = commits[min(health_calls, len(commits) - 1)]
            health_calls += 1
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "service": "bktstr",
                    "version": version,
                    "git_commit": commit,
                },
                request=request,
            )
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


def test_run_acceptance_requires_expected_deployment_commit():
    module = _module()
    report = module.run_acceptance(
        "https://bktstr.example",
        expected_commit="new-commit",
        deployment_attempts=2,
        deployment_poll_seconds=0,
        sleeper=lambda _: None,
        transport=_transport(health_commits=["old-commit", "new-commit"]),
    )
    assert report["git_commit"] == "new-commit"


def test_run_acceptance_rejects_commit_that_never_deploys():
    module = _module()
    with pytest.raises(module.AcceptanceError, match="expected commit new-commit"):
        module.run_acceptance(
            "https://bktstr.example",
            expected_commit="new-commit",
            deployment_attempts=2,
            deployment_poll_seconds=0,
            sleeper=lambda _: None,
            transport=_transport(health_commits=["old-commit"]),
        )


def test_run_acceptance_sleeps_only_between_deployment_attempts():
    module = _module()
    sleeps = []

    report = module.run_acceptance(
        "https://bktstr.example",
        expected_commit="new-commit",
        deployment_attempts=3,
        deployment_poll_seconds=7,
        sleeper=sleeps.append,
        transport=_transport(health_commits=["old-commit", "old-commit", "new-commit"]),
    )

    assert report["git_commit"] == "new-commit"
    assert sleeps == [7, 7]


def test_run_acceptance_exhaustion_reports_last_identity_and_http_error():
    module = _module()
    health_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal health_calls
        health_calls += 1
        if health_calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            json={"version": "0.3.5", "git_commit": "old-commit"},
            request=request,
        )

    with pytest.raises(module.AcceptanceError) as error:
        module.run_acceptance(
            "https://bktstr.example",
            expected_commit="new-commit",
            deployment_attempts=2,
            deployment_poll_seconds=0,
            sleeper=lambda _: None,
            transport=httpx.MockTransport(handler),
        )

    message = str(error.value)
    assert "expected version 0.3.5" in message
    assert "expected commit new-commit" in message
    assert "observed version 0.3.5" in message
    assert "observed commit old-commit" in message
    assert "503 Service Unavailable" in message


def test_main_writes_success_report_for_expected_commit(monkeypatch, tmp_path, capsys):
    module = _module()
    output_path = tmp_path / "acceptance.json"

    def run_acceptance(base_url, expected_version, **options):
        assert base_url == "https://bktstr.example"
        assert expected_version == "0.3.5"
        assert options["expected_commit"] == "new-commit"
        assert options["deployment_attempts"] == 3
        assert options["deployment_poll_seconds"] == 10
        return {"status": "pass", "git_commit": options["expected_commit"]}

    monkeypatch.setattr(module, "run_acceptance", run_acceptance)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "production_acceptance.py",
            "--base-url",
            "https://bktstr.example",
            "--expected-commit",
            "new-commit",
            "--deployment-wait-seconds",
            "20",
            "--output",
            str(output_path),
        ],
    )

    assert module.main() == 0
    written = output_path.read_text(encoding="utf-8")
    assert written == capsys.readouterr().out
    assert written.endswith("\n")
    assert json.loads(written) == {"status": "pass", "git_commit": "new-commit"}


def test_main_writes_failure_report(monkeypatch, tmp_path, capsys):
    module = _module()
    output_path = tmp_path / "acceptance.json"

    def reject_deployment(*args, **kwargs):
        raise module.AcceptanceError("expected commit new-commit, got old-commit")

    monkeypatch.setattr(module, "run_acceptance", reject_deployment)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "production_acceptance.py",
            "--base-url",
            "https://bktstr.example",
            "--expected-commit",
            "new-commit",
            "--output",
            str(output_path),
        ],
    )

    assert module.main() == 1
    written = output_path.read_text(encoding="utf-8")
    assert written == capsys.readouterr().out
    assert written.endswith("\n")
    assert json.loads(written) == {
        "status": "fail",
        "error": "expected commit new-commit, got old-commit",
    }
