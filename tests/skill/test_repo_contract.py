from __future__ import annotations

import builtins
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

import yaml

TEST_DIR = Path(__file__).resolve().parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

import run_forward_eval


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = (
    REPO_ROOT
    / ".agents"
    / "skills"
    / "kaoyan-math1-fullscore-coach"
    / "scripts"
)
VALIDATOR_PATH = SCRIPTS_DIR / "validate_math1_repo.py"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import repo_model  # noqa: E402
import validate_math1_repo as validator  # noqa: E402


PROBLEM_ID = "MATH1-CALC-0001"
PRACTICE_ID = "MATH1-CALC-0002"
KNOWLEDGE_ID = "MATH1-KN-CALC-0001"
METHOD_ID = "MATH1-KN-CALC-0002"
PITFALL_ID = "MATH1-KN-CALC-0003"
CHAPTER_KEY = "calc-01"
CHAPTER_FILE = "tex/chapters/calculus/01_function_limit_continuity.tex"
PRACTICE_FILE = "tex/practice/calculus/calc-01-problems.tex"
ANSWER_FILE = "tex/practice/calculus/calc-01-answers.tex"


EVAL_RUBRIC = {
    "math_correctness_and_conditions": 40,
    "intuition_and_exam_reproducibility": 20,
    "transfer_network_and_memory": 20,
    "archive_correctness": 15,
    "resource_efficiency": 5,
}


def comparison_summary(
    prompt_digest: str,
    rows: list[dict[str, object]],
    *,
    effort: str = "max",
    attest: bool = True,
) -> dict[str, object]:
    results = []
    for index, row in enumerate(rows, start=1):
        score = row.get("score")
        fatal_reviewed = bool(row.get("fatal_reviewed", attest))
        results.append(
            {
                "case_id": row.get("case_id", f"case_{index}"),
                "repetition": 1,
                "slice": row.get("slice", "math"),
                "rubric": "default",
                "automatic_pass": row.get("automatic_pass", True),
                "automatic_fatal_pass": row.get("automatic_pass", True),
                "elapsed_seconds": 1.0,
                "usage": {"total_tokens": row.get("tokens", 100)} if row.get("tokens", 100) is not None else {},
                "usage_complete": row.get("tokens", 100) is not None,
                "human_rubric_scores": (
                    {name: score for name in EVAL_RUBRIC} if score is not None else None
                ),
                "human_fatal_reviewed": fatal_reviewed,
                "human_fatal_failures": list(row.get("fatal", [])) if fatal_reviewed else None,
                "human_review_package_id": "package" if fatal_reviewed else None,
                "human_review_id": f"BR-{index:03d}" if fatal_reviewed else None,
                "oracle": {"summary": "oracle"},
                "hard_fail_if": ["wrong_final_answer"],
            }
        )
    summary: dict[str, object] = {
        "manifest_sha256": "manifest",
        "model": "gpt-5.6-sol",
        "effort": effort,
        "snapshot": "worktree",
        "runner": "wsl",
        "runner_isolation": run_forward_eval.WSL_RUNNER_ISOLATION,
        "sandbox": "workspace-write",
        "base_tree_sha256": "tree",
        "automatic_fatal_policy_id": run_forward_eval.AUTOMATIC_FATAL_POLICY_ID,
        "prompt_stack_sha256": prompt_digest,
        "fatal_failures": ["wrong_final_answer"],
        "rubrics": {"default": EVAL_RUBRIC},
        "results": results,
    }
    if attest:
        summary["human_review_attestation"] = {
            "package_id": "package",
            "reviewer": "Human reviewer",
            "reviewer_type": "human",
            "attested": True,
            "reviewed_at": "2026-07-18T12:00:00+00:00",
            "review_package_sha256": "a" * 64,
            "input_summary_sha256": "b" * 64,
        }
    return summary


def reclassification_summary() -> dict[str, object]:
    def result(
        case_id: str,
        automatic_failures: list[str] | None,
        *,
        detected_fatal_failures: list[str] | None = None,
        harness_error: str | None = None,
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "case_id": case_id,
            "repetition": 1,
            "slice": "math",
            "model": "gpt-5.6-sol",
            "effort": "max",
            "snapshot": "worktree",
            "prompt_source": "snapshot",
            "runner": "wsl",
            "runner_isolation": run_forward_eval.WSL_RUNNER_ISOLATION,
            "sandbox": "workspace-write",
            "frozen_tree_sha256": "frozen-tree",
            "automatic_pass": False,
            "automatic_fatal_pass": False,
            "detected_fatal_failures": detected_fatal_failures or [],
            "prompt": f"solve {case_id}",
            "expected": {"intent": "solve", "collection": "none", "persistence": "skip"},
            "task_kind": "solve",
            "fixture": {"base": "repository_snapshot"},
            "file_expectations": {"require_change": False, "allowed_changes": []},
            "oracle": {"summary": "oracle"},
            "rubric": "default",
            "hard_fail_if": ["wrong_final_answer"],
            "usage": {"total_tokens": 100},
            "usage_complete": True,
            "human_rubric_scores": None,
            "human_fatal_reviewed": False,
            "human_fatal_failures": None,
        }
        if harness_error is None:
            value["automatic_failures"] = automatic_failures or []
        else:
            value["harness_error"] = harness_error
            value["usage"] = {}
            value["usage_complete"] = False
        return value

    return {
        "schema_version": 1,
        "created_at": "2026-07-18T12:00:00+00:00",
        "repo_head": "a" * 40,
        "model": "gpt-5.6-sol",
        "effort": "max",
        "snapshot": "worktree",
        "prompt_source": "snapshot",
        "runner": "wsl",
        "runner_isolation": run_forward_eval.WSL_RUNNER_ISOLATION,
        "sandbox": "workspace-write",
        "base_tree_sha256": "base-tree",
        "frozen_tree_sha256": "frozen-tree",
        "prompt_stack_sha256": "prompt-stack",
        "manifest_sha256": "manifest",
        "automatic_fatal_policy_id": run_forward_eval.AUTOMATIC_FATAL_POLICY_ID,
        "fatal_failures": ["wrong_final_answer"],
        "rubrics": {"default": EVAL_RUBRIC},
        "results": [
            result(
                "semantic",
                [
                    "tool_execution",
                    "output_must_match:(?s)answer",
                    "output_must_not_match:(?s)forbidden",
                ],
            ),
            result("mechanical", ["required_change"]),
            result(
                "harness",
                None,
                detected_fatal_failures=["harness_error"],
                harness_error="runner failed",
            ),
        ],
    }


