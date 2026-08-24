from pathlib import Path


ROOT = Path(__file__).parents[1]
RELEASE_ROWS = {
    "v0.4.0": "Baseline and documentation repair",
    "v0.5.0": "Strategy-neutral core",
    "v0.6.0": "FastAPI application foundation",
    "v0.7.0": "Persistence and single-owner authentication",
    "v0.8.0": "Durable execution jobs",
    "v0.9.0": "React research workspace",
    "v1.0.0": "Railway production cutover",
}


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_release_plan_publishes_complete_v1_ladder():
    text = _read("docs/roadmap/v1-release-plan.md")
    for version, milestone in RELEASE_ROWS.items():
        assert version in text
        assert milestone in text
    assert "outcome-driven" in text.lower()
    assert "GitHub Project owns live status" in text


def test_changelog_has_unreleased_and_immutable_v035_history():
    text = _read("CHANGELOG.md")
    assert "## [Unreleased]" in text
    assert "## [0.3.5] - 2026-08-24" in text
    assert "[Unreleased]: https://github.com/M00SEDR0iD/bktstr/compare/v0.3.5...HEAD" in text
    assert "[0.3.5]: https://github.com/M00SEDR0iD/bktstr/releases/tag/v0.3.5" in text


def test_contributor_entry_point_links_detailed_workflows():
    text = _read("CONTRIBUTING.md")
    for required in [
        "Closes #",
        "short-lived branch",
        "squash",
        "docs/development/git-workflow.md",
        "docs/development/releases.md",
    ]:
        assert required in text


def test_git_workflow_documents_normal_and_emergency_paths():
    text = _read("docs/development/git-workflow.md")
    for required in [
        "main",
        "feat/<issue>-<slug>",
        "zero external approvals",
        "force push",
        "Emergency changes",
        "incident Issue",
    ]:
        assert required in text


def test_release_workflow_gates_tags_on_production_acceptance():
    text = _read("docs/development/releases.md")
    for required in [
        "release: prepare",
        "annotated tag",
        "expected Git SHA",
        "production-acceptance.yml",
        "Rollback",
    ]:
        assert required in text


def test_v035_archive_records_tag_and_post_release_doc_commit():
    text = _read("docs/archive/releases/v0.3.5.md")
    assert "add435d" in text
    assert "219dc71" in text
    assert "roadmap-only" in text
    assert "tag was not moved" in text
