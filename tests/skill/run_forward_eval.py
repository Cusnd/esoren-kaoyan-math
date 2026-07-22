from __future__ import annotations

import argparse
import copy
import datetime as dt
import difflib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path(__file__).with_name("cases.yml")
IGNORED_PARTS = {".git", ".codex", "build", "node_modules", "__pycache__", ".pytest_cache"}
IGNORED_SUFFIXES = {
    ".aux",
    ".fdb_latexmk",
    ".fls",
    ".log",
    ".out",
    ".pdf",
    ".synctex.gz",
    ".toc",
    ".xdv",
}
EVAL_ONLY_PREFIXES = ("tests/skill/",)
PROMPT_STACK_FILES = (
    "AGENTS.md",
    ".agents/skills/kaoyan-math1-fullscore-coach/SKILL.md",
    ".agents/skills/kaoyan-math1-fullscore-coach/agents/openai.yaml",
)
PROMPT_REFERENCE_PREFIX = ".agents/skills/kaoyan-math1-fullscore-coach/references/"
SENSITIVE_BASENAMES = {
    ".env",
    ".env.local",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
WSL_RUNNER_ISOLATION = "bwrap-ro-root-hidden-windows-drives-v2"
NATIVE_RUNNER_ISOLATION = "codex-native-sandbox-v1"
AUTOMATIC_FATAL_POLICY_ID = "math1-automatic-fatal-v2-ignore-tool-and-output-regex"


class ManifestError(ValueError):
    pass


class SummaryError(ValueError):
    pass


def resolve_codex_command(
    platform_name: str | None = None,
    which: Any = shutil.which,
    comspec: str | None = None,
) -> list[str]:
    """Return a subprocess-safe Codex command prefix on every supported OS."""
    platform_name = platform_name or os.name
    if platform_name == "nt":
        command_file = which("codex.cmd")
        if command_file:
            return [comspec or os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command_file]
        executable = which("codex.exe")
        if executable:
            return [executable]
    else:
        executable = which("codex")
        if executable:
            return [executable]
    raise RuntimeError("Codex CLI was not found on PATH")


def to_wsl_path(path: Path) -> str:
    completed = subprocess.run(
        ["wsl.exe", "-e", "wslpath", "-a", "-u", str(path.resolve())],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode or not completed.stdout.strip():
        raise RuntimeError(completed.stderr.strip() or f"wslpath failed for {path}")
    return completed.stdout.strip()


def runner_isolation(runner: str) -> str:
    return WSL_RUNNER_ISOLATION if runner == "wsl" else NATIVE_RUNNER_ISOLATION


def require_wsl_bwrap() -> str:
    completed = subprocess.run(
        ["wsl.exe", "-e", "sh", "-lc", "command -v bwrap"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=sanitized_environment(),
    )
    executable = completed.stdout.strip()
    if completed.returncode or not executable:
        raise RuntimeError(
            "Windows WSL evaluation requires bubblewrap (bwrap); install it in the active WSL distribution"
        )
    return executable


def build_wsl_bwrap_command(
    root: Path,
    output_dir: Path,
    inner_command: list[str],
) -> list[str]:
    """Run a command with only the disposable workspace and output writable.

    The WSL root stays read-only.  The outer shell copies only auth.json and
    config.toml into a short-lived private Codex home; the real .codex tree is
    masked.  A private /tmp hosts that runtime plus the two explicit bind
    mounts.  Windows drive directories below /mnt are empty tmpfs mounts while
    /mnt/wsl remains visible for WSL DNS; the network namespace stays shared.
    """
    runner_root = to_wsl_path(root)
    runner_output = to_wsl_path(output_dir)
    wrapper = (
        'workspace="$1"; output="$2"; shift 2; '
        'command -v bwrap >/dev/null 2>&1 || { echo "bwrap is required" >&2; exit 127; }; '
        'runtime="$(mktemp -d -- "$HOME/.codex-eval-runtime-XXXXXX")" || exit 1; '
        'chmod 700 "$runtime" || exit 1; '
        'cleanup() { '
        'if [[ -n "${runtime:-}" && "$runtime" == "$HOME"/.codex-eval-runtime-* ]]; then '
        'rm -rf -- "$runtime"; fi; }; '
        'trap cleanup EXIT; trap "exit 129" HUP; trap "exit 130" INT; trap "exit 143" TERM; '
        'for name in auth.json config.toml; do source="$HOME/.codex/$name"; '
        'if [[ -f "$source" && ! -L "$source" ]]; then '
        'cp -- "$source" "$runtime/$name" || exit 1; chmod 600 "$runtime/$name" || exit 1; fi; done; '
        'inner=("$@"); '
        'args=(bwrap --die-with-parent --new-session --unshare-pid '
        '--ro-bind / / --proc /proc --dev /dev --tmpfs /tmp '
        '--dir /tmp/eval-home --dir /tmp/eval-home/.codex '
        '--bind "$workspace" /tmp/workspace --bind "$output" /tmp/output '
        '--bind "$runtime" /tmp/eval-home/.codex --tmpfs "$runtime"); '
        'if [[ -d "$HOME/.codex" ]]; then args+=(--tmpfs "$HOME/.codex"); fi; '
        'for drive in /mnt/[a-z]; do if [[ -d "$drive" ]]; then args+=(--tmpfs "$drive"); fi; done; '
        'args+=(--setenv HOME /tmp/eval-home '
        '--setenv CODEX_HOME /tmp/eval-home/.codex --chdir /tmp/workspace); '
        '"${args[@]}" "${inner[@]}"'
    )
    return [
        "wsl.exe",
        "-e",
        "bash",
        "-lc",
        wrapper,
        "bash",
        runner_root,
        runner_output,
        *inner_command,
    ]


def build_codex_command(
    root: Path, final_path: Path, args: argparse.Namespace
) -> list[str]:
    runner_root = "/tmp/workspace" if args.runner == "wsl" else str(root)
    runner_final = (
        f"/tmp/output/{final_path.name}" if args.runner == "wsl" else str(final_path)
    )
    codex_args = [
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
        "--json",
        "--sandbox",
        args.sandbox,
        "-C",
        runner_root,
        "-m",
        args.model,
        "-c",
        f'model_reasoning_effort="{args.effort}"',
        "-c",
        'approval_policy="never"',
        "-o",
        runner_final,
        "-",
    ]
    if args.runner == "wsl":
        return build_wsl_bwrap_command(
            root,
            final_path.parent,
            [
                "timeout",
                "--signal=TERM",
                "--kill-after=10s",
                str(args.timeout),
                "codex",
                *codex_args,
            ],
        )
    return [*resolve_codex_command(), *codex_args]


def sanitized_environment() -> dict[str, str]:
    allowed = {
        "APPDATA",
        "COMSPEC",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERDOMAIN",
        "USERNAME",
        "USERPROFILE",
        "WINDIR",
        "WSLENV",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ManifestError("cases.yml must be a schema_version: 1 mapping")
    defaults = raw.get("defaults")
    cases = raw.get("cases")
    rubrics = raw.get("rubrics")
    if not isinstance(defaults, dict) or not isinstance(cases, list) or not isinstance(rubrics, dict):
        raise ManifestError("defaults, rubrics and cases are required")
    if len(cases) != 27:
        raise ManifestError(f"expected 27 cases, found {len(cases)}")
    fatal_failures = raw.get("fatal_failures")
    if (
        not isinstance(fatal_failures, list)
        or not fatal_failures
        or any(not isinstance(value, str) or not value for value in fatal_failures)
        or len(fatal_failures) != len(set(fatal_failures))
    ):
        raise ManifestError("fatal_failures must be a non-empty unique string list")
    fatal_taxonomy = set(fatal_failures)

    expanded: list[dict[str, Any]] = []
    ids: set[str] = set()
    slice_counts: dict[str, int] = {}
    for item in cases:
        if not isinstance(item, dict):
            raise ManifestError("every case must be a mapping")
        case = deep_merge(defaults, item)
        case_id = case.get("id")
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9_]+", case_id):
            raise ManifestError(f"invalid case id: {case_id!r}")
        if case_id in ids:
            raise ManifestError(f"duplicate case id: {case_id}")
        ids.add(case_id)
        if not str(case.get("prompt", "")).strip():
            raise ManifestError(f"{case_id}: prompt is required")
        expected = case.get("expected")
        if not isinstance(expected, dict) or set(expected) != {"intent", "collection", "persistence"}:
            raise ManifestError(f"{case_id}: expected must contain intent, collection and persistence")
        rubric_name = case.get("rubric")
        if rubric_name not in rubrics:
            raise ManifestError(f"{case_id}: unknown rubric {rubric_name!r}")
        if sum(rubrics[rubric_name].values()) != 100:
            raise ManifestError(f"{case_id}: rubric weights must total 100")
        if not isinstance(case.get("oracle"), dict) or not case["oracle"]:
            raise ManifestError(f"{case_id}: oracle is required")
        hard_fail_if = case.get("hard_fail_if")
        if not isinstance(hard_fail_if, list) or not hard_fail_if or any(
            not isinstance(value, str) or not value for value in hard_fail_if
        ):
            raise ManifestError(f"{case_id}: hard_fail_if must be a non-empty string list")
        if len(hard_fail_if) != len(set(hard_fail_if)):
            raise ManifestError(f"{case_id}: hard_fail_if must contain unique values")
        unknown_fatals = sorted(set(hard_fail_if) - fatal_taxonomy)
        if unknown_fatals:
            raise ManifestError(
                f"{case_id}: hard_fail_if values are absent from fatal_failures: "
                + ", ".join(unknown_fatals)
            )
        if not isinstance(case.get("checks"), dict):
            raise ManifestError(f"{case_id}: checks must be a mapping")
        for group in ("output_must_match", "output_must_not_match", "diff_must_match", "diff_must_not_match"):
            patterns = case["checks"].get(group, [])
            if not isinstance(patterns, list):
                raise ManifestError(f"{case_id}: {group} must be a list")
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise ManifestError(f"{case_id}: invalid {group} regex {pattern!r}: {exc}") from exc
        repetitions = case.get("repetitions")
        if not isinstance(repetitions, int) or repetitions < 1:
            raise ManifestError(f"{case_id}: repetitions must be a positive integer")
        case_slice = str(case.get("slice"))
        slice_counts[case_slice] = slice_counts.get(case_slice, 0) + 1
        expanded.append(case)

    if slice_counts != {"math": 9, "teaching": 8, "persistence": 10}:
        raise ManifestError(f"unexpected slice distribution: {slice_counts}")
    if sum(bool(case.get("smoke")) for case in expanded) != 8:
        raise ManifestError("exactly 8 cases must be marked smoke")
    return raw, expanded


def selected_cases(cases: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = cases
    if args.case:
        wanted = set(args.case)
        known = {case["id"] for case in cases}
        missing = sorted(wanted - known)
        if missing:
            raise ManifestError(f"unknown case ids: {', '.join(missing)}")
        selected = [case for case in selected if case["id"] in wanted]
    if args.slice:
        selected = [case for case in selected if case["slice"] == args.slice]
    if args.smoke:
        selected = [case for case in selected if case.get("smoke")]
    if not selected:
        raise ManifestError("selection contains no cases")
    return selected


def ensure_inside(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ManifestError(f"fixture path escapes snapshot: {relative}")
    return target


def prepare_output_directory(requested: Path | None) -> Path:
    if requested is None:
        return Path(tempfile.mkdtemp(prefix="math1-forward-eval-results-")).resolve()
    if requested.is_symlink():
        raise ManifestError(f"output directory must not be a symbolic link: {requested}")
    output = requested.resolve()
    repo = REPO_ROOT.resolve()
    if output == repo or repo in output.parents:
        raise ManifestError("output directory must be outside the repository")
    if output.exists():
        if not output.is_dir():
            raise ManifestError(f"output path is not a directory: {output}")
        if any(output.iterdir()):
            raise ManifestError(f"output directory must be empty: {output}")
    else:
        output.mkdir(parents=True)
    return output


def make_snapshot(source: str, destination: Path) -> None:
    if source == "worktree":
        completed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.decode(errors="replace").strip())
        destination.mkdir(parents=True)
        for raw_path in completed.stdout.split(b"\0"):
            if not raw_path:
                continue
            relative = raw_path.decode("utf-8")
            if is_eval_only_path(relative):
                continue
            source_path = ensure_inside(REPO_ROOT, relative)
            if not source_path.exists():
                continue
            if source_path.is_symlink():
                raise ManifestError(f"worktree snapshot refuses symbolic link: {relative}")
            lowered_name = source_path.name.lower()
            if (
                lowered_name in SENSITIVE_BASENAMES
                or lowered_name.startswith(".env.")
                or source_path.suffix.lower() in SENSITIVE_SUFFIXES
            ):
                raise ManifestError(f"worktree snapshot refuses sensitive file: {relative}")
            target = ensure_inside(destination, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)
        return

    archive = destination.parent / f"{destination.name}.zip"
    completed = subprocess.run(
        ["git", "archive", "--format=zip", "--output", str(archive), "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "git archive failed")
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            ensure_inside(destination, member.filename)
        bundle.extractall(destination)
    archive.unlink()
    remove_eval_only_paths(destination)


def is_eval_only_path(relative: str) -> bool:
    normalized = relative.replace("\\", "/").lstrip("./")
    return any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in EVAL_ONLY_PREFIXES)


def remove_eval_only_paths(root: Path) -> None:
    for prefix in EVAL_ONLY_PREFIXES:
        target = ensure_inside(root, prefix.rstrip("/"))
        if target.is_symlink():
            raise ManifestError(f"snapshot contains an eval-only symbolic link: {prefix}")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def prompt_stack_paths(source: str) -> list[str]:
    if source == "head":
        completed = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip() or "git ls-tree failed")
        available = completed.stdout.splitlines()
    else:
        available = [relative for relative in PROMPT_STACK_FILES if (REPO_ROOT / relative).is_file()]
        reference_root = REPO_ROOT / PROMPT_REFERENCE_PREFIX.rstrip("/")
        if reference_root.is_dir():
            available.extend(
                path.relative_to(REPO_ROOT).as_posix()
                for path in reference_root.rglob("*")
                if path.is_file()
            )
    return sorted(
        path
        for path in available
        if path in PROMPT_STACK_FILES or path.startswith(PROMPT_REFERENCE_PREFIX)
    )


def apply_prompt_overlay(source: str, destination: Path) -> None:
    if source == "snapshot":
        return
    references = destination / PROMPT_REFERENCE_PREFIX.rstrip("/")
    if references.exists():
        shutil.rmtree(references)
    for relative in PROMPT_STACK_FILES:
        target = destination / relative
        if target.exists():
            target.unlink()
    for relative in prompt_stack_paths(source):
        target = ensure_inside(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source == "head":
            completed = subprocess.run(
                ["git", "show", f"HEAD:{relative}"],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr.decode(errors="replace").strip())
            target.write_bytes(completed.stdout)
        else:
            shutil.copy2(REPO_ROOT / relative, target)


def apply_fixture(root: Path, fixture: dict[str, Any]) -> None:
    for required in fixture.get("requires", []):
        if not ensure_inside(root, required).exists():
            raise ManifestError(f"fixture requires missing path: {required}")
    for entry in fixture.get("files", []):
        target = ensure_inside(root, entry["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(entry["content"]), encoding="utf-8", newline="\n")
    for entry in fixture.get("append", []):
        target = ensure_inside(root, entry["path"])
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        separator = "" if not existing or existing.endswith("\n") else "\n"
        target.write_text(existing + separator + str(entry["content"]), encoding="utf-8", newline="\n")


def initialize_snapshot_git(root: Path) -> None:
    commands = (
        ["git", "init", "--quiet"],
        ["git", "config", "user.name", "Math1 Evaluation Harness"],
        ["git", "config", "user.email", "math1-eval@invalid.local"],
        ["git", "config", "commit.gpgsign", "false"],
        ["git", "add", "-A"],
        ["git", "commit", "--quiet", "--no-gpg-sign", "-m", "evaluation baseline"],
    )
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode:
            details = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"failed to initialize evaluation Git baseline with {' '.join(command)}: {details}"
            )


def ignored_path(relative: str) -> bool:
    path = Path(relative)
    if any(part in IGNORED_PARTS for part in path.parts):
        return True
    text = relative.lower()
    return any(text.endswith(suffix) for suffix in IGNORED_SUFFIXES)


def file_state(root: Path) -> dict[str, bytes]:
    state: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if not ignored_path(relative):
                state[relative] = path.read_bytes()
    return state


def changed_paths(before: dict[str, bytes], after: dict[str, bytes]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def render_diff(before: dict[str, bytes], after: dict[str, bytes], paths: list[str]) -> str:
    chunks: list[str] = []
    for path in paths:
        try:
            old = before.get(path, b"").decode("utf-8").splitlines(keepends=True)
            new = after.get(path, b"").decode("utf-8").splitlines(keepends=True)
        except UnicodeDecodeError:
            chunks.append(f"Binary file changed: {path}\n")
            continue
        chunks.extend(difflib.unified_diff(old, new, fromfile=f"a/{path}", tofile=f"b/{path}"))
    return "".join(chunks)


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def automatic_checks(
    case: dict[str, Any],
    final_message: str,
    diff: str,
    paths: list[str],
    returncode: int,
    validation: dict[str, Any] | None,
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, details: str = "") -> None:
        checks.append({"name": name, "passed": passed, "details": details})

    record("codex_exit", returncode == 0, f"returncode={returncode}")
    record("tool_execution", not metrics["failed_tools"], "\n".join(metrics["failed_tools"]))
    record("skill_loaded", bool(metrics["skill_loaded"]))
    record("usage_recorded", bool(metrics["usage_complete"]), json.dumps(metrics["usage"]))
    file_rules = case["file_expectations"]
    allowed = file_rules.get("allowed_changes", [])
    disallowed = [path for path in paths if not matches_any(path, allowed)]
    record("allowed_paths", not disallowed, ", ".join(disallowed))
    record("required_change", bool(paths) if file_rules.get("require_change") else not paths, ", ".join(paths))

    added_diff = "\n".join(
        line for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    for name, text, should_match in (
        ("output_must_match", final_message, True),
        ("output_must_not_match", final_message, False),
        ("diff_must_match", added_diff, True),
        ("diff_must_not_match", added_diff, False),
    ):
        for pattern in case["checks"].get(name, []):
            found = re.search(pattern, text) is not None
            record(f"{name}:{pattern}", found == should_match)

    if file_rules.get("post_validate"):
        passed = bool(validation) and validation.get("returncode") == 0
        record(
            "post_validate",
            passed,
            "" if validation is None else validation.get("stdout", "")[-1000:],
        )
        record("model_validator_executed", bool(metrics["model_validator_succeeded"]))
    claimed_pass = re.search(
        r"(?:验证|校验|validator|validate)[^\n]{0,80}(?:\bPASS(?:_WITH_SKIPS)?\b|(?:全部|均|已经|已)?通过|成功)"
        r"|(?:\bPASS(?:_WITH_SKIPS)?\b|(?:全部|均|已经|已)?通过)[^\n]{0,80}(?:验证|校验|validator|validate)",
        final_message,
        flags=re.IGNORECASE,
    ) is not None
    record(
        "validation_claim_truthful",
        not claimed_pass or bool(metrics["model_validator_succeeded"]),
    )
    return checks


def automatically_detected_hard_failures(
    case: dict[str, Any], checks: list[dict[str, Any]], paths: list[str]
) -> list[str]:
    """Map only mechanically conclusive failures to case-level fatal names.

    Semantic conditions such as mathematical correctness remain deliberately
    unclaimed and require the per-run blind fatal review.
    """
    declared = set(str(value) for value in case.get("hard_fail_if", []))
    failed_checks = {str(check.get("name")) for check in checks if not check.get("passed")}
    detected: set[str] = set()
    if paths and not case["file_expectations"].get("require_change"):
        if "repository_changed" in declared:
            detected.add("repository_changed")
        if "authorization_violation" in declared:
            detected.add("authorization_violation")
    if "allowed_paths" in failed_checks and "authorization_violation" in declared:
        detected.add("authorization_violation")
    if "validation_claim_truthful" in failed_checks:
        detected.add("false_validation_claim")
    return sorted(detected)


ALLOWLIST_RESCORE_MODE = "evaluator-only-allowed-changes-v1"
ALLOWLIST_DERIVED_RESULT_FIELDS = {
    "file_expectations",
    "automatic_checks",
    "automatic_failures",
    "automatic_pass",
    "automatic_fatal_pass",
    "detected_fatal_failures",
}


def _load_rescore_summary(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink():
        raise ManifestError(f"rescore source must not be a symbolic link: {path}")
    try:
        stat = path.stat()
    except OSError as exc:
        raise ManifestError(f"cannot inspect rescore source {path}: {exc}") from exc
    if not path.is_file():
        raise ManifestError(f"rescore source must be a regular file: {path}")
    if stat.st_nlink != 1:
        raise ManifestError(f"rescore source must not be a hard link: {path}")
    if stat.st_size > 64 * 1024 * 1024:
        raise ManifestError("rescore source exceeds 64 MiB")
    raw = path.read_bytes()

    def reject_constant(value: str) -> None:
        raise ManifestError(f"non-finite JSON value is not allowed: {value}")

    try:
        summary = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"rescore source is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(summary, dict) or summary.get("schema_version") != 1:
        raise ManifestError("rescore source must be a schema_version: 1 summary")
    if summary.get("automatic_fatal_policy_id") != AUTOMATIC_FATAL_POLICY_ID:
        raise ManifestError("rescore source uses an unknown automatic fatal policy")
    return summary, raw


def _allowed_paths_check(
    changed: list[str], allowed: list[str]
) -> tuple[bool, str]:
    disallowed = [path for path in changed if not matches_any(path, allowed)]
    return not disallowed, ", ".join(disallowed)


def _expected_automatic_check_names(case: dict[str, Any]) -> list[str]:
    names = [
        "codex_exit",
        "tool_execution",
        "skill_loaded",
        "usage_recorded",
        "allowed_paths",
        "required_change",
    ]
    for group in (
        "output_must_match",
        "output_must_not_match",
        "diff_must_match",
        "diff_must_not_match",
    ):
        names.extend(f"{group}:{pattern}" for pattern in case["checks"].get(group, []))
    if case["file_expectations"].get("post_validate"):
        names.extend(("post_validate", "model_validator_executed"))
    names.append("validation_claim_truthful")
    return names


def _validate_rescore_source_result(
    result: dict[str, Any], current_case: dict[str, Any]
) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    case_id = current_case["id"]
    for field in (
        "slice",
        "prompt",
        "expected",
        "task_kind",
        "case_repetitions",
        "smoke",
        "fixture",
        "oracle",
        "rubric",
        "hard_fail_if",
        "checks_spec",
    ):
        if field == "checks_spec":
            expected_value = current_case["checks"]
        elif field == "case_repetitions":
            expected_value = current_case["repetitions"]
        elif field == "smoke":
            expected_value = bool(current_case.get("smoke"))
        else:
            expected_value = current_case.get(field)
        if result.get(field) != expected_value:
            raise ManifestError(f"{case_id}: evaluator field {field} changed")

    stored_rules = result.get("file_expectations")
    current_rules = current_case.get("file_expectations")
    if not isinstance(stored_rules, dict) or not isinstance(current_rules, dict):
        raise ManifestError(f"{case_id}: file_expectations must be mappings")
    stored_non_allowlist = {
        key: value for key, value in stored_rules.items() if key != "allowed_changes"
    }
    current_non_allowlist = {
        key: value for key, value in current_rules.items() if key != "allowed_changes"
    }
    if stored_non_allowlist != current_non_allowlist:
        raise ManifestError(
            f"{case_id}: file_expectations changed outside allowed_changes"
        )
    stored_allowed = stored_rules.get("allowed_changes")
    current_allowed = current_rules.get("allowed_changes")
    if (
        not isinstance(stored_allowed, list)
        or any(not isinstance(value, str) for value in stored_allowed)
        or not isinstance(current_allowed, list)
        or any(not isinstance(value, str) for value in current_allowed)
    ):
        raise ManifestError(f"{case_id}: allowed_changes must be string arrays")

    changed = result.get("changed_paths")
    if (
        not isinstance(changed, list)
        or any(not isinstance(value, str) or not value for value in changed)
        or changed != sorted(set(changed))
    ):
        raise ManifestError(f"{case_id}: changed_paths must be a sorted unique string array")
    raw_checks = result.get("automatic_checks")
    if not isinstance(raw_checks, list) or any(not isinstance(value, dict) for value in raw_checks):
        raise ManifestError(f"{case_id}: automatic_checks must be an object array")
    checks = copy.deepcopy(raw_checks)
    check_names = [check.get("name") for check in checks]
    if check_names != _expected_automatic_check_names(current_case):
        raise ManifestError(f"{case_id}: automatic_checks do not match the stored case spec")
    allowed_indexes = [
        index for index, check in enumerate(checks) if check.get("name") == "allowed_paths"
    ]
    if len(allowed_indexes) != 1:
        raise ManifestError(f"{case_id}: exactly one allowed_paths check is required")
    old_passed, old_details = _allowed_paths_check(changed, stored_allowed)
    old_check = checks[allowed_indexes[0]]
    if old_check.get("passed") is not old_passed or old_check.get("details", "") != old_details:
        raise ManifestError(f"{case_id}: stored allowed_paths check is inconsistent")
    source_failures = [
        str(check.get("name")) for check in checks if check.get("passed") is not True
    ]
    if result.get("automatic_failures") != source_failures:
        raise ManifestError(f"{case_id}: stored automatic_failures are inconsistent")
    source_case = copy.deepcopy(current_case)
    source_case["file_expectations"] = copy.deepcopy(stored_rules)
    source_detected = automatically_detected_hard_failures(source_case, checks, changed)
    if result.get("detected_fatal_failures") != source_detected:
        raise ManifestError(f"{case_id}: stored detected_fatal_failures are inconsistent")
    if result.get("automatic_pass") is not (not source_failures):
        raise ManifestError(f"{case_id}: stored automatic_pass is inconsistent")
    if result.get("automatic_fatal_pass") is not automatic_fatal_pass(
        source_failures, source_detected
    ):
        raise ManifestError(f"{case_id}: stored automatic_fatal_pass is inconsistent")
    return changed, checks, current_rules


def rescore_allowlist_summary(
    source_path: Path, manifest_path: Path = DEFAULT_MANIFEST
) -> dict[str, Any]:
    summary, raw_summary = _load_rescore_summary(source_path)
    validate_reclassifiable_summary(summary)
    manifest, cases = load_manifest(manifest_path)
    if summary.get("fatal_failures") != manifest.get("fatal_failures"):
        raise ManifestError("fatal_failures changed since the source evaluation")
    if summary.get("rubrics") != manifest.get("rubrics"):
        raise ManifestError("rubrics changed since the source evaluation")
    current_cases = {case["id"]: case for case in cases}
    raw_results = summary.get("results")
    if not isinstance(raw_results, list) or not raw_results:
        raise ManifestError("rescore source must contain results")
    seen_keys: set[tuple[str, int]] = set()
    rescored_results: list[dict[str, Any]] = []
    changed_cases: set[str] = set()
    for index, raw_result in enumerate(raw_results):
        if not isinstance(raw_result, dict):
            raise ManifestError(f"results[{index}] must be an object")
        case_id = raw_result.get("case_id")
        repetition = raw_result.get("repetition")
        if not isinstance(case_id, str) or case_id not in current_cases:
            raise ManifestError(f"results[{index}] has an unknown case_id")
        current_case = current_cases[case_id]
        if (
            not isinstance(repetition, int)
            or isinstance(repetition, bool)
            or not 1 <= repetition <= current_case["repetitions"]
        ):
            raise ManifestError(f"{case_id}: invalid repetition {repetition!r}")
        run_key = (case_id, repetition)
        if run_key in seen_keys:
            raise ManifestError(f"duplicate run key: {case_id}#{repetition}")
        seen_keys.add(run_key)
        changed, checks, current_rules = _validate_rescore_source_result(
            raw_result, current_case
        )
        allowed_index = next(
            index for index, check in enumerate(checks) if check.get("name") == "allowed_paths"
        )
        new_passed, new_details = _allowed_paths_check(
            changed, current_rules["allowed_changes"]
        )
        checks[allowed_index] = {
            **checks[allowed_index],
            "passed": new_passed,
            "details": new_details,
        }
        failures = [
            str(check.get("name")) for check in checks if check.get("passed") is not True
        ]
        detected = automatically_detected_hard_failures(current_case, checks, changed)
        rescored = copy.deepcopy(raw_result)
        rescored["file_expectations"] = copy.deepcopy(current_rules)
        rescored["automatic_checks"] = checks
        rescored["automatic_failures"] = failures
        rescored["detected_fatal_failures"] = detected
        rescored["automatic_pass"] = not failures
        rescored["automatic_fatal_pass"] = automatic_fatal_pass(failures, detected)
        changed_fields = {
            field
            for field in set(raw_result) | set(rescored)
            if raw_result.get(field) != rescored.get(field)
        }
        if not changed_fields <= ALLOWLIST_DERIVED_RESULT_FIELDS:
            raise ManifestError(
                f"{case_id}: rescore attempted forbidden result changes: {sorted(changed_fields)}"
            )
        if raw_result.get("file_expectations", {}).get("allowed_changes") != current_rules.get(
            "allowed_changes"
        ):
            changed_cases.add(case_id)
        rescored_results.append(rescored)

    selected_case_ids = {case_id for case_id, _ in seen_keys}
    expected_run_keys = {
        (case_id, repetition)
        for case_id in selected_case_ids
        for repetition in range(1, current_cases[case_id]["repetitions"] + 1)
    }
    if seen_keys != expected_run_keys:
        missing = sorted(expected_run_keys - seen_keys)
        unexpected = sorted(seen_keys - expected_run_keys)
        raise ManifestError(
            "rescore source is incomplete for its selected cases: "
            f"missing={missing}, unexpected={unexpected}"
        )

    old_manifest_sha = summary.get("manifest_sha256")
    if not isinstance(old_manifest_sha, str) or re.fullmatch(r"[0-9a-f]{64}", old_manifest_sha) is None:
        raise ManifestError("source summary has an invalid manifest_sha256")
    new_manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    rescored_summary = copy.deepcopy(summary)
    rescored_summary["manifest_sha256"] = new_manifest_sha
    rescored_summary["automatic_fatal_policy_id"] = AUTOMATIC_FATAL_POLICY_ID
    rescored_summary["results"] = rescored_results
    rescored_summary["allowlist_rescore"] = {
        "mode": ALLOWLIST_RESCORE_MODE,
        "source_summary_sha256": hashlib.sha256(raw_summary).hexdigest(),
        "source_manifest_sha256": old_manifest_sha,
        "target_manifest_sha256": new_manifest_sha,
        "rescored_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "automatic_fatal_policy_id": AUTOMATIC_FATAL_POLICY_ID,
        "changed_cases": sorted(changed_cases),
    }
    return rescored_summary


def write_new_summary_atomic(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    if path.exists() or path.is_symlink():
        raise ManifestError(f"rescore output must be a new path: {path}")
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ManifestError(f"rescore output parent must be an existing real directory: {parent}")
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary = parent / f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}"
    published = False
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.stat().st_nlink != 1:
            raise ManifestError("rescore temporary output unexpectedly has hard links")
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ManifestError(f"rescore output already exists: {path}") from exc
        published = True
        temporary.unlink()
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ManifestError("rescore output is not a single-link regular file")
    except Exception:
        if temporary.exists():
            temporary.unlink()
        if published and path.exists():
            path.unlink()
        raise


def automatic_fatal_pass(
    automatic_failures: list[str], detected_fatal_failures: list[str]
) -> bool:
    nonfatal_prefixes = ("output_must_match:", "output_must_not_match:")
    fatal_relevant = [
        failure
        for failure in automatic_failures
        if failure != "tool_execution"
        and not failure.startswith(nonfatal_prefixes)
    ]
    return not fatal_relevant and not detected_fatal_failures


def run_validator(root: Path) -> dict[str, Any]:
    script = root / ".agents/skills/kaoyan-math1-fullscore-coach/scripts/validate_math1_repo.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--root", str(root), "--no-compile", "--format", "json"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )
    return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def prompt_stack_digest(root: Path) -> str:
    paths = [root / relative for relative in PROMPT_STACK_FILES]
    reference_root = root / ".agents/skills/kaoyan-math1-fullscore-coach/references"
    if reference_root.is_dir():
        paths.extend(sorted(path for path in reference_root.rglob("*") if path.is_file()))
    digest = hashlib.sha256()
    for path in paths:
        if path.exists():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, content in sorted(file_state(root).items()):
        digest.update(relative.encode())
        digest.update(content)
    return digest.hexdigest()


def event_metrics(jsonl: str, stderr: str = "") -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for line in jsonl.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)

    aliases = {
        "input_tokens": "input_tokens",
        "cached_input_tokens": "cached_input_tokens",
        "output_tokens": "output_tokens",
        "reasoning_tokens": "reasoning_tokens",
        "reasoning_output_tokens": "reasoning_tokens",
        "total_tokens": "total_tokens",
    }
    usage = {name: 0 for name in set(aliases.values())}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                canonical = aliases.get(key)
                if canonical and isinstance(child, (int, float)):
                    usage[canonical] = max(usage[canonical], int(child))
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(events)
    if not usage["total_tokens"]:
        usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    usage_complete = usage["total_tokens"] > 0

    tool_ids: set[str] = set()
    anonymous_tools = 0
    turns = 0
    failed_tools: list[str] = []
    successful_commands: list[str] = []
    successful_command_outputs: list[str] = []
    for event in events:
        event_type = str(event.get("type", ""))
        if event_type in {"turn.completed", "turn.failed"}:
            turns += 1
        if event_type == "turn.failed":
            failed_tools.append(str(event.get("error") or "turn.failed"))
        item = event.get("item")
        if not isinstance(item, dict) or not event_type.endswith("completed"):
            continue
        item_type = str(item.get("type", ""))
        is_tool = "tool" in item_type or item_type in {
            "command_execution",
            "file_change",
            "mcp_call",
            "web_search",
        }
        if is_tool:
            item_id = item.get("id")
            if isinstance(item_id, str):
                tool_ids.add(item_id)
            else:
                anonymous_tools += 1
            if item_type != "command_execution" and (
                item.get("status") == "failed" or item.get("error")
            ):
                failed_tools.append(
                    f"{item_type or 'tool'}: {item.get('error') or item.get('status')}"
                )
        if item_type == "command_execution":
            command = str(item.get("command", ""))
            output = str(item.get("aggregated_output", ""))
            exit_code = item.get("exit_code")
            failed = item.get("status") == "failed" or not isinstance(exit_code, int) or exit_code != 0
            if failed:
                failure = f"{command} (exit={exit_code})"
                if failure not in failed_tools:
                    failed_tools.append(failure)
            else:
                successful_commands.append(command)
                successful_command_outputs.append(output)
    for match in re.finditer(
        r"(?m)^.*\bERROR\b.*\btools::router:\s*error=([^\r\n]+)",
        stderr,
    ):
        failure = f"router: {match.group(1).strip()}"
        if failure not in failed_tools:
            failed_tools.append(failure)
    skill_loaded = any(
        "kaoyan-math1-fullscore-coach" in command
        and "SKILL.md" in command
        and "name: kaoyan-math1-fullscore-coach" in output
        for command, output in zip(successful_commands, successful_command_outputs)
    )
    model_validator_succeeded = any(
        "validate_math1_repo.py" in command
        and re.search(r"RESULT:\s*PASS", output, flags=re.IGNORECASE)
        for command, output in zip(successful_commands, successful_command_outputs)
    )
    return {
        "events": len(events),
        "turns": turns,
        "tool_calls": len(tool_ids) + anonymous_tools,
        "usage": usage,
        "usage_complete": usage_complete,
        "failed_tools": failed_tools,
        "successful_command_count": len(successful_commands),
        "skill_loaded": skill_loaded,
        "model_validator_succeeded": model_validator_succeeded,
    }


def run_case(
    case: dict[str, Any],
    repetition: int,
    args: argparse.Namespace,
    output_dir: Path,
    frozen_root: Path,
    frozen_digest: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"math1-eval-{case['id']}-") as temporary:
        root = Path(temporary) / "repo"
        shutil.copytree(frozen_root, root)
        apply_fixture(root, case["fixture"])
        initialize_snapshot_git(root)
        before = file_state(root)
        stack_digest = prompt_stack_digest(root)
        final_path = output_dir / f"{case['id']}-{repetition}-final.md"
        events_path = output_dir / f"{case['id']}-{repetition}-events.jsonl"
        evaluation_prompt = (
            "你正在一个一次性的隔离仓库快照中工作，只能处理当前仓库。"
            "先实际读取仓库 AGENTS.md 与唯一数学 Skill，再完成用户任务和必要验证；"
            "不要访问仓库外路径，不要提交、推送或部署。"
            + (
                "当前执行器位于 WSL；PowerShell 示例不可用时，使用 python3 运行同一个 validator。"
                if args.runner == "wsl"
                else ""
            )
            + "\n\n用户任务：\n"
            + case["prompt"]
        )
        command = build_codex_command(root, final_path, args)
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            input=evaluation_prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=args.timeout + (30 if args.runner == "wsl" else 0),
            env=sanitized_environment(),
        )
        elapsed = time.perf_counter() - started
        events_path.write_text(completed.stdout, encoding="utf-8", newline="\n")
        final_message = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
        after = file_state(root)
        paths = changed_paths(before, after)
        diff = render_diff(before, after, paths)
        diff_path = output_dir / f"{case['id']}-{repetition}.diff"
        diff_path.write_text(diff, encoding="utf-8", newline="\n")
        validation = run_validator(root) if case["file_expectations"].get("post_validate") else None
        metrics = event_metrics(completed.stdout, completed.stderr)
        checks = automatic_checks(
            case,
            final_message,
            diff,
            paths,
            completed.returncode,
            validation,
            metrics,
        )
        automatic_failures = [
            check["name"] for check in checks if not check["passed"]
        ]
        detected_fatal_failures = automatically_detected_hard_failures(case, checks, paths)
        return {
            "case_id": case["id"],
            "repetition": repetition,
            "slice": case["slice"],
            "model": args.model,
            "effort": args.effort,
            "snapshot": args.snapshot,
            "prompt_source": args.prompt_source,
            "runner": args.runner,
            "runner_isolation": runner_isolation(args.runner),
            "sandbox": args.sandbox,
            "frozen_tree_sha256": frozen_digest,
            "elapsed_seconds": round(elapsed, 3),
            "prompt_stack_sha256": stack_digest,
            "event_count": metrics["events"],
            "turn_count": metrics["turns"],
            "tool_call_count": metrics["tool_calls"],
            "successful_command_count": metrics["successful_command_count"],
            "failed_tools": metrics["failed_tools"],
            "skill_loaded": metrics["skill_loaded"],
            "model_validator_succeeded": metrics["model_validator_succeeded"],
            "usage": metrics["usage"],
            "usage_complete": metrics["usage_complete"],
            "changed_paths": paths,
            "automatic_pass": not automatic_failures,
            "automatic_fatal_pass": automatic_fatal_pass(
                automatic_failures, detected_fatal_failures
            ),
            "automatic_failures": automatic_failures,
            "detected_fatal_failures": detected_fatal_failures,
            "automatic_checks": checks,
            "oracle": case["oracle"],
            "prompt": case["prompt"],
            "expected": case["expected"],
            "task_kind": case.get("task_kind"),
            "case_repetitions": case["repetitions"],
            "smoke": bool(case.get("smoke")),
            "fixture": case["fixture"],
            "file_expectations": case["file_expectations"],
            "checks_spec": case["checks"],
            "rubric": case["rubric"],
            "hard_fail_if": case.get("hard_fail_if", []),
            "human_rubric_scores": None,
            "human_fatal_reviewed": False,
            "human_fatal_failures": None,
            "human_notes": None,
            "human_review_package_id": None,
            "human_review_id": None,
            "stderr": completed.stderr,
            "validation": validation,
        }


def validate_reclassifiable_summary(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict) or summary.get("schema_version") != 1:
        raise SummaryError("input must be a complete schema_version: 1 summary object")

    required_summary_fields = {
        "created_at",
        "repo_head",
        "model",
        "effort",
        "snapshot",
        "prompt_source",
        "runner",
        "runner_isolation",
        "sandbox",
        "base_tree_sha256",
        "frozen_tree_sha256",
        "prompt_stack_sha256",
        "manifest_sha256",
        "fatal_failures",
        "rubrics",
        "automatic_fatal_policy_id",
        "results",
    }
    missing = sorted(required_summary_fields - set(summary))
    if missing:
        raise SummaryError(f"summary is incomplete; missing fields: {', '.join(missing)}")

    for field in (
        "created_at",
        "repo_head",
        "model",
        "effort",
        "snapshot",
        "prompt_source",
        "runner",
        "runner_isolation",
        "sandbox",
        "base_tree_sha256",
        "manifest_sha256",
    ):
        if not isinstance(summary.get(field), str) or not summary[field].strip():
            raise SummaryError(f"summary.{field} must be a non-empty string")
    for field in ("frozen_tree_sha256", "prompt_stack_sha256"):
        if summary.get(field) is not None and (
            not isinstance(summary[field], str) or not summary[field].strip()
        ):
            raise SummaryError(f"summary.{field} must be null or a non-empty string")

    fatal_taxonomy = summary.get("fatal_failures")
    if (
        not isinstance(fatal_taxonomy, list)
        or not fatal_taxonomy
        or any(not isinstance(value, str) or not value for value in fatal_taxonomy)
        or len(fatal_taxonomy) != len(set(fatal_taxonomy))
    ):
        raise SummaryError("summary.fatal_failures must be a non-empty unique string array")
    rubrics = summary.get("rubrics")
    if not isinstance(rubrics, dict) or not rubrics or any(
        not isinstance(name, str)
        or not name
        or not isinstance(weights, dict)
        or not weights
        for name, weights in rubrics.items()
    ):
        raise SummaryError("summary.rubrics must be a non-empty rubric mapping")

    results = summary.get("results")
    if not isinstance(results, list) or not results:
        raise SummaryError("summary.results must be a non-empty array")
    required_result_fields = {
        "case_id",
        "repetition",
        "slice",
        "automatic_pass",
        "automatic_fatal_pass",
        "detected_fatal_failures",
        "usage",
        "usage_complete",
        "prompt",
        "expected",
        "fixture",
        "file_expectations",
        "oracle",
        "rubric",
        "hard_fail_if",
    }
    seen: set[tuple[str, int]] = set()
    for index, result in enumerate(results):
        label = f"summary.results[{index}]"
        if not isinstance(result, dict):
            raise SummaryError(f"{label} must be an object")
        missing = sorted(required_result_fields - set(result))
        if missing:
            raise SummaryError(f"{label} is incomplete; missing fields: {', '.join(missing)}")
        case_id = result.get("case_id")
        repetition = result.get("repetition")
        if not isinstance(case_id, str) or not case_id:
            raise SummaryError(f"{label}.case_id must be a non-empty string")
        if not isinstance(repetition, int) or isinstance(repetition, bool) or repetition < 1:
            raise SummaryError(f"{label}.repetition must be a positive integer")
        key = (case_id, repetition)
        if key in seen:
            raise SummaryError(f"summary contains duplicate run key {case_id}#{repetition}")
        seen.add(key)
        for field in ("slice", "prompt", "rubric"):
            if not isinstance(result.get(field), str) or not result[field].strip():
                raise SummaryError(f"{label}.{field} must be a non-empty string")
        if result["rubric"] not in rubrics:
            raise SummaryError(f"{label}.rubric references an unknown rubric")
        for field in ("automatic_pass", "automatic_fatal_pass", "usage_complete"):
            if not isinstance(result.get(field), bool):
                raise SummaryError(f"{label}.{field} must be boolean")
        for field in ("expected", "fixture", "file_expectations", "oracle", "usage"):
            if not isinstance(result.get(field), dict):
                raise SummaryError(f"{label}.{field} must be an object")
        hard_failures = result.get("hard_fail_if")
        if (
            not isinstance(hard_failures, list)
            or any(not isinstance(value, str) or not value for value in hard_failures)
            or not set(hard_failures) <= set(fatal_taxonomy)
        ):
            raise SummaryError(f"{label}.hard_fail_if is invalid")
        detected = result.get("detected_fatal_failures")
        if not isinstance(detected, list) or any(
            not isinstance(value, str) or not value for value in detected
        ):
            raise SummaryError(f"{label}.detected_fatal_failures must be a string array")
        if "harness_error" in result:
            if not isinstance(result["harness_error"], str) or not result["harness_error"].strip():
                raise SummaryError(f"{label}.harness_error must be a non-empty string")
            if "harness_error" not in detected:
                raise SummaryError(f"{label} must classify its harness_error")
        else:
            failures = result.get("automatic_failures")
            if not isinstance(failures, list) or any(
                not isinstance(value, str) or not value for value in failures
            ):
                raise SummaryError(f"{label}.automatic_failures must be a string array")
    return summary


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def reclassify_summary(input_path: Path, output_path: Path) -> dict[str, Any]:
    source = input_path.resolve(strict=True)
    destination = output_path.resolve(strict=False)
    if source == destination or (output_path.exists() and os.path.samefile(source, output_path)):
        raise SummaryError("reclassification output must not overwrite its input summary")

    source_bytes = source.read_bytes()
    summary = validate_reclassifiable_summary(json.loads(source_bytes))
    reclassified = copy.deepcopy(summary)
    for result in reclassified["results"]:
        if "harness_error" in result:
            result["automatic_fatal_pass"] = False
            continue
        result["automatic_fatal_pass"] = automatic_fatal_pass(
            result["automatic_failures"], result["detected_fatal_failures"]
        )
    reclassified["source_summary_sha256"] = hashlib.sha256(source_bytes).hexdigest()
    reclassified["reclassified_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    reclassified["automatic_fatal_policy_id"] = AUTOMATIC_FATAL_POLICY_ID
    atomic_write_json(destination, reclassified)
    return reclassified


def compare_summaries(
    baseline_path: Path, candidate_path: Path, mode: str = "prompt"
) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))

    for field in (
        "manifest_sha256",
        "model",
        "snapshot",
        "runner",
        "runner_isolation",
        "sandbox",
        "base_tree_sha256",
        "fatal_failures",
        "rubrics",
    ):
        if baseline.get(field) != candidate.get(field):
            raise ValueError(f"incompatible summaries: {field} differs")
    fatal_taxonomy = baseline.get("fatal_failures")
    if (
        not isinstance(fatal_taxonomy, list)
        or not fatal_taxonomy
        or any(not isinstance(value, str) or not value for value in fatal_taxonomy)
        or len(fatal_taxonomy) != len(set(fatal_taxonomy))
    ):
        raise ValueError("invalid non-empty unique fatal taxonomy")
    if not isinstance(baseline.get("runner_isolation"), str) or not baseline["runner_isolation"]:
        raise ValueError("summary is missing runner isolation metadata")
    if mode == "prompt":
        if baseline.get("effort") != candidate.get("effort"):
            raise ValueError("incompatible prompt comparison: effort differs")
        if baseline.get("prompt_stack_sha256") == candidate.get("prompt_stack_sha256"):
            raise ValueError("incompatible prompt comparison: prompt stacks are identical")
    elif mode == "effort":
        if baseline.get("prompt_stack_sha256") != candidate.get("prompt_stack_sha256"):
            raise ValueError("incompatible effort comparison: prompt stacks differ")
        if baseline.get("effort") == candidate.get("effort"):
            raise ValueError("incompatible effort comparison: effort is identical")
    else:
        raise ValueError(f"unknown comparison mode: {mode}")

    def run_keys(summary: dict[str, Any]) -> list[tuple[str, int]]:
        keys = [
            (str(result.get("case_id")), int(result.get("repetition", 0)))
            for result in summary.get("results", [])
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("summary contains duplicate case/repetition keys")
        return sorted(keys)

    if run_keys(baseline) != run_keys(candidate):
        raise ValueError("incompatible summaries: case/repetition sets differ")

    rubrics = baseline["rubrics"]

    def result_map(summary: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
        return {
            (str(result.get("case_id")), int(result.get("repetition", 0))): result
            for result in summary.get("results", [])
        }

    baseline_results = result_map(baseline)
    candidate_results = result_map(candidate)
    for key in sorted(baseline_results):
        old_result = baseline_results[key]
        new_result = candidate_results[key]
        for field in (
            "slice",
            "rubric",
            "oracle",
            "hard_fail_if",
            "prompt",
            "expected",
            "task_kind",
            "case_repetitions",
            "smoke",
            "fixture",
            "file_expectations",
            "checks_spec",
        ):
            if old_result.get(field) != new_result.get(field):
                raise ValueError(
                    f"incompatible summaries: {key[0]}#{key[1]} field {field} differs"
                )
        hard_failures = old_result.get("hard_fail_if")
        if (
            not isinstance(hard_failures, list)
            or not hard_failures
            or any(not isinstance(value, str) for value in hard_failures)
            or not set(hard_failures) <= set(fatal_taxonomy)
        ):
            raise ValueError(
                f"incompatible summaries: {key[0]}#{key[1]} has invalid hard_fail_if"
            )

    def valid_attestation(summary: dict[str, Any]) -> dict[str, Any] | None:
        value = summary.get("human_review_attestation")
        if not isinstance(value, dict):
            return None
        if (
            value.get("reviewer_type") != "human"
            or value.get("attested") is not True
            or not isinstance(value.get("reviewer"), str)
            or not value["reviewer"].strip()
            or not isinstance(value.get("package_id"), str)
            or not value["package_id"].strip()
            or not isinstance(value.get("reviewed_at"), str)
            or not value["reviewed_at"].strip()
            or not isinstance(value.get("review_package_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", value["review_package_sha256"]) is None
            or not isinstance(value.get("input_summary_sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", value["input_summary_sha256"]) is None
        ):
            return None
        return value

    baseline_attestation = valid_attestation(baseline)
    candidate_attestation = valid_attestation(candidate)
    if baseline_attestation is not None and candidate_attestation is not None:
        for field in (
            "package_id",
            "reviewer",
            "reviewer_type",
            "reviewed_at",
            "review_package_sha256",
        ):
            if baseline_attestation.get(field) != candidate_attestation.get(field):
                raise ValueError(f"incompatible human review attestations: {field} differs")

    def fatal_review(
        result: dict[str, Any], attestation: dict[str, Any] | None
    ) -> list[str] | None:
        fatal = result.get("human_fatal_failures")
        if (
            attestation is None
            or result.get("human_fatal_reviewed") is not True
            or not isinstance(fatal, list)
            or not isinstance(result.get("human_review_package_id"), str)
            or not isinstance(result.get("human_review_id"), str)
            or result.get("human_review_package_id") != attestation.get("package_id")
            or any(
                not isinstance(item, str)
                or item not in set(fatal_taxonomy)
                for item in fatal
            )
        ):
            return None
        return [str(item) for item in fatal]

    def reviewed_score(
        result: dict[str, Any], attestation: dict[str, Any] | None
    ) -> tuple[float, list[str]] | None:
        scores = result.get("human_rubric_scores")
        fatal = fatal_review(result, attestation)
        rubric = rubrics.get(result.get("rubric"))
        if not isinstance(scores, dict) or not isinstance(fatal, list) or not isinstance(rubric, dict):
            return None
        if set(scores) != set(rubric):
            return None
        if any(
            not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100
            for value in scores.values()
        ):
            return None
        weighted = sum(float(scores[name]) * float(weight) for name, weight in rubric.items()) / 100
        return weighted, [str(item) for item in fatal]

    def aggregate(
        summary: dict[str, Any], attestation: dict[str, Any] | None
    ) -> dict[str, Any]:
        results = summary.get("results", [])
        slices: dict[str, dict[str, Any]] = {}
        elapsed = 0.0
        tokens = 0
        token_metrics_complete = True
        human_scores: list[float] = []
        human_fatal_failures: list[str] = []
        human_review_keys: list[tuple[str, int]] = []
        fatal_review_keys: list[tuple[str, int]] = []
        for result in results:
            key = (str(result.get("case_id")), int(result.get("repetition", 0)))
            name = str(result.get("slice", "unknown"))
            bucket = slices.setdefault(
                name,
                {"passed": 0, "fatal_passed": 0, "total": 0, "human_scores": []},
            )
            bucket["total"] += 1
            bucket["passed"] += int(bool(result.get("automatic_pass")))
            bucket["fatal_passed"] += int(bool(result.get("automatic_fatal_pass")))
            elapsed += float(result.get("elapsed_seconds", 0))
            usage = result.get("usage") or {}
            total_tokens = usage.get("total_tokens")
            valid_tokens = (
                isinstance(total_tokens, (int, float))
                and not isinstance(total_tokens, bool)
                and int(total_tokens) > 0
                and result.get("usage_complete") is not False
            )
            if valid_tokens:
                tokens += int(total_tokens)
            else:
                token_metrics_complete = False
            fatal = fatal_review(result, attestation)
            if fatal is not None:
                fatal_review_keys.append(key)
                human_fatal_failures.extend(fatal)
            reviewed = reviewed_score(result, attestation)
            if reviewed is not None:
                score, fatal = reviewed
                human_scores.append(score)
                bucket["human_scores"].append(score)
                human_review_keys.append(key)
        slice_summary = {}
        for name, bucket in sorted(slices.items()):
            scores = bucket.pop("human_scores")
            slice_summary[name] = {
                **bucket,
                "pass_rate": bucket["passed"] / bucket["total"],
                "fatal_pass_rate": bucket["fatal_passed"] / bucket["total"],
                "human_score_mean": sum(scores) / len(scores) if scores else None,
                "human_review_count": len(scores),
            }
        return {
            "runs": len(results),
            "automatic_passes": sum(int(bool(result.get("automatic_pass"))) for result in results),
            "automatic_all_pass": bool(results) and all(bool(result.get("automatic_pass")) for result in results),
            "automatic_fatal_all_pass": bool(results)
            and all(bool(result.get("automatic_fatal_pass")) for result in results),
            "slices": slice_summary,
            "elapsed_seconds": round(elapsed, 3),
            "total_tokens": tokens,
            "token_metrics_complete": token_metrics_complete,
            "human_review_count": len(human_scores),
            "human_score_mean": sum(human_scores) / len(human_scores) if human_scores else None,
            "human_fatal_failures": human_fatal_failures,
            "human_review_keys": human_review_keys,
            "fatal_review_count": len(fatal_review_keys),
            "fatal_review_keys": fatal_review_keys,
        }

    old = aggregate(baseline, baseline_attestation)
    new = aggregate(candidate, candidate_attestation)
    if set(old["human_review_keys"]) != set(new["human_review_keys"]):
        raise ValueError("incompatible summaries: human-reviewed run sets differ")
    if set(old["fatal_review_keys"]) != set(new["fatal_review_keys"]):
        raise ValueError("incompatible summaries: fatal-reviewed run sets differ")
    for key in set(old["human_review_keys"]) | set(old["fatal_review_keys"]):
        old_result = baseline_results[key]
        new_result = candidate_results[key]
        for field in ("human_review_package_id", "human_review_id"):
            if old_result.get(field) != new_result.get(field):
                raise ValueError(f"incompatible human review mapping for {key[0]}#{key[1]}")

    required_slices = set(old["slices"])
    slice_review_coverage = bool(required_slices) and all(
        old["slices"][name]["human_review_count"] > 0
        and new["slices"][name]["human_review_count"] > 0
        for name in required_slices
    )
    slice_quality_drops = {
        name: old["slices"][name]["human_score_mean"]
        - new["slices"][name]["human_score_mean"]
        for name in sorted(required_slices)
        if old["slices"][name]["human_score_mean"] is not None
        and new["slices"][name]["human_score_mean"] is not None
    }
    slice_quality_gate: bool | None = None
    if slice_review_coverage:
        slice_quality_gate = all(drop <= 2.0 for drop in slice_quality_drops.values())
    deterministic_gate = new["automatic_fatal_all_pass"]

    quality_gate: bool | None = None
    quality_reason = "pending human scores"
    old_quality = old["human_score_mean"]
    new_quality = new["human_score_mean"]
    review_coverage = (
        old["runs"] > 0
        and new["runs"] > 0
        and old["human_review_count"] / old["runs"] >= 0.20
        and new["human_review_count"] / new["runs"] >= 0.20
        and set(old["human_review_keys"]) == set(new["human_review_keys"])
    )
    paired_success_keys = [
        key
        for key in sorted(baseline_results)
        if baseline_results[key].get("automatic_pass") is True
        and candidate_results[key].get("automatic_pass") is True
    ]

    def valid_total(result: dict[str, Any]) -> int | None:
        usage = result.get("usage")
        if not isinstance(usage, dict):
            return None
        value = usage.get("total_tokens")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or int(value) <= 0
            or result.get("usage_complete") is False
        ):
            return None
        return int(value)

    paired_token_values = [
        (valid_total(baseline_results[key]), valid_total(candidate_results[key]))
        for key in paired_success_keys
    ]
    token_metrics_complete = bool(paired_token_values) and all(
        old_value is not None and new_value is not None
        for old_value, new_value in paired_token_values
    )
    old_success_tokens = (
        sum(int(old_value) for old_value, _ in paired_token_values if old_value is not None)
        if token_metrics_complete
        else None
    )
    new_success_tokens = (
        sum(int(new_value) for _, new_value in paired_token_values if new_value is not None)
        if token_metrics_complete
        else None
    )
    token_ratio = (
        new_success_tokens / old_success_tokens
        if old_success_tokens is not None and old_success_tokens > 0 and new_success_tokens is not None
        else None
    )
    if (
        old_quality is not None
        and new_quality is not None
        and review_coverage
        and slice_quality_gate is True
        and token_ratio is not None
    ):
        improved = new_quality >= old_quality + 5 and token_ratio <= 1.10
        efficient = new_quality >= old_quality - 2 and token_ratio <= 0.80
        quality_gate = improved or efficient
        quality_reason = "quality +5 within 10% cost, or quality non-inferior within 2 and tokens -20%"

    human_fatal_coverage = (
        old["runs"] > 0
        and new["runs"] > 0
        and old["fatal_review_count"] == old["runs"]
        and new["fatal_review_count"] == new["runs"]
    )
    human_fatal_gate: bool | None = None
    if human_fatal_coverage:
        human_fatal_gate = not new["human_fatal_failures"]

    if (
        not deterministic_gate
        or human_fatal_gate is False
        or quality_gate is False
        or slice_quality_gate is False
    ):
        verdict = "fail"
    elif (
        quality_gate is True
        and human_fatal_gate is True
        and slice_quality_gate is True
        and baseline_attestation is not None
        and candidate_attestation is not None
    ):
        verdict = "pass"
    else:
        verdict = "pending_human_review"

    return {
        "baseline": old,
        "candidate": new,
        "comparison_mode": mode,
        "slice_human_score_drop": slice_quality_drops,
        "slice_human_review_coverage_met": slice_review_coverage,
        "slice_quality_gate": slice_quality_gate,
        "deterministic_gate": deterministic_gate,
        "human_review_coverage_met": review_coverage,
        "human_fatal_coverage_met": human_fatal_coverage,
        "human_fatal_gate": human_fatal_gate,
        "paired_successful_run_count": len(paired_success_keys),
        "token_metrics_complete": token_metrics_complete,
        "baseline_success_tokens": old_success_tokens,
        "candidate_success_tokens": new_success_tokens,
        "token_ratio": token_ratio,
        "quality_gate": quality_gate,
        "quality_gate_reason": quality_reason,
        "verdict": verdict,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run math Skill forward evaluations in disposable repository snapshots.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--list", action="store_true", help="List selected cases (the default behavior).")
    parser.add_argument("--run", action="store_true", help="Explicitly run Codex in disposable snapshots.")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BASELINE", "CANDIDATE"), help="Compare two summary.json files without model calls.")
    parser.add_argument(
        "--reclassify",
        nargs=2,
        type=Path,
        metavar=("INPUT", "OUTPUT"),
        help="Recompute automatic fatal flags in a complete summary without model calls.",
    )
    parser.add_argument(
        "--rescore-allowlist",
        nargs=2,
        type=Path,
        metavar=("INPUT", "OUTPUT"),
        help=(
            "Offline-only: permit changes solely to file_expectations.allowed_changes, "
            "then re-score stored changed_paths into a new summary."
        ),
    )
    parser.add_argument(
        "--comparison-mode",
        choices=("prompt", "effort"),
        default="prompt",
        help="Require same effort for prompt A/B, or same prompt stack for effort A/B.",
    )
    parser.add_argument("--case", action="append", help="Select a case id; repeat to select more than one.")
    parser.add_argument("--slice", choices=("math", "teaching", "persistence"))
    parser.add_argument("--smoke", action="store_true", help="Select the 8-case smoke suite.")
    parser.add_argument("--snapshot", choices=("head", "worktree"), default="worktree")
    parser.add_argument(
        "--prompt-source",
        choices=("snapshot", "head", "worktree"),
        default="snapshot",
        help="Overlay only AGENTS/Skill/reference files after freezing the base snapshot.",
    )
    parser.add_argument(
        "--runner",
        choices=("native", "wsl"),
        default="wsl" if os.name == "nt" and shutil.which("wsl.exe") else "native",
        help="Use WSL on Windows so workspace-write has a real OS sandbox.",
    )
    parser.add_argument(
        "--sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default="workspace-write",
    )
    parser.add_argument(
        "--acknowledge-unsandboxed-native",
        action="store_true",
        help="Required for native danger-full-access evaluation runs.",
    )
    parser.add_argument("--model", default=os.environ.get("CODEX_EVAL_MODEL", "gpt-5.6-sol"))
    parser.add_argument("--effort", default=os.environ.get("CODEX_EVAL_EFFORT", "max"))
    parser.add_argument("--timeout", type=int, default=900, help="Per-run timeout in seconds.")
    parser.add_argument("--output-dir", type=Path, help="Result directory; defaults to the OS temporary directory.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if sum(
        (
            bool(args.run),
            bool(args.list),
            bool(args.compare),
            bool(args.reclassify),
            bool(args.rescore_allowlist),
        )
    ) > 1:
        print(
            "error: choose one of --list, --run, --compare, --reclassify or --rescore-allowlist",
            file=sys.stderr,
        )
        return 2
    if args.rescore_allowlist:
        try:
            source, output = args.rescore_allowlist
            rescored = rescore_allowlist_summary(source, args.manifest)
            if source.resolve(strict=True) == output.resolve(strict=False):
                raise ManifestError("rescore output must not overwrite its source")
            write_new_summary_atomic(output, rescored)
        except (OSError, json.JSONDecodeError, TypeError, ValueError, yaml.YAMLError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        provenance = rescored["allowlist_rescore"]
        print(
            "ALLOWLIST RESCORED "
            f"{len(rescored['results'])} runs with policy "
            f"{provenance['automatic_fatal_policy_id']}: {output}"
        )
        return 0
    if args.reclassify:
        try:
            reclassified = reclassify_summary(*args.reclassify)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(
            "RECLASSIFIED "
            f"{len(reclassified['results'])} runs with policy "
            f"{reclassified['automatic_fatal_policy_id']}: {args.reclassify[1]}"
        )
        return 0
    if args.compare:
        try:
            comparison = compare_summaries(*args.compare, mode=args.comparison_mode)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(comparison, ensure_ascii=False, indent=2))
        if comparison["verdict"] == "pass":
            return 0
        return 3 if comparison["verdict"] == "pending_human_review" else 1
    try:
        manifest, cases = load_manifest(args.manifest)
        chosen = selected_cases(cases, args)
    except (OSError, yaml.YAMLError, ManifestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.run:
        for case in chosen:
            marker = "smoke" if case.get("smoke") else "full"
            print(f"{case['id']}\t{case['slice']}\t{marker}\tx{case['repetitions']}")
        runs = sum(case["repetitions"] for case in chosen)
        print(f"LIST ONLY: {len(chosen)} cases, {runs} runs. Pass --run to execute isolated model calls.")
        return 0

    if (
        args.runner == "native"
        and args.sandbox == "danger-full-access"
        and not args.acknowledge_unsandboxed_native
    ):
        print(
            "error: native danger-full-access requires --acknowledge-unsandboxed-native",
            file=sys.stderr,
        )
        return 2

    try:
        if args.runner == "wsl":
            require_wsl_bwrap()
        output_dir = prepare_output_directory(args.output_dir)
    except (OSError, RuntimeError, ManifestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False
    ).stdout.strip()
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="math1-eval-frozen-") as frozen_temporary:
        frozen_root = Path(frozen_temporary) / "repo"
        make_snapshot(args.snapshot, frozen_root)
        base_digest = tree_digest(frozen_root)
        apply_prompt_overlay(args.prompt_source, frozen_root)
        frozen_digest = tree_digest(frozen_root)
        for case in chosen:
            for repetition in range(1, case["repetitions"] + 1):
                print(f"RUN {case['id']} [{repetition}/{case['repetitions']}]", flush=True)
                try:
                    result = run_case(
                        case,
                        repetition,
                        args,
                        output_dir,
                        frozen_root,
                        frozen_digest,
                    )
                except (OSError, RuntimeError, ManifestError, subprocess.TimeoutExpired) as exc:
                    result = {
                        "case_id": case["id"],
                        "repetition": repetition,
                        "slice": case["slice"],
                        "model": args.model,
                        "effort": args.effort,
                        "snapshot": args.snapshot,
                        "prompt_source": args.prompt_source,
                        "runner": args.runner,
                        "runner_isolation": runner_isolation(args.runner),
                        "sandbox": args.sandbox,
                        "frozen_tree_sha256": frozen_digest,
                        "automatic_pass": False,
                        "automatic_fatal_pass": False,
                        "detected_fatal_failures": ["harness_error"],
                        "harness_error": str(exc),
                        "prompt": case["prompt"],
                        "expected": case["expected"],
                        "task_kind": case.get("task_kind"),
                        "case_repetitions": case["repetitions"],
                        "smoke": bool(case.get("smoke")),
                        "fixture": case["fixture"],
                        "file_expectations": case["file_expectations"],
                        "checks_spec": case["checks"],
                        "oracle": case["oracle"],
                        "rubric": case["rubric"],
                        "hard_fail_if": case.get("hard_fail_if", []),
                        "usage": {},
                        "usage_complete": False,
                        "human_rubric_scores": None,
                        "human_fatal_reviewed": False,
                        "human_fatal_failures": None,
                    }
                results.append(result)

    summary = {
        "schema_version": 1,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repo_head": head,
        "automatic_fatal_policy_id": AUTOMATIC_FATAL_POLICY_ID,
        "model": args.model,
        "effort": args.effort,
        "snapshot": args.snapshot,
        "prompt_source": args.prompt_source,
        "runner": args.runner,
        "runner_isolation": runner_isolation(args.runner),
        "sandbox": args.sandbox,
        "base_tree_sha256": base_digest,
        "frozen_tree_sha256": results[0].get("frozen_tree_sha256") if results else None,
        "prompt_stack_sha256": results[0].get("prompt_stack_sha256") if results else None,
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "fatal_failures": manifest["fatal_failures"],
        "rubrics": manifest["rubrics"],
        "results": results,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    passed = sum(bool(item.get("automatic_pass")) for item in results)
    print(f"RESULT {passed}/{len(results)} automatic checks passed; artifacts: {output_dir}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
