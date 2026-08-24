from pathlib import Path
import subprocess
import sys

from scripts import check_release_consistency as module


ROOT = Path(__file__).parents[1]


def test_extract_python_version_reads_literal_assignment(tmp_path):
    path = tmp_path / "version.py"
    path.write_text('__version__ = "0.4.0"\n', encoding="utf-8")
    assert module.extract_python_version(path) == "0.4.0"


def test_broken_link_check_ignores_urls_and_reports_missing_files(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "present.md").write_text("# Present\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "[present](docs/present.md) [missing](docs/missing.md) [web](https://example.com)\n",
        encoding="utf-8",
    )
    errors = module.find_broken_local_links(tmp_path)
    assert len(errors) == 1
    assert "docs/missing.md" in errors[0]


def test_repository_release_identity_and_links_are_consistent():
    assert module.check_repository(ROOT) == []


def test_consistency_cli_passes_repository():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release_consistency.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Release consistency checks passed." in completed.stdout
