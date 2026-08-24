from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_ci_workflow_runs_full_release_checks():
    path = ROOT / ".github" / "workflows" / "ci.yml"
    assert path.exists(), "CI workflow is missing"
    text = path.read_text(encoding="utf-8")
    for required in [
        "pull_request:",
        "push:",
        "actions/checkout@v7",
        "actions/setup-python@v7",
        "python-version: '3.12'",
        "cache: 'pip'",
        "python -m pip install -r requirements-dev.txt",
        "python -m pytest -q",
        "python -m compileall -q bktstr bktstr_cache integration scripts benchmarks tests",
        "python benchmarks/benchmark_cache.py",
        "git ls-files",
        "__pycache__",
    ]:
        assert required in text


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
