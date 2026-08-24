from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]


def _top_level_block(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if line == f"{key}:"]
    assert len(matches) == 1, f"expected one top-level {key!r} block"

    block: list[str] = []
    for line in lines[matches[0] + 1 :]:
        if line and not line.startswith((" ", "\t")):
            break
        block.append(line)
    return block


def _mapping_blocks(lines: list[str], indentation: int) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    prefix = " " * indentation

    for line in lines:
        if not line:
            continue
        if line.startswith(prefix) and not line.startswith(prefix + " "):
            key, separator, value = line.strip().partition(":")
            assert separator and not value, f"expected mapping block, got {line!r}"
            assert key not in blocks, f"duplicate mapping key {key!r}"
            blocks[key] = []
            current = key
        elif current is not None:
            blocks[current].append(line)
    return blocks


def _scalar_mapping(lines: list[str], indentation: int) -> dict[str, str]:
    values: dict[str, str] = {}
    prefix = " " * indentation
    for line in lines:
        if not line:
            continue
        assert line.startswith(prefix) and not line.startswith(prefix + " "), (
            f"expected scalar mapping at indentation {indentation}, got {line!r}"
        )
        key, separator, value = line.strip().partition(":")
        assert separator and value.strip(), f"expected scalar mapping, got {line!r}"
        assert key not in values, f"duplicate mapping key {key!r}"
        values[key] = value.strip()
    return values


def _job_name(lines: list[str]) -> str:
    names = [line.removeprefix("    name: ") for line in lines if line.startswith("    name: ")]
    assert len(names) == 1, "each job must define exactly one name"
    return names[0]


def _job_scalar(lines: list[str], key: str) -> str:
    prefix = f"    {key}: "
    values = [line.removeprefix(prefix) for line in lines if line.startswith(prefix)]
    assert len(values) == 1, f"each job must define exactly one {key!r} value"
    return values[0]


def _job_steps(lines: list[str]) -> list[str]:
    indices = [index for index, line in enumerate(lines) if line == "    steps:"]
    assert len(indices) == 1, "each job must define exactly one steps container"

    steps: list[str] = []
    for line in lines[indices[0] + 1 :]:
        if line.startswith("    ") and not line.startswith("      "):
            break
        steps.append(line)
    assert any(line.startswith("      - ") for line in steps), "steps must contain workflow steps"
    return steps


def _named_step(lines: list[str], name: str) -> list[str]:
    step_header = f"      - name: {name}"
    indices = [index for index, line in enumerate(lines) if line == step_header]
    assert len(indices) == 1, f"expected one {name!r} step"

    step: list[str] = []
    for line in lines[indices[0] :]:
        if step and line.startswith("      - "):
            break
        step.append(line)
    return step


def _step_values(lines: list[str], key: str) -> list[str]:
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        for prefix in (f"- {key}: ", f"{key}: "):
            if stripped.startswith(prefix):
                value = stripped.removeprefix(prefix)
                if value != "|":
                    values.append(value)
                break
    return values


def _assert_ci_workflow_contract(text: str) -> None:
    triggers = _mapping_blocks(_top_level_block(text, "on"), 2)
    assert triggers == {
        "push": ["    branches: [main]"],
        "pull_request": [],
        "workflow_dispatch": [],
    }

    assert _scalar_mapping(_top_level_block(text, "permissions"), 2) == {"contents": "read"}
    assert "secrets." not in text

    expected_jobs = {
        "hygiene": {
            "name": "Hygiene",
            "actions": ["actions/checkout@v7"],
            "commands": [],
            "body": ["git ls-files", "__pycache__"],
        },
        "tests": {
            "name": "Tests",
            "actions": ["actions/checkout@v7", "actions/setup-python@v7"],
            "commands": ["python -m pip install -r requirements-dev.txt", "python -m pytest -q"],
            "body": ["python-version: '3.12'", "cache: pip", "cache-dependency-path: requirements-dev.txt"],
        },
        "compile": {
            "name": "Compile",
            "actions": ["actions/checkout@v7", "actions/setup-python@v7"],
            "commands": ["python -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests"],
            "body": ["python-version: '3.12'"],
        },
        "production_image": {
            "name": "Production image",
            "actions": ["actions/checkout@v7"],
            "commands": ["docker build --tag bktstr:${{ github.sha }} ."],
            "body": [],
        },
        "documentation": {
            "name": "Documentation",
            "actions": ["actions/checkout@v7", "actions/setup-python@v7"],
            "commands": ["python -m pip install -r requirements-dev.txt", "python scripts/check_release_consistency.py"],
            "body": ["python-version: '3.12'", "cache: pip", "cache-dependency-path: requirements-dev.txt"],
        },
        "cache_benchmark": {
            "name": "Cache benchmark",
            "actions": ["actions/checkout@v7", "actions/setup-python@v7"],
            "commands": ["python -m pip install -r requirements-dev.txt", "python benchmarks/benchmark_cache.py"],
            "body": ["python-version: '3.12'", "cache: pip", "cache-dependency-path: requirements-dev.txt"],
        },
    }
    jobs = _mapping_blocks(_top_level_block(text, "jobs"), 2)
    assert set(jobs) == set(expected_jobs)

    for key, expected in expected_jobs.items():
        job = jobs[key]
        assert _job_name(job) == expected["name"]
        assert _job_scalar(job, "runs-on") == "ubuntu-latest"
        assert not any(line.startswith("    needs:") for line in job)
        steps = _job_steps(job)
        assert _step_values(steps, "uses") == expected["actions"]
        assert _step_values(steps, "run") == expected["commands"]
        for required in expected["body"]:
            assert required in "\n".join(steps)

    assert _named_step(_job_steps(jobs["hygiene"]), "Reject tracked generated files") == [
        "      - name: Reject tracked generated files",
        "        shell: bash",
        "        run: |",
        "          bad=\"$(git ls-files | grep -E '(^|/)(__pycache__|\\.pytest_cache)(/|$)|\\.py[co]$' || true)\"",
        "          if [ -n \"$bad\" ]; then",
        "            echo \"Generated files are tracked and must be removed:\"",
        "            echo \"$bad\"",
        "            exit 1",
        "          fi",
    ]


