from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

import prepare_blind_review
import apply_blind_review
import run_forward_eval


RUBRIC = {
    "default": {
        "math_correctness_and_conditions": 40,
        "intuition_and_exam_reproducibility": 20,
        "transfer_network_and_memory": 20,
        "archive_correctness": 15,
        "resource_efficiency": 5,
    }
}
FATAL_TAXONOMY = ["wrong_final_answer", "fabricated_source_or_year"]


def make_summary(root: Path, keys: list[tuple[str, int]], role: str) -> Path:
    results = []
    for case_id, repetition in keys:
        results.append(
            {
                "case_id": case_id,
                "repetition": repetition,
                "slice": "math",
                "model": "gpt-secret-model",
                "snapshot": role,
                "prompt_source": role,
                "oracle": {"summary": f"oracle for {case_id}"},
                "rubric": "default",
                "hard_fail_if": ["wrong_final_answer"],
                "prompt": f"solve {case_id}",
                "expected": {"intent": "solve", "collection": "none", "persistence": "skip"},
                "task_kind": "solve",
                "fixture": {"base": "repository_snapshot"},
                "file_expectations": {"require_change": False, "allowed_changes": []},
                "automatic_pass": True,
                "automatic_fatal_pass": True,
                "elapsed_seconds": 1.0,
                "tool_call_count": 1,
                "usage": {"total_tokens": 100},
                "usage_complete": True,
                "human_rubric_scores": None,
                "human_fatal_reviewed": False,
                "human_fatal_failures": None,
            }
        )
        (root / f"{case_id}-{repetition}-final.md").write_text(
            f"model: gpt-secret-model\n{role} final for {case_id}\n",
            encoding="utf-8",
        )
        (root / f"{case_id}-{repetition}.diff").write_text(
            f"prompt_source: {role}\n+{role} diff for {case_id}\n",
            encoding="utf-8",
        )
    summary = {
        "schema_version": 1,
        "manifest_sha256": "manifest",
        "model": "gpt-secret-model",
        "effort": "max",
        "snapshot": "worktree",
        "prompt_source": role,
        "runner": "wsl",
        "runner_isolation": run_forward_eval.WSL_RUNNER_ISOLATION,
        "sandbox": "workspace-write",
        "base_tree_sha256": "same-tree",
        "automatic_fatal_policy_id": run_forward_eval.AUTOMATIC_FATAL_POLICY_ID,
        "prompt_stack_sha256": f"prompt-{role}",
        "fatal_failures": FATAL_TAXONOMY,
        "rubrics": RUBRIC,
        "results": results,
    }
    path = root / "summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    return path


