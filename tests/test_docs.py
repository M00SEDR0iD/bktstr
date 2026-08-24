import json
from pathlib import Path
from bktstr.server import CAPABILITIES

ROOT=Path(__file__).parents[1]


def test_gui_contract_matches_runtime_version_and_outputs():
    c=json.loads((ROOT/"docs/gui/sentiment-data-contract.json").read_text())
    assert c["version"]==CAPABILITIES["version"]=="0.3.5"
    assert set(CAPABILITIES["sentiment"]["outputs"]).issubset(c["sentiment"]["outputs"])


def test_manual_and_runbook_publish_v035_cache_pg_net_and_release_identity():
    manual=(ROOT/"docs/BKTSTR_SYSTEM_MANUAL.md").read_text()
    runbook=(ROOT/"AGENT_BACKTEST_RUNBOOK.md").read_text()
    for phrase in ["QQQ broad technology/risk", "SOXX semiconductor", "derived cache", "BKTSTR_DERIVED_CACHE_ENABLED", "git_commit"]:
        assert phrase.lower() in manual.lower()
    for phrase in ["pg_net", "net.http_get", "feature branch", "GitHub CI", "production_acceptance.py", "GitHub-through-Supabase"]:
        assert phrase.lower() in runbook.lower()


def test_readme_and_status_describe_v035_release_workflow():
    readme=(ROOT/"README.md").read_text()
    status=(ROOT/"BUILD_STATUS.md").read_text()
    checklist=(ROOT/"MERGE_CHECKLIST.md").read_text()
    assert "Current release: v0.3.5" in readme
    assert "RAILWAY_GIT_COMMIT_SHA" in readme
    assert "GitHub Actions" in readme
    assert "v0.3.5" in status and "49/49" in status
    assert "production_acceptance.py" in checklist
    assert "git ls-files" in checklist