def test_ci_workflow_runs_full_release_checks():
    path = ROOT / ".github" / "workflows" / "ci.yml"
    assert path.exists(), "CI workflow is missing"
    _assert_ci_workflow_contract(path.read_text(encoding="utf-8"))


def test_ci_workflow_contract_rejects_semantic_mutations():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    swapped_commands = text.replace("python -m pytest -q", "__test_command__", 1)
    swapped_commands = swapped_commands.replace(
        "python scripts/check_release_consistency.py", "python -m pytest -q", 1
    )
    swapped_commands = swapped_commands.replace(
        "__test_command__", "python scripts/check_release_consistency.py", 1
    )
    mutations = {
        "a non-main push trigger": text.replace("branches: [main]", "branches: [release]", 1),
        "a write permission": text.replace("contents: read", "contents: write", 1),
        "commands assigned to the wrong jobs": swapped_commands,
        "a job dependency": text.replace("name: Tests\n", "name: Tests\n    needs: hygiene\n", 1),
        "a Windows runner": text.replace("runs-on: ubuntu-latest", "runs-on: windows-latest", 1),
        "a renamed steps container": text.replace("    steps:", "    x-steps:", 1),
        "a weakened hygiene regex": text.replace(r"\.py[co]$", r"\.py$", 1),
    }

    for mutation in mutations.values():
        with pytest.raises(AssertionError):
            _assert_ci_workflow_contract(mutation)


def test_ci_is_read_only_by_default():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "contents: read" in text
    assert "secrets." not in text


def test_supabase_github_bridge_assets_are_present_and_safe():
    sql_path = ROOT / "ops" / "supabase" / "github_bridge.sql"
    runbook_path = ROOT / "ops" / "supabase" / "GITHUB_BRIDGE.md"
    assert sql_path.exists(), "Supabase GitHub bridge migration is missing"
    assert runbook_path.exists(), "Supabase GitHub bridge runbook is missing"

    sql = sql_path.read_text(encoding="utf-8")
    for required in [
        "bktstr_repo_snapshots",
        "bktstr_repo_blob_requests",
        "bktstr_repo_files",
        "bktstr_github_enqueue_commit",
        "bktstr_github_enqueue_tree",
        "bktstr_github_enqueue_blobs",
        "bktstr_github_collect_blobs",
        "https://api.github.com/repos/",
        "https://raw.githubusercontent.com/",
        "__pycache__",
        r"\.py[co]$",
        "net.http_get",
        "bktstr_repo_fetch_staging",
    ]:
        assert required in sql
    for forbidden in ["github_pat_", "ghp_", "service_role", "MASSIVE_API_KEY"]:
        assert forbidden not in sql


def test_supabase_bridge_runbook_documents_four_phase_recovery():
    text = (ROOT / "ops" / "supabase" / "GITHUB_BRIDGE.md").read_text(encoding="utf-8")
    for required in [
        "enqueue commit",
        "enqueue tree",
        "enqueue blobs",
        "collect blobs",
        "net._http_response",
        "content_base64",
    ]:
        assert required.lower() in text.lower()
