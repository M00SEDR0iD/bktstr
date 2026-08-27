from importlib import import_module
import json
import math
import sys

import httpx
import pytest


AUTH = {"Authorization": "Bearer test-key"}
RESEARCH_PATHS = {
    "/api/v1/backtests",
    "/api/v1/parameter-sweeps",
    "/api/v1/compare",
    "/api/v1/regime-comparison",
    "/api/v1/experiments/{experiment_id}",
    "/api/v1/market-data",
}


def _module():
    try:
        return import_module("scripts.production_acceptance")
    except ModuleNotFoundError:
        pytest.fail("scripts.production_acceptance is not implemented")


def _completed_backtest(
    *, experiment_id: str = "exp_acceptance", status: str = "completed"
) -> dict:
    return {
        "experiment_id": experiment_id,
        "operation": "backtest",
        "status": status,
        "execution": "auto",
        "result": {
            "metrics": {"trade_count": 1},
            "trades": [],
            "configuration": {},
            "provenance": {},
        },
    }


def _transport(
    *,
    version: str = "0.6.0",
    health_commits: list[str] | None = None,
    backtest_status: str = "completed",
    include_comparison: bool = True,
    publish_openapi_contract: bool = True,
    comparison_headers: bool = True,
    comparison_statuses: list[str] | None = None,
):
    health_calls = 0
    backtest_calls = 0
    comparison_polls = 0
    commits = health_commits or ["test-commit"]
    statuses = comparison_statuses or ["completed"]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal health_calls, backtest_calls, comparison_polls
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
        if request.url.path == "/openapi.json":
            async_headers = (
                {"Location": {}, "Retry-After": {}}
                if publish_openapi_contract
                else {}
            )
            polling_headers = (
                {"Retry-After": {}} if publish_openapi_contract else {}
            )
            schemas = (
                {
                    "MarketCreate": {
                        "properties": {
                            "timeframe": {
                                "$ref": "#/components/schemas/MarketTimeframe"
                            },
                            "source": {"$ref": "#/components/schemas/MarketSource"},
                        }
                    },
                    "CompareExperimentResponse": {
                        "properties": {
                            "status_url": {"type": "string"},
                            "retry_after_seconds": {
                                "anyOf": [{"type": "integer"}, {"type": "null"}]
                            },
                        }
                    },
                }
                if publish_openapi_contract
                else {}
            )
            return httpx.Response(
                200,
                json={
                    "openapi": "3.1.0",
                    "paths": {
                        **{path: {} for path in RESEARCH_PATHS},
                        "/api/v1/compare": {
                            "post": {
                                "responses": {
                                    "200": {
                                        "headers": async_headers
                                    },
                                    "202": {
                                        "headers": async_headers
                                    },
                                }
                            }
                        },
                        "/api/v1/experiments/{experiment_id}": {
                            "get": {
                                "responses": {
                                    "200": {"headers": polling_headers}
                                }
                            }
                        },
                    },
                    "components": {"schemas": schemas},
                },
                request=request,
            )
        if request.headers.get("Authorization") != AUTH["Authorization"]:
            return httpx.Response(401, request=request)
        if request.url.path == "/api/v1/capabilities":
            return httpx.Response(
                200,
                json={
                    "version": version,
                    "api": {"authentication": {"scheme": "bearer", "header": "Authorization"}},
                },
                request=request,
            )
        if request.url.path == "/api/v1/backtests" and request.method == "POST":
            experiment_id = f"exp_acceptance_{backtest_calls + 1}"
            backtest_calls += 1
            return httpx.Response(
                200,
                json=_completed_backtest(
                    experiment_id=experiment_id, status=backtest_status
                ),
                request=request,
            )
        if include_comparison and request.url.path == "/api/v1/compare":
            assert request.method == "POST"
            assert json.loads(request.content) == {
                "candidates": ["exp_acceptance_1", "exp_acceptance_2"],
                "execution": "async",
            }
            return httpx.Response(
                202,
                headers=(
                    {
                        "Location": "/api/v1/experiments/exp_compare",
                        "Retry-After": "2",
                    }
                    if comparison_headers
                    else {}
                ),
                json={
                    "experiment_id": "exp_compare",
                    "operation": "compare",
                    "status": "queued",
                    "status_url": "/api/v1/experiments/exp_compare",
                    "retry_after_seconds": 2,
                    "result": None,
                    "error": None,
                },
                request=request,
            )
        if (
            include_comparison
            and request.url.path == "/api/v1/experiments/exp_compare"
        ):
            status = statuses[min(comparison_polls, len(statuses) - 1)]
            comparison_polls += 1
            terminal = status in {"completed", "failed"}
            return httpx.Response(
                200,
                headers=({"Retry-After": "2"} if not terminal else {}),
                json={
                    "experiment_id": "exp_compare",
                    "operation": "compare",
                    "status": status,
                    "status_url": "/api/v1/experiments/exp_compare",
                    "retry_after_seconds": None if terminal else 2,
                    "result": (
                        {
                            "candidates": [
                                {"name": "anchor"},
                                {"name": "changed"},
                            ]
                        }
                        if status == "completed"
                        else None
                    ),
                    "error": (
                        {"code": "operation_failed", "message": "safe failure"}
                        if status == "failed"
                        else None
                    ),
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    return httpx.MockTransport(handler)


def test_production_acceptance_uses_bearer_and_completed_backtest():
    # Break caught: acceptance could validate only unauthenticated discovery or a queued job.
    module = _module()
    report = module.run_acceptance(
        "https://bktstr.example", api_key="test-key", transport=_transport()
    )

    assert report["status"] == "pass"
    assert report["version"] == "0.6.0"
    assert report["backtest"] == {
        "experiment_id": "exp_acceptance_1",
        "status": "completed",
        "trade_count": 1,
    }


def test_production_acceptance_submits_and_polls_comparison():
    # Break caught: deployment acceptance could pass without exercising comparison serialization.
    sleeps = []
    report = _module().run_acceptance(
        "https://bktstr.example",
        api_key="test-key",
        sleeper=sleeps.append,
        transport=_transport(include_comparison=True),
    )

    assert report["comparison"] == {
        "experiment_id": "exp_compare",
        "status": "completed",
        "candidate_count": 2,
    }
    assert sleeps == [2]


def test_production_acceptance_rejects_missing_openapi_async_contract():
    # Break caught: deployed schemas could lose enum refs or polling fields and headers.
    module = _module()

    with pytest.raises(module.AcceptanceError, match="OpenAPI"):
        module.run_acceptance(
            "https://bktstr.example",
            api_key="test-key",
            transport=_transport(
                include_comparison=True, publish_openapi_contract=False
            ),
        )


def test_production_acceptance_requires_queued_response_headers():
    # Break caught: acceptance could trust polling body metadata while headers regress.
    module = _module()

    with pytest.raises(module.AcceptanceError, match="polling headers"):
        module.run_acceptance(
            "https://bktstr.example",
            api_key="test-key",
            transport=_transport(
                include_comparison=True, comparison_headers=False
            ),
        )


def test_production_acceptance_comparison_polling_has_finite_deadline():
    # Break caught: a permanently nonterminal deployment could hang release acceptance.
    module = _module()
    sleeps = []

    with pytest.raises(module.AcceptanceError, match="timed out"):
        module.run_acceptance(
            "https://bktstr.example",
            api_key="test-key",
            sleeper=sleeps.append,
            timeout_seconds=3,
            transport=_transport(
                include_comparison=True,
                comparison_statuses=["running", "failed"],
            ),
        )

    assert sleeps == [2]


def test_run_acceptance_requires_bearer_key():
    module = _module()

    with pytest.raises(module.AcceptanceError, match="BKTSTR_API_KEY"):
        module.run_acceptance("https://bktstr.example", transport=_transport())


def test_run_acceptance_rejects_queued_backtest():
    module = _module()

    with pytest.raises(module.AcceptanceError, match="did not complete inline"):
        module.run_acceptance(
            "https://bktstr.example",
            api_key="test-key",
            transport=_transport(backtest_status="queued"),
        )


def test_run_acceptance_rejects_wrong_version():
    module = _module()

    with pytest.raises(module.AcceptanceError, match="expected version 0.6.0"):
        module.run_acceptance(
            "https://bktstr.example", api_key="test-key", transport=_transport(version="0.5.0")
        )


def test_run_acceptance_requires_expected_deployment_commit():
    module = _module()
    report = module.run_acceptance(
        "https://bktstr.example",
        api_key="test-key",
        expected_commit="new-commit",
        deployment_attempts=2,
        deployment_poll_seconds=0,
        sleeper=lambda _: None,
        transport=_transport(health_commits=["old-commit", "new-commit"]),
    )

    assert report["git_commit"] == "new-commit"


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
            json={"version": "0.6.0", "git_commit": "old-commit"},
            request=request,
        )

    with pytest.raises(module.AcceptanceError) as error:
        module.run_acceptance(
            "https://bktstr.example",
            api_key="test-key",
            expected_commit="new-commit",
            deployment_attempts=2,
            deployment_poll_seconds=0,
            sleeper=lambda _: None,
            transport=httpx.MockTransport(handler),
        )

    message = str(error.value)
    assert "expected version 0.6.0" in message
    assert "expected commit new-commit" in message
    assert "observed version 0.6.0" in message
    assert "observed commit old-commit" in message
    assert "503 Service Unavailable" in message


@pytest.mark.parametrize(
    ("options", "field"),
    [
        ({"deployment_attempts": 0}, "deployment_attempts"),
        ({"deployment_attempts": -1}, "deployment_attempts"),
        ({"deployment_attempts": 1.5}, "deployment_attempts"),
        ({"deployment_poll_seconds": -1}, "deployment_poll_seconds"),
        ({"deployment_poll_seconds": math.nan}, "deployment_poll_seconds"),
    ],
)
def test_run_acceptance_rejects_invalid_deployment_timing(options, field):
    module = _module()

    with pytest.raises(module.AcceptanceError, match=field):
        module.run_acceptance(
            "https://bktstr.example", api_key="test-key", transport=_transport(), **options
        )


def test_main_reads_bearer_key_from_environment(monkeypatch, tmp_path, capsys):
    module = _module()
    output_path = tmp_path / "acceptance.json"

    def run_acceptance(base_url, expected_version, **options):
        assert base_url == "https://bktstr.example"
        assert expected_version == "0.6.0"
        assert options["api_key"] == "test-key"
        assert options["expected_commit"] == "new-commit"
        return {"status": "pass", "git_commit": options["expected_commit"]}

    monkeypatch.setattr(module, "run_acceptance", run_acceptance)
    monkeypatch.setenv("BKTSTR_API_KEY", "test-key")
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

    assert module.main() == 0
    written = output_path.read_text(encoding="utf-8")
    assert written == capsys.readouterr().out
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
            "--api-key",
            "test-key",
            "--expected-commit",
            "new-commit",
            "--output",
            str(output_path),
        ],
    )

    assert module.main() == 1
    written = output_path.read_text(encoding="utf-8")
    assert written == capsys.readouterr().out
    assert json.loads(written) == {
        "status": "fail",
        "error": "expected commit new-commit, got old-commit",
    }
