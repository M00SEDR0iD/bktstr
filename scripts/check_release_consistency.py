from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote


ROOT = Path(__file__).parents[1]
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\((<[^>]+>|[^)\s]+)")
README_VERSION_PATTERN = re.compile(r"\*\*Current release: v([^*]+)\*\*")
IGNORED_PREFIXES = ("http:", "https:", "mailto:", "app:", "#")
BLOCKQUOTE_PREFIX_PATTERN = re.compile(r" {0,3}>[ \t]?")
LIST_ITEM_PREFIX_PATTERN = re.compile(r" {0,3}(?:[-+*]|\d{1,9}[.)])[ \t]+")


def _strip_blockquote_prefixes(line: str, limit: int | None = None) -> tuple[str, int]:
    position = 0
    depth = 0
    while limit is None or depth < limit:
        match = BLOCKQUOTE_PREFIX_PATTERN.match(line, position)
        if not match:
            break
        position = match.end()
        depth += 1
    return line[position:], depth


def _opening_container(line: str) -> tuple[str, int, int]:
    content, blockquote_depth = _strip_blockquote_prefixes(line)
    list_indent = 0
    while True:
        match = LIST_ITEM_PREFIX_PATTERN.match(content)
        if not match:
            break
        list_indent += match.end()
        content = content[match.end() :]
    return content, blockquote_depth, list_indent


def _continued_container(
    line: str,
    blockquote_depth: int,
    list_indent: int,
) -> str | None:
    if blockquote_depth == 0 and list_indent == 0:
        return line
    content, observed_depth = _strip_blockquote_prefixes(line, blockquote_depth)
    if observed_depth < blockquote_depth:
        return None
    if list_indent == 0:
        return content
    if not content.strip():
        return ""
    leading_spaces = len(content) - len(content.lstrip(" "))
    if leading_spaces < list_indent:
        return None
    return content[list_indent:]


def _backtick_run_is_escaped(text: str, start: int) -> bool:
    backslashes = 0
    position = start - 1
    while position >= 0 and text[position] == "\\":
        backslashes += 1
        position -= 1
    return backslashes % 2 == 1


def _mask_inline_code(text: str) -> str:
    masked = list(text)
    index = 0
    while index < len(text):
        if text[index] != "`":
            index += 1
            continue
        opener_start = index
        while index < len(text) and text[index] == "`":
            index += 1
        if _backtick_run_is_escaped(text, opener_start):
            continue
        opener_length = index - opener_start
        search_from = index
        closer_end = None
        while search_from < len(text):
            closer_start = text.find("`", search_from)
            if closer_start < 0:
                break
            candidate_end = closer_start
            while candidate_end < len(text) and text[candidate_end] == "`":
                candidate_end += 1
            if _backtick_run_is_escaped(text, closer_start):
                search_from = candidate_end
                continue
            if candidate_end - closer_start == opener_length:
                closer_end = candidate_end
                break
            search_from = candidate_end
        if closer_end is None:
            index = opener_start + opener_length
            continue
        for position in range(opener_start, closer_end):
            if masked[position] not in "\r\n":
                masked[position] = " "
        index = closer_end
    return "".join(masked)


def markdown_without_fenced_code(text: str) -> str:
    lines = []
    fence_character = None
    fence_length = 0
    fence_blockquote_depth = 0
    fence_list_indent = 0
    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if fence_character is not None:
            container_content = _continued_container(
                content,
                fence_blockquote_depth,
                fence_list_indent,
            )
            if container_content is None:
                fence_character = None
                fence_length = 0
                fence_blockquote_depth = 0
                fence_list_indent = 0
            else:
                stripped = container_content.lstrip(" ")
                indent = len(container_content) - len(stripped)
                closing = stripped.rstrip(" \t")
                if (
                    indent <= 3
                    and closing
                    and set(closing) == {fence_character}
                    and len(closing) >= fence_length
                ):
                    fence_character = None
                    fence_length = 0
                    fence_blockquote_depth = 0
                    fence_list_indent = 0
                continue
        container_content, blockquote_depth, list_indent = _opening_container(content)
        stripped = container_content.lstrip(" ")
        indent = len(container_content) - len(stripped)
        marker = re.match(r"(`{3,}|~{3,})", stripped) if indent <= 3 else None
        invalid_backtick_info = (
            marker
            and marker.group(1)[0] == "`"
            and "`" in stripped[marker.end() :]
        )
        if marker and not invalid_backtick_info:
            fence_character = marker.group(1)[0]
            fence_length = len(marker.group(1))
            fence_blockquote_depth = blockquote_depth
            fence_list_indent = list_indent
        else:
            lines.append(line)
    return _mask_inline_code("".join(lines))


def extract_python_version(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    values.append(ast.literal_eval(node.value))
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError(f"expected one literal __version__ assignment in {path}")
    return values[0]


def extract_function_default(path: Path, function_name: str, parameter_name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            positional = [*node.args.posonlyargs, *node.args.args]
            defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
            for argument, default in zip(positional, defaults, strict=True):
                if argument.arg == parameter_name and default is not None:
                    value = ast.literal_eval(default)
                    if isinstance(value, str):
                        return value
    raise ValueError(f"missing literal default for {function_name}.{parameter_name} in {path}")


def markdown_documents(root: Path) -> list[Path]:
    documents = [root / "README.md", root / "CONTRIBUTING.md", root / "CHANGELOG.md"]
    documents.extend(sorted((root / "docs").rglob("*.md")))
    return [path for path in documents if path.exists()]


def find_broken_local_links(root: Path) -> list[str]:
    errors = []
    for document in markdown_documents(root):
        markdown = markdown_without_fenced_code(document.read_text(encoding="utf-8"))
        for match in LINK_PATTERN.finditer(markdown):
            target = match.group(1).strip("<>")
            if target.lower().startswith(IGNORED_PREFIXES):
                continue
            path_text = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not path_text:
                continue
            destination = (document.parent / path_text).resolve()
            if not destination.exists():
                relative_document = document.relative_to(root).as_posix()
                errors.append(f"{relative_document}: missing local link {target}")
    return errors


def check_repository(root: Path) -> list[str]:
    errors = []
    runtime_version = extract_python_version(root / "bktstr" / "__init__.py")
    readme = (root / "README.md").read_text(encoding="utf-8")
    match = README_VERSION_PATTERN.search(readme)
    readme_version = match.group(1) if match else None
    gui_version = json.loads(
        (root / "docs" / "gui" / "sentiment-data-contract.json").read_text(encoding="utf-8")
    )["version"]
    acceptance_version = extract_function_default(
        root / "scripts" / "production_acceptance.py",
        "run_acceptance",
        "expected_version",
    )
    observed = {
        "README": readme_version,
        "GUI contract": gui_version,
        "production acceptance": acceptance_version,
    }
    for source, version in observed.items():
        if version != runtime_version:
            errors.append(f"{source} version {version!r} does not match runtime {runtime_version!r}")
    errors.extend(find_broken_local_links(root))
    return errors


def main() -> int:
    errors = check_repository(ROOT)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Release consistency checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