def allowlist_rescore_summary() -> tuple[dict[str, object], dict[str, object]]:
    manifest, cases = run_forward_eval.load_manifest(
        REPO_ROOT / "tests/skill/cases.yml"
    )
    case = next(
        item for item in cases if item["id"] == "persist_duplicate_add_solution"
    )
    old_file_expectations = copy.deepcopy(case["file_expectations"])
    old_file_expectations["allowed_changes"] = [
        "tex/chapters/calculus/01_function_limit_continuity.tex"
    ]
    changed_paths = ["tex/indexes/method_index.tex"]
    if run_forward_eval.matches_any(
        changed_paths[0], old_file_expectations["allowed_changes"]
    ):
        raise AssertionError("test fixture must fail the source allowlist")
    if not run_forward_eval.matches_any(
        changed_paths[0], case["file_expectations"]["allowed_changes"]
    ):
        raise AssertionError("test fixture must pass the current allowlist")

    automatic_checks = []
    for name in run_forward_eval._expected_automatic_check_names(case):
        passed = name != "allowed_paths"
        details = changed_paths[0] if name == "allowed_paths" else ""
        if name == "required_change":
            details = changed_paths[0]
        automatic_checks.append(
            {"name": name, "passed": passed, "details": details}
        )

    results = []
    for repetition in range(1, case["repetitions"] + 1):
        results.append(
            {
                "case_id": case["id"],
                "repetition": repetition,
                "slice": case["slice"],
                "model": "gpt-5.6-sol",
                "effort": "max",
                "snapshot": "worktree",
                "prompt_source": "snapshot",
                "runner": "wsl",
                "runner_isolation": run_forward_eval.WSL_RUNNER_ISOLATION,
                "sandbox": "workspace-write",
                "frozen_tree_sha256": "b" * 64,
                "prompt_stack_sha256": "c" * 64,
                "returncode": 0,
                "elapsed_seconds": 1.0,
                "usage": {"total_tokens": 100},
                "usage_complete": True,
                "changed_paths": copy.deepcopy(changed_paths),
                "automatic_checks": copy.deepcopy(automatic_checks),
                "automatic_failures": ["allowed_paths"],
                "automatic_pass": False,
                "automatic_fatal_pass": False,
                "detected_fatal_failures": [],
                "oracle": copy.deepcopy(case["oracle"]),
                "prompt": case["prompt"],
                "expected": copy.deepcopy(case["expected"]),
                "task_kind": case.get("task_kind"),
                "case_repetitions": case["repetitions"],
                "smoke": bool(case.get("smoke")),
                "fixture": copy.deepcopy(case["fixture"]),
                "file_expectations": copy.deepcopy(old_file_expectations),
                "checks_spec": copy.deepcopy(case["checks"]),
                "rubric": case["rubric"],
                "hard_fail_if": copy.deepcopy(case["hard_fail_if"]),
                "human_rubric_scores": None,
                "human_fatal_reviewed": False,
                "human_fatal_failures": None,
            }
        )

    return (
        {
            "schema_version": 1,
            "created_at": "2026-07-18T12:00:00+00:00",
            "repo_head": "d" * 40,
            "model": "gpt-5.6-sol",
            "effort": "max",
            "snapshot": "worktree",
            "prompt_source": "snapshot",
            "runner": "wsl",
            "runner_isolation": run_forward_eval.WSL_RUNNER_ISOLATION,
            "sandbox": "workspace-write",
            "base_tree_sha256": "e" * 64,
            "frozen_tree_sha256": "b" * 64,
            "prompt_stack_sha256": "c" * 64,
            "manifest_sha256": "a" * 64,
            "automatic_fatal_policy_id": run_forward_eval.AUTOMATIC_FATAL_POLICY_ID,
            "fatal_failures": copy.deepcopy(manifest["fatal_failures"]),
            "rubrics": copy.deepcopy(manifest["rubrics"]),
            "results": results,
        },
        case,
    )


class RepositoryFixture:
    def __init__(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)
        self._create()

    def close(self) -> None:
        self._temporary_directory.cleanup()

    def write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8", newline="\n")

    def read(self, relative_path: str) -> str:
        return (self.root / relative_path).read_text(encoding="utf-8")

    def load_yaml(self, relative_path: str) -> object:
        return yaml.safe_load(self.read(relative_path))

    def write_yaml(self, relative_path: str, value: object) -> None:
        self.write(
            relative_path,
            yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
        )

    def _create(self) -> None:
        self.write(
            "data/textbook_catalog.yml",
            f"""
subjects:
  calculus:
    name: "高等数学"
    lectures:
      - number: 1
        chapter_key: "{CHAPTER_KEY}"
        title: "函数、极限与连续"
        file: "{CHAPTER_FILE}"
    appendices: []
""",
        )
        tick = chr(96)
        self.write(
            "docs/textbook_catalog.md",
            f"""
# 教材目录

- {tick}{CHAPTER_KEY}{tick} {tick}{CHAPTER_FILE}{tick}
""",
        )
        self.write("data/problem_registry.yml", self.core_registry_entry())
        self.write(
            "data/web_pages.yml",
            f"""
schemaVersion: 2
pages:
  - slug: calc-01
    source: "{CHAPTER_FILE}"
  - slug: practice-calc-01
    source: "{PRACTICE_FILE}"
""",
        )
        self.write(
            "data/knowledge_registry.yml",
            f"""
schema_version: 1
nodes:
  - id: {KNOWLEDGE_ID}
    title: "极限"
    kind: concept
    subject: "高等数学"
    chapter_key: {CHAPTER_KEY}
    tex_anchor:
      file: "{CHAPTER_FILE}"
      id: {KNOWLEDGE_ID}
  - id: {METHOD_ID}
    title: "等价替换"
    kind: method
    subject: "高等数学"
    chapter_key: {CHAPTER_KEY}
  - id: {PITFALL_ID}
    title: "忽略条件"
    kind: pitfall
    subject: "高等数学"
    chapter_key: {CHAPTER_KEY}
edges:
  - source: {KNOWLEDGE_ID}
    target: {METHOD_ID}
    type: prerequisite_for
""",
        )
        self.write(
            "main.tex",
            rf"""
\input{{tex/preamble.tex}}
\input{{{CHAPTER_FILE}}}
""",
        )
        self.write(
            "main-web.tex",
            rf"""
\input{{tex/preamble_web.tex}}
\input{{{CHAPTER_FILE}}}
\input{{{PRACTICE_FILE}}}
\input{{{ANSWER_FILE}}}
""",
        )
        self.write(
            "practice.tex",
            rf"""
\input{{tex/preamble.tex}}
\input{{{PRACTICE_FILE}}}
""",
        )
        self.write(
            "practice-answers.tex",
            rf"""
\input{{tex/preamble.tex}}
\input{{{ANSWER_FILE}}}
""",
        )
        self.write("tex/preamble.tex", "% PDF preamble")
        self.write("tex/preamble_web.tex", "% Web preamble")
        for name in (
            "problem_template.tex",
            "practice_problem_template.tex",
            "knowledge_template.tex",
            "method_template.tex",
            "mistake_template.tex",
        ):
            self.write(f"tex/templates/{name}", f"% {name}")
        self.write(
            CHAPTER_FILE,
            rf"""
\studySubsection{{calc-01}}{{函数、极限与连续}}
\knowledgeAnchor[{KNOWLEDGE_ID}]{{极限}}
\problemAnchor{{{PROBLEM_ID}}}
\begin{{problemBox}}
测试题面。
\end{{problemBox}}
\begin{{solutionBox}}
完整解答。
\end{{solutionBox}}
""",
        )
        self.write(PRACTICE_FILE, "\\studySubsection{practice-calc-01}{练习库}")
        self.write(ANSWER_FILE, "% empty answer library")
        self.write(
            "tex/indexes/problem_index.tex",
            rf"""
\problemIndexAnchor{{{PROBLEM_ID}}}
\problemRef{{{PROBLEM_ID}}}
""",
        )
        self.write("tex/indexes/method_index.tex", "% method index")
        self.write("tex/indexes/mistake_index.tex", "% mistake index")
        self.write("tex/indexes/formula_index.tex", "% formula index")

    @staticmethod
    def core_registry_entry() -> str:
        return f"""
- id: {PROBLEM_ID}
  collection: core
  origin: core
  subject: "高等数学"
  chapter_key: {CHAPTER_KEY}
  title: "一个测试题"
  file: "{CHAPTER_FILE}"
  source: "用户粘贴"
  difficulty: "基础"
  knowledge_ids: [{KNOWLEDGE_ID}]
  method_ids: [{METHOD_ID}]
  pitfall_ids: [{PITFALL_ID}]
  verification_status: verified
"""

    @staticmethod
    def practice_entry(status: str = "verified") -> dict[str, object]:
        return {
            "id": PRACTICE_ID,
            "collection": "practice",
            "origin": "generated",
            "subject": "高等数学",
            "chapter_key": CHAPTER_KEY,
            "title": "一个练习题",
            "file": PRACTICE_FILE,
            "answer_file": ANSWER_FILE,
            "source": "用户要求生成 / 未注明来源",
            "difficulty": "基础",
            "knowledge_ids": [KNOWLEDGE_ID],
            "method_ids": [METHOD_ID],
            "pitfall_ids": [PITFALL_ID],
            "verification_status": status,
            "practice_stage": "near-transfer",
            "task_type": "calculation",
            "estimated_minutes": 5,
            "variant_of": PROBLEM_ID,
        }

    def add_practice_problem(self, status: str = "verified") -> None:
        entries = self.load_yaml("data/problem_registry.yml")
        assert isinstance(entries, list)
        entries.append(self.practice_entry(status))
        self.write_yaml("data/problem_registry.yml", entries)
        self.write(
            PRACTICE_FILE,
            rf"""
\studySubsection{{practice-calc-01}}{{练习库}}
\problemAnchor{{{PRACTICE_ID}}}
\begin{{problemBox}}练习题面。\end{{problemBox}}
""",
        )
        self.write(
            ANSWER_FILE,
            rf"""
\answerAnchor{{{PRACTICE_ID}}}
\begin{{solutionBox}}练习答案。\end{{solutionBox}}
""",
        )


class ValidatorContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepositoryFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    @staticmethod
    def failure_codes(report: validator.Report) -> set[str]:
        return {check.code for check in report.failures}

    @staticmethod
    def status_for(report: validator.Report, code: str) -> str:
        return next(check.status for check in report.checks if check.code == code)

    def validate(self) -> validator.Report:
        return validator.validate_repository(self.fixture.root, compile_enabled=False)

    def test_valid_fixture_passes_with_three_compile_skips(self) -> None:
        report = self.validate()
        self.assertFalse(report.failures)
        self.assertEqual("pass_with_skips", report.result)
        compile_checks = [
            check for check in report.checks if check.code.startswith("latex.compile.")
        ]
        self.assertEqual(3, len(compile_checks))
        self.assertTrue(all(check.status == "SKIP" for check in compile_checks))

    def test_invalid_registry_yaml_is_reported(self) -> None:
        self.fixture.write("data/problem_registry.yml", "- id: [unterminated")
        self.assertIn("registry.parse", self.failure_codes(self.validate()))

    def test_invalid_catalog_yaml_is_reported(self) -> None:
        self.fixture.write("data/textbook_catalog.yml", "subjects: [unterminated")
        self.assertIn("catalog.parse", self.failure_codes(self.validate()))

    def test_duplicate_registry_id_is_rejected(self) -> None:
        self.fixture.write(
            "data/problem_registry.yml",
            RepositoryFixture.core_registry_entry()
            + RepositoryFixture.core_registry_entry(),
        )
        self.assertIn("registry.schema", self.failure_codes(self.validate()))

    def test_missing_web_chapter_input_is_rejected(self) -> None:
        self.fixture.write("main-web.tex", "\\input{tex/preamble_web.tex}")
        self.assertIn("entrypoint.main-web.tex", self.failure_codes(self.validate()))

    def test_web_page_manifest_is_required(self) -> None:
        (self.fixture.root / "data/web_pages.yml").unlink()
        self.assertIn("repository.required_paths", self.failure_codes(self.validate()))

    def test_live_web_subsection_missing_from_manifest_is_rejected(self) -> None:
        manifest = self.fixture.load_yaml("data/web_pages.yml")
        assert isinstance(manifest, dict) and isinstance(manifest["pages"], list)
        manifest["pages"] = manifest["pages"][:1]
        self.fixture.write_yaml("data/web_pages.yml", manifest)
        self.assertIn("web_pages.mapping", self.failure_codes(self.validate()))

    def test_extra_web_manifest_slug_is_rejected(self) -> None:
        manifest = self.fixture.load_yaml("data/web_pages.yml")
        assert isinstance(manifest, dict) and isinstance(manifest["pages"], list)
        manifest["pages"].append(
            {"slug": "calc-01-extra", "source": CHAPTER_FILE}
        )
        self.fixture.write_yaml("data/web_pages.yml", manifest)
        self.assertIn("web_pages.mapping", self.failure_codes(self.validate()))

    def test_duplicate_web_manifest_slug_is_rejected(self) -> None:
        manifest = self.fixture.load_yaml("data/web_pages.yml")
        assert isinstance(manifest, dict) and isinstance(manifest["pages"], list)
        manifest["pages"].append(dict(manifest["pages"][0]))
        self.fixture.write_yaml("data/web_pages.yml", manifest)
        self.assertIn("web_pages.mapping", self.failure_codes(self.validate()))

    def test_web_manifest_source_must_be_the_tex_file_containing_slug(self) -> None:
        manifest = self.fixture.load_yaml("data/web_pages.yml")
        assert isinstance(manifest, dict) and isinstance(manifest["pages"], list)
        manifest["pages"][0]["source"] = PRACTICE_FILE
        self.fixture.write_yaml("data/web_pages.yml", manifest)
        self.assertIn("web_pages.mapping", self.failure_codes(self.validate()))

    def test_web_manifest_rejects_unsafe_and_missing_sources(self) -> None:
        for source in ("../outside.tex", "tex/chapters/calculus/missing.tex"):
            with self.subTest(source=source):
                manifest = self.fixture.load_yaml("data/web_pages.yml")
                assert isinstance(manifest, dict) and isinstance(manifest["pages"], list)
                manifest["pages"][0]["source"] = source
                self.fixture.write_yaml("data/web_pages.yml", manifest)
                self.assertIn("web_pages.mapping", self.failure_codes(self.validate()))
                self.fixture._create()

    def test_web_mapping_rejects_invalid_or_duplicate_live_ascii_slugs(self) -> None:
        chapter = self.fixture.read(CHAPTER_FILE)
        self.fixture.write(CHAPTER_FILE, chapter.replace("{calc-01}", "{中文-slug}"))
        self.assertIn("web_pages.mapping", self.failure_codes(self.validate()))

        self.fixture._create()
        chapter = self.fixture.read(CHAPTER_FILE)
        self.fixture.write(
            CHAPTER_FILE,
            chapter + "\\studySubsection{calc-01}{重复页面}\n",
        )
        self.assertIn("web_pages.mapping", self.failure_codes(self.validate()))

    def test_web_mapping_ignores_comments_study_sections_and_templates(self) -> None:
        chapter = self.fixture.read(CHAPTER_FILE)
        self.fixture.write(
            CHAPTER_FILE,
            chapter
            + "% \\studySubsection{commented-out}{注释}\n"
            + "\\studySection{not-a-page}{章节}\n",
        )
        self.fixture.write(
            "tex/templates/problem_template.tex",
            "\\studySubsection{template-only}{模板占位}",
        )
        self.assertNotIn("web_pages.mapping", self.failure_codes(self.validate()))

    def test_commented_chapter_input_is_not_treated_as_live(self) -> None:
        self.fixture.write(
            "main.tex",
            rf"""
\input{{tex/preamble.tex}}
% \input{{{CHAPTER_FILE}}}
""",
        )
        self.assertIn("entrypoint.main.tex", self.failure_codes(self.validate()))

    def test_nested_practice_input_is_rejected_from_main_pdf(self) -> None:
        chapter = self.fixture.read(CHAPTER_FILE) + f"\\input{{{PRACTICE_FILE}}}\n"
        self.fixture.write(CHAPTER_FILE, chapter)
        self.assertIn("entrypoint.main.tex", self.failure_codes(self.validate()))

    def test_core_registry_path_must_match_catalog(self) -> None:
        registry = self.fixture.read("data/problem_registry.yml").replace(
            CHAPTER_FILE,
            "tex/chapters/calculus/99_missing.tex",
        )
        self.fixture.write("data/problem_registry.yml", registry)
        self.assertIn("registry.schema", self.failure_codes(self.validate()))

    def test_missing_problem_anchor_is_rejected(self) -> None:
        self.fixture.write(
            CHAPTER_FILE,
            f"\\knowledgeAnchor[{KNOWLEDGE_ID}]{{极限}}",
        )
        self.assertIn("problems.content_anchors", self.failure_codes(self.validate()))

    def test_missing_core_solution_is_rejected(self) -> None:
        chapter = self.fixture.read(CHAPTER_FILE).replace(
            "\\begin{solutionBox}\n完整解答。\n\\end{solutionBox}",
            "",
        )
        self.fixture.write(CHAPTER_FILE, chapter)
        self.assertIn("problems.required_blocks", self.failure_codes(self.validate()))

    def test_dangling_problem_and_knowledge_refs_are_rejected(self) -> None:
        self.fixture.write(
            "tex/indexes/method_index.tex",
            "\\problemRef{MATH1-CALC-9999}\\knowledgeRef[MATH1-KN-CALC-9999]{未知}",
        )
        self.assertIn("references.dangling", self.failure_codes(self.validate()))

    def test_knowledge_edge_self_loop_is_rejected(self) -> None:
        graph = self.fixture.load_yaml("data/knowledge_registry.yml")
        assert isinstance(graph, dict) and isinstance(graph["edges"], list)
        graph["edges"].append(
            {"source": KNOWLEDGE_ID, "target": KNOWLEDGE_ID, "type": "same_structure_as"}
        )
        self.fixture.write_yaml("data/knowledge_registry.yml", graph)
        self.assertIn("knowledge.schema", self.failure_codes(self.validate()))

    def test_malformed_yaml_value_types_report_failures_instead_of_crashing(self) -> None:
        entries = self.fixture.load_yaml("data/problem_registry.yml")
        assert isinstance(entries, list)
        entries[0]["collection"] = ["core"]
        self.fixture.write_yaml("data/problem_registry.yml", entries)
        self.assertIn("registry.schema", self.failure_codes(self.validate()))

        self.fixture.write("data/problem_registry.yml", RepositoryFixture.core_registry_entry())
        graph = self.fixture.load_yaml("data/knowledge_registry.yml")
        assert isinstance(graph, dict) and isinstance(graph["edges"], list)
        graph["edges"][0]["source"] = [KNOWLEDGE_ID]
        self.fixture.write_yaml("data/knowledge_registry.yml", graph)
        self.assertIn("knowledge.schema", self.failure_codes(self.validate()))

    def test_malformed_practice_enum_types_report_registry_failure(self) -> None:
        self.fixture.add_practice_problem("verified")
        entries = self.fixture.load_yaml("data/problem_registry.yml")
        assert isinstance(entries, list)
        entries[-1]["practice_stage"] = ["near-transfer"]
        entries[-1]["task_type"] = ["calculation"]
        self.fixture.write_yaml("data/problem_registry.yml", entries)
        self.assertIn("registry.schema", self.failure_codes(self.validate()))

    def test_problem_and_knowledge_id_domains_must_match_chapter(self) -> None:
        registry = self.fixture.read("data/problem_registry.yml").replace(
            PROBLEM_ID, "MATH1-LA-0001"
        )
        self.fixture.write("data/problem_registry.yml", registry)
        self.assertIn("registry.schema", self.failure_codes(self.validate()))

        self.fixture.write("data/problem_registry.yml", RepositoryFixture.core_registry_entry())
        graph = self.fixture.load_yaml("data/knowledge_registry.yml")
        assert isinstance(graph, dict) and isinstance(graph["nodes"], list)
        graph["nodes"][0]["id"] = "MATH1-KN-LA-0001"
        graph["nodes"][0]["tex_anchor"]["id"] = "MATH1-KN-LA-0001"
        self.fixture.write_yaml("data/knowledge_registry.yml", graph)
        self.assertIn("knowledge.schema", self.failure_codes(self.validate()))

    def test_knowledge_anchor_path_must_stay_inside_repository(self) -> None:
        graph = self.fixture.load_yaml("data/knowledge_registry.yml")
        assert isinstance(graph, dict) and isinstance(graph["nodes"], list)
        graph["nodes"][0]["tex_anchor"]["file"] = str(Path(__file__).resolve())
        self.fixture.write_yaml("data/knowledge_registry.yml", graph)
        self.assertIn("knowledge.schema", self.failure_codes(self.validate()))

    def test_duplicate_knowledge_destination_is_rejected(self) -> None:
        self.fixture.write(
            "tex/indexes/method_index.tex",
            rf"\knowledgeAnchor[{KNOWLEDGE_ID}]{{重复目标}}",
        )
        self.assertIn("references.dangling", self.failure_codes(self.validate()))

    def test_registry_node_kind_must_match_reference_field(self) -> None:
        entries = self.fixture.load_yaml("data/problem_registry.yml")
        assert isinstance(entries, list)
        entries[0]["method_ids"] = [PITFALL_ID]
        self.fixture.write_yaml("data/problem_registry.yml", entries)
        self.assertIn("registry.schema", self.failure_codes(self.validate()))

    def test_verified_practice_problem_and_answer_pass(self) -> None:
        self.fixture.add_practice_problem("verified")
        report = self.validate()
        self.assertFalse(report.failures)
        self.assertIn(PRACTICE_ID, repo_model.existing_problem_ids(self.fixture.root))

        next_id = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "next_problem_id.py"),
                "--root",
                str(self.fixture.root),
                "--subject",
                "calc",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, next_id.returncode, next_id.stderr)
        self.assertEqual("MATH1-CALC-0003", next_id.stdout.strip())

    def test_practice_answer_anchor_and_solution_are_required(self) -> None:
        self.fixture.add_practice_problem("verified")
        self.fixture.write(ANSWER_FILE, "% missing answer")
        self.assertIn("practice.answers", self.failure_codes(self.validate()))

    def test_commented_answer_anchor_and_solution_are_not_treated_as_live(self) -> None:
        self.fixture.add_practice_problem("verified")
        self.fixture.write(
            ANSWER_FILE,
            rf"""
% \answerAnchor{{{PRACTICE_ID}}}
% \begin{{solutionBox}}伪答案。\end{{solutionBox}}
""",
        )
        self.assertIn("practice.answers", self.failure_codes(self.validate()))

    def test_draft_in_public_practice_file_is_rejected(self) -> None:
        self.fixture.add_practice_problem("draft")
        self.assertIn("publication.library_isolation", self.failure_codes(self.validate()))

    def test_main_pdf_cannot_include_practice_files(self) -> None:
        self.fixture.write(
            "main.tex",
            rf"""
\input{{tex/preamble.tex}}
\input{{{CHAPTER_FILE}}}
\input{{{PRACTICE_FILE}}}
""",
        )
        self.assertIn("entrypoint.main.tex", self.failure_codes(self.validate()))

    def test_reference_namespace_and_argument_shape_are_enforced(self) -> None:
        self.fixture.write(
            "tex/indexes/method_index.tex",
            rf"\knowledgeIndexRef[{KNOWLEDGE_ID}]{{错误命名空间}}",
        )
        self.assertIn("references.dangling", self.failure_codes(self.validate()))

        self.fixture.write(
            "tex/indexes/method_index.tex",
            "\\problemRef{NOT-A-PROBLEM-ID}",
        )
        self.assertIn("references.dangling", self.failure_codes(self.validate()))

    def test_missing_pyyaml_is_a_dependency_error(self) -> None:
        real_import = builtins.__import__

        def import_without_yaml(name: str, *args: object, **kwargs: object) -> object:
            if name == "yaml":
                raise ImportError("simulated missing PyYAML")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=import_without_yaml):
            with self.assertRaises(repo_model.RepositoryDependencyError):
                repo_model.load_registry(self.fixture.root)

    def test_missing_compiler_skips_all_three_pdfs(self) -> None:
        report = validator.Report()
        with mock.patch.object(validator.shutil, "which", return_value=None):
            validator._compile_entrypoints(self.fixture.root, report, enabled=True)
        self.assertEqual(3, len(report.checks))
        self.assertTrue(all(check.status == "SKIP" for check in report.checks))

    def test_cli_exit_codes_and_json_output(self) -> None:
        success = self.run_cli(self.fixture.root)
        self.assertEqual(0, success.returncode, success.stderr)
        self.assertEqual("pass_with_skips", json.loads(success.stdout)["result"])

        self.fixture.write("data/problem_registry.yml", "- id: [unterminated")
        failure = self.run_cli(self.fixture.root)
        self.assertEqual(1, failure.returncode, failure.stderr)
        self.assertEqual("fail", json.loads(failure.stdout)["result"])

        missing_root = self.fixture.root / "does-not-exist"
        usage_error = self.run_cli(missing_root)
        self.assertEqual(2, usage_error.returncode, usage_error.stderr)
        self.assertEqual("error", json.loads(usage_error.stdout)["result"])

    @staticmethod
    def run_cli(root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                "--root",
                str(root),
                "--no-compile",
                "--format",
                "json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


class CurrentRepositoryContractTests(unittest.TestCase):
    def test_practice_workbook_uses_printable_cross_pdf_answer_locations(self) -> None:
        workbook = (REPO_ROOT / "practice.tex").read_text(encoding="utf-8")
        template = (
            REPO_ROOT / "tex/templates/practice_problem_template.tex"
        ).read_text(encoding="utf-8")
        self.assertIn(r"\RenewDocumentCommand{\answerRef}", workbook)
        self.assertIn("答案册同编号", workbook)
        self.assertIn(r"\answerRef{MATH1-CALC-0000}", template)
        self.assertIn(r"\texttt{MATH1-CALC-0000}", template)

    def test_current_repository_has_expected_library_and_graph_contract(self) -> None:
        report = validator.validate_repository(REPO_ROOT, compile_enabled=False)
        self.assertFalse(
            report.failures,
            "\n".join(
                f"{check.code}: {check.details or check.message}"
                for check in report.failures
            ),
        )
        catalog = repo_model.load_catalog(REPO_ROOT)
        registry = repo_model.load_registry(REPO_ROOT)
        graph = repo_model.load_knowledge_registry(REPO_ROOT)
        self.assertEqual(37, len(catalog))
        self.assertEqual(37, len({entry.chapter_key for entry in catalog}))
        self.assertEqual(10, len(registry))
        self.assertTrue(all(entry["collection"] == "core" for entry in registry))
        self.assertGreaterEqual(len(graph["nodes"]), 20)
        self.assertTrue(graph["edges"])
        statuses = {check.code: check.status for check in report.checks}
        for code in (
            "catalog.documentation",
            "entrypoint.main.tex",
            "entrypoint.main-web.tex",
            "knowledge.schema",
            "registry.schema",
            "practice.file_pairs",
            "practice.entrypoint.practice.tex",
            "practice.entrypoint.practice-answers.tex",
            "web_pages.mapping",
            "problems.content_anchors",
            "problems.registry_paths",
            "problems.required_blocks",
            "practice.answers",
            "problems.index_anchors",
            "publication.library_isolation",
            "references.dangling",
        ):
            self.assertEqual("PASS", statuses[code], code)

    def test_behavior_eval_manifest_has_expected_slices_and_gates(self) -> None:
        manifest = yaml.safe_load(
            (REPO_ROOT / "tests/skill/cases.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(1, manifest["schema_version"])
        cases = manifest["cases"]
        self.assertEqual(24, len(cases))
        self.assertEqual(
            Counter({"math": 9, "teaching": 6, "persistence": 9}),
            Counter(case["slice"] for case in cases),
        )
        self.assertEqual(8, sum(bool(case.get("smoke")) for case in cases))
        self.assertEqual(100, sum(manifest["rubrics"]["default"].values()))
        self.assertIn("wrong_final_answer", manifest["fatal_failures"])
        self.assertIn("wrong_collection", manifest["fatal_failures"])
        self.assertEqual(len(manifest["fatal_failures"]), len(set(manifest["fatal_failures"])))
        fatal_taxonomy = set(manifest["fatal_failures"])
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["prompt"].strip())
                self.assertIn("expected", case)
                self.assertIn("oracle", case)
                self.assertTrue(case["hard_fail_if"])
                self.assertLessEqual(set(case["hard_fail_if"]), fatal_taxonomy)

    def test_behavior_eval_manifest_accepts_equivalent_representative_outputs(self) -> None:
        manifest = yaml.safe_load(
            (REPO_ROOT / "tests/skill/cases.yml").read_text(encoding="utf-8")
        )
        cases = {case["id"]: case for case in manifest["cases"]}
        representative_outputs = {
            "math_calc_limit_second_order": (
                r"结论为 \(\frac12\)，由恒等变形可知该等价替换合法。"
            ),
            "math_prob_bayes": r"由贝叶斯公式，结果为 \(15.38\%\)。",
            "teach_guided_continuity_differentiability": (
                "先把连续钉牢，暂时不谈可导。你只回答三个判断问题，想一想再回复。"
            ),
        }

        for case_id, output in representative_outputs.items():
            patterns = cases[case_id]["checks"]["output_must_match"]
            self.assertTrue(patterns, case_id)
            for pattern in patterns:
                with self.subTest(case=case_id, pattern=pattern):
                    self.assertIsNotNone(re.search(pattern, output))

        diagnosis_patterns = cases["teach_diagnose_false_implication"]["checks"][
            "output_must_match"
        ]
        diagnosis_variants = (
            r"把定理方向倒置了；反例 (f(x)=|x-x_0|) 连续但不可导，左右极限不同。",
            r"把逆命题当成真命题；反例 (f(x)=|x|) 的左右导数不相等，因此不可导。",
        )
        for output in diagnosis_variants:
            for pattern in diagnosis_patterns:
                with self.subTest(case="teach_diagnose_false_implication", output=output):
                    self.assertIsNotNone(re.search(pattern, output))

    def test_forward_eval_manifest_rejects_invalid_fatal_taxonomy(self) -> None:
        manifest = yaml.safe_load(
            (REPO_ROOT / "tests/skill/cases.yml").read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cases.yml"
            for fatal_failures, expected_error in (
                ([], "non-empty unique"),
                (["duplicate", "duplicate"], "non-empty unique"),
            ):
                altered = dict(manifest)
                altered["fatal_failures"] = fatal_failures
                path.write_text(yaml.safe_dump(altered), encoding="utf-8")
                with self.assertRaisesRegex(run_forward_eval.ManifestError, expected_error):
                    run_forward_eval.load_manifest(path)

            altered = yaml.safe_load(yaml.safe_dump(manifest))
            altered["cases"][0]["hard_fail_if"] = ["outside_taxonomy"]
            path.write_text(yaml.safe_dump(altered), encoding="utf-8")
            with self.assertRaisesRegex(run_forward_eval.ManifestError, "absent from fatal_failures"):
                run_forward_eval.load_manifest(path)

    def test_forward_eval_runner_defaults_to_safe_list_mode(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tests/skill/run_forward_eval.py"),
                "--smoke",
            ],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("LIST ONLY: 8 cases, 14 runs", completed.stdout)
        self.assertNotIn("RUN ", completed.stdout)

    def test_forward_eval_runner_resolves_windows_codex_executable(self) -> None:
        def command_first(name: str) -> str | None:
            mapping = {
                "codex.cmd": "C:/npm/codex.cmd",
                "codex.exe": "C:/Codex/codex.exe",
            }
            return mapping.get(name)

        self.assertEqual(
            ["C:/Windows/System32/cmd.exe", "/d", "/s", "/c", "C:/npm/codex.cmd"],
            run_forward_eval.resolve_codex_command(
                "nt", command_first, "C:/Windows/System32/cmd.exe"
            ),
        )

        def executable_fallback(name: str) -> str | None:
            return "C:/Codex/codex.exe" if name == "codex.exe" else None

        self.assertEqual(
            ["C:/Codex/codex.exe"],
            run_forward_eval.resolve_codex_command("nt", executable_fallback),
        )

    def test_forward_eval_output_directory_must_be_external_and_empty(self) -> None:
        with self.assertRaisesRegex(run_forward_eval.ManifestError, "outside the repository"):
            run_forward_eval.prepare_output_directory(REPO_ROOT / ".eval-output")
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            nonempty = parent / "nonempty"
            nonempty.mkdir()
            (nonempty / "old-summary.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(run_forward_eval.ManifestError, "must be empty"):
                run_forward_eval.prepare_output_directory(nonempty)
            empty = parent / "empty"
            empty.mkdir()
            self.assertEqual(empty.resolve(), run_forward_eval.prepare_output_directory(empty))

    def test_wsl_runner_fails_before_evaluation_when_bwrap_is_missing(self) -> None:
        missing = subprocess.CompletedProcess(
            args=["wsl.exe"], returncode=127, stdout="", stderr="not found"
        )
        with mock.patch.object(run_forward_eval.subprocess, "run", return_value=missing):
            with self.assertRaisesRegex(RuntimeError, "requires bubblewrap"):
                run_forward_eval.require_wsl_bwrap()

    @unittest.skipUnless(os.name == "nt" and shutil.which("wsl.exe"), "requires Windows WSL")
    def test_wsl_bwrap_exposes_only_disposable_workspace_and_output(self) -> None:
        run_forward_eval.require_wsl_bwrap()
        def runtime_directories() -> set[str]:
            completed = subprocess.run(
                [
                    "wsl.exe",
                    "-e",
                    "bash",
                    "-lc",
                    'find "$HOME" -maxdepth 1 -type d -name ".codex-eval-runtime-*" -print',
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
                env=run_forward_eval.sanitized_environment(),
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            return set(completed.stdout.splitlines())

        runtime_before = runtime_directories()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            output = root / "output"
            workspace.mkdir()
            output.mkdir()
            (workspace / "visible.txt").write_text("workspace", encoding="utf-8")
            original_oracle = run_forward_eval.to_wsl_path(
                REPO_ROOT / "tests/skill/cases.yml"
            )
            original_codex_home = subprocess.run(
                ["wsl.exe", "-e", "bash", "-lc", 'printf %s "$HOME/.codex"'],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                env=run_forward_eval.sanitized_environment(),
            ).stdout
            command = run_forward_eval.build_wsl_bwrap_command(
                workspace,
                output,
                [
                    "sh",
                    "-c",
                    'test -f visible.txt && test -d /tmp/output && test ! -e "$1" '
                    '&& test -d /mnt/wsl && test -r /etc/resolv.conf '
                    '&& test ! -e /mnt/c/Users && test "$HOME" = /tmp/eval-home '
                    '&& test "$CODEX_HOME" = /tmp/eval-home/.codex '
                    '&& test -w "$CODEX_HOME" && test ! -e "$2/auth.json" '
                    '&& command -v codex >/dev/null && command -v node >/dev/null '
                    '&& for drive in /mnt/[a-z]; do '
                    'test ! -d "$drive" || test -z "$(find "$drive" -mindepth 1 -maxdepth 1 -print -quit)" '
                    '|| exit 1; done '
                    '&& getent hosts chatgpt.com > /tmp/output/dns-resolution.txt '
                    '&& codex --version > /tmp/output/codex-version.txt '
                    '&& node --version > /tmp/output/node-version.txt '
                    '&& printf isolated > /tmp/output/probe.txt',
                    "sh",
                    original_oracle,
                    original_codex_home,
                ],
            )
            self.assertNotIn("--unshare-net", " ".join(command))
            completed = subprocess.run(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=60,
                env=run_forward_eval.sanitized_environment(),
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("isolated", (output / "probe.txt").read_text(encoding="utf-8"))
            self.assertTrue((output / "dns-resolution.txt").read_text(encoding="utf-8").strip())
            self.assertTrue((output / "codex-version.txt").read_text(encoding="utf-8").strip())
            self.assertTrue((output / "node-version.txt").read_text(encoding="utf-8").strip())
        self.assertEqual(runtime_before, runtime_directories())

    def test_forward_eval_compare_is_offline_and_reports_pending_human_review(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            summary = {
                "manifest_sha256": "manifest",
                "model": "gpt-5.6-sol",
                "effort": "max",
                "snapshot": "worktree",
                "runner": "wsl",
                "runner_isolation": run_forward_eval.WSL_RUNNER_ISOLATION,
                "sandbox": "workspace-write",
                "base_tree_sha256": "tree",
                "automatic_fatal_policy_id": run_forward_eval.AUTOMATIC_FATAL_POLICY_ID,
                "prompt_stack_sha256": "baseline-prompt",
                "fatal_failures": ["wrong_final_answer"],
                "rubrics": {
                    "default": {
                        "math_correctness_and_conditions": 40,
                        "intuition_and_exam_reproducibility": 20,
                        "transfer_network_and_memory": 20,
                        "archive_correctness": 15,
                        "resource_efficiency": 5,
                    }
                },
                "results": [
                    {
                        "case_id": "sample",
                        "repetition": 1,
                        "slice": "math",
                        "rubric": "default",
                        "automatic_pass": True,
                        "automatic_fatal_pass": True,
                        "elapsed_seconds": 1.0,
                        "usage": {"total_tokens": 100},
                        "hard_fail_if": ["wrong_final_answer"],
                        "human_rubric_scores": None,
                        "human_fatal_failures": None,
                    }
                ]
            }
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(json.dumps(summary), encoding="utf-8")
            candidate_summary = dict(summary)
            candidate_summary["prompt_stack_sha256"] = "candidate-prompt"
            candidate.write_text(json.dumps(candidate_summary), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tests/skill/run_forward_eval.py"),
                    "--compare",
                    str(baseline),
                    str(candidate),
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(3, completed.returncode, completed.stderr)
        comparison = json.loads(completed.stdout)
        self.assertTrue(comparison["deterministic_gate"])
        self.assertFalse(comparison["human_fatal_coverage_met"])
        self.assertFalse(comparison["human_review_coverage_met"])
        self.assertEqual("pending_human_review", comparison["verdict"])

    def test_forward_eval_event_metrics_detect_failed_tools_and_real_validation(self) -> None:
        events = "\n".join(
            [
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "skill",
                            "type": "command_execution",
                            "command": "Get-Content .agents/skills/kaoyan-math1-fullscore-coach/SKILL.md",
                            "aggregated_output": "---\nname: kaoyan-math1-fullscore-coach\n---\n# Skill",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "validator",
                            "type": "command_execution",
                            "command": "python validate_math1_repo.py",
                            "aggregated_output": "RESULT: PASS_WITH_SKIPS",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "failed",
                            "type": "command_execution",
                            "command": "broken command",
                            "aggregated_output": "sandbox error",
                            "exit_code": -1,
                            "status": "failed",
                        },
                    }
                ),
            ]
        )
        metrics = run_forward_eval.event_metrics(events)
        self.assertTrue(metrics["skill_loaded"])
        self.assertTrue(metrics["model_validator_succeeded"])
        self.assertTrue(metrics["usage_complete"])
        self.assertEqual(1, len(metrics["failed_tools"]))

    def test_forward_eval_compare_applies_weighted_review_and_fatal_gates(self) -> None:
        rubric = {
            "math_correctness_and_conditions": 40,
            "intuition_and_exam_reproducibility": 20,
            "transfer_network_and_memory": 20,
            "archive_correctness": 15,
            "resource_efficiency": 5,
        }

        def summary(prompt: str, score: int, fatal: list[str]) -> dict[str, object]:
            results = []
            for index in range(5):
                reviewed = index == 0
                results.append(
                    {
                        "case_id": f"sample_{index}",
                        "repetition": 1,
                        "slice": "math",
                        "rubric": "default",
                        "automatic_pass": True,
                        "automatic_fatal_pass": True,
                        "elapsed_seconds": 1,
                        "usage": {"total_tokens": 100},
                        "usage_complete": True,
                        "human_rubric_scores": (
                            {name: score for name in rubric} if reviewed else None
                        ),
                        "human_fatal_reviewed": True,
                        "human_fatal_failures": fatal if reviewed else [],
                        "human_review_package_id": "package",
                        "human_review_id": f"BR-{index + 1:03d}",
                        "hard_fail_if": ["wrong_final_answer"],
                    }
                )
            return {
                "manifest_sha256": "manifest",
                "model": "gpt-5.6-sol",
                "effort": "max",
                "snapshot": "worktree",
                "runner": "wsl",
                "runner_isolation": run_forward_eval.WSL_RUNNER_ISOLATION,
                "sandbox": "workspace-write",
                "base_tree_sha256": "tree",
                "automatic_fatal_policy_id": run_forward_eval.AUTOMATIC_FATAL_POLICY_ID,
                "prompt_stack_sha256": prompt,
                "fatal_failures": ["wrong_final_answer"],
                "rubrics": {"default": rubric},
                "human_review_attestation": {
                    "package_id": "package",
                    "reviewer": "Human reviewer",
                    "reviewer_type": "human",
                    "attested": True,
                    "reviewed_at": "2026-07-18T12:00:00+00:00",
                    "review_package_sha256": "a" * 64,
                    "input_summary_sha256": "b" * 64,
                },
                "results": results,
            }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(json.dumps(summary("old", 80, [])), encoding="utf-8")
            candidate.write_text(json.dumps(summary("new", 86, [])), encoding="utf-8")
            comparison = run_forward_eval.compare_summaries(baseline, candidate)
            self.assertEqual("pass", comparison["verdict"])
            self.assertTrue(comparison["human_review_coverage_met"])

            candidate.write_text(
                json.dumps(summary("new", 86, ["wrong_final_answer"])),
                encoding="utf-8",
            )
            comparison = run_forward_eval.compare_summaries(baseline, candidate)
            self.assertEqual("fail", comparison["verdict"])
            self.assertFalse(comparison["human_fatal_gate"])

    def test_forward_eval_snapshot_excludes_eval_only_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            destination = Path(temporary) / "snapshot"
            (source / "tests/skill").mkdir(parents=True)
            (source / "AGENTS.md").write_text("contract", encoding="utf-8")
            (source / "tests/skill/cases.yml").write_text("oracle", encoding="utf-8")
            listed = b"AGENTS.md\0tests/skill/cases.yml\0"
            completed = subprocess.CompletedProcess(
                args=["git"], returncode=0, stdout=listed, stderr=b""
            )
            with mock.patch.object(run_forward_eval, "REPO_ROOT", source), mock.patch.object(
                run_forward_eval.subprocess, "run", return_value=completed
            ):
                run_forward_eval.make_snapshot("worktree", destination)
            self.assertEqual("contract", (destination / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertFalse((destination / "tests/skill").exists())

    def test_forward_eval_initializes_clean_local_git_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracked = root / "tracked.txt"
            tracked.write_text("baseline\n", encoding="utf-8")
            run_forward_eval.initialize_snapshot_git(root)

            clean = subprocess.run(
                ["git", "status", "--short"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, clean.returncode, clean.stderr)
            self.assertEqual("", clean.stdout)
            self.assertFalse(any(path.startswith(".git/") for path in run_forward_eval.file_state(root)))

            tracked.write_text("changed\n", encoding="utf-8")
            changed = subprocess.run(
                ["git", "status", "--short"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, changed.returncode, changed.stderr)
            self.assertIn(" M tracked.txt", changed.stdout)

    def test_forward_eval_skill_read_and_usage_require_real_evidence(self) -> None:
        events = "\n".join(
            [
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "fake",
                            "type": "command_execution",
                            "command": "echo .agents/skills/kaoyan-math1-fullscore-coach/SKILL.md",
                            "aggregated_output": "SKILL.md",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    }
                ),
                json.dumps({"type": "turn.completed"}),
            ]
        )
        metrics = run_forward_eval.event_metrics(events)
        self.assertFalse(metrics["skill_loaded"])
        self.assertFalse(metrics["usage_complete"])

    def test_forward_eval_event_metrics_capture_router_errors_but_ignore_path_warning(self) -> None:
        stderr = "\n".join(
            [
                "WARNING: proceeding, even though we could not create PATH aliases: temporary dir /tmp",
                "2026-07-18T19:08:42Z ERROR codex_core::tools::router: "
                "error=apply_patch verification failed: missing context",
            ]
        )
        metrics = run_forward_eval.event_metrics(
            json.dumps({"type": "turn.completed", "usage": {"total_tokens": 10}}),
            stderr,
        )
        self.assertEqual(
            ["router: apply_patch verification failed: missing context"],
            metrics["failed_tools"],
        )

    def test_tool_execution_failure_is_automatic_but_not_fatal_by_itself(self) -> None:
        self.assertTrue(run_forward_eval.automatic_fatal_pass(["tool_execution"], []))
        self.assertTrue(
            run_forward_eval.automatic_fatal_pass(
                ["tool_execution", "output_must_match:answer"], []
            )
        )
        self.assertTrue(
            run_forward_eval.automatic_fatal_pass(
                ["output_must_not_match:forbidden"], []
            )
        )
        self.assertFalse(run_forward_eval.automatic_fatal_pass(["required_change"], []))
        self.assertFalse(
            run_forward_eval.automatic_fatal_pass(
                ["tool_execution"], ["false_validation_claim"]
            )
        )

    def test_forward_eval_reclassifies_complete_summary_without_mutating_source(self) -> None:
        summary = reclassification_summary()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            output = root / "reclassified.json"
            source_bytes = (
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
            source.write_bytes(source_bytes)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tests/skill/run_forward_eval.py"),
                    "--reclassify",
                    str(source),
                    str(output),
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(source_bytes, source.read_bytes())
            reclassified = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(
            hashlib.sha256(source_bytes).hexdigest(),
            reclassified["source_summary_sha256"],
        )
        self.assertEqual(
            run_forward_eval.AUTOMATIC_FATAL_POLICY_ID,
            reclassified["automatic_fatal_policy_id"],
        )
        self.assertTrue(reclassified["reclassified_at"])
        expected_results = json.loads(json.dumps(summary["results"]))
        expected_results[0]["automatic_fatal_pass"] = True
        expected_results[1]["automatic_fatal_pass"] = False
        expected_results[2]["automatic_fatal_pass"] = False
        self.assertEqual(expected_results, reclassified["results"])

    def test_forward_eval_reclassify_rejects_overwrite_and_malformed_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source_bytes = json.dumps(reclassification_summary()).encode("utf-8")
            source.write_bytes(source_bytes)
            overwrite = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tests/skill/run_forward_eval.py"),
                    "--reclassify",
                    str(source),
                    str(source),
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(2, overwrite.returncode)
            self.assertEqual(source_bytes, source.read_bytes())

            malformed = root / "malformed.json"
            malformed.write_text(
                json.dumps({"schema_version": 1, "results": []}), encoding="utf-8"
            )
            output = root / "should-not-exist.json"
            rejected = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tests/skill/run_forward_eval.py"),
                    "--reclassify",
                    str(malformed),
                    str(output),
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(2, rejected.returncode)
            self.assertFalse(output.exists())

    def test_forward_eval_rescores_only_allowlist_into_a_new_audited_summary(self) -> None:
        summary, current_case = allowlist_rescore_summary()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            output = root / "rescored.json"
            source_bytes = (
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
            source.write_bytes(source_bytes)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "tests/skill/run_forward_eval.py"),
                    "--manifest",
                    str(REPO_ROOT / "tests/skill/cases.yml"),
                    "--rescore-allowlist",
                    str(source),
                    str(output),
                ],
                cwd=REPO_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("ALLOWLIST RESCORED", completed.stdout)
            self.assertEqual(source_bytes, source.read_bytes())
            self.assertEqual(1, output.stat().st_nlink)
            rescored = json.loads(output.read_text(encoding="utf-8"))

        target_manifest_sha = hashlib.sha256(
            (REPO_ROOT / "tests/skill/cases.yml").read_bytes()
        ).hexdigest()
        provenance = rescored["allowlist_rescore"]
        self.assertEqual(
            run_forward_eval.ALLOWLIST_RESCORE_MODE, provenance["mode"]
        )
        self.assertEqual(
            hashlib.sha256(source_bytes).hexdigest(),
            provenance["source_summary_sha256"],
        )
        self.assertEqual("a" * 64, provenance["source_manifest_sha256"])
        self.assertEqual(target_manifest_sha, provenance["target_manifest_sha256"])
        self.assertEqual(target_manifest_sha, rescored["manifest_sha256"])
        self.assertEqual(
            run_forward_eval.AUTOMATIC_FATAL_POLICY_ID,
            provenance["automatic_fatal_policy_id"],
        )
        self.assertTrue(provenance["rescored_at"])
        self.assertEqual([current_case["id"]], provenance["changed_cases"])
        self.assertEqual(current_case["repetitions"], len(rescored["results"]))
        for result in rescored["results"]:
            allowed_check = next(
                check
                for check in result["automatic_checks"]
                if check["name"] == "allowed_paths"
            )
            self.assertEqual(
                current_case["file_expectations"], result["file_expectations"]
            )
            self.assertTrue(allowed_check["passed"])
            self.assertEqual("", allowed_check["details"])
            self.assertEqual([], result["automatic_failures"])
            self.assertEqual([], result["detected_fatal_failures"])
            self.assertTrue(result["automatic_pass"])
            self.assertTrue(result["automatic_fatal_pass"])

    def test_forward_eval_allowlist_rescore_rejects_other_case_drift(self) -> None:
        original, _ = allowlist_rescore_summary()
        mutations = {
            "prompt": lambda result: result.__setitem__("prompt", "tampered"),
            "fixture": lambda result: result.__setitem__(
                "fixture", {"base": "tampered"}
            ),
            "expected": lambda result: result["expected"].__setitem__(
                "intent", "tampered"
            ),
            "checks_spec": lambda result: result.__setitem__("checks_spec", {}),
            "oracle": lambda result: result.__setitem__(
                "oracle", {"summary": "tampered"}
            ),
            "hard_fail_if": lambda result: result.__setitem__(
                "hard_fail_if", ["wrong_final_answer"]
            ),
            "require_change": lambda result: result["file_expectations"].__setitem__(
                "require_change", False
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mutate in mutations.items():
                with self.subTest(field=name):
                    summary = copy.deepcopy(original)
                    mutate(summary["results"][0])
                    source = root / f"{name}.json"
                    source.write_text(
                        json.dumps(summary, ensure_ascii=False), encoding="utf-8"
                    )
                    with self.assertRaisesRegex(
                        run_forward_eval.ManifestError,
                        "changed|outside allowed_changes",
                    ):
                        run_forward_eval.rescore_allowlist_summary(source)

    def test_forward_eval_allowlist_rescore_rejects_inconsistent_or_incomplete_source(self) -> None:
        original, _ = allowlist_rescore_summary()
        invalid_summaries = {}

        inconsistent = copy.deepcopy(original)
        allowed_check = next(
            check
            for check in inconsistent["results"][0]["automatic_checks"]
            if check["name"] == "allowed_paths"
        )
        allowed_check["passed"] = True
        allowed_check["details"] = ""
        invalid_summaries["inconsistent"] = inconsistent

        incomplete = copy.deepcopy(original)
        incomplete["results"].pop()
        invalid_summaries["incomplete"] = incomplete

        wrong_policy = copy.deepcopy(original)
        wrong_policy["automatic_fatal_policy_id"] = "unknown-policy"
        invalid_summaries["policy"] = wrong_policy

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, summary in invalid_summaries.items():
                with self.subTest(branch=name):
                    source = root / f"{name}.json"
                    source.write_text(json.dumps(summary), encoding="utf-8")
                    with self.assertRaises(run_forward_eval.ManifestError):
                        run_forward_eval.rescore_allowlist_summary(source)

    def test_forward_eval_allowlist_rescore_rejects_overwrite_and_hardlinked_source(self) -> None:
        summary, _ = allowlist_rescore_summary()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            source.write_text(json.dumps(summary), encoding="utf-8")
            rescored = run_forward_eval.rescore_allowlist_summary(source)

            output = root / "existing.json"
            original_output = b"do not overwrite"
            output.write_bytes(original_output)
            with self.assertRaisesRegex(
                run_forward_eval.ManifestError, "new path|already exists"
            ):
                run_forward_eval.write_new_summary_atomic(output, rescored)
            self.assertEqual(original_output, output.read_bytes())

            hardlink = root / "source-hardlink.json"
            try:
                os.link(source, hardlink)
            except OSError as exc:
                self.skipTest(f"hard links are unavailable: {exc}")
            with self.assertRaisesRegex(run_forward_eval.ManifestError, "hard link"):
                run_forward_eval.rescore_allowlist_summary(source)

    def test_forward_eval_maps_mechanically_conclusive_hard_failures(self) -> None:
        case = {
            "hard_fail_if": ["repository_changed", "authorization_violation"],
            "file_expectations": {"require_change": False},
        }
        checks = [
            {"name": "required_change", "passed": False},
            {"name": "allowed_paths", "passed": False},
            {"name": "validation_claim_truthful", "passed": False},
        ]
        detected = run_forward_eval.automatically_detected_hard_failures(
            case, checks, ["unexpected.tex"]
        )
        self.assertEqual(
            [
                "authorization_violation",
                "false_validation_claim",
                "repository_changed",
            ],
            detected,
        )

    def test_forward_eval_compare_rejects_different_reviewed_run_sets(self) -> None:
        baseline_summary = comparison_summary(
            "old", [{"case_id": "one", "score": 80}, {"case_id": "two"}]
        )
        candidate_summary = comparison_summary(
            "new", [{"case_id": "one"}, {"case_id": "two", "score": 86}]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(json.dumps(baseline_summary), encoding="utf-8")
            candidate.write_text(json.dumps(candidate_summary), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "human-reviewed run sets differ"):
                run_forward_eval.compare_summaries(baseline, candidate)

    def test_forward_eval_missing_tokens_can_never_be_zero_cost_pass(self) -> None:
        rows_old = [{"case_id": f"case_{index}", "score": 80} for index in range(1, 6)]
        rows_new = [
            {"case_id": f"case_{index}", "score": 80, "tokens": None}
            for index in range(1, 6)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(
                json.dumps(comparison_summary("old", rows_old)), encoding="utf-8"
            )
            candidate.write_text(
                json.dumps(comparison_summary("new", rows_new)), encoding="utf-8"
            )
            comparison = run_forward_eval.compare_summaries(baseline, candidate)
        self.assertIsNone(comparison["token_ratio"])
        self.assertFalse(comparison["token_metrics_complete"])
        self.assertNotEqual("pass", comparison["verdict"])

    def test_forward_eval_slice_quality_drop_and_missing_slice_coverage_gate(self) -> None:
        baseline_rows = [
            {"case_id": "math", "slice": "math", "score": 90},
            {"case_id": "teaching", "slice": "teaching", "score": 70},
        ]
        candidate_rows = [
            {"case_id": "math", "slice": "math", "score": 87},
            {"case_id": "teaching", "slice": "teaching", "score": 80},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(
                json.dumps(comparison_summary("old", baseline_rows)), encoding="utf-8"
            )
            candidate.write_text(
                json.dumps(comparison_summary("new", candidate_rows)), encoding="utf-8"
            )
            comparison = run_forward_eval.compare_summaries(baseline, candidate)
            self.assertEqual("fail", comparison["verdict"])
            self.assertFalse(comparison["slice_quality_gate"])

            baseline_rows[1].pop("score")
            candidate_rows[1].pop("score")
            baseline.write_text(
                json.dumps(comparison_summary("old", baseline_rows)), encoding="utf-8"
            )
            candidate.write_text(
                json.dumps(comparison_summary("new", candidate_rows)), encoding="utf-8"
            )
            comparison = run_forward_eval.compare_summaries(baseline, candidate)
        self.assertEqual("pending_human_review", comparison["verdict"])
        self.assertFalse(comparison["slice_human_review_coverage_met"])

    def test_forward_eval_requires_fatal_review_for_every_run(self) -> None:
        baseline_rows = [
            {"case_id": "reviewed", "score": 80},
            {"case_id": "not_reviewed", "fatal_reviewed": False},
        ]
        candidate_rows = [
            {"case_id": "reviewed", "score": 86},
            {"case_id": "not_reviewed", "fatal_reviewed": False},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(
                json.dumps(comparison_summary("old", baseline_rows)), encoding="utf-8"
            )
            candidate.write_text(
                json.dumps(comparison_summary("new", candidate_rows)), encoding="utf-8"
            )
            comparison = run_forward_eval.compare_summaries(baseline, candidate)
        self.assertFalse(comparison["human_fatal_coverage_met"])
        self.assertIsNone(comparison["human_fatal_gate"])
        self.assertEqual("pending_human_review", comparison["verdict"])

    def test_forward_eval_effort_comparison_requires_same_prompt_and_different_effort(self) -> None:
        rows = [{"case_id": f"case_{index}", "score": 80} for index in range(1, 6)]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            maximum = root / "max.json"
            xhigh = root / "xhigh.json"
            maximum.write_text(
                json.dumps(comparison_summary("same", rows, effort="max")), encoding="utf-8"
            )
            xhigh.write_text(
                json.dumps(comparison_summary("same", rows, effort="xhigh")), encoding="utf-8"
            )
            comparison = run_forward_eval.compare_summaries(
                maximum, xhigh, mode="effort"
            )
            self.assertEqual("effort", comparison["comparison_mode"])

            changed_prompt = comparison_summary("different", rows, effort="xhigh")
            xhigh.write_text(json.dumps(changed_prompt), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prompt stacks differ"):
                run_forward_eval.compare_summaries(maximum, xhigh, mode="effort")


if __name__ == "__main__":
    unittest.main()
