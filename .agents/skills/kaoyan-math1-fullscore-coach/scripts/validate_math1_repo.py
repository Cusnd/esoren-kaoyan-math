#!/usr/bin/env python3
"""Validate the Math I core/practice libraries and their knowledge graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from repo_model import (
    ANSWER_ANCHOR_PATTERN,
    ANSWER_REF_PATTERN,
    KNOWLEDGE_ANCHOR_PATTERN,
    KNOWLEDGE_CONTENT_ANCHOR_PATTERN,
    KNOWLEDGE_CONTENT_REF_PATTERN,
    KNOWLEDGE_ID_PATTERN,
    KNOWLEDGE_INDEX_ANCHOR_PATTERN,
    KNOWLEDGE_INDEX_REF_PATTERN,
    KNOWLEDGE_REF_PATTERN,
    PRACTICE_REQUIRED_FIELDS,
    PROBLEM_ANCHOR_PATTERN,
    PROBLEM_ID_PATTERN,
    PROBLEM_INDEX_ANCHOR_PATTERN,
    PROBLEM_INDEX_REF_PATTERN,
    PROBLEM_REF_PATTERN,
    REGISTRY_REQUIRED_FIELDS,
    RepositoryDataError,
    RepositoryDependencyError,
    chapter_files,
    load_catalog,
    load_knowledge_registry,
    load_resource_manifest,
    load_registry,
    practice_answer_files,
    practice_problem_files,
    problem_blocks,
    strip_tex_comments,
    tex_input_closure,
    tex_inputs,
)


REQUIRED_PATHS = (
    "main.tex",
    "main-web.tex",
    "practice.tex",
    "practice-answers.tex",
    "tex/preamble.tex",
    "tex/preamble_web.tex",
    "tex/templates/problem_template.tex",
    "tex/templates/practice_problem_template.tex",
    "tex/templates/knowledge_template.tex",
    "tex/templates/method_template.tex",
    "tex/templates/mistake_template.tex",
    "tex/indexes/problem_index.tex",
    "tex/indexes/method_index.tex",
    "tex/indexes/mistake_index.tex",
    "tex/indexes/formula_index.tex",
    "data/textbook_catalog.yml",
    "docs/textbook_catalog.md",
    "data/problem_registry.yml",
    "data/knowledge_registry.yml",
    "data/web_pages.yml",
    "resources/manifest.yml",
)
DOC_CHAPTER_PATH_PATTERN = re.compile(r"`(tex/chapters/[^`]+\.tex)`")
DOC_CHAPTER_KEY_PATTERN = re.compile(
    r"`((?:calc-(?:\d{2}|app-\d{2})|la-\d{2}|prob-\d{2}))`"
)
PROBLEM_REF_ARGUMENT_PATTERN = re.compile(
    r"\\(?:problemRef|problemIndexRef|answerRef)\{([^}]*)\}"
)
KNOWLEDGE_REF_ARGUMENT_PATTERN = re.compile(
    r"\\knowledge(?:Index)?Ref\[([^]]*)\]"
)
STUDY_SUBSECTION_PATTERN = re.compile(
    r"\\studySubsection\s*\{(?P<slug>[^{}]*)\}\s*\{"
)
ASCII_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NODE_KINDS = {"concept", "theorem", "formula", "method", "problem_family", "pitfall"}
KNOWLEDGE_KINDS = {"concept", "theorem", "formula", "problem_family"}
EDGE_TYPES = {
    "prerequisite_for",
    "generalizes_to",
    "contrasts_with",
    "same_structure_as",
}
SYMMETRIC_EDGE_TYPES = {"contrasts_with", "same_structure_as"}
COLLECTIONS = {"core", "practice"}
VERIFICATION_STATUSES = {"draft", "verified", "rejected"}
PRACTICE_STAGES = {
    "recognition",
    "procedure",
    "near-transfer",
    "far-transfer",
    "interleaved",
}
TASK_TYPES = {
    "calculation",
    "proof",
    "choice",
    "concept-diagnosis",
    "error-correction",
    "comprehensive",
}
CALC_MAP_PACKAGE_ID = "calc-map-2026"
CALC_MAP_REF_PATTERN = re.compile(r"^calc-map-2026:(K\d{3}|T\d{2})$")
CALC_MAP_BOUNDARY_REFS = {
    "K044",
    "K045",
    "K078",
    "K112",
    "K131",
    "K178",
    "K208",
    "K237",
    "K238",
    "K262",
}
CALC_MAP_FILES = {
    "resources/考研数学一高等数学全量知识点地图_2026.md": "narrative_map",
    "resources/考研数学一高等数学查漏补缺清单_2026.md": "audit_checklist",
    "resources/考研数学一高等数学知识点数据库_2026.xlsx": "structured_workbook",
}
CALC_MAP_CHAPTER_MAPPING = {
    "calc-01": ["K001-K015", "K024-K045", "T01-T04"],
    "calc-02": ["K016-K023", "T05"],
    "calc-03": ["K046-K049", "K059-K060", "T06"],
    "calc-04": ["K050-K058", "T07"],
    "calc-05": ["K070-K078", "T11"],
    "calc-06": ["K061-K069", "T08-T10", "T51"],
    "calc-07": [],
    "calc-08": ["K079-K081", "K088-K092", "K096-K100", "T13-T15"],
    "calc-09": ["K082-K087", "K093-K095", "K101-K105", "K112", "T12", "T16"],
    "calc-10": ["K106-K109", "T18"],
    "calc-11": ["T17"],
    "calc-12": ["K110-K111"],
    "calc-13": ["K132-K158", "T20-T26"],
    "calc-14": ["K159-K169", "T27-T28"],
    "calc-15": ["K239-K262", "T46-T50"],
    "calc-16": ["K209-K238", "T41-T45"],
    "calc-17": ["K113-K131", "T19"],
    "calc-18": ["K170-K208", "T29-T40"],
}


def _is_safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    return (
        not pure.is_absolute()
        and ".." not in pure.parts
        and not windows.is_absolute()
        and not windows.drive
    )


def _chapter_domain(chapter_key: Any) -> str | None:
    if not isinstance(chapter_key, str):
        return None
    if chapter_key.startswith("calc-"):
        return "CALC"
    if chapter_key.startswith("la-"):
        return "LA"
    if chapter_key.startswith("prob-"):
        return "PROB"
    return None


@dataclass(frozen=True)
class Check:
    status: str
    code: str
    message: str
    details: str | None = None


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(self, status: str, code: str, message: str, details: str | None = None) -> None:
        self.checks.append(Check(status, code, message, details))

    def passed(self, code: str, message: str) -> None:
        self.add("PASS", code, message)

    def failed(self, code: str, message: str, details: str | None = None) -> None:
        self.add("FAIL", code, message, details)

    def skipped(self, code: str, message: str) -> None:
        self.add("SKIP", code, message)

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if check.status == "FAIL"]

    @property
    def result(self) -> str:
        if self.failures:
            return "fail"
        if any(check.status == "SKIP" for check in self.checks):
            return "pass_with_skips"
        return "pass"

    def as_json(self) -> dict[str, Any]:
        counts = Counter(check.status.lower() for check in self.checks)
        return {
            "result": self.result,
            "summary": {
                "pass": counts["pass"],
                "fail": counts["fail"],
                "skip": counts["skip"],
            },
            "checks": [asdict(check) for check in self.checks],
        }


def _check_required_paths(root: Path, report: Report) -> None:
    missing = [path for path in REQUIRED_PATHS if not (root / path).is_file()]
    if missing:
        report.failed(
            "repository.required_paths",
            f"Missing {len(missing)} required file(s).",
            "\n".join(missing),
        )
    else:
        report.passed(
            "repository.required_paths",
            f"Found all {len(REQUIRED_PATHS)} required files.",
        )


def _check_catalog(root: Path, report: Report) -> tuple[list[Any] | None, list[str]]:
    try:
        entries = load_catalog(root)
    except RepositoryDependencyError:
        raise
    except RepositoryDataError as exc:
        report.failed("catalog.parse", "Catalog is invalid.", str(exc))
        return None, []

    files = [entry.file for entry in entries]
    report.passed(
        "catalog.parse",
        f"Parsed {len(entries)} catalog entries with stable chapter keys.",
    )
    missing = [path for path in files if not (root / path).is_file()]
    if missing:
        report.failed(
            "catalog.files",
            f"Catalog references {len(missing)} missing file(s).",
            "\n".join(missing),
        )
    else:
        report.passed("catalog.files", f"All {len(files)} catalog files exist.")

    docs_path = root / "docs/textbook_catalog.md"
    if docs_path.is_file():
        docs_text = docs_path.read_text(encoding="utf-8", errors="replace")
        documented = DOC_CHAPTER_PATH_PATTERN.findall(docs_text)
        documented_keys = DOC_CHAPTER_KEY_PATTERN.findall(docs_text)
        expected_keys = [entry.chapter_key for entry in entries]
        if documented == files and documented_keys == expected_keys:
            report.passed(
                "catalog.documentation",
                "Human-readable catalog matches YAML order and paths.",
            )
        else:
            details = [
                f"expected_count={len(files)}",
                f"documented_count={len(documented)}",
                f"expected_key_count={len(expected_keys)}",
                f"documented_key_count={len(documented_keys)}",
            ]
            missing_docs = [path for path in files if path not in documented]
            extra_docs = [path for path in documented if path not in files]
            if missing_docs:
                details.append("missing:\n" + "\n".join(missing_docs))
            if extra_docs:
                details.append("extra:\n" + "\n".join(extra_docs))
            if not missing_docs and not extra_docs:
                details.append("The same paths are present in a different order.")
            if documented_keys != expected_keys:
                details.append("chapter_key values or order differ from YAML.")
            report.failed(
                "catalog.documentation",
                "Human-readable catalog does not match YAML exactly.",
                "\n".join(details),
            )
    return entries, files


def _check_core_entrypoint(
    root: Path,
    report: Report,
    filename: str,
    preamble: str,
    expected_chapters: list[str],
) -> None:
    path = root / filename
    if not path.is_file():
        return
    inputs = tex_inputs(path)
    reachable_inputs = tex_input_closure(root, path)
    code = f"entrypoint.{filename}"
    errors: list[str] = []
    if preamble not in inputs:
        errors.append(f"missing preamble input: {preamble}")
    unsafe_inputs = [item for item in reachable_inputs if not _is_safe_relative_path(item)]
    if unsafe_inputs:
        errors.append("unsafe input paths:\n" + "\n".join(unsafe_inputs))
    missing_targets = [item for item in reachable_inputs if not (root / item).is_file()]
    if missing_targets:
        errors.append("missing targets:\n" + "\n".join(missing_targets))
    chapter_inputs = [item for item in inputs if item.startswith("tex/chapters/")]
    if chapter_inputs != expected_chapters:
        errors.append(
            f"catalog inputs differ: expected={len(expected_chapters)} actual={len(chapter_inputs)}"
        )
    if filename == "main.tex":
        practice_inputs = [
            item for item in reachable_inputs if item.startswith("tex/practice/")
        ]
        if practice_inputs:
            errors.append("main.tex must not include practice files:\n" + "\n".join(practice_inputs))
    if errors:
        report.failed(code, f"{filename} violates its input contract.", "\n".join(errors))
    else:
        report.passed(
            code,
            f"{filename} contains all {len(expected_chapters)} core chapters in order.",
        )


def _relative_paths(root: Path, paths: list[Path]) -> list[str]:
    return [path.relative_to(root).as_posix() for path in paths]


def _is_draft_path(path: str) -> bool:
    return "drafts" in PurePosixPath(path).parts


def _check_practice_pairs_and_entrypoints(root: Path, report: Report) -> dict[str, list[str]]:
    problems = _relative_paths(root, practice_problem_files(root))
    answers = _relative_paths(root, practice_answer_files(root))
    expected_answers = {path.removesuffix("-problems.tex") + "-answers.tex" for path in problems}
    expected_problems = {path.removesuffix("-answers.tex") + "-problems.tex" for path in answers}
    pair_errors = sorted(expected_answers - set(answers)) + sorted(expected_problems - set(problems))
    if pair_errors:
        report.failed(
            "practice.file_pairs",
            "Practice problem/answer files must be paired by lecture.",
            "\n".join(pair_errors),
        )
    else:
        report.passed(
            "practice.file_pairs",
            f"Found {len(problems)} paired practice lecture file set(s).",
        )

    public_problems = [path for path in problems if not _is_draft_path(path)]
    public_answers = [path for path in answers if not _is_draft_path(path)]
    entrypoint_inputs: dict[str, list[str]] = {}
    expectations = {
        "practice.tex": ("tex/preamble.tex", public_problems, public_answers),
        "practice-answers.tex": ("tex/preamble.tex", public_answers, public_problems),
        "main-web.tex": (
            "tex/preamble_web.tex",
            public_problems + public_answers,
            [],
        ),
    }
    for filename, (preamble, required, forbidden) in expectations.items():
        path = root / filename
        if not path.is_file():
            continue
        inputs = tex_inputs(path)
        reachable_inputs = tex_input_closure(root, path)
        entrypoint_inputs[filename] = reachable_inputs
        errors: list[str] = []
        if preamble not in inputs:
            errors.append(f"missing preamble: {preamble}")
        unsafe_inputs = [
            item for item in reachable_inputs if not _is_safe_relative_path(item)
        ]
        if unsafe_inputs:
            errors.append("unsafe input paths:\n" + "\n".join(unsafe_inputs))
        missing_targets = [
            item for item in reachable_inputs if not (root / item).is_file()
        ]
        if missing_targets:
            errors.append("missing targets:\n" + "\n".join(missing_targets))
        missing = [item for item in required if item not in inputs]
        extra_forbidden = [item for item in forbidden if item in reachable_inputs]
        if missing:
            errors.append("missing practice inputs:\n" + "\n".join(missing))
        if extra_forbidden:
            errors.append("forbidden practice inputs:\n" + "\n".join(extra_forbidden))
        duplicates = [item for item, count in Counter(inputs).items() if count > 1]
        if duplicates:
            errors.append("duplicate inputs:\n" + "\n".join(duplicates))
        code = f"practice.entrypoint.{filename}"
        if errors:
            report.failed(code, f"{filename} violates practice isolation.", "\n".join(errors))
        else:
            report.passed(code, f"{filename} has the expected practice inputs.")
    return entrypoint_inputs


def _check_web_page_mapping(
    root: Path,
    report: Report,
    main_web_inputs: list[str],
) -> None:
    """Match every live Web subsection to exactly one manifest source entry."""

    manifest_path = root / "data/web_pages.yml"
    if not manifest_path.is_file():
        return

    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RepositoryDependencyError(
            "PyYAML is required for Math I repository scripts. "
            "Run them in the configured codex-tools environment."
        ) from exc

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        report.failed(
            "web_pages.parse",
            "Web page manifest is invalid.",
            str(exc),
        )
        return

    if not isinstance(raw, dict) or not isinstance(raw.get("pages"), list):
        report.failed(
            "web_pages.parse",
            "Web page manifest is invalid.",
            "root must be a mapping containing a pages list",
        )
        return

    errors: list[str] = []
    manifest_occurrences: defaultdict[str, list[tuple[int, str]]] = defaultdict(list)
    for index, page in enumerate(raw["pages"]):
        context = f"pages[{index}]"
        if not isinstance(page, dict):
            errors.append(f"{context}: must be a mapping")
            continue

        slug = page.get("slug")
        source = page.get("source")
        if not isinstance(slug, str) or not ASCII_SLUG_PATTERN.fullmatch(slug):
            errors.append(f"{context}: invalid ASCII slug {slug!r}")
            continue
        if not _is_safe_relative_path(source):
            errors.append(f"{context}: unsafe or empty source {source!r}")
            continue

        normalized_source = str(source).replace("\\", "/")
        if not normalized_source.endswith(".tex"):
            errors.append(f"{context}: source must be a .tex file")
        elif not (root / normalized_source).is_file():
            errors.append(f"{context}: source does not exist: {normalized_source}")
        manifest_occurrences[slug].append((index, normalized_source))

    duplicate_manifest = sorted(
        slug for slug, occurrences in manifest_occurrences.items() if len(occurrences) > 1
    )
    if duplicate_manifest:
        errors.append("duplicate manifest slugs:\n" + "\n".join(duplicate_manifest))

    live_occurrences: defaultdict[str, list[str]] = defaultdict(list)
    for relative in dict.fromkeys(main_web_inputs):
        if not _is_safe_relative_path(relative):
            continue
        path = root / relative
        if not path.is_file():
            continue
        text = strip_tex_comments(path.read_text(encoding="utf-8", errors="replace"))
        for match in STUDY_SUBSECTION_PATTERN.finditer(text):
            slug = match.group("slug")
            if not ASCII_SLUG_PATTERN.fullmatch(slug):
                errors.append(f"invalid ASCII subsection slug {slug!r}: {relative}")
                continue
            live_occurrences[slug].append(relative)

    duplicate_live = sorted(
        slug for slug, occurrences in live_occurrences.items() if len(occurrences) > 1
    )
    if duplicate_live:
        errors.append("duplicate live subsection slugs:\n" + "\n".join(duplicate_live))

    manifest_slugs = set(manifest_occurrences)
    live_slugs = set(live_occurrences)
    missing = sorted(live_slugs - manifest_slugs)
    extra = sorted(manifest_slugs - live_slugs)
    if missing:
        errors.append("live subsections missing from manifest:\n" + "\n".join(missing))
    if extra:
        errors.append("manifest slugs absent from main-web input closure:\n" + "\n".join(extra))

    for slug in sorted(manifest_slugs & live_slugs):
        manifest_sources = {source for _, source in manifest_occurrences[slug]}
        live_sources = set(live_occurrences[slug])
        if manifest_sources != live_sources:
            errors.append(
                f"source mismatch for {slug}: "
                f"manifest={sorted(manifest_sources)!r} live={sorted(live_sources)!r}"
            )

    if errors:
        report.failed(
            "web_pages.mapping",
            "Web page manifest and live study subsections are not one-to-one.",
            "\n".join(errors),
        )
    else:
        report.passed(
            "web_pages.mapping",
            f"Mapped all {len(live_slugs)} live Web subsections to their TeX sources.",
        )


def _validate_string_list(value: Any, allow_empty: bool = True) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def _check_knowledge_registry(
    root: Path,
    report: Report,
    catalog_by_key: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]] | None, set[str]]:
    try:
        raw = load_knowledge_registry(root)
    except RepositoryDependencyError:
        raise
    except RepositoryDataError as exc:
        report.failed("knowledge.parse", "Knowledge registry is invalid.", str(exc))
        return None, set()

    errors: list[str] = []
    if raw.get("schema_version") != 2:
        errors.append("schema_version must equal 2")
    nodes_raw = raw.get("nodes")
    edges_raw = raw.get("edges")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        errors.append("nodes must be a non-empty list")
        nodes_raw = []
    if not isinstance(edges_raw, list):
        errors.append("edges must be a list")
        edges_raw = []

    nodes: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(nodes_raw):
        context = f"nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{context}: must be a mapping")
            continue
        for field in ("id", "title", "kind", "subject", "chapter_key"):
            if not isinstance(node.get(field), str) or not node[field].strip():
                errors.append(f"{context}: {field} must be a non-empty string")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not KNOWLEDGE_ID_PATTERN.fullmatch(node_id):
            errors.append(f"{context}: invalid knowledge id {node_id!r}")
            continue
        if node_id in nodes:
            errors.append(f"{context}: duplicate id {node_id}")
            continue
        nodes[node_id] = node
        node_match = KNOWLEDGE_ID_PATTERN.fullmatch(node_id)
        if node_match and node_match.group(1) != _chapter_domain(node.get("chapter_key")):
            errors.append(f"{context}: id domain does not match chapter_key")
        kind = node.get("kind")
        if not isinstance(kind, str) or kind not in NODE_KINDS:
            errors.append(f"{context}: invalid kind {kind!r}")
        chapter_key = node.get("chapter_key")
        chapter = catalog_by_key.get(chapter_key) if isinstance(chapter_key, str) else None
        if chapter is None:
            errors.append(f"{context}: unknown chapter_key {node.get('chapter_key')!r}")
        elif node.get("subject") != chapter.subject_name:
            errors.append(f"{context}: subject does not match chapter_key")
        if "aliases" in node and not _validate_string_list(node["aliases"]):
            errors.append(f"{context}: aliases must be a list of non-empty strings")
        source_refs = node.get("source_refs")
        if source_refs is not None:
            if not _validate_string_list(source_refs, allow_empty=False):
                errors.append(f"{context}: source_refs must be a non-empty string list")
            else:
                for source_ref in source_refs:
                    if not CALC_MAP_REF_PATTERN.fullmatch(source_ref):
                        errors.append(f"{context}: invalid source_ref {source_ref!r}")
        if "reviewable" in node and not isinstance(node["reviewable"], bool):
            errors.append(f"{context}: reviewable must be a boolean")
        anchor = node.get("tex_anchor")
        if anchor is not None:
            if not isinstance(anchor, dict):
                errors.append(f"{context}: tex_anchor must be a mapping")
            else:
                anchor_id = anchor.get("id")
                anchor_file = anchor.get("file")
                if anchor_id != node_id:
                    errors.append(f"{context}: tex_anchor.id must equal node id")
                if (
                    not _is_safe_relative_path(anchor_file)
                    or not str(anchor_file).replace("\\", "/").endswith(".tex")
                    or not (root / str(anchor_file)).is_file()
                ):
                    errors.append(f"{context}: tex_anchor.file is missing")
                else:
                    text = strip_tex_comments(
                        (root / anchor_file).read_text(encoding="utf-8", errors="replace")
                    )
                    count = sum(
                        match.group("id") == node_id
                        for match in KNOWLEDGE_ANCHOR_PATTERN.finditer(text)
                    )
                    if count != 1:
                        errors.append(
                            f"{context}: expected one {node_id} anchor in {anchor_file}, found {count}"
                        )

    edge_keys: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(edges_raw):
        context = f"edges[{index}]"
        if not isinstance(edge, dict):
            errors.append(f"{context}: must be a mapping")
            continue
        source, target, edge_type = edge.get("source"), edge.get("target"), edge.get("type")
        if not isinstance(source, str) or source not in nodes:
            errors.append(f"{context}: unknown source {source!r}")
        if not isinstance(target, str) or target not in nodes:
            errors.append(f"{context}: unknown target {target!r}")
        if not isinstance(edge_type, str) or edge_type not in EDGE_TYPES:
            errors.append(f"{context}: invalid type {edge_type!r}")
        if source == target:
            errors.append(f"{context}: self-loops are forbidden")
        if isinstance(source, str) and isinstance(target, str) and isinstance(edge_type, str):
            key = (source, target, edge_type)
            reverse = (target, source, edge_type)
            if key in edge_keys or (edge_type in SYMMETRIC_EDGE_TYPES and reverse in edge_keys):
                errors.append(f"{context}: duplicate edge {key}")
            edge_keys.add(key)
            if edge_type in SYMMETRIC_EDGE_TYPES and source > target:
                errors.append(f"{context}: symmetric edge endpoints must be lexical order")

    if errors:
        report.failed(
            "knowledge.schema",
            f"Knowledge registry has {len(errors)} schema/reference error(s).",
            "\n".join(errors),
        )
    else:
        report.passed(
            "knowledge.schema",
            f"Validated {len(nodes)} knowledge nodes and {len(edge_keys)} explicit edges.",
        )
    return (None if errors else nodes), set(nodes)


def _expand_calc_map_token(token: str) -> list[str]:
    match = re.fullmatch(r"([KT])(\d{2,3})(?:-([KT])(\d{2,3}))?", token)
    if not match:
        raise ValueError(f"invalid source range {token!r}")
    prefix, start_raw, end_prefix, end_raw = match.groups()
    if end_prefix is not None and end_prefix != prefix:
        raise ValueError(f"mixed source range {token!r}")
    width = len(start_raw)
    start = int(start_raw)
    end = int(end_raw) if end_raw is not None else start
    if end < start or (end_raw is not None and len(end_raw) != width):
        raise ValueError(f"invalid source range {token!r}")
    return [f"{prefix}{number:0{width}d}" for number in range(start, end + 1)]


def _calc_map_expected_chapters() -> dict[str, str]:
    result: dict[str, str] = {}
    for chapter_key, tokens in CALC_MAP_CHAPTER_MAPPING.items():
        for token in tokens:
            for source_id in _expand_calc_map_token(token):
                if source_id in result:
                    raise ValueError(f"duplicate source mapping for {source_id}")
                result[source_id] = chapter_key
    return result


def _check_calc_map_bundle(
    root: Path,
    report: Report,
    nodes: dict[str, dict[str, Any]],
) -> None:
    try:
        manifest = load_resource_manifest(root)
    except RepositoryDependencyError:
        raise
    except RepositoryDataError as exc:
        report.failed("resources.calc_map", "Resource manifest is invalid.", str(exc))
        return

    packages_raw = manifest.get("research_packages")
    packages = packages_raw if isinstance(packages_raw, list) else []
    matching = [
        package
        for package in packages
        if isinstance(package, dict) and package.get("id") == CALC_MAP_PACKAGE_ID
    ]
    has_refs = any(
        isinstance(source_ref, str) and source_ref.startswith(f"{CALC_MAP_PACKAGE_ID}:")
        for node in nodes.values()
        for source_ref in node.get("source_refs", [])
    )
    if not matching and not has_refs:
        report.skipped(
            "resources.calc_map",
            "No calc-map-2026 research package is active in this fixture.",
        )
        return

    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("resource manifest schema_version must equal 1")
    if not isinstance(packages_raw, list):
        errors.append("research_packages must be a list")
    if len(matching) != 1:
        errors.append("calc-map-2026 must appear exactly once in research_packages")
        package: dict[str, Any] = {}
    else:
        package = matching[0]

    if package.get("authority") != "non_authoritative_research":
        errors.append("calc-map-2026 authority must be non_authoritative_research")
    if package.get("build_input") is not False:
        errors.append("calc-map-2026 must not be a build input")
    if package.get("source_ranges") != {
        "knowledge": "K001-K262",
        "problem_families": "T01-T51",
    }:
        errors.append("calc-map-2026 source_ranges are not the approved K/T ranges")

    projection = package.get("projection_policy")
    if not isinstance(projection, dict):
        errors.append("projection_policy must be a mapping")
        projection = {}
    if projection.get("searchable_aliases") is not True:
        errors.append("external K/T aliases must be searchable")
    if projection.get("expose_source_refs") is not False:
        errors.append("source_refs must remain private build metadata")
    if projection.get("import_personal_state") is not False:
        errors.append("personal learning state import must stay disabled")
    excluded = projection.get("excluded_public_fields")
    required_excluded = {
        "exam_frequency",
        "trend",
        "research_rating",
        "learning_status",
        "review_count",
        "review_date",
        "personal_notes",
    }
    if not isinstance(excluded, list) or set(excluded) != required_excluded:
        errors.append("excluded_public_fields must list the seven private/research fields")

    files_raw = package.get("files")
    file_rows = files_raw if isinstance(files_raw, list) else []
    files_by_path = {
        row.get("path"): row
        for row in file_rows
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    if set(files_by_path) != set(CALC_MAP_FILES) or len(file_rows) != 3:
        errors.append("calc-map-2026 must register exactly the three approved source files")
    for relative_path, expected_role in CALC_MAP_FILES.items():
        row = files_by_path.get(relative_path)
        if not isinstance(row, dict):
            continue
        if row.get("role") != expected_role:
            errors.append(f"{relative_path}: unexpected role {row.get('role')!r}")
        digest = row.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"{relative_path}: sha256 must be 64 lowercase hex characters")
            continue
        target = root / relative_path
        if not target.is_file():
            errors.append(f"{relative_path}: source file is missing")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != digest:
            errors.append(f"{relative_path}: sha256 mismatch")

    if package.get("chapter_mapping") != CALC_MAP_CHAPTER_MAPPING:
        errors.append("chapter_mapping does not match the approved 18-lecture projection")
    gaps = package.get("coverage_gaps")
    if not isinstance(gaps, list) or not any(
        isinstance(gap, dict)
        and gap.get("chapter_key") == "calc-07"
        and isinstance(gap.get("reason"), str)
        and gap["reason"].strip()
        for gap in gaps
    ):
        errors.append("calc-07 must remain an explicit documented coverage gap")

    expected_chapters = _calc_map_expected_chapters()
    expected_sources = set(expected_chapters)
    expected_sources.update(f"K{number:03d}" for number in range(1, 263))
    expected_sources.update(f"T{number:02d}" for number in range(1, 52))
    if len(expected_sources) != 313 or set(expected_chapters) != expected_sources:
        errors.append("internal approved source mapping is not exactly 313 items")

    ref_nodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    false_refs: set[str] = set()
    for node in nodes.values():
        aliases = node.get("aliases", [])
        source_refs = node.get("source_refs", [])
        for source_ref in source_refs:
            match = CALC_MAP_REF_PATTERN.fullmatch(source_ref) if isinstance(source_ref, str) else None
            if not match:
                continue
            source_id = match.group(1)
            ref_nodes[source_id].append(node)
            if source_id not in aliases:
                errors.append(f"{source_id}: external id is missing from aliases")
            expected_chapter = expected_chapters.get(source_id)
            if expected_chapter and node.get("chapter_key") != expected_chapter:
                errors.append(
                    f"{source_id}: expected {expected_chapter}, got {node.get('chapter_key')!r}"
                )
            if source_id.startswith("T") and node.get("kind") != "problem_family":
                errors.append(f"{source_id}: T entries must be problem_family nodes")
            if source_id.startswith("K") and node.get("kind") not in {
                "concept",
                "theorem",
                "formula",
                "method",
            }:
                errors.append(f"{source_id}: K entries have invalid semantic kind")
            if node.get("reviewable", True) is False:
                false_refs.add(source_id)

    missing_refs = sorted(expected_sources - set(ref_nodes))
    extra_refs = sorted(set(ref_nodes) - expected_sources)
    duplicated_refs = sorted(source_id for source_id, mapped in ref_nodes.items() if len(mapped) != 1)
    if missing_refs:
        errors.append(f"missing source refs: {', '.join(missing_refs)}")
    if extra_refs:
        errors.append(f"unexpected source refs: {', '.join(extra_refs)}")
    if duplicated_refs:
        errors.append(f"source refs must map exactly once: {', '.join(duplicated_refs)}")
    if len(nodes) != 359:
        errors.append(f"expected 359 stable nodes, found {len(nodes)}")
    expected_new_ids = {f"MATH1-KN-CALC-{number:04d}" for number in range(61, 361)}
    if not expected_new_ids.issubset(nodes):
        errors.append("stable id range MATH1-KN-CALC-0061..0360 is incomplete")
    if false_refs != CALC_MAP_BOUNDARY_REFS:
        errors.append(
            "reviewable:false refs must be exactly "
            + ", ".join(sorted(CALC_MAP_BOUNDARY_REFS))
        )
    false_nodes = [node for node in nodes.values() if node.get("reviewable", True) is False]
    if len(false_nodes) != 10:
        errors.append(f"expected exactly 10 non-reviewable nodes, found {len(false_nodes)}")
    for source_id in ("K158", "K177"):
        mapped = ref_nodes.get(source_id, [])
        if len(mapped) == 1 and mapped[0].get("reviewable", True) is not True:
            errors.append(f"{source_id} must remain reviewable")

    content_counts: Counter[str] = Counter()
    for file in chapter_files(root):
        text = strip_tex_comments(file.read_text(encoding="utf-8", errors="replace"))
        content_counts.update(
            match.group("id") for match in KNOWLEDGE_CONTENT_ANCHOR_PATTERN.finditer(text)
        )
    first_batch = {
        *(f"K{number:03d}" for number in range(1, 46)),
        *(f"T{number:02d}" for number in range(1, 6)),
    }
    for source_id in sorted(first_batch):
        mapped = ref_nodes.get(source_id, [])
        if len(mapped) != 1:
            continue
        node_id = mapped[0]["id"]
        if content_counts[node_id] != 1:
            errors.append(
                f"{source_id}: expected one content anchor for {node_id}, found {content_counts[node_id]}"
            )

    try:
        registry = load_knowledge_registry(root)
    except (RepositoryDataError, RepositoryDependencyError):
        registry = {}
    edge_keys = {
        (edge.get("source"), edge.get("target"), edge.get("type"))
        for edge in registry.get("edges", [])
        if isinstance(edge, dict)
    }
    family_prerequisites = {
        "T01": ["K002", "K003", "K009"],
        "T02": ["K012", "K025", "K038", "K039", "K040"],
        "T03": [*(f"K{number:03d}" for number in range(27, 38))],
        "T04": ["K035", "K037"],
        "T05": ["K021", "K022", "K023"],
    }
    stable_for = {
        source_id: mapped[0]["id"]
        for source_id, mapped in ref_nodes.items()
        if len(mapped) == 1
    }
    for family, prerequisites in family_prerequisites.items():
        for prerequisite in prerequisites:
            required = (
                stable_for.get(prerequisite),
                stable_for.get(family),
                "prerequisite_for",
            )
            if None not in required and required not in edge_keys:
                errors.append(f"missing explicit prerequisite edge {prerequisite} -> {family}")
    for family in ("T03", "T04"):
        for prerequisite in ("MATH1-KN-CALC-0059", "MATH1-KN-CALC-0060"):
            required = (prerequisite, stable_for.get(family), "prerequisite_for")
            if None not in required and required not in edge_keys:
                errors.append(f"missing explicit prerequisite edge {prerequisite} -> {family}")

    if errors:
        report.failed(
            "resources.calc_map",
            f"calc-map-2026 has {len(errors)} manifest/projection error(s).",
            "\n".join(errors),
        )
    else:
        report.passed(
            "resources.calc_map",
            "Verified three source files, 313 one-to-one refs, 359 nodes, 10 boundaries and first-batch anchors.",
        )


def _safe_practice_path(value: Any, suffix: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = value.replace("\\", "/")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts:
        return None
    if not path.startswith("tex/practice/") or not path.endswith(suffix):
        return None
    return pure.as_posix()


def _check_registry(
    root: Path,
    report: Report,
    catalog_by_key: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, set[str]]:
    try:
        entries = load_registry(root)
    except RepositoryDependencyError:
        raise
    except RepositoryDataError as exc:
        report.failed("registry.parse", "Problem registry is invalid.", str(exc))
        return None, set()

    report.passed("registry.parse", f"Parsed {len(entries)} problem registry entries.")
    errors: list[str] = []
    ids: list[str] = []
    legacy_fields = {"chapter", "tags", "mistakes", "status"}
    for index, entry in enumerate(entries):
        context = f"entry[{index}]"
        missing = [field for field in REGISTRY_REQUIRED_FIELDS if field not in entry]
        if missing:
            errors.append(f"{context}: missing fields {', '.join(missing)}")
            continue
        legacy = sorted(legacy_fields & set(entry))
        if legacy:
            errors.append(f"{context}: legacy fields are forbidden: {', '.join(legacy)}")
        for field in (
            "id",
            "collection",
            "origin",
            "subject",
            "chapter_key",
            "title",
            "file",
            "source",
            "difficulty",
            "verification_status",
        ):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"{context}: {field} must be a non-empty string")
        problem_id = entry.get("id")
        if not isinstance(problem_id, str) or not PROBLEM_ID_PATTERN.fullmatch(problem_id):
            errors.append(f"{context}: invalid problem id {problem_id!r}")
            continue
        ids.append(problem_id)
        problem_match = PROBLEM_ID_PATTERN.fullmatch(problem_id)
        if problem_match and problem_match.group(1) != _chapter_domain(entry.get("chapter_key")):
            errors.append(f"{context}: id domain does not match chapter_key")
        collection = entry.get("collection")
        if not isinstance(collection, str) or collection not in COLLECTIONS:
            errors.append(f"{context}: invalid collection {collection!r}")
        verification_status = entry.get("verification_status")
        if (
            not isinstance(verification_status, str)
            or verification_status not in VERIFICATION_STATUSES
        ):
            errors.append(
                f"{context}: invalid verification_status {verification_status!r}"
            )
        chapter_key = entry.get("chapter_key")
        chapter = catalog_by_key.get(chapter_key) if isinstance(chapter_key, str) else None
        if chapter is None:
            errors.append(f"{context}: unknown chapter_key {entry.get('chapter_key')!r}")
        elif entry.get("subject") != chapter.subject_name:
            errors.append(f"{context}: subject does not match chapter_key")

        for field, expected_kinds in (
            ("knowledge_ids", KNOWLEDGE_KINDS),
            ("method_ids", {"method"}),
            ("pitfall_ids", {"pitfall"}),
        ):
            values = entry.get(field)
            if not _validate_string_list(values):
                errors.append(f"{context}: {field} must be a list of non-empty IDs")
                continue
            for node_id in values:
                node = nodes.get(node_id)
                if node is None:
                    errors.append(f"{context}: {field} references unknown node {node_id}")
                elif node.get("kind") not in expected_kinds:
                    errors.append(
                        f"{context}: {node_id} kind {node.get('kind')!r} is invalid for {field}"
                    )

        file = entry.get("file")
        if entry.get("collection") == "core":
            if chapter is not None and file != chapter.file:
                errors.append(f"{context}: core file must match chapter catalog path")
            if entry.get("verification_status") != "verified":
                errors.append(f"{context}: core entries must be verified")
            if not isinstance(file, str) or not (root / file).is_file():
                errors.append(f"{context}: core file is missing")
        elif entry.get("collection") == "practice":
            missing_practice = [field for field in PRACTICE_REQUIRED_FIELDS if field not in entry]
            if missing_practice:
                errors.append(
                    f"{context}: missing practice fields {', '.join(missing_practice)}"
                )
            problem_file = _safe_practice_path(file, "-problems.tex")
            answer_file = _safe_practice_path(entry.get("answer_file"), "-answers.tex")
            if problem_file is None:
                errors.append(f"{context}: invalid practice problem file")
            elif not (root / problem_file).is_file():
                errors.append(f"{context}: practice problem file is missing")
            if answer_file is None:
                errors.append(f"{context}: invalid practice answer_file")
            elif not (root / answer_file).is_file():
                errors.append(f"{context}: practice answer_file is missing")
            if problem_file and answer_file:
                expected_answer = problem_file.removesuffix("-problems.tex") + "-answers.tex"
                if answer_file != expected_answer:
                    errors.append(f"{context}: problem and answer files are not a lecture pair")
            practice_stage = entry.get("practice_stage")
            if not isinstance(practice_stage, str) or practice_stage not in PRACTICE_STAGES:
                errors.append(f"{context}: invalid practice_stage")
            task_type = entry.get("task_type")
            if not isinstance(task_type, str) or task_type not in TASK_TYPES:
                errors.append(f"{context}: invalid task_type")
            minutes = entry.get("estimated_minutes")
            if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
                errors.append(f"{context}: estimated_minutes must be a positive integer")
            variant_of = entry.get("variant_of")
            if variant_of is not None and (
                not isinstance(variant_of, str) or not PROBLEM_ID_PATTERN.fullmatch(variant_of)
            ):
                errors.append(f"{context}: invalid variant_of {variant_of!r}")

    duplicate_ids = [item for item, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        errors.append("duplicate ids: " + ", ".join(sorted(duplicate_ids)))
    known_ids = set(ids)
    for index, entry in enumerate(entries):
        variant_of = entry.get("variant_of")
        if isinstance(variant_of, str) and variant_of not in known_ids:
            errors.append(f"entry[{index}]: variant_of references unknown problem {variant_of}")

    if errors:
        report.failed(
            "registry.schema",
            f"Problem registry has {len(errors)} schema/reference error(s).",
            "\n".join(errors),
        )
    else:
        core_count = sum(entry.get("collection") == "core" for entry in entries)
        practice_count = len(entries) - core_count
        report.passed(
            "registry.schema",
            f"Validated {core_count} core and {practice_count} practice problems.",
        )
    return (None if errors else entries), known_ids


def _check_problem_contract(
    root: Path,
    report: Report,
    registry: list[dict[str, Any]],
    registry_ids: set[str],
) -> None:
    blocks = problem_blocks(root)
    anchor_counts = Counter(block.problem_id for block in blocks)
    anchor_ids = set(anchor_counts)
    duplicates = sorted(item for item, count in anchor_counts.items() if count > 1)
    details: list[str] = []
    if duplicates:
        details.append("duplicate anchors:\n" + "\n".join(duplicates))
    missing = sorted(registry_ids - anchor_ids)
    extra = sorted(anchor_ids - registry_ids)
    if missing:
        details.append("registry without anchor:\n" + "\n".join(missing))
    if extra:
        details.append("anchor without registry:\n" + "\n".join(extra))
    if details:
        report.failed(
            "problems.content_anchors",
            "Problem anchors and registry IDs must match exactly.",
            "\n".join(details),
        )
    else:
        report.passed(
            "problems.content_anchors",
            f"All {len(registry_ids)} problem IDs have one content anchor.",
        )

    paths_by_id: dict[str, set[str]] = defaultdict(set)
    block_by_id: dict[str, Any] = {}
    for block in blocks:
        paths_by_id[block.problem_id].add(block.file)
        block_by_id[block.problem_id] = block
    path_errors = [
        f"{entry.get('id')}: registry={entry.get('file')} anchors={sorted(paths_by_id.get(entry.get('id'), set()))}"
        for entry in registry
        if paths_by_id.get(entry.get("id"), set()) != {entry.get("file")}
    ]
    if path_errors:
        report.failed(
            "problems.registry_paths",
            "Registry file fields do not match problem anchor locations.",
            "\n".join(path_errors),
        )
    else:
        report.passed("problems.registry_paths", "Registry files match anchor locations.")

    structure_errors: list[str] = []
    for entry in registry:
        block = block_by_id.get(entry.get("id"))
        if block is None:
            continue
        if "\\begin{problemBox}" not in block.text:
            structure_errors.append(f"{entry['id']}: missing problemBox")
        if entry.get("collection") == "core" and "\\begin{solutionBox}" not in block.text:
            structure_errors.append(f"{entry['id']}: core problem missing solutionBox")
    if structure_errors:
        report.failed(
            "problems.required_blocks",
            "Problem content is missing required semantic blocks.",
            "\n".join(structure_errors),
        )
    else:
        report.passed("problems.required_blocks", "All problem blocks are structurally complete.")

    answer_locations: dict[str, list[str]] = defaultdict(list)
    answer_text_by_id: dict[str, str] = {}
    for path in practice_answer_files(root):
        text = strip_tex_comments(path.read_text(encoding="utf-8", errors="replace"))
        matches = list(ANSWER_ANCHOR_PATTERN.finditer(text))
        for index, match in enumerate(matches):
            problem_id = match.group("id")
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            answer_locations[problem_id].append(path.relative_to(root).as_posix())
            answer_text_by_id[problem_id] = text[match.start() : end]
    answer_errors: list[str] = []
    practice_ids = {entry["id"] for entry in registry if entry.get("collection") == "practice"}
    for entry in registry:
        if entry.get("collection") != "practice":
            continue
        locations = answer_locations.get(entry["id"], [])
        if locations != [entry.get("answer_file")]:
            answer_errors.append(
                f"{entry['id']}: registry={entry.get('answer_file')} anchors={locations}"
            )
        if "\\begin{solutionBox}" not in answer_text_by_id.get(entry["id"], ""):
            answer_errors.append(f"{entry['id']}: answer missing solutionBox")
    extra_answers = sorted(set(answer_locations) - practice_ids)
    if extra_answers:
        answer_errors.append("answers without practice registry:\n" + "\n".join(extra_answers))
    if answer_errors:
        report.failed(
            "practice.answers",
            "Every practice problem must have exactly one complete paired answer.",
            "\n".join(answer_errors),
        )
    else:
        report.passed(
            "practice.answers",
            f"Validated paired answers for {len(practice_ids)} practice problems.",
        )

    core_ids = {entry["id"] for entry in registry if entry.get("collection") == "core"}
    index_path = root / "tex/indexes/problem_index.tex"
    if index_path.is_file():
        text = strip_tex_comments(index_path.read_text(encoding="utf-8", errors="replace"))
        index_ids = [match.group("id") for match in PROBLEM_INDEX_ANCHOR_PATTERN.finditer(text)]
        duplicate_index = [item for item, count in Counter(index_ids).items() if count > 1]
        if duplicate_index or set(index_ids) != core_ids:
            index_details = []
            if duplicate_index:
                index_details.append("duplicate:\n" + "\n".join(sorted(duplicate_index)))
            missing_index = sorted(core_ids - set(index_ids))
            extra_index = sorted(set(index_ids) - core_ids)
            if missing_index:
                index_details.append("missing core:\n" + "\n".join(missing_index))
            if extra_index:
                index_details.append("non-core in main index:\n" + "\n".join(extra_index))
            report.failed(
                "problems.index_anchors",
                "Main problem index must contain core IDs exactly.",
                "\n".join(index_details),
            )
        else:
            report.passed(
                "problems.index_anchors",
                f"Main problem index contains all {len(core_ids)} core IDs only.",
            )


def _check_publication_isolation(
    report: Report,
    registry: list[dict[str, Any]],
    entrypoint_inputs: dict[str, list[str]],
) -> None:
    main_inputs = set(entrypoint_inputs.get("main.tex", []))
    web_inputs = set(entrypoint_inputs.get("main-web.tex", []))
    practice_inputs = set(entrypoint_inputs.get("practice.tex", []))
    answer_inputs = set(entrypoint_inputs.get("practice-answers.tex", []))
    errors: list[str] = []
    for entry in registry:
        file = entry.get("file")
        answer_file = entry.get("answer_file")
        status = entry.get("verification_status")
        if entry.get("collection") == "core":
            if file not in main_inputs or file not in web_inputs:
                errors.append(f"{entry.get('id')}: verified core file is not in main and web")
            if file in practice_inputs or file in answer_inputs:
                errors.append(f"{entry.get('id')}: core file leaked into practice PDF")
        elif status == "verified":
            if file not in practice_inputs or file not in web_inputs:
                errors.append(f"{entry.get('id')}: verified practice problem is not published")
            if answer_file not in answer_inputs or answer_file not in web_inputs:
                errors.append(f"{entry.get('id')}: verified practice answer is not published")
            if _is_draft_path(str(file)) or _is_draft_path(str(answer_file)):
                errors.append(f"{entry.get('id')}: verified practice entry remains under drafts/")
        else:
            leaking = [
                filename
                for filename, inputs in entrypoint_inputs.items()
                if file in inputs or answer_file in inputs
            ]
            if leaking:
                errors.append(
                    f"{entry.get('id')}: {status} content leaks into {', '.join(leaking)}"
                )
            if not _is_draft_path(str(file)) or not _is_draft_path(str(answer_file)):
                errors.append(f"{entry.get('id')}: non-verified practice must live under drafts/")
    if errors:
        report.failed(
            "publication.library_isolation",
            "Core, verified practice, and non-public drafts are not isolated.",
            "\n".join(errors),
        )
    else:
        report.passed(
            "publication.library_isolation",
            "Core, practice, and draft publication boundaries are intact.",
        )


def _all_contract_tex(root: Path) -> list[Path]:
    paths = chapter_files(root)
    paths += practice_problem_files(root)
    paths += practice_answer_files(root)
    paths += sorted((root / "tex/indexes").glob("*.tex"))
    return paths


def _check_dangling_refs(
    root: Path,
    report: Report,
    registry_ids: set[str],
    knowledge_ids: set[str],
) -> None:
    documents: list[tuple[str, str]] = []
    problem_anchors: set[str] = set()
    problem_index_anchors: set[str] = set()
    answer_anchors: set[str] = set()
    knowledge_anchor_counts: Counter[str] = Counter()
    knowledge_index_anchor_counts: Counter[str] = Counter()
    for path in _all_contract_tex(root):
        text = strip_tex_comments(path.read_text(encoding="utf-8", errors="replace"))
        relative = path.relative_to(root).as_posix()
        documents.append((relative, text))
        problem_anchors.update(match.group("id") for match in PROBLEM_ANCHOR_PATTERN.finditer(text))
        problem_index_anchors.update(
            match.group("id") for match in PROBLEM_INDEX_ANCHOR_PATTERN.finditer(text)
        )
        answer_anchors.update(match.group("id") for match in ANSWER_ANCHOR_PATTERN.finditer(text))
        knowledge_anchor_counts.update(
            match.group("id") for match in KNOWLEDGE_CONTENT_ANCHOR_PATTERN.finditer(text)
        )
        knowledge_index_anchor_counts.update(
            match.group("id") for match in KNOWLEDGE_INDEX_ANCHOR_PATTERN.finditer(text)
        )

    details: list[str] = []
    knowledge_anchors = set(knowledge_anchor_counts)
    knowledge_index_anchors = set(knowledge_index_anchor_counts)
    duplicate_knowledge_anchors = sorted(
        node_id for node_id, count in knowledge_anchor_counts.items() if count > 1
    )
    duplicate_knowledge_index_anchors = sorted(
        node_id for node_id, count in knowledge_index_anchor_counts.items() if count > 1
    )
    if duplicate_knowledge_anchors:
        details.append(
            "duplicate knowledge anchors: " + ", ".join(duplicate_knowledge_anchors)
        )
    if duplicate_knowledge_index_anchors:
        details.append(
            "duplicate knowledge-index anchors: "
            + ", ".join(duplicate_knowledge_index_anchors)
        )
    invalid_anchor_ids = sorted(
        (problem_anchors | problem_index_anchors | answer_anchors) - registry_ids
    )
    if invalid_anchor_ids:
        details.append("problem anchors outside registry: " + ", ".join(invalid_anchor_ids))
    invalid_knowledge_anchors = sorted(
        (knowledge_anchors | knowledge_index_anchors) - knowledge_ids
    )
    if invalid_knowledge_anchors:
        details.append(
            "knowledge anchors outside registry: " + ", ".join(invalid_knowledge_anchors)
        )

    target_patterns = (
        ("problemRef", PROBLEM_REF_PATTERN, problem_anchors),
        ("problemIndexRef", PROBLEM_INDEX_REF_PATTERN, problem_index_anchors),
        ("answerRef", ANSWER_REF_PATTERN, answer_anchors),
        ("knowledgeRef", KNOWLEDGE_CONTENT_REF_PATTERN, knowledge_anchors),
        ("knowledgeIndexRef", KNOWLEDGE_INDEX_REF_PATTERN, knowledge_index_anchors),
    )
    for relative, text in documents:
        for match in PROBLEM_REF_ARGUMENT_PATTERN.finditer(text):
            argument = match.group(1)
            if not PROBLEM_ID_PATTERN.fullmatch(argument):
                details.append(f"malformed problem reference {argument!r}: {relative}")
        for match in KNOWLEDGE_REF_ARGUMENT_PATTERN.finditer(text):
            argument = match.group(1)
            if not KNOWLEDGE_ID_PATTERN.fullmatch(argument):
                details.append(f"malformed knowledge reference {argument!r}: {relative}")
        for label, pattern, targets in target_patterns:
            for match in pattern.finditer(text):
                if match.group("id") not in targets:
                    details.append(f"dangling {label} {match.group('id')}: {relative}")

    if details:
        report.failed(
            "references.dangling",
            "Found malformed or unresolved TeX references.",
            "\n".join(sorted(set(details))),
        )
    else:
        report.passed(
            "references.dangling",
            "All problem and knowledge references resolve in the correct namespace.",
        )


def _compile_entrypoints(root: Path, report: Report, enabled: bool) -> None:
    entrypoints = ("main.tex", "practice.tex", "practice-answers.tex")
    if not enabled:
        for entrypoint in entrypoints:
            report.skipped(
                f"latex.compile.{entrypoint}",
                f"{entrypoint} compile disabled by --no-compile.",
            )
        return

    latexmk = shutil.which("latexmk")
    xelatex = shutil.which("xelatex")
    if not latexmk and not xelatex:
        for entrypoint in entrypoints:
            report.skipped(
                f"latex.compile.{entrypoint}",
                "Neither latexmk nor xelatex is available; compile skipped.",
            )
        return

    build = root / "build"
    build.mkdir(exist_ok=True)
    for entrypoint in entrypoints:
        if latexmk:
            commands = [[
                latexmk,
                "-xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                f"-outdir={build}",
                entrypoint,
            ]]
        else:
            command = [
                xelatex,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                f"-output-directory={build}",
                entrypoint,
            ]
            commands = [command, command]
        output = ""
        failed = False
        for command in commands:
            result = subprocess.run(
                command,
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            output += result.stdout
            if result.returncode != 0:
                failed = True
                break
        pdf_path = build / f"{Path(entrypoint).stem}.pdf"
        valid_pdf = pdf_path.is_file() and pdf_path.read_bytes()[:5] == b"%PDF-"
        code = f"latex.compile.{entrypoint}"
        if failed or not valid_pdf:
            report.failed(code, f"{entrypoint} compile failed.", output[-4000:])
        else:
            report.passed(code, f"{entrypoint} compiled to {pdf_path.name}.")


def validate_repository(root: Path, compile_enabled: bool = True) -> Report:
    report = Report()
    _check_required_paths(root, report)
    catalog, catalog_files = _check_catalog(root, report)
    catalog_entries = catalog or []
    catalog_by_key = {entry.chapter_key: entry for entry in catalog_entries}
    if catalog is not None:
        _check_core_entrypoint(root, report, "main.tex", "tex/preamble.tex", catalog_files)
        _check_core_entrypoint(
            root, report, "main-web.tex", "tex/preamble_web.tex", catalog_files
        )

    nodes, knowledge_ids = _check_knowledge_registry(root, report, catalog_by_key)
    if nodes is None:
        report.skipped(
            "resources.calc_map",
            "calc-map-2026 checks require a valid knowledge registry.",
        )
    else:
        _check_calc_map_bundle(root, report, nodes)
    registry, registry_ids = _check_registry(root, report, catalog_by_key, nodes or {})

    entrypoint_inputs = _check_practice_pairs_and_entrypoints(root, report)
    for filename in ("main.tex", "main-web.tex"):
        if (root / filename).is_file():
            entrypoint_inputs[filename] = tex_input_closure(root, root / filename)

    _check_web_page_mapping(
        root,
        report,
        entrypoint_inputs.get("main-web.tex", []),
    )

    if registry is not None:
        _check_problem_contract(root, report, registry, registry_ids)
        _check_publication_isolation(report, registry, entrypoint_inputs)
        _check_dangling_refs(root, report, registry_ids, knowledge_ids)

    _compile_entrypoints(root, report, compile_enabled)
    return report


def _render_text(report: Report) -> None:
    for check in report.checks:
        print(f"{check.status}: [{check.code}] {check.message}")
        if check.details:
            print(check.details)
    counts = Counter(check.status for check in report.checks)
    print(
        f"RESULT: {report.result.upper()} "
        f"(pass={counts['PASS']}, fail={counts['FAIL']}, skip={counts['SKIP']})"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        message = f"Repository root is not a directory: {root}"
        if args.format == "json":
            print(json.dumps({"result": "error", "error": message}, ensure_ascii=False))
        else:
            print(message, file=sys.stderr)
        return 2

    try:
        report = validate_repository(root, compile_enabled=not args.no_compile)
    except RepositoryDependencyError as exc:
        if args.format == "json":
            print(json.dumps({"result": "error", "error": str(exc)}, ensure_ascii=False))
        else:
            print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report.as_json(), ensure_ascii=False, indent=2))
    else:
        _render_text(report)
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
