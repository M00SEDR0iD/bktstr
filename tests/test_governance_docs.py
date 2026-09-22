from pathlib import Path
from urllib.parse import unquote

import pytest

from scripts.check_release_consistency import LINK_PATTERN, markdown_without_fenced_code


ROOT = Path(__file__).parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _local_links(relative_path: str) -> set[Path]:
    document = ROOT / relative_path
    return {
        (document.parent / unquote(match.group(1).strip("<>").split("#", 1)[0])).resolve()
        for match in LINK_PATTERN.finditer(markdown_without_fenced_code(_read(relative_path)))
        if not match.group(1).lower().startswith(("http:", "https:", "mailto:", "#"))
    }


@pytest.mark.parametrize("entry", [
    "README.md", "AGENTS.md", "docs/README.md", "AGENT_BACKTEST_RUNBOOK.md",
    "CONTRIBUTING.md", "integration/INTEGRATION_GUIDE.md",
])
def test_current_entry_points_link_to_design_and_plan(entry):
    links = _local_links(entry)
    for target in ("docs/BKTSTR_SYSTEM_MANUAL.md", "docs/IMPLEMENTATION_PLAN.md"):
        destination = (ROOT / target).resolve()
        assert destination.is_file()
        assert destination in links, f"{entry} must link to {target}"


def test_readme_distinguishes_planned_integrations_from_current_capability():
    text = " ".join(_read("README.md").lower().split())
    planned = text[text.index("jev integration,"):text.index("## intended workflow")]
    for capability in ("macro", "paper", "clear street"):
        assert capability in planned
    assert "planned" in planned and "not implemented" in planned
    assert "current application places no brokerage orders" in planned


def test_project_identity_is_independent_of_fund_portfolios():
    for entry in ("README.md", "AGENTS.md", "docs/BKTSTR_SYSTEM_MANUAL.md"):
        text = " ".join(_read(entry).lower().split())
        assert "separate from the bailey fund" in text


def test_contribution_guide_keeps_verification_and_review_gates():
    text = " ".join(_read("CONTRIBUTING.md").lower().split())
    assert (ROOT / "docs/development/releases.md").resolve() in _local_links("CONTRIBUTING.md")
    assert "required repository checks must pass before merge" in text
    assert "do not rewrite published history or move release tags" in text
    for command in ("python -m pytest", "scripts/check_release_consistency.py"):
        assert command in text


def test_release_workflow_requires_identity_authentication_and_rollback():
    text = " ".join(_read("docs/development/releases.md").lower().split())
    for requirement in (
        "expected version and `git_commit`",
        "authenticated acceptance against that exact deployment",
        "tag and publish only after acceptance succeeds",
        "a failed candidate must not be tagged",
        "verify storage compatibility before rollback",
    ):
        assert requirement in text
