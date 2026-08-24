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
