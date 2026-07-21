#!/usr/bin/env python3
"""Shared repository parsing helpers for the Math I note-maintenance scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


PROBLEM_ID_PATTERN = re.compile(r"^MATH1-(CALC|LA|PROB)-(\d{4})$")
PROBLEM_ID_IN_TEXT_PATTERN = re.compile(r"MATH1-(?:CALC|LA|PROB)-\d{4}")
KNOWLEDGE_ID_PATTERN = re.compile(r"^MATH1-KN-(CALC|LA|PROB)-(\d{4})$")
CHAPTER_KEY_PATTERN = re.compile(r"^(?:calc-(?:\d{2}|app-\d{2})|la-\d{2}|prob-\d{2})$")
PROBLEM_ANCHOR_PATTERN = re.compile(
    r"\\problemAnchor\{(?P<id>MATH1-(?:CALC|LA|PROB)-\d{4})\}"
)
ANSWER_ANCHOR_PATTERN = re.compile(
    r"\\answerAnchor\{(?P<id>MATH1-(?:CALC|LA|PROB)-\d{4})\}"
)
PROBLEM_INDEX_ANCHOR_PATTERN = re.compile(
    r"\\problemIndexAnchor\{(?P<id>MATH1-(?:CALC|LA|PROB)-\d{4})\}"
)
PROBLEM_REF_PATTERN = re.compile(
    r"\\problemRef\{(?P<id>MATH1-(?:CALC|LA|PROB)-\d{4})\}"
)
PROBLEM_INDEX_REF_PATTERN = re.compile(
    r"\\problemIndexRef\{(?P<id>MATH1-(?:CALC|LA|PROB)-\d{4})\}"
)
ANSWER_REF_PATTERN = re.compile(
    r"\\answerRef\{(?P<id>MATH1-(?:CALC|LA|PROB)-\d{4})\}"
)
KNOWLEDGE_ANCHOR_PATTERN = re.compile(
    r"\\knowledge(?:Index)?Anchor\[(?P<id>MATH1-KN-(?:CALC|LA|PROB)-\d{4})\]"
)
KNOWLEDGE_REF_PATTERN = re.compile(
    r"\\knowledge(?:Index)?Ref\[(?P<id>MATH1-KN-(?:CALC|LA|PROB)-\d{4})\]"
)
KNOWLEDGE_CONTENT_ANCHOR_PATTERN = re.compile(
    r"\\knowledgeAnchor\[(?P<id>MATH1-KN-(?:CALC|LA|PROB)-\d{4})\]"
)
KNOWLEDGE_INDEX_ANCHOR_PATTERN = re.compile(
    r"\\knowledgeIndexAnchor\[(?P<id>MATH1-KN-(?:CALC|LA|PROB)-\d{4})\]"
)
KNOWLEDGE_CONTENT_REF_PATTERN = re.compile(
    r"\\knowledgeRef\[(?P<id>MATH1-KN-(?:CALC|LA|PROB)-\d{4})\]"
)
KNOWLEDGE_INDEX_REF_PATTERN = re.compile(
    r"\\knowledgeIndexRef\[(?P<id>MATH1-KN-(?:CALC|LA|PROB)-\d{4})\]"
)
TEX_INPUT_PATTERN = re.compile(r"\\input\{([^}]+)\}")

REGISTRY_REQUIRED_FIELDS = (
    "id",
    "collection",
    "origin",
    "subject",
    "chapter_key",
    "title",
    "file",
    "source",
    "difficulty",
    "knowledge_ids",
    "method_ids",
    "pitfall_ids",
    "verification_status",
)
PRACTICE_REQUIRED_FIELDS = (
    "answer_file",
    "practice_stage",
    "task_type",
    "estimated_minutes",
)


class RepositoryDependencyError(RuntimeError):
    """Raised when a required runtime dependency is unavailable."""


class RepositoryDataError(RuntimeError):
    """Raised when a repository data file cannot be parsed structurally."""


@dataclass(frozen=True)
class CatalogEntry:
    subject_key: str
    subject_name: str
    group: str
    number: int
    chapter_key: str
    title: str
    file: str


@dataclass(frozen=True)
class ProblemBlock:
    problem_id: str
    file: str
    text: str


def _load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RepositoryDependencyError(
            "PyYAML is required for Math I repository scripts. "
            "Run them in the configured codex-tools environment."
        ) from exc

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RepositoryDataError(f"Missing YAML file: {path}") from exc
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RepositoryDataError(f"Cannot parse {path}: {exc}") from exc


def _nonempty_string(value: Any, field: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RepositoryDataError(f"{context}: {field} must be a non-empty string")
    return value.strip()


def _safe_tex_path(value: Any, context: str, prefix: str) -> str:
    path = _nonempty_string(value, "file", context).replace("\\", "/")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise RepositoryDataError(f"{context}: unsafe path {path!r}")
    if not path.startswith(prefix) or not path.endswith(".tex"):
        raise RepositoryDataError(f"{context}: file must be a {prefix}*.tex path")
    return pure.as_posix()


def load_catalog(root: Path) -> list[CatalogEntry]:
    path = root / "data/textbook_catalog.yml"
    raw = _load_yaml(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("subjects"), dict):
        raise RepositoryDataError(f"{path}: root must contain a subjects mapping")
    if not raw["subjects"]:
        raise RepositoryDataError(f"{path}: subjects must not be empty")

    entries: list[CatalogEntry] = []
    seen_files: set[str] = set()
    seen_keys: set[str] = set()
    for subject_key, subject in raw["subjects"].items():
        context = f"{path}: subject {subject_key!r}"
        if not isinstance(subject_key, str) or not subject_key:
            raise RepositoryDataError(f"{path}: subject keys must be non-empty strings")
        if not isinstance(subject, dict):
            raise RepositoryDataError(f"{context} must be a mapping")
        subject_name = _nonempty_string(subject.get("name"), "name", context)

        for group in ("lectures", "appendices"):
            items = subject.get(group, [])
            if items is None:
                items = []
            if not isinstance(items, list):
                raise RepositoryDataError(f"{context}: {group} must be a list")
            seen_numbers: set[int] = set()
            for index, item in enumerate(items):
                item_context = f"{context} {group}[{index}]"
                if not isinstance(item, dict):
                    raise RepositoryDataError(f"{item_context} must be a mapping")
                number = item.get("number")
                if isinstance(number, bool) or not isinstance(number, int):
                    raise RepositoryDataError(f"{item_context}: number must be an integer")
                if number in seen_numbers:
                    raise RepositoryDataError(f"{context}: duplicate {group} number {number}")
                seen_numbers.add(number)
                chapter_key = _nonempty_string(
                    item.get("chapter_key"), "chapter_key", item_context
                )
                if not CHAPTER_KEY_PATTERN.fullmatch(chapter_key):
                    raise RepositoryDataError(
                        f"{item_context}: invalid chapter_key {chapter_key!r}"
                    )
                if chapter_key in seen_keys:
                    raise RepositoryDataError(f"{path}: duplicate chapter_key {chapter_key}")
                seen_keys.add(chapter_key)
                title = _nonempty_string(item.get("title"), "title", item_context)
                file = _safe_tex_path(item.get("file"), item_context, "tex/chapters/")
                if file in seen_files:
                    raise RepositoryDataError(f"{path}: duplicate catalog file {file}")
                seen_files.add(file)
                entries.append(
                    CatalogEntry(
                        subject_key=subject_key,
                        subject_name=subject_name,
                        group=group,
                        number=number,
                        chapter_key=chapter_key,
                        title=title,
                        file=file,
                    )
                )

    if not entries:
        raise RepositoryDataError(f"{path}: catalog contains no chapter entries")
    return entries


def load_registry(root: Path) -> list[dict[str, Any]]:
    path = root / "data/problem_registry.yml"
    raw = _load_yaml(path)
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise RepositoryDataError(f"{path}: registry root must be a list")
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise RepositoryDataError(f"{path}: registry entry {index} must be a mapping")
        entries.append(item)
    return entries


def load_knowledge_registry(root: Path) -> dict[str, Any]:
    path = root / "data/knowledge_registry.yml"
    raw = _load_yaml(path)
    if not isinstance(raw, dict):
        raise RepositoryDataError(f"{path}: registry root must be a mapping")
    return raw


def load_resource_manifest(root: Path) -> dict[str, Any]:
    path = root / "resources/manifest.yml"
    raw = _load_yaml(path)
    if not isinstance(raw, dict):
        raise RepositoryDataError(f"{path}: manifest root must be a mapping")
    return raw


def strip_tex_comments(text: str) -> str:
    """Remove unescaped TeX comments while preserving line boundaries."""

    cleaned: list[str] = []
    for line in text.splitlines(keepends=True):
        comment_at: int | None = None
        for index, char in enumerate(line):
            if char != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                comment_at = index
                break
        if comment_at is None:
            cleaned.append(line)
            continue
        newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        cleaned.append(line[:comment_at] + newline)
    return "".join(cleaned)


def tex_inputs(path: Path) -> list[str]:
    text = strip_tex_comments(path.read_text(encoding="utf-8", errors="replace"))
    return [item.replace("\\", "/") for item in TEX_INPUT_PATTERN.findall(text)]


def tex_input_closure(root: Path, path: Path) -> list[str]:
    """Return every live repository-relative input reachable from ``path``."""

    result: list[str] = []
    visited: set[str] = set()

    def visit(current: Path) -> None:
        for item in tex_inputs(current):
            result.append(item)
            if item in visited:
                continue
            visited.add(item)
            pure = PurePosixPath(item)
            if pure.is_absolute() or ".." in pure.parts:
                continue
            target = root / pure.as_posix()
            if target.is_file():
                visit(target)

    visit(path)
    return result


def chapter_files(root: Path) -> list[Path]:
    base = root / "tex/chapters"
    return sorted(base.rglob("*.tex")) if base.exists() else []


def practice_problem_files(root: Path) -> list[Path]:
    base = root / "tex/practice"
    return sorted(base.rglob("*-problems.tex")) if base.exists() else []


def practice_answer_files(root: Path) -> list[Path]:
    base = root / "tex/practice"
    return sorted(base.rglob("*-answers.tex")) if base.exists() else []


def content_problem_files(root: Path) -> list[Path]:
    return chapter_files(root) + practice_problem_files(root)


def problem_blocks(root: Path) -> list[ProblemBlock]:
    blocks: list[ProblemBlock] = []
    for path in content_problem_files(root):
        text = strip_tex_comments(path.read_text(encoding="utf-8", errors="replace"))
        matches = list(PROBLEM_ANCHOR_PATTERN.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            blocks.append(
                ProblemBlock(
                    problem_id=match.group("id"),
                    file=path.relative_to(root).as_posix(),
                    text=text[match.start() : end].strip(),
                )
            )
    return blocks


def existing_problem_ids(root: Path) -> set[str]:
    ids = {block.problem_id for block in problem_blocks(root)}
    for entry in load_registry(root):
        value = entry.get("id")
        if isinstance(value, str) and PROBLEM_ID_PATTERN.fullmatch(value):
            ids.add(value)
    return ids


def registry_search_text(entry: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("title", "subject", "chapter_key", "source", "difficulty"):
        value = entry.get(field)
        if isinstance(value, str):
            parts.append(value)
    for field in ("knowledge_ids", "method_ids", "pitfall_ids"):
        value = entry.get(field)
        if isinstance(value, list):
            parts.extend(item for item in value if isinstance(item, str))
    return " ".join(parts)


def ids_from(pattern: re.Pattern[str], texts: Iterable[str]) -> list[str]:
    result: list[str] = []
    for text in texts:
        result.extend(match.group("id") for match in pattern.finditer(text))
    return result
