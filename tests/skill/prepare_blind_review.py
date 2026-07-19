from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MIN_SAMPLE_FRACTION = 0.20
MAX_SUMMARY_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
CASE_ID_PATTERN = re.compile(r"[a-z0-9_]+")


class BlindReviewError(ValueError):
    pass


def _reject_json_constant(value: str) -> None:
    raise BlindReviewError(f"non-finite JSON value is not allowed: {value}")


def _read_regular_file(path: Path, *, limit: int, label: str) -> bytes:
    if path.is_symlink():
        raise BlindReviewError(f"{label} must not be a symbolic link: {path}")
    try:
        stat = path.stat()
    except OSError as exc:
        raise BlindReviewError(f"cannot read {label}: {path}: {exc}") from exc
    if not path.is_file():
        raise BlindReviewError(f"{label} must be a regular file: {path}")
    if stat.st_size > limit:
        raise BlindReviewError(f"{label} exceeds {limit} bytes: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise BlindReviewError(f"cannot read {label}: {path}: {exc}") from exc


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    raw = _read_regular_file(path, limit=MAX_SUMMARY_BYTES, label=label)
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlindReviewError(f"invalid UTF-8 JSON in {label}: {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise BlindReviewError(f"{label} must contain a JSON object")
    return parsed


def _validated_rubrics(summary: dict[str, Any], label: str) -> dict[str, dict[str, float]]:
    raw = summary.get("rubrics")
    if not isinstance(raw, dict) or not raw:
        raise BlindReviewError(f"{label}.rubrics must be a non-empty object")
    rubrics: dict[str, dict[str, float]] = {}
    for name, weights in raw.items():
        if not isinstance(name, str) or not name or not isinstance(weights, dict) or not weights:
            raise BlindReviewError(f"{label}.rubrics contains an invalid rubric")
        normalized: dict[str, float] = {}
        for criterion, weight in weights.items():
            if (
                not isinstance(criterion, str)
                or not criterion
                or not isinstance(weight, (int, float))
                or isinstance(weight, bool)
                or not math.isfinite(float(weight))
                or float(weight) < 0
            ):
                raise BlindReviewError(f"{label}.rubrics.{name} contains an invalid weight")
            normalized[criterion] = float(weight)
        if not math.isclose(sum(normalized.values()), 100.0, abs_tol=1e-9):
            raise BlindReviewError(f"{label}.rubrics.{name} weights must total 100")
        rubrics[name] = normalized
    return rubrics


def _validated_fatal_taxonomy(summary: dict[str, Any], label: str) -> list[str]:
    raw = summary.get("fatal_failures")
    if (
        not isinstance(raw, list)
        or not raw
        or any(not isinstance(value, str) or not value for value in raw)
        or len(raw) != len(set(raw))
    ):
        raise BlindReviewError(f"{label}.fatal_failures must be a non-empty unique string array")
    return list(raw)


def _result_key(result: dict[str, Any], *, label: str) -> tuple[str, int]:
    case_id = result.get("case_id")
    repetition = result.get("repetition")
    if not isinstance(case_id, str) or CASE_ID_PATTERN.fullmatch(case_id) is None:
        raise BlindReviewError(f"{label} has an invalid case_id: {case_id!r}")
    if not isinstance(repetition, int) or isinstance(repetition, bool) or repetition < 1:
        raise BlindReviewError(f"{label} has an invalid repetition: {repetition!r}")
    return case_id, repetition


def _validated_results(
    summary: dict[str, Any],
    rubrics: dict[str, dict[str, float]],
    fatal_taxonomy: list[str],
    label: str,
) -> dict[tuple[str, int], dict[str, Any]]:
    if summary.get("schema_version") != SCHEMA_VERSION:
        raise BlindReviewError(f"{label}.schema_version must be {SCHEMA_VERSION}")
    raw = summary.get("results")
    if not isinstance(raw, list) or not raw:
        raise BlindReviewError(f"{label}.results must be a non-empty array")
    results: dict[tuple[str, int], dict[str, Any]] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise BlindReviewError(f"{label}.results[{index}] must be an object")
        key = _result_key(item, label=f"{label}.results[{index}]")
        if key in results:
            raise BlindReviewError(f"{label} contains duplicate run key {key[0]}#{key[1]}")
        rubric_name = item.get("rubric")
        if not isinstance(rubric_name, str) or rubric_name not in rubrics:
            raise BlindReviewError(f"{label} {key[0]}#{key[1]} has an unknown rubric")
        if not isinstance(item.get("oracle"), dict) or not item["oracle"]:
            raise BlindReviewError(f"{label} {key[0]}#{key[1]} has no oracle")
        hard_failures = item.get("hard_fail_if")
        if not isinstance(hard_failures, list) or any(
            not isinstance(value, str) or not value for value in hard_failures
        ):
            raise BlindReviewError(f"{label} {key[0]}#{key[1]} has invalid hard_fail_if")
        if len(hard_failures) != len(set(hard_failures)):
            raise BlindReviewError(f"{label} {key[0]}#{key[1]} has duplicate hard_fail_if")
        unknown = sorted(set(hard_failures) - set(fatal_taxonomy))
        if unknown:
            raise BlindReviewError(
                f"{label} {key[0]}#{key[1]} hard_fail_if is outside fatal taxonomy: {unknown}"
            )
        if not isinstance(item.get("slice"), str) or not item["slice"]:
            raise BlindReviewError(f"{label} {key[0]}#{key[1]} has an invalid slice")
        if not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
            raise BlindReviewError(f"{label} {key[0]}#{key[1]} has no user prompt")
        if not isinstance(item.get("expected"), dict) or not item["expected"]:
            raise BlindReviewError(f"{label} {key[0]}#{key[1]} has no expected routing")
        if not isinstance(item.get("fixture"), dict):
            raise BlindReviewError(f"{label} {key[0]}#{key[1]} has an invalid fixture")
        if not isinstance(item.get("file_expectations"), dict):
            raise BlindReviewError(
                f"{label} {key[0]}#{key[1]} has invalid file expectations"
            )
        results[key] = item
    return results


def _stable_digest(seed: str, purpose: str, key: tuple[str, int]) -> bytes:
    material = f"{seed}\0{purpose}\0{key[0]}\0{key[1]}".encode("utf-8")
    return hashlib.sha256(material).digest()


def _artifact_path(summary_path: Path, key: tuple[str, int], suffix: str) -> Path:
    filename = f"{key[0]}-{key[1]}{suffix}"
    parent = summary_path.resolve().parent
    candidate = parent / filename
    if candidate.is_symlink():
        raise BlindReviewError(f"artifact must not be a symbolic link: {candidate}")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise BlindReviewError(f"missing artifact for {key[0]}#{key[1]}: {candidate}") from exc
    if resolved.parent != parent:
        raise BlindReviewError(f"artifact escapes summary directory: {candidate}")
    return resolved


def _read_artifact(summary_path: Path, key: tuple[str, int], suffix: str) -> str:
    path = _artifact_path(summary_path, key, suffix)
    raw = _read_regular_file(path, limit=MAX_ARTIFACT_BYTES, label="evaluation artifact")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BlindReviewError(f"artifact is not UTF-8: {path}: {exc}") from exc


def _redact_metadata(text: str, summaries: tuple[dict[str, Any], dict[str, Any]]) -> str:
    redacted = text
    model_values = {
        value
        for summary in summaries
        if isinstance((value := summary.get("model")), str) and value.strip()
    }
    for value in sorted(model_values, key=len, reverse=True):
        redacted = re.sub(re.escape(value), "[REDACTED MODEL]", redacted, flags=re.IGNORECASE)
    source_values = {
        value.strip()
        for summary in summaries
        for field in ("prompt_source", "snapshot")
        if isinstance((value := summary.get(field)), str) and value.strip()
    }
    for value in sorted(source_values, key=len, reverse=True):
        redacted = re.sub(
            rf"(?<![\w-]){re.escape(value)}(?![\w-])",
            "[REDACTED SOURCE]",
            redacted,
            flags=re.IGNORECASE,
        )
    redacted = re.sub(
        r"(?im)^(\s*(?:model|prompt[_ -]?source|snapshot)\s*[:=]\s*).*$",
        r"\1[REDACTED]",
        redacted,
    )
    return redacted


def _validate_pair_metadata(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    key: tuple[str, int],
    rubrics: dict[str, dict[str, float]],
) -> tuple[dict[str, Any], str, list[str], str]:
    for field in (
        "slice",
        "oracle",
        "rubric",
        "hard_fail_if",
        "prompt",
        "expected",
        "task_kind",
        "fixture",
        "file_expectations",
    ):
        if baseline.get(field) != candidate.get(field):
            raise BlindReviewError(f"run metadata differs for {key[0]}#{key[1]}: {field}")
    rubric_name = str(baseline["rubric"])
    return (
        baseline["oracle"],
        rubric_name,
        list(baseline["hard_fail_if"]),
        str(baseline["slice"]),
    )


def build_blind_review(
    baseline_path: Path,
    candidate_path: Path,
    *,
    sample_fraction: float = MIN_SAMPLE_FRACTION,
    sample_count: int | None = None,
    seed: str | None = None,
    comparison_mode: str = "prompt",
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        if baseline_path.resolve(strict=True) == candidate_path.resolve(strict=True):
            raise BlindReviewError("baseline and candidate summaries must be different files")
    except OSError as exc:
        raise BlindReviewError(f"cannot resolve input summary: {exc}") from exc
    if seed is None:
        seed = secrets.token_hex(32)
    if not isinstance(seed, str) or not seed.strip() or len(seed) > 256:
        raise BlindReviewError("seed must contain 1 to 256 characters")
    if (
        not isinstance(sample_fraction, (int, float))
        or isinstance(sample_fraction, bool)
        or not math.isfinite(float(sample_fraction))
        or not MIN_SAMPLE_FRACTION <= float(sample_fraction) <= 1.0
    ):
        raise BlindReviewError("sample_fraction must be between 0.20 and 1.00")
    if sample_count is not None and (
        not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 1
    ):
        raise BlindReviewError("sample_count must be a positive integer")

    baseline_summary = _load_json(baseline_path, label="baseline summary")
    candidate_summary = _load_json(candidate_path, label="candidate summary")
    for field in (
        "manifest_sha256",
        "model",
        "snapshot",
        "runner",
        "runner_isolation",
        "sandbox",
        "base_tree_sha256",
        "fatal_failures",
        "automatic_fatal_policy_id",
    ):
        if baseline_summary.get(field) != candidate_summary.get(field):
            raise BlindReviewError(f"baseline and candidate {field} differ")
    if comparison_mode == "prompt":
        if baseline_summary.get("effort") != candidate_summary.get("effort"):
            raise BlindReviewError("prompt comparison requires identical effort")
        if baseline_summary.get("prompt_stack_sha256") == candidate_summary.get(
            "prompt_stack_sha256"
        ):
            raise BlindReviewError("prompt comparison requires different prompt stacks")
    elif comparison_mode == "effort":
        if baseline_summary.get("prompt_stack_sha256") != candidate_summary.get(
            "prompt_stack_sha256"
        ):
            raise BlindReviewError("effort comparison requires identical prompt stacks")
        if baseline_summary.get("effort") == candidate_summary.get("effort"):
            raise BlindReviewError("effort comparison requires different effort values")
    else:
        raise BlindReviewError(f"unknown comparison mode: {comparison_mode}")
    baseline_rubrics = _validated_rubrics(baseline_summary, "baseline summary")
    candidate_rubrics = _validated_rubrics(candidate_summary, "candidate summary")
    if baseline_rubrics != candidate_rubrics:
        raise BlindReviewError("baseline and candidate rubric definitions differ")
    baseline_fatals = _validated_fatal_taxonomy(baseline_summary, "baseline summary")
    candidate_fatals = _validated_fatal_taxonomy(candidate_summary, "candidate summary")
    if baseline_fatals != candidate_fatals:
        raise BlindReviewError("baseline and candidate fatal taxonomies differ")
    baseline_results = _validated_results(
        baseline_summary, baseline_rubrics, baseline_fatals, "baseline summary"
    )
    candidate_results = _validated_results(
        candidate_summary, candidate_rubrics, candidate_fatals, "candidate summary"
    )
    if set(baseline_results) != set(candidate_results):
        only_baseline = sorted(set(baseline_results) - set(candidate_results))
        only_candidate = sorted(set(candidate_results) - set(baseline_results))
        raise BlindReviewError(
            "case_id/repetition sets differ: "
            f"baseline_only={only_baseline}, candidate_only={only_candidate}"
        )

    population = len(baseline_results)
    minimum_count = max(1, math.ceil(population * MIN_SAMPLE_FRACTION))
    required_slices = sorted({str(item["slice"]) for item in baseline_results.values()})
    minimum_count = max(minimum_count, len(required_slices))
    if sample_count is None:
        selected_count = max(minimum_count, math.ceil(population * float(sample_fraction)))
    else:
        if sample_count < minimum_count:
            raise BlindReviewError(
                f"sample_count must be at least {minimum_count} "
                f"(20% of {population}, with every slice represented)"
            )
        selected_count = sample_count
    if selected_count > population:
        raise BlindReviewError(f"sample_count cannot exceed population size {population}")

    ranked_keys = sorted(
        baseline_results,
        key=lambda key: (_stable_digest(seed, "sample", key), key),
    )
    selected: list[tuple[str, int]] = []
    for case_slice in required_slices:
        selected.append(
            next(key for key in ranked_keys if baseline_results[key]["slice"] == case_slice)
        )
    selected.extend(key for key in ranked_keys if key not in selected)
    selected = selected[:selected_count]
    selected_set = set(selected)
    package_id = hashlib.sha256(
        (seed + "\0" + "\0".join(f"{key[0]}#{key[1]}" for key in selected)).encode("utf-8")
    ).hexdigest()[:16]

    review_items: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    summaries = (baseline_summary, candidate_summary)
    for index, key in enumerate(sorted(baseline_results), start=1):
        baseline_result = baseline_results[key]
        candidate_result = candidate_results[key]
        oracle, rubric_name, hard_fail_if, case_slice = _validate_pair_metadata(
            baseline_result, candidate_result, key, baseline_rubrics
        )
        baseline_artifacts = {
            "final": _redact_metadata(
                _read_artifact(baseline_path, key, "-final.md"), summaries
            ),
            "diff": _redact_metadata(_read_artifact(baseline_path, key, ".diff"), summaries),
            "resource_usage": {
                "total_tokens": (baseline_result.get("usage") or {}).get("total_tokens"),
                "elapsed_seconds": baseline_result.get("elapsed_seconds"),
                "tool_call_count": baseline_result.get("tool_call_count"),
            },
        }
        candidate_artifacts = {
            "final": _redact_metadata(
                _read_artifact(candidate_path, key, "-final.md"), summaries
            ),
            "diff": _redact_metadata(_read_artifact(candidate_path, key, ".diff"), summaries),
            "resource_usage": {
                "total_tokens": (candidate_result.get("usage") or {}).get("total_tokens"),
                "elapsed_seconds": candidate_result.get("elapsed_seconds"),
                "tool_call_count": candidate_result.get("tool_call_count"),
            },
        }
        baseline_is_a = _stable_digest(seed, "labels", key)[0] % 2 == 0
        response_a = baseline_artifacts if baseline_is_a else candidate_artifacts
        response_b = candidate_artifacts if baseline_is_a else baseline_artifacts
        review_id = f"BR-{index:03d}"
        rubric_required = key in selected_set
        blank_scores = (
            {criterion: None for criterion in baseline_rubrics[rubric_name]}
            if rubric_required
            else None
        )
        review_items.append(
            {
                "review_id": review_id,
                "case_id": key[0],
                "repetition": key[1],
                "slice": case_slice,
                "prompt": baseline_result["prompt"],
                "expected": baseline_result["expected"],
                "task_kind": baseline_result.get("task_kind"),
                "fixture": baseline_result["fixture"],
                "file_expectations": baseline_result["file_expectations"],
                "oracle": oracle,
                "rubric": {
                    "name": rubric_name,
                    "weights": baseline_rubrics[rubric_name],
                },
                "hard_fail_if": hard_fail_if,
                "rubric_required": rubric_required,
                "response_a": response_a,
                "response_b": response_b,
                "review_form": {
                    "response_a": {
                        "rubric_scores": dict(blank_scores) if blank_scores is not None else None,
                        "fatal_reviewed": False,
                        "fatal_failures": [],
                        "notes": "",
                    },
                    "response_b": {
                        "rubric_scores": dict(blank_scores) if blank_scores is not None else None,
                        "fatal_reviewed": False,
                        "fatal_failures": [],
                        "notes": "",
                    },
                },
            }
        )
        mappings.append(
            {
                "review_id": review_id,
                "case_id": key[0],
                "repetition": key[1],
                "response_a": "baseline" if baseline_is_a else "candidate",
                "response_b": "candidate" if baseline_is_a else "baseline",
            }
        )

    package = {
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "comparison_mode": comparison_mode,
        "instructions": {
            "score_range": "Each rubric score must be from 0 to 100.",
            "fatal_failures": "Review every response against the complete fatal_taxonomy and record every applicable value exactly; hard_fail_if is only a case-specific highlight.",
            "blindness": "Do not infer candidate identity; evaluate A and B independently.",
            "fatal_coverage": "Set fatal_reviewed=true for both responses on every item; every run requires fatal review.",
            "score_submission": "Complete the separate review-scores.template.json; do not edit this package.",
        },
        "fatal_taxonomy": baseline_fatals,
        "sampling": {
            "population_size": population,
            "selected_count": selected_count,
            "minimum_fraction": MIN_SAMPLE_FRACTION,
            "rubric_review_ids": [
                item["review_id"] for item in review_items if item["rubric_required"]
            ],
            "fatal_review_count": population,
        },
        "reviews": review_items,
    }
    package_bytes = (
        json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    answer_key = {
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "comparison_mode": comparison_mode,
        "review_package_sha256": hashlib.sha256(package_bytes).hexdigest(),
        "sampling_seed": seed,
        "summary_sha256": {
            "baseline": hashlib.sha256(
                _read_regular_file(
                    baseline_path, limit=MAX_SUMMARY_BYTES, label="baseline summary"
                )
            ).hexdigest(),
            "candidate": hashlib.sha256(
                _read_regular_file(
                    candidate_path, limit=MAX_SUMMARY_BYTES, label="candidate summary"
                )
            ).hexdigest(),
        },
        "mappings": mappings,
    }
    return package, answer_key


def build_score_template(package: dict[str, Any]) -> dict[str, Any]:
    reviews = package.get("reviews")
    if not isinstance(reviews, list):
        raise BlindReviewError("review package has no reviews")
    return {
        "schema_version": SCHEMA_VERSION,
        "package_id": package.get("package_id"),
        "reviewer": None,
        "reviewer_type": "human",
        "attested": False,
        "reviewed_at": None,
        "reviews": [
            {
                "review_id": item["review_id"],
                "response_a": json.loads(json.dumps(item["review_form"]["response_a"])),
                "response_b": json.loads(json.dumps(item["review_form"]["response_b"])),
            }
            for item in reviews
        ],
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_review_bundle(
    output_dir: Path,
    package: dict[str, Any],
    answer_key: dict[str, Any],
) -> tuple[Path, Path, Path]:
    if output_dir.is_symlink():
        raise BlindReviewError(f"output directory must not be a symbolic link: {output_dir}")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise BlindReviewError(f"output path is not a directory: {output_dir}")
        try:
            if any(output_dir.iterdir()):
                raise BlindReviewError(f"output directory must be empty: {output_dir}")
        except OSError as exc:
            raise BlindReviewError(f"cannot inspect output directory: {output_dir}: {exc}") from exc
    else:
        output_dir.mkdir(parents=True)

    share_dir = output_dir / "share"
    private_dir = output_dir / "private"
    share_dir.mkdir()
    private_dir.mkdir()
    package_path = share_dir / "review-package.json"
    scores_path = share_dir / "review-scores.template.json"
    answer_path = private_dir / "answer-key.json"
    _atomic_write_json(package_path, package)
    _atomic_write_json(scores_path, build_score_template(package))
    _atomic_write_json(answer_path, answer_key)
    try:
        answer_path.chmod(0o600)
    except OSError:
        pass
    return package_path, scores_path, answer_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a label-hidden human review bundle from two compatible eval runs."
    )
    parser.add_argument("baseline", type=Path, help="Baseline summary.json")
    parser.add_argument("candidate", type=Path, help="Candidate summary.json")
    parser.add_argument("--output-dir", required=True, type=Path, help="New or empty output directory")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--sample-fraction",
        type=float,
        default=MIN_SAMPLE_FRACTION,
        help="Fraction receiving full rubric scores (0.20 to 1.00; all runs still receive fatal review)",
    )
    selection.add_argument(
        "--sample-count",
        type=int,
        help="Explicit full-rubric count, never below 20%% or required slice coverage",
    )
    parser.add_argument(
        "--seed",
        default=None,
        help="Explicit deterministic seed for tests/reproduction; omitted uses a private random seed.",
    )
    parser.add_argument(
        "--comparison-mode",
        choices=("prompt", "effort"),
        default="prompt",
        help="Match the compatibility rules used by run_forward_eval.py --compare.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        package, answer_key = build_blind_review(
            args.baseline,
            args.candidate,
            sample_fraction=args.sample_fraction,
            sample_count=args.sample_count,
            seed=args.seed,
            comparison_mode=args.comparison_mode,
        )
        package_path, scores_path, answer_path = write_review_bundle(
            args.output_dir, package, answer_key
        )
    except (BlindReviewError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"review package: {package_path}")
    print(f"score template: {scores_path}")
    print(f"private answer key: {answer_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
