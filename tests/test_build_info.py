from importlib import import_module

import pytest


def _module():
    try:
        return import_module("bktstr.build_info")
    except ModuleNotFoundError:
        pytest.fail("bktstr.build_info is not implemented")


def test_runtime_build_info_uses_railway_git_metadata(monkeypatch):
    module = _module()
    monkeypatch.delenv("BKTSTR_GIT_COMMIT", raising=False)
    monkeypatch.delenv("BKTSTR_BUILD_TIME", raising=False)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123def456")
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "main")
    monkeypatch.setenv("RAILWAY_GIT_REPO_OWNER", "M00SEDR0iD")
    monkeypatch.setenv("RAILWAY_GIT_REPO_NAME", "bktstr")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "deploy-123")

    assert module.runtime_build_info() == {
        "git_commit": "abc123def456",
        "git_branch": "main",
        "git_repo": "M00SEDR0iD/bktstr",
        "deployment_id": "deploy-123",
        "build_time": None,
    }


def test_runtime_build_info_local_overrides_take_precedence(monkeypatch):
    module = _module()
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "railway-sha")
    monkeypatch.setenv("BKTSTR_GIT_COMMIT", "local-sha")
    monkeypatch.setenv("BKTSTR_BUILD_TIME", "2026-08-24T05:00:00Z")

    info = module.runtime_build_info()

    assert info["git_commit"] == "local-sha"
    assert info["build_time"] == "2026-08-24T05:00:00Z"


def test_runtime_build_info_is_null_safe(monkeypatch):
    module = _module()
    for name in [
        "BKTSTR_GIT_COMMIT",
        "BKTSTR_BUILD_TIME",
        "RAILWAY_GIT_COMMIT_SHA",
        "RAILWAY_GIT_BRANCH",
        "RAILWAY_GIT_REPO_OWNER",
        "RAILWAY_GIT_REPO_NAME",
        "RAILWAY_DEPLOYMENT_ID",
    ]:
        monkeypatch.delenv(name, raising=False)

    assert module.runtime_build_info() == {
        "git_commit": None,
        "git_branch": None,
        "git_repo": None,
        "deployment_id": None,
        "build_time": None,
    }
