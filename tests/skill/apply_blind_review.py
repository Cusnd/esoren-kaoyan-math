from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import prepare_blind_review as blind


class ReviewImportError(ValueError):
    pass


def _sha256_file(path: Path, *, label: str) -> str:
    return hashlib.sha256(
        blind._read_regular_file(path, limit=blind.MAX_SUMMARY_BYTES, label=label)
    ).hexdigest()


def _reviewed_at(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewImportError("reviewed_at must be a timezone-aware ISO-8601 timestamp")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ReviewImportError("reviewed_at must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReviewImportError("reviewed_at must include a timezone")
    return value.strip()


def _validate_attestation(scores: dict[str, Any]) -> dict[str, Any]:
    reviewer = scores.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 200:
        raise ReviewImportError("reviewer must identify the human reviewer")
    if scores.get("reviewer_type") != "human":
        raise ReviewImportError("reviewer_type must be exactly 'human'")
    if scores.get("attested") is not True:
        raise ReviewImportError("attested must be true after real human review")
    return {
        "reviewer": reviewer.strip(),
        "reviewer_type": "human",
        "attested": True,
        "reviewed_at": _reviewed_at(scores.get("reviewed_at")),
    }


def _validate_scores(
    response: Any,
    *,
    rubric_required: bool,
    rubric_keys: set[str],
    allowed_fatals: set[str],
    label: str,
) -> tuple[dict[str, float] | None, list[str], str]:
    if not isinstance(response, dict) or set(response) != {
        "rubric_scores",
        "fatal_reviewed",
        "fatal_failures",
        "notes",
    }:
        raise ReviewImportError(f"{label} must contain the exact review response fields")
    if response.get("fatal_reviewed") is not True:
        raise ReviewImportError(f"{label}.fatal_reviewed must be true")
    fatal = response.get("fatal_failures")
    if not isinstance(fatal, list) or any(not isinstance(value, str) for value in fatal):
        raise ReviewImportError(f"{label}.fatal_failures must be a string array")
    if len(fatal) != len(set(fatal)):
        raise ReviewImportError(f"{label}.fatal_failures contains duplicates")
    unknown = sorted(set(fatal) - allowed_fatals)
    if unknown:
        raise ReviewImportError(f"{label}.fatal_failures contains unknown values: {unknown}")
    notes = response.get("notes")
    if not isinstance(notes, str) or len(notes) > 20_000:
        raise ReviewImportError(f"{label}.notes must be a string of at most 20000 characters")

    raw_scores = response.get("rubric_scores")
    if not rubric_required:
        if raw_scores is not None:
            raise ReviewImportError(f"{label}.rubric_scores must be null for fatal-only review")
        return None, list(fatal), notes
    if not isinstance(raw_scores, dict) or set(raw_scores) != rubric_keys:
        raise ReviewImportError(f"{label}.rubric_scores must contain every rubric criterion exactly")
    normalized: dict[str, float] = {}
    for criterion, value in raw_scores.items():
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 100
        ):
            raise ReviewImportError(f"{label}.rubric_scores.{criterion} must be from 0 to 100")
        normalized[criterion] = float(value)
    return normalized, list(fatal), notes


def apply_review(
    package_path: Path,
    answer_key_path: Path,
    scores_path: Path,
    baseline_path: Path,
    candidate_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    package = blind._load_json(package_path, label="review package")
    answer_key = blind._load_json(answer_key_path, label="private answer key")
    scores = blind._load_json(scores_path, label="completed review scores")
    baseline = blind._load_json(baseline_path, label="baseline summary")
    candidate = blind._load_json(candidate_path, label="candidate summary")

    for label, value in (
        ("review package", package),
        ("private answer key", answer_key),
        ("completed review scores", scores),
    ):
        if value.get("schema_version") != blind.SCHEMA_VERSION:
            raise ReviewImportError(f"{label}.schema_version must be {blind.SCHEMA_VERSION}")
    if set(scores) != {
        "schema_version",
        "package_id",
        "reviewer",
        "reviewer_type",
        "attested",
        "reviewed_at",
        "reviews",
    }:
        raise ReviewImportError("completed review scores contain unexpected top-level fields")
    package_id = package.get("package_id")
    if (
        not isinstance(package_id, str)
        or not package_id
        or answer_key.get("package_id") != package_id
        or scores.get("package_id") != package_id
    ):
        raise ReviewImportError("package_id does not match across package, key and scores")
    if answer_key.get("comparison_mode") != package.get("comparison_mode"):
        raise ReviewImportError("comparison_mode does not match the private answer key")
    package_sha = _sha256_file(package_path, label="review package")
    if answer_key.get("review_package_sha256") != package_sha:
        raise ReviewImportError("review package hash does not match the private answer key")
    summary_hashes = answer_key.get("summary_sha256")
    if not isinstance(summary_hashes, dict):
        raise ReviewImportError("private answer key has no bound summary hashes")
    actual_hashes = {
        "baseline": _sha256_file(baseline_path, label="baseline summary"),
        "candidate": _sha256_file(candidate_path, label="candidate summary"),
    }
    if summary_hashes != actual_hashes:
        raise ReviewImportError("baseline or candidate summary changed after package creation")

    attestation = _validate_attestation(scores)
    rubrics = blind._validated_rubrics(baseline, "baseline summary")
    if rubrics != blind._validated_rubrics(candidate, "candidate summary"):
        raise ReviewImportError("baseline and candidate rubrics differ")
    fatal_taxonomy = blind._validated_fatal_taxonomy(baseline, "baseline summary")
    if fatal_taxonomy != blind._validated_fatal_taxonomy(candidate, "candidate summary"):
        raise ReviewImportError("baseline and candidate fatal taxonomies differ")
    if package.get("fatal_taxonomy") != fatal_taxonomy:
        raise ReviewImportError("review package fatal taxonomy does not match the summaries")
    baseline_results = blind._validated_results(
        baseline, rubrics, fatal_taxonomy, "baseline summary"
    )
    candidate_results = blind._validated_results(
        candidate, rubrics, fatal_taxonomy, "candidate summary"
    )
    if set(baseline_results) != set(candidate_results):
        raise ReviewImportError("baseline and candidate result keys differ")

    raw_reviews = package.get("reviews")
    raw_mappings = answer_key.get("mappings")
    raw_scores = scores.get("reviews")
    if not isinstance(raw_reviews, list) or not isinstance(raw_mappings, list) or not isinstance(raw_scores, list):
        raise ReviewImportError("reviews and mappings must be arrays")

    def by_review_id(values: list[Any], label: str) -> dict[str, dict[str, Any]]:
        mapped: dict[str, dict[str, Any]] = {}
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                raise ReviewImportError(f"{label}[{index}] must be an object")
            review_id = value.get("review_id")
            if not isinstance(review_id, str) or not review_id:
                raise ReviewImportError(f"{label}[{index}] has an invalid review_id")
            if review_id in mapped:
                raise ReviewImportError(f"{label} contains duplicate review_id {review_id}")
            mapped[review_id] = value
        return mapped

    reviews_by_id = by_review_id(raw_reviews, "review package reviews")
    mappings_by_id = by_review_id(raw_mappings, "private mappings")
    scores_by_id = by_review_id(raw_scores, "completed scores")
    if set(reviews_by_id) != set(mappings_by_id) or set(reviews_by_id) != set(scores_by_id):
        raise ReviewImportError("review_id sets differ across package, key and scores")

    baseline_out = copy.deepcopy(baseline)
    candidate_out = copy.deepcopy(candidate)
    output_maps: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}
    for role, summary in (("baseline", baseline_out), ("candidate", candidate_out)):
        output_maps[role] = {
            blind._result_key(result, label=f"{role} output"): result
            for result in summary["results"]
        }

    mapped_keys: set[tuple[str, int]] = set()
    for review_id in sorted(reviews_by_id):
        review = reviews_by_id[review_id]
        mapping = mappings_by_id[review_id]
        completed = scores_by_id[review_id]
        if set(completed) != {"review_id", "response_a", "response_b"}:
            raise ReviewImportError(f"scores {review_id} contains unexpected fields")
        case_id = review.get("case_id")
        repetition = review.get("repetition")
        key = (case_id, repetition)
        if (
            not isinstance(case_id, str)
            or not isinstance(repetition, int)
            or mapping.get("case_id") != case_id
            or mapping.get("repetition") != repetition
            or key not in baseline_results
        ):
            raise ReviewImportError(f"review mapping is invalid for {review_id}")
        if key in mapped_keys:
            raise ReviewImportError(f"multiple reviews map to {case_id}#{repetition}")
        mapped_keys.add(key)
        if {mapping.get("response_a"), mapping.get("response_b")} != {
            "baseline",
            "candidate",
        }:
            raise ReviewImportError(f"private role mapping is invalid for {review_id}")
        rubric_name = review.get("rubric", {}).get("name") if isinstance(review.get("rubric"), dict) else None
        if rubric_name not in rubrics:
            raise ReviewImportError(f"review {review_id} has an unknown rubric")
        rubric_keys = set(rubrics[rubric_name])
        case_fatals = review.get("hard_fail_if", [])
        if not isinstance(case_fatals, list) or not set(case_fatals) <= set(fatal_taxonomy):
            raise ReviewImportError(f"review {review_id} has invalid case fatal highlights")
        allowed_fatals = set(fatal_taxonomy)
        rubric_required = review.get("rubric_required") is True
        for response_name in ("response_a", "response_b"):
            role = mapping[response_name]
            normalized_scores, fatal, notes = _validate_scores(
                completed[response_name],
                rubric_required=rubric_required,
                rubric_keys=rubric_keys,
                allowed_fatals=allowed_fatals,
                label=f"{review_id}.{response_name}",
            )
            result = output_maps[role][key]
            result["human_rubric_scores"] = normalized_scores
            result["human_fatal_reviewed"] = True
            result["human_fatal_failures"] = fatal
            result["human_notes"] = notes
            result["human_review_package_id"] = package_id
            result["human_review_id"] = review_id

    if mapped_keys != set(baseline_results):
        missing = sorted(set(baseline_results) - mapped_keys)
        raise ReviewImportError(f"fatal review does not cover every run: {missing}")
    common_attestation = {
        **attestation,
        "package_id": package_id,
        "review_package_sha256": package_sha,
    }
    baseline_out["human_review_attestation"] = {
        **common_attestation,
        "input_summary_sha256": actual_hashes["baseline"],
    }
    candidate_out["human_review_attestation"] = {
        **common_attestation,
        "input_summary_sha256": actual_hashes["candidate"],
    }
    return baseline_out, candidate_out


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    if path.is_symlink() or path.exists():
        raise ReviewImportError(f"output must be a new regular path: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        raise ReviewImportError(f"temporary output path already exists: {temporary}")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_reviewed_summaries(
    baseline_output: Path,
    candidate_output: Path,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    if baseline_output.resolve() == candidate_output.resolve():
        raise ReviewImportError("baseline and candidate outputs must differ")
    _write_new_json(baseline_output, baseline)
    try:
        _write_new_json(candidate_output, candidate)
    except Exception:
        try:
            baseline_output.unlink()
        except OSError:
            pass
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and map completed blind human review scores into two new summaries."
    )
    parser.add_argument("package", type=Path)
    parser.add_argument("answer_key", type=Path)
    parser.add_argument("scores", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--baseline-output", type=Path, required=True)
    parser.add_argument("--candidate-output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        inputs = {
            args.package.resolve(strict=True),
            args.answer_key.resolve(strict=True),
            args.scores.resolve(strict=True),
            args.baseline.resolve(strict=True),
            args.candidate.resolve(strict=True),
        }
        if args.baseline_output.resolve() in inputs or args.candidate_output.resolve() in inputs:
            raise ReviewImportError("outputs must not overwrite any input")
        baseline, candidate = apply_review(
            args.package,
            args.answer_key,
            args.scores,
            args.baseline,
            args.candidate,
        )
        write_reviewed_summaries(
            args.baseline_output,
            args.candidate_output,
            baseline,
            candidate,
        )
    except (OSError, blind.BlindReviewError, ReviewImportError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"reviewed baseline: {args.baseline_output}")
    print(f"reviewed candidate: {args.candidate_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
