#!/usr/bin/env python3
"""Shared repository parsing helpers for the Math I note-maintenance scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


PROBLEM_ID_PATTERN = re.compile(r"^MATH1-(CALC|LA|PROB)-(\d{4})$")
PROBLEM_ID_IN_TEXT_PATTERN = re.compile(r"MATH1-(?:CALC|LA|PROB)-\d{4}")
PROBLEM_ANCHOR_PATTERN = re.compile(
    r"\\problemAnchor\{(?P<id>MATH1-(?:CALC|LA|PROB)-\d{4})\}"
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
TEX_INPUT_PATTERN = re.compile(r"\\input\{([^}]+)\}")

REGISTRY_REQUIRED_FIELDS = (
    "id",
    "title",
    "subject",
    "chapter",
    "file",
    "source",
    "difficulty",
    "tags",
    "mistakes",
    "status",
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


def _catalog_path(value: Any, context: str) -> str:
    path = _nonempty_string(value, "file", context).replace("\\", "/")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        raise RepositoryDataError(f"{context}: unsafe catalog path {path!r}")
    if not path.startswith("tex/chapters/") or not path.endswith(".tex"):
        raise RepositoryDataError(
            f"{context}: catalog file must be a tex/chapters/*.tex path"
        )
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
                    raise RepositoryDataError(
                        f"{item_context}: number must be an integer"
                    )
                if number in seen_numbers:
                    raise RepositoryDataError(
                        f"{context}: duplicate {group} number {number}"
                    )
                seen_numbers.add(number)
                title = _nonempty_string(item.get("title"), "title", item_context)
                file = _catalog_path(item.get("file"), item_context)
                if file in seen_files:
                    raise RepositoryDataError(f"{path}: duplicate catalog file {file}")
                seen_files.add(file)
                entries.append(
                    CatalogEntry(
                        subject_key=subject_key,
                        subject_name=subject_name,
                        group=group,
                        number=number,
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


def tex_inputs(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [item.replace("\\", "/") for item in TEX_INPUT_PATTERN.findall(text)]


def chapter_files(root: Path) -> list[Path]:
    base = root / "tex/chapters"
    if not base.exists():
        return []
    return sorted(base.rglob("*.tex"))


def problem_blocks(root: Path) -> list[ProblemBlock]:
    blocks: list[ProblemBlock] = []
    for path in chapter_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
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
    for field in ("title", "subject", "chapter"):
        value = entry.get(field)
        if isinstance(value, str):
            parts.append(value)
    for field in ("tags", "mistakes"):
        value = entry.get(field)
        if isinstance(value, list):
            parts.extend(item for item in value if isinstance(item, str))
    return " ".join(parts)


def ids_from(pattern: re.Pattern[str], texts: Iterable[str]) -> list[str]:
    result: list[str] = []
    for text in texts:
        result.extend(match.group("id") for match in pattern.finditer(text))
    return result
