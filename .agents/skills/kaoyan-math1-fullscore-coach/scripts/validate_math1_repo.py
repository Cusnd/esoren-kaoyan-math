#!/usr/bin/env python3
"""Validate the active Kaoyan Math I notes repository and its cross-file contracts."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from repo_model import (
    PROBLEM_ID_PATTERN,
    PROBLEM_INDEX_ANCHOR_PATTERN,
    PROBLEM_INDEX_REF_PATTERN,
    PROBLEM_REF_PATTERN,
    REGISTRY_REQUIRED_FIELDS,
    RepositoryDataError,
    RepositoryDependencyError,
    chapter_files,
    load_catalog,
    load_registry,
    problem_blocks,
    tex_inputs,
)


REQUIRED_PATHS = (
    "main.tex",
    "main-web.tex",
    "tex/preamble.tex",
    "tex/preamble_web.tex",
    "tex/templates/problem_template.tex",
    "tex/templates/knowledge_template.tex",
    "tex/templates/mistake_template.tex",
    "tex/indexes/problem_index.tex",
    "tex/indexes/method_index.tex",
    "tex/indexes/mistake_index.tex",
    "tex/indexes/formula_index.tex",
    "data/textbook_catalog.yml",
    "docs/textbook_catalog.md",
    "data/problem_registry.yml",
)
DOC_CHAPTER_PATH_PATTERN = re.compile(r"`(tex/chapters/[^`]+\.tex)`")


@dataclass(frozen=True)
class Check:
    status: str
    code: str
    message: str
    details: str | None = None


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []

    def add(
        self, status: str, code: str, message: str, details: str | None = None
    ) -> None:
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


def _check_catalog(
    root: Path, report: Report
) -> tuple[list[Any] | None, list[str]]:
    try:
        entries = load_catalog(root)
    except RepositoryDependencyError:
        raise
    except RepositoryDataError as exc:
        report.failed("catalog.parse", "Catalog is invalid.", str(exc))
        return None, []

    files = [entry.file for entry in entries]
    report.passed("catalog.parse", f"Parsed {len(entries)} catalog entries.")

    missing = [path for path in files if not (root / path).is_file()]
    if missing:
        report.failed(
            "catalog.files", f"Catalog references {len(missing)} missing file(s).", "\n".join(missing)
        )
    else:
        report.passed("catalog.files", f"All {len(files)} catalog files exist.")

    docs_path = root / "docs/textbook_catalog.md"
    if docs_path.is_file():
        documented = DOC_CHAPTER_PATH_PATTERN.findall(
            docs_path.read_text(encoding="utf-8", errors="replace")
        )
        if documented == files:
            report.passed(
                "catalog.documentation",
                "Human-readable catalog matches YAML order and paths.",
            )
        else:
            missing_docs = [path for path in files if path not in documented]
            extra_docs = [path for path in documented if path not in files]
            details = [
                f"expected_count={len(files)}",
                f"documented_count={len(documented)}",
            ]
            if missing_docs:
                details.append("missing:\n" + "\n".join(missing_docs))
            if extra_docs:
                details.append("extra:\n" + "\n".join(extra_docs))
            if not missing_docs and not extra_docs:
                details.append("The same paths are present in a different order.")
            report.failed(
                "catalog.documentation",
                "Human-readable catalog does not match YAML exactly.",
                "\n".join(details),
            )
    return entries, files


def _check_entrypoint(
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
    code = f"entrypoint.{filename}"
    if preamble not in inputs:
        report.failed(code, f"{filename} does not input {preamble}.")
        return

    missing_targets = [item for item in inputs if not (root / item).is_file()]
    chapter_inputs = [item for item in inputs if item.startswith("tex/chapters/")]
    if missing_targets:
        report.failed(
            code,
            f"{filename} has missing input target(s).",
            "\n".join(missing_targets),
        )
    elif chapter_inputs != expected_chapters:
        missing = [item for item in expected_chapters if item not in chapter_inputs]
        extra = [item for item in chapter_inputs if item not in expected_chapters]
        duplicate = [
            item for item, count in Counter(chapter_inputs).items() if count > 1
        ]
        details = [
            f"expected_count={len(expected_chapters)}",
            f"actual_count={len(chapter_inputs)}",
        ]
        if missing:
            details.append("missing:\n" + "\n".join(missing))
        if extra:
            details.append("extra:\n" + "\n".join(extra))
        if duplicate:
            details.append("duplicate:\n" + "\n".join(duplicate))
        if not missing and not extra and not duplicate:
            details.append("The same chapter paths are present in a different order.")
        report.failed(
            code,
            f"{filename} chapter inputs do not match the catalog.",
            "\n".join(details),
        )
    else:
        report.passed(
            code,
            f"{filename} contains all {len(expected_chapters)} catalog chapters in order.",
        )


def _validate_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def _check_registry(
    root: Path,
    report: Report,
    catalog_files: set[str],
) -> tuple[list[dict[str, Any]] | None, set[str]]:
    try:
        entries = load_registry(root)
    except RepositoryDependencyError:
        raise
    except RepositoryDataError as exc:
        report.failed("registry.parse", "Problem registry is invalid.", str(exc))
        return None, set()

    report.passed("registry.parse", f"Parsed {len(entries)} registry entries.")
    errors: list[str] = []
    ids: list[str] = []
    valid_entries: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        context = f"entry[{index}]"
        missing = [field for field in REGISTRY_REQUIRED_FIELDS if field not in entry]
        if missing:
            errors.append(f"{context}: missing fields {', '.join(missing)}")
            continue

        invalid_strings = [
            field
            for field in (
                "id",
                "title",
                "subject",
                "chapter",
                "file",
                "source",
                "difficulty",
                "status",
            )
            if not isinstance(entry.get(field), str) or not entry[field].strip()
        ]
        if invalid_strings:
            errors.append(
                f"{context}: fields must be non-empty strings: {', '.join(invalid_strings)}"
            )
            continue
        if not PROBLEM_ID_PATTERN.fullmatch(entry["id"]):
            errors.append(f"{context}: invalid problem id {entry['id']!r}")
            continue
        if not _validate_string_list(entry["tags"]):
            errors.append(f"{context}: tags must be a list of non-empty strings")
        if not _validate_string_list(entry["mistakes"]):
            errors.append(f"{context}: mistakes must be a list of non-empty strings")
        normalized_file = entry["file"].replace("\\", "/")
        entry["file"] = normalized_file
        if normalized_file not in catalog_files:
            errors.append(
                f"{context}: registry file is not in catalog: {normalized_file}"
            )
        if not (root / normalized_file).is_file():
            errors.append(f"{context}: registry file is missing: {normalized_file}")
        ids.append(entry["id"])
        valid_entries.append(entry)

    duplicate_ids = [item for item, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        errors.append("duplicate ids: " + ", ".join(sorted(duplicate_ids)))

    if errors:
        report.failed(
            "registry.schema",
            f"Registry has {len(errors)} schema or reference error(s).",
            "\n".join(errors),
        )
    else:
        report.passed(
            "registry.schema", "Registry fields, IDs, and catalog paths are valid."
        )
    return valid_entries, set(ids)


def _check_problem_contract(
    root: Path,
    report: Report,
    registry: list[dict[str, Any]],
    registry_ids: set[str],
) -> None:
    blocks = problem_blocks(root)
    anchor_counts = Counter(block.problem_id for block in blocks)
    duplicate_anchors = [item for item, count in anchor_counts.items() if count > 1]
    anchor_ids = set(anchor_counts)
    if duplicate_anchors:
        report.failed(
            "problems.chapter_anchors",
            "Problem anchors must be unique across chapter files.",
            "\n".join(sorted(duplicate_anchors)),
        )
    elif anchor_ids != registry_ids:
        details: list[str] = []
        missing = sorted(registry_ids - anchor_ids)
        extra = sorted(anchor_ids - registry_ids)
        if missing:
            details.append("registry_without_anchor:\n" + "\n".join(missing))
        if extra:
            details.append("anchor_without_registry:\n" + "\n".join(extra))
        report.failed(
            "problems.chapter_anchors",
            "Registry IDs and chapter anchors differ.",
            "\n".join(details),
        )
    else:
        report.passed(
            "problems.chapter_anchors",
            f"All {len(registry_ids)} registry IDs have one chapter anchor.",
        )

    paths_by_id: dict[str, set[str]] = defaultdict(set)
    for block in blocks:
        paths_by_id[block.problem_id].add(block.file)
    path_errors = [
        f"{entry['id']}: registry={entry['file']} anchors={sorted(paths_by_id[entry['id']])}"
        for entry in registry
        if entry.get("id") in registry_ids
        and paths_by_id.get(entry["id"], set()) != {entry.get("file")}
    ]
    if path_errors:
        report.failed(
            "problems.registry_paths",
            "Registry file fields do not match anchor locations.",
            "\n".join(path_errors),
        )
    else:
        report.passed(
            "problems.registry_paths", "Registry files match chapter anchor locations."
        )

    index_path = root / "tex/indexes/problem_index.tex"
    if index_path.is_file():
        text = index_path.read_text(encoding="utf-8", errors="replace")
        index_ids = [match.group("id") for match in PROBLEM_INDEX_ANCHOR_PATTERN.finditer(text)]
        index_counts = Counter(index_ids)
        duplicates = [item for item, count in index_counts.items() if count > 1]
        if duplicates or set(index_ids) != registry_ids:
            details = []
            if duplicates:
                details.append("duplicate:\n" + "\n".join(sorted(duplicates)))
            missing = sorted(registry_ids - set(index_ids))
            extra = sorted(set(index_ids) - registry_ids)
            if missing:
                details.append("missing:\n" + "\n".join(missing))
            if extra:
                details.append("extra:\n" + "\n".join(extra))
            report.failed(
                "problems.index_anchors",
                "Problem index anchors do not match registry IDs exactly.",
                "\n".join(details),
            )
        else:
            report.passed(
                "problems.index_anchors",
                f"Problem index has one anchor for each of {len(registry_ids)} IDs.",
            )


def _check_dangling_problem_refs(
    root: Path, report: Report, registry_ids: set[str]
) -> None:
    unknown: dict[str, set[str]] = defaultdict(set)
    paths = chapter_files(root) + sorted((root / "tex/indexes").glob("*.tex"))
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in (PROBLEM_REF_PATTERN, PROBLEM_INDEX_REF_PATTERN):
            for match in pattern.finditer(text):
                problem_id = match.group("id")
                if problem_id not in registry_ids:
                    unknown[problem_id].add(path.relative_to(root).as_posix())

    if unknown:
        details = [
            f"{problem_id}: {', '.join(sorted(paths))}"
            for problem_id, paths in sorted(unknown.items())
        ]
        report.failed(
            "problems.dangling_refs",
            "Found problem references without registry entries.",
            "\n".join(details),
        )
    else:
        report.passed("problems.dangling_refs", "No dangling problem references found.")


def _compile_pdf(root: Path, report: Report, enabled: bool) -> None:
    if not enabled:
        report.skipped("latex.compile", "LaTeX compile disabled by --no-compile.")
        return

    latexmk = shutil.which("latexmk")
    xelatex = shutil.which("xelatex")
    if not latexmk and not xelatex:
        report.skipped(
            "latex.compile", "Neither latexmk nor xelatex is available; compile skipped."
        )
        return

    build = root / "build"
    build.mkdir(exist_ok=True)
    if latexmk:
        commands = [
            [
                latexmk,
                "-xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                f"-outdir={build}",
                "main.tex",
            ]
        ]
    else:
        command = [
            xelatex,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            f"-output-directory={build}",
            "main.tex",
        ]
        commands = [command, command]

    for command in commands:
        result = subprocess.run(
            command,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.returncode != 0:
            report.failed(
                "latex.compile",
                "LaTeX compile failed.",
                result.stdout[-4000:],
            )
            return
    report.passed(
        "latex.compile",
        f"LaTeX compile completed with {Path(commands[0][0]).name}.",
    )


def validate_repository(root: Path, compile_enabled: bool = True) -> Report:
    report = Report()
    _check_required_paths(root, report)
    catalog, catalog_files = _check_catalog(root, report)
    if catalog is not None:
        _check_entrypoint(
            root,
            report,
            "main.tex",
            "tex/preamble.tex",
            catalog_files,
        )
        _check_entrypoint(
            root,
            report,
            "main-web.tex",
            "tex/preamble_web.tex",
            catalog_files,
        )

    registry, registry_ids = _check_registry(root, report, set(catalog_files))
    if registry is not None:
        _check_problem_contract(root, report, registry, registry_ids)
        _check_dangling_problem_refs(root, report, registry_ids)

    _compile_pdf(root, report, compile_enabled)
    return report


def _render_text(report: Report) -> None:
    for check in report.checks:
        print(f"{check.status}: [{check.code}] {check.message}")
        if check.details:
            print(check.details)
    counts = Counter(check.status for check in report.checks)
    label = report.result.upper()
    print(
        f"RESULT: {label} "
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
            print(
                json.dumps(
                    {"result": "error", "error": str(exc)}, ensure_ascii=False
                )
            )
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
