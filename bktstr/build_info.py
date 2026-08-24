from __future__ import annotations

import os


def _value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def runtime_build_info() -> dict[str, str | None]:
    """Return deployment identity without making startup depend on metadata."""
    owner = _value("RAILWAY_GIT_REPO_OWNER")
    name = _value("RAILWAY_GIT_REPO_NAME")
    return {
        "git_commit": _value("BKTSTR_GIT_COMMIT") or _value("RAILWAY_GIT_COMMIT_SHA"),
        "git_branch": _value("RAILWAY_GIT_BRANCH"),
        "git_repo": f"{owner}/{name}" if owner and name else None,
        "deployment_id": _value("RAILWAY_DEPLOYMENT_ID"),
        "build_time": _value("BKTSTR_BUILD_TIME"),
    }
