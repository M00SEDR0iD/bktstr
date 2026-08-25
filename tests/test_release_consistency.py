from pathlib import Path
import subprocess
import sys

from scripts import check_release_consistency as module
from bktstr import __version__
from bktstr.api.app import create_app


ROOT = Path(__file__).parents[1]


def test_v060_release_metadata_requires_fastapi_research_contract():
    assert __version__ == "0.6.0"
    schema = create_app().openapi()
    expected = {
        "/api/v1/backtests",
        "/api/v1/parameter-sweeps",
        "/api/v1/compare",
        "/api/v1/regime-comparison",
        "/api/v1/experiments/{experiment_id}",
        "/api/v1/market-data",
    }
    assert expected <= set(schema["paths"])


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


def test_broken_link_check_ignores_ordinary_fenced_code(tmp_path):
    (tmp_path / "README.md").write_text(
        "```markdown\n[example](missing.md)\n```\n",
        encoding="utf-8",
    )
    assert module.find_broken_local_links(tmp_path) == []


def test_broken_link_check_ignores_blockquoted_fenced_code(tmp_path):
    (tmp_path / "README.md").write_text(
        "> ```markdown\n> [example](missing.md)\n> ```\n",
        encoding="utf-8",
    )
    assert module.find_broken_local_links(tmp_path) == []


def test_broken_link_check_ignores_list_container_fenced_code(tmp_path):
    (tmp_path / "README.md").write_text(
        "- ```markdown\n  [example](missing.md)\n  ```\n",
        encoding="utf-8",
    )
    assert module.find_broken_local_links(tmp_path) == []


def test_tab_indented_list_fence_uses_markdown_columns(tmp_path):
    (tmp_path / "README.md").write_text(
        "- ```markdown\n"
        "\t[inside](inside-missing.md)\n"
        "\t```\n"
        "[outside](outside-missing.md)\n",
        encoding="utf-8",
    )
    errors = module.find_broken_local_links(tmp_path)
    assert len(errors) == 1
    assert "outside-missing.md" in errors[0]


def test_unclosed_nested_blockquote_fence_stops_at_container_end(tmp_path):
    (tmp_path / "README.md").write_text(
        "> > ```markdown\n> > [inside](inside-missing.md)\n[top](top-missing.md)\n",
        encoding="utf-8",
    )
    errors = module.find_broken_local_links(tmp_path)
    assert len(errors) == 1
    assert "top-missing.md" in errors[0]


def test_unclosed_nested_list_fence_stops_at_container_end(tmp_path):
    (tmp_path / "README.md").write_text(
        "- item\n  - ```markdown\n    [inside](inside-missing.md)\n[top](top-missing.md)\n",
        encoding="utf-8",
    )
    errors = module.find_broken_local_links(tmp_path)
    assert len(errors) == 1
    assert "top-missing.md" in errors[0]


def test_broken_link_check_ignores_inline_code(tmp_path):
    (tmp_path / "README.md").write_text(
        "`[single](missing.md)` and ``[double](also-missing.md)``\n",
        encoding="utf-8",
    )
    assert module.find_broken_local_links(tmp_path) == []


def test_odd_backslashes_escape_backtick_delimiters_and_leave_links_live(tmp_path):
    (tmp_path / "README.md").write_text(
        r"\`[single](single-missing.md)\`" "\n"
        r"\\\`[triple](triple-missing.md)\\\`" "\n",
        encoding="utf-8",
    )
    errors = module.find_broken_local_links(tmp_path)
    assert len(errors) == 2
    assert "single-missing.md" in errors[0]
    assert "triple-missing.md" in errors[1]


def test_even_backslashes_do_not_escape_inline_code_delimiters(tmp_path):
    (tmp_path / "README.md").write_text(
        r"\\`[example](missing.md)\\`" "\n",
        encoding="utf-8",
    )
    assert module.find_broken_local_links(tmp_path) == []


def test_backslash_before_closer_does_not_prevent_inline_code_closure(tmp_path):
    (tmp_path / "README.md").write_text(
        "`[inside](inside.md)\\`\n",
        encoding="utf-8",
    )
    assert module.find_broken_local_links(tmp_path) == []


def test_list_then_blockquote_fence_preserves_ordered_containers(tmp_path):
    (tmp_path / "README.md").write_text(
        "- > ```markdown\n"
        "  > [inside](inside-missing.md)\n"
        "  > ```\n"
        "[outside](outside-missing.md)\n",
        encoding="utf-8",
    )
    errors = module.find_broken_local_links(tmp_path)
    assert len(errors) == 1
    assert "outside-missing.md" in errors[0]


def test_blockquote_list_blockquote_fence_preserves_ordered_containers(tmp_path):
    (tmp_path / "README.md").write_text(
        "> - > ```markdown\n"
        ">   > [inside](inside-missing.md)\n"
        ">   > ```\n"
        "[outside](outside-missing.md)\n",
        encoding="utf-8",
    )
    errors = module.find_broken_local_links(tmp_path)
    assert len(errors) == 1
    assert "outside-missing.md" in errors[0]


def test_broken_link_check_does_not_mask_invalid_backtick_fence_openers(tmp_path):
    (tmp_path / "README.md").write_text(
        "```bad`info\n[example](missing.md)\n",
        encoding="utf-8",
    )
    errors = module.find_broken_local_links(tmp_path)
    assert len(errors) == 1
    assert "missing.md" in errors[0]


def test_broken_link_check_ignores_mixed_case_url_schemes(tmp_path):
    (tmp_path / "README.md").write_text(
        "[http](HtTp://example.com) [web](hTtPs://example.com) "
        "[email](MaIlTo:user@example.com) [app](ApP://resource)\n",
        encoding="utf-8",
    )
    assert module.find_broken_local_links(tmp_path) == []


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
