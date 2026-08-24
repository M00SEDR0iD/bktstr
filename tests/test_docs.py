import json
from pathlib import Path

from bktstr.server import CAPABILITIES


def test_gui_sentiment_contract_matches_runtime_capabilities():
    contract_path = Path(__file__).parents[1] / "docs" / "gui" / "sentiment-data-contract.json"
    contract = json.loads(contract_path.read_text())
    assert contract["version"] == CAPABILITIES["version"] == "0.3.2"
    runtime_outputs = set(CAPABILITIES["sentiment"]["outputs"])
    contract_outputs = set(contract["sentiment"]["outputs"].keys())
    assert runtime_outputs.issubset(contract_outputs)
    assert contract["provenance"]["default_profile"] == "clean"
    assert contract["provenance"]["tiers"]["A"]["label"] == "clean"


def test_system_manual_contains_required_gui_and_provenance_sections():
    manual = (Path(__file__).parents[1] / "docs" / "BKTSTR_SYSTEM_MANUAL.md").read_text()
    for heading in [
        "# BKTSTR System Manual",
        "## System schematic",
        "## Sentiment layer definitions",
        "## Data provenance and quality tiers",
        "## GUI implementation contract",
        "## Look-ahead safety",
    ]:
        assert heading in manual
