from pathlib import Path


ROOT = Path(__file__).parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_issue_forms_require_outcome_acceptance_and_verification():
    forms = {
        "feature.yml": "type:feature",
        "bug.yml": "type:bug",
        "documentation.yml": "type:docs",
        "release.yml": "type:maintenance",
    }
    for filename, label in forms.items():
        text = _read(f".github/ISSUE_TEMPLATE/{filename}")
        assert label in text
        assert "acceptance" in text.lower()
        assert "verification" in text.lower()
    assert "non_goals" in _read(".github/ISSUE_TEMPLATE/feature.yml")


def test_pull_request_template_requires_release_evidence():
    text = _read(".github/PULL_REQUEST_TEMPLATE.md")
    for required in [
        "Closes #",
        "## Summary",
        "## Verification",
        "Trading semantics",
        "Documentation and changelog",
        "Deployment and rollback",
    ]:
        assert required in text


def test_generated_release_notes_use_governance_labels():
    text = _read(".github/release.yml")
    for required in [
        "type:feature",
        "type:bug",
        "type:docs",
        "type:security",
        "type:maintenance",
        'labels: ["*"]',
    ]:
        assert required in text
