import json
from pathlib import Path
from bktstr.server import CAPABILITIES

ROOT=Path(__file__).parents[1]


def test_gui_contract_matches_runtime_version_and_outputs():
    c=json.loads((ROOT/"docs/gui/sentiment-data-contract.json").read_text())
    assert c["version"]==CAPABILITIES["version"]=="0.3.4"
    assert set(CAPABILITIES["sentiment"]["outputs"]).issubset(c["sentiment"]["outputs"])


def test_manual_and_runbook_publish_v034_cache_and_pg_net():
    manual=(ROOT/"docs/BKTSTR_SYSTEM_MANUAL.md").read_text(); runbook=(ROOT/"AGENT_BACKTEST_RUNBOOK.md").read_text()
    for phrase in ["QQQ broad technology/risk", "SOXX semiconductor", "derived cache", "BKTSTR_DERIVED_CACHE_ENABLED"]:
        assert phrase.lower() in manual.lower()
    assert "pg_net" in runbook and "net.http_get" in runbook