class BlindReviewTests(unittest.TestCase):
    def test_explicit_seed_is_deterministic_blind_and_at_least_twenty_percent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            keys = [(f"case_{index:02d}", 1) for index in range(1, 11)]
            baseline = make_summary(baseline_root, keys, "baseline")
            candidate = make_summary(candidate_root, keys, "candidate")

            first_package, first_key = prepare_blind_review.build_blind_review(
                baseline, candidate, seed="test-secret-seed"
            )
            second_package, second_key = prepare_blind_review.build_blind_review(
                baseline, candidate, seed="test-secret-seed"
            )

        self.assertEqual(first_package, second_package)
        self.assertEqual(first_key, second_key)
        self.assertEqual(2, first_package["sampling"]["selected_count"])
        self.assertEqual(10, len(first_package["reviews"]))
        self.assertEqual(10, first_package["sampling"]["fatal_review_count"])
        self.assertEqual(2, sum(item["rubric_required"] for item in first_package["reviews"]))
        serialized = json.dumps(first_package)
        self.assertNotIn("gpt-secret-model", serialized)
        self.assertNotIn("baseline final", serialized)
        self.assertNotIn("candidate final", serialized)
        self.assertNotIn('"model"', serialized)
        self.assertNotIn('"prompt_source"', serialized)
        self.assertNotIn('"snapshot"', serialized)
        for mapping in first_key["mappings"]:
            self.assertEqual(
                {"baseline", "candidate"},
                {mapping["response_a"], mapping["response_b"]},
            )
        self.assertNotIn("test-secret-seed", serialized)

    def test_default_seed_is_private_random_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            keys = [(f"case_{index:02d}", 1) for index in range(1, 11)]
            baseline = make_summary(baseline_root, keys, "baseline")
            candidate = make_summary(candidate_root, keys, "candidate")
            first_package, first_key = prepare_blind_review.build_blind_review(
                baseline, candidate
            )
            second_package, second_key = prepare_blind_review.build_blind_review(
                baseline, candidate
            )

        self.assertNotEqual(first_key["sampling_seed"], second_key["sampling_seed"])
        self.assertNotIn(first_key["sampling_seed"], json.dumps(first_package))
        self.assertNotIn(second_key["sampling_seed"], json.dumps(second_package))

    def test_full_rubric_sample_covers_every_slice_while_fatal_review_covers_all(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            keys = [(f"case_{index:02d}", 1) for index in range(1, 7)]
            baseline = make_summary(baseline_root, keys, "baseline")
            candidate = make_summary(candidate_root, keys, "candidate")
            for path in (baseline, candidate):
                summary = json.loads(path.read_text(encoding="utf-8"))
                for index, result in enumerate(summary["results"]):
                    result["slice"] = ("math", "teaching", "persistence")[index // 2]
                path.write_text(json.dumps(summary), encoding="utf-8")
            package, _ = prepare_blind_review.build_blind_review(
                baseline, candidate, seed="slice-secret"
            )

        selected_slices = {
            item["slice"] for item in package["reviews"] if item["rubric_required"]
        }
        self.assertEqual({"math", "teaching", "persistence"}, selected_slices)
        self.assertEqual(3, package["sampling"]["selected_count"])
        self.assertEqual(6, package["sampling"]["fatal_review_count"])

    def test_case_and_repetition_sets_must_match_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            baseline = make_summary(baseline_root, [("same", 1), ("baseline_only", 1)], "b")
            candidate = make_summary(candidate_root, [("same", 1), ("candidate_only", 1)], "c")

            with self.assertRaisesRegex(prepare_blind_review.BlindReviewError, "sets differ"):
                prepare_blind_review.build_blind_review(baseline, candidate)

    def test_effort_bundle_requires_same_prompt_stack_and_different_effort(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            baseline = make_summary(baseline_root, [("same", 1)], "baseline")
            candidate = make_summary(candidate_root, [("same", 1)], "candidate")
            baseline_summary = json.loads(baseline.read_text(encoding="utf-8"))
            candidate_summary = json.loads(candidate.read_text(encoding="utf-8"))
            baseline_summary["prompt_stack_sha256"] = "same-prompt"
            candidate_summary["prompt_stack_sha256"] = "same-prompt"
            candidate_summary["effort"] = "xhigh"
            baseline.write_text(json.dumps(baseline_summary), encoding="utf-8")
            candidate.write_text(json.dumps(candidate_summary), encoding="utf-8")

            package, key = prepare_blind_review.build_blind_review(
                baseline,
                candidate,
                seed="effort-secret",
                comparison_mode="effort",
            )
            self.assertEqual("effort", package["comparison_mode"])
            self.assertEqual("effort", key["comparison_mode"])
            with self.assertRaisesRegex(
                prepare_blind_review.BlindReviewError, "prompt comparison"
            ):
                prepare_blind_review.build_blind_review(
                    baseline, candidate, seed="effort-secret"
                )

    def test_sample_parameters_and_duplicate_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            keys = [(f"case_{index:02d}", 1) for index in range(1, 11)]
            baseline = make_summary(baseline_root, keys, "b")
            candidate = make_summary(candidate_root, keys, "c")
            summary = json.loads(baseline.read_text(encoding="utf-8"))
            summary["results"].append(dict(summary["results"][0]))
            baseline.write_text(json.dumps(summary), encoding="utf-8")

            with self.assertRaisesRegex(prepare_blind_review.BlindReviewError, "duplicate"):
                prepare_blind_review.build_blind_review(baseline, candidate)

            baseline = make_summary(baseline_root, keys, "b")
            with self.assertRaisesRegex(prepare_blind_review.BlindReviewError, "at least 2"):
                prepare_blind_review.build_blind_review(
                    baseline, candidate, sample_count=1
                )
            with self.assertRaisesRegex(prepare_blind_review.BlindReviewError, "0.20"):
                prepare_blind_review.build_blind_review(
                    baseline, candidate, sample_fraction=0.19
                )

    def test_bundle_separates_shareable_package_from_private_answer_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            baseline = make_summary(baseline_root, [("sample", 1)], "b")
            candidate = make_summary(candidate_root, [("sample", 1)], "c")
            package, answer_key = prepare_blind_review.build_blind_review(
                baseline, candidate
            )
            output = root / "output"
            package_path, scores_path, answer_path = prepare_blind_review.write_review_bundle(
                output, package, answer_key
            )

            self.assertEqual(output / "share" / "review-package.json", package_path)
            self.assertEqual(
                output / "share" / "review-scores.template.json", scores_path
            )
            self.assertEqual(output / "private" / "answer-key.json", answer_path)
            self.assertTrue(package_path.is_file())
            self.assertTrue(scores_path.is_file())
            self.assertTrue(answer_path.is_file())
            with self.assertRaisesRegex(prepare_blind_review.BlindReviewError, "must be empty"):
                prepare_blind_review.write_review_bundle(output, package, answer_key)

    @staticmethod
    def complete_score_template(
        package: dict[str, object], template: dict[str, object]
    ) -> dict[str, object]:
        completed = json.loads(json.dumps(template))
        completed["reviewer"] = "Independent human reviewer"
        completed["reviewer_type"] = "human"
        completed["attested"] = True
        completed["reviewed_at"] = "2026-07-18T12:00:00+00:00"
        package_reviews = {
            item["review_id"]: item for item in package["reviews"]  # type: ignore[index]
        }
        for review in completed["reviews"]:  # type: ignore[index]
            package_review = package_reviews[review["review_id"]]
            for response_name, score in (("response_a", 80), ("response_b", 86)):
                response = review[response_name]
                response["fatal_reviewed"] = True
                if package_review["rubric_required"]:
                    response["rubric_scores"] = {
                        criterion: score
                        for criterion in package_review["rubric"]["weights"]
                    }
        return completed

    def test_strict_score_import_maps_every_fatal_review_and_sampled_rubrics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            keys = [(f"case_{index:02d}", 1) for index in range(1, 11)]
            baseline = make_summary(baseline_root, keys, "baseline")
            candidate = make_summary(candidate_root, keys, "candidate")
            package, answer_key = prepare_blind_review.build_blind_review(
                baseline, candidate, seed="private-import-seed"
            )
            bundle = root / "bundle"
            package_path, template_path, key_path = prepare_blind_review.write_review_bundle(
                bundle, package, answer_key
            )
            template = json.loads(template_path.read_text(encoding="utf-8"))
            completed = self.complete_score_template(package, template)
            completed["reviews"][0]["response_a"]["fatal_failures"] = [
                "fabricated_source_or_year"
            ]
            scores_path = root / "completed-scores.json"
            scores_path.write_text(json.dumps(completed), encoding="utf-8")

            baseline_out, candidate_out = apply_blind_review.apply_review(
                package_path, key_path, scores_path, baseline, candidate
            )

        for summary in (baseline_out, candidate_out):
            self.assertEqual("human", summary["human_review_attestation"]["reviewer_type"])
            self.assertTrue(summary["human_review_attestation"]["attested"])
            self.assertTrue(
                all(result["human_fatal_reviewed"] for result in summary["results"])
            )
            self.assertEqual(
                2,
                sum(result["human_rubric_scores"] is not None for result in summary["results"]),
            )
        self.assertEqual(
            1,
            sum(
                "fabricated_source_or_year" in result["human_fatal_failures"]
                for summary in (baseline_out, candidate_out)
                for result in summary["results"]
            ),
        )

    def test_score_import_rejects_unreviewed_or_unknown_fatal_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            baseline = make_summary(baseline_root, [("sample", 1)], "baseline")
            candidate = make_summary(candidate_root, [("sample", 1)], "candidate")
            package, answer_key = prepare_blind_review.build_blind_review(
                baseline, candidate, seed="private-import-seed"
            )
            package_path, template_path, key_path = prepare_blind_review.write_review_bundle(
                root / "bundle", package, answer_key
            )
            template = json.loads(template_path.read_text(encoding="utf-8"))
            completed = self.complete_score_template(package, template)
            completed["reviews"][0]["response_a"]["fatal_reviewed"] = False
            scores_path = root / "scores.json"
            scores_path.write_text(json.dumps(completed), encoding="utf-8")
            with self.assertRaisesRegex(apply_blind_review.ReviewImportError, "fatal_reviewed"):
                apply_blind_review.apply_review(
                    package_path, key_path, scores_path, baseline, candidate
                )

            completed["reviews"][0]["response_a"]["fatal_reviewed"] = True
            completed["reviews"][0]["response_a"]["fatal_failures"] = ["not_declared"]
            scores_path.write_text(json.dumps(completed), encoding="utf-8")
            with self.assertRaisesRegex(apply_blind_review.ReviewImportError, "unknown values"):
                apply_blind_review.apply_review(
                    package_path, key_path, scores_path, baseline, candidate
                )

    def test_imported_human_review_can_unlock_comparison_only_after_all_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            keys = [(f"case_{index:02d}", 1) for index in range(1, 6)]
            baseline = make_summary(baseline_root, keys, "baseline")
            candidate = make_summary(candidate_root, keys, "candidate")
            candidate_summary = json.loads(candidate.read_text(encoding="utf-8"))
            for result in candidate_summary["results"]:
                result["usage"]["total_tokens"] = 80
            candidate.write_text(json.dumps(candidate_summary), encoding="utf-8")
            package, answer_key = prepare_blind_review.build_blind_review(
                baseline, candidate, seed="end-to-end-secret"
            )
            package_path, template_path, key_path = prepare_blind_review.write_review_bundle(
                root / "bundle", package, answer_key
            )
            completed = self.complete_score_template(
                package, json.loads(template_path.read_text(encoding="utf-8"))
            )
            for review in completed["reviews"]:
                for response_name in ("response_a", "response_b"):
                    scores = review[response_name]["rubric_scores"]
                    if scores is not None:
                        review[response_name]["rubric_scores"] = {
                            criterion: 80 for criterion in scores
                        }
            scores_path = root / "scores.json"
            scores_path.write_text(json.dumps(completed), encoding="utf-8")
            baseline_out, candidate_out = apply_blind_review.apply_review(
                package_path, key_path, scores_path, baseline, candidate
            )
            baseline_reviewed = root / "baseline-reviewed.json"
            candidate_reviewed = root / "candidate-reviewed.json"
            baseline_reviewed.write_text(json.dumps(baseline_out), encoding="utf-8")
            candidate_reviewed.write_text(json.dumps(candidate_out), encoding="utf-8")
            comparison = run_forward_eval.compare_summaries(
                baseline_reviewed, candidate_reviewed
            )

        self.assertEqual("pass", comparison["verdict"])
        self.assertTrue(comparison["human_fatal_coverage_met"])
        self.assertTrue(comparison["human_review_coverage_met"])
        self.assertEqual(0.8, comparison["token_ratio"])

    def test_score_import_rejects_package_or_summary_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline_root = root / "baseline"
            candidate_root = root / "candidate"
            baseline_root.mkdir()
            candidate_root.mkdir()
            baseline = make_summary(baseline_root, [("sample", 1)], "baseline")
            candidate = make_summary(candidate_root, [("sample", 1)], "candidate")
            package, answer_key = prepare_blind_review.build_blind_review(
                baseline, candidate, seed="private-import-seed"
            )
            package_path, template_path, key_path = prepare_blind_review.write_review_bundle(
                root / "bundle", package, answer_key
            )
            completed = self.complete_score_template(
                package, json.loads(template_path.read_text(encoding="utf-8"))
            )
            scores_path = root / "scores.json"
            scores_path.write_text(json.dumps(completed), encoding="utf-8")
            tampered_package = json.loads(package_path.read_text(encoding="utf-8"))
            tampered_package["fatal_taxonomy"].append("tampered_fatal")
            package_path.write_text(json.dumps(tampered_package), encoding="utf-8")
            with self.assertRaisesRegex(apply_blind_review.ReviewImportError, "hash"):
                apply_blind_review.apply_review(
                    package_path, key_path, scores_path, baseline, candidate
                )

            package_path.write_bytes(
                (
                    json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8")
            )
            baseline.write_text(
                baseline.read_text(encoding="utf-8") + " ", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                apply_blind_review.ReviewImportError, "summary changed"
            ):
                apply_blind_review.apply_review(
                    package_path, key_path, scores_path, baseline, candidate
                )


if __name__ == "__main__":
    unittest.main()
