from __future__ import annotations

import builtins
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml


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
CHAPTER_FILE = "tex/chapters/calculus/01_function_limit_continuity.tex"


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

    def _create(self) -> None:
        self.write(
            "data/textbook_catalog.yml",
            f"""
subjects:
  calculus:
    name: "高等数学"
    lectures:
      - number: 1
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

- {tick}{CHAPTER_FILE}{tick}
""",
        )
        self.write(
            "data/problem_registry.yml",
            self.registry_entry(),
        )
        self.write(
            "main.tex",
            f"""
\\input{{tex/preamble.tex}}
\\input{{{CHAPTER_FILE}}}
""",
        )
        self.write(
            "main-web.tex",
            f"""
\\input{{tex/preamble_web.tex}}
\\input{{{CHAPTER_FILE}}}
""",
        )
        self.write("tex/preamble.tex", "% PDF preamble")
        self.write("tex/preamble_web.tex", "% Web preamble")
        self.write("tex/templates/problem_template.tex", "% problem template")
        self.write("tex/templates/knowledge_template.tex", "% knowledge template")
        self.write("tex/templates/mistake_template.tex", "% mistake template")
        self.write(
            CHAPTER_FILE,
            f"""
\\section{{函数、极限与连续}}
\\problemAnchor{{{PROBLEM_ID}}}
\\subsection{{一个测试题}}
\\begin{{problemBox}}
测试题面。
\\end{{problemBox}}
""",
        )
        self.write(
            "tex/indexes/problem_index.tex",
            f"""
\\problemIndexAnchor{{{PROBLEM_ID}}}
\\problemRef{{{PROBLEM_ID}}}
""",
        )
        self.write("tex/indexes/method_index.tex", "% method index")
        self.write("tex/indexes/mistake_index.tex", "% mistake index")
        self.write("tex/indexes/formula_index.tex", "% formula index")

    @staticmethod
    def registry_entry() -> str:
        return f"""
- id: {PROBLEM_ID}
  title: "一个测试题"
  subject: "高等数学"
  chapter: "函数、极限与连续"
  file: "{CHAPTER_FILE}"
  source: "用户粘贴"
  difficulty: "基础"
  tags:
    - "极限"
  mistakes:
    - "忽略条件"
  status: "已整理"
"""


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
        return validator.validate_repository(
            self.fixture.root,
            compile_enabled=False,
        )

    def test_valid_fixture_passes_with_compile_skip(self) -> None:
        report = self.validate()
        self.assertFalse(report.failures)
        self.assertEqual("pass_with_skips", report.result)
        self.assertEqual("SKIP", self.status_for(report, "latex.compile"))

    def test_invalid_registry_yaml_is_reported(self) -> None:
        self.fixture.write("data/problem_registry.yml", "- id: [unterminated")
        report = self.validate()
        self.assertIn("registry.parse", self.failure_codes(report))

    def test_invalid_catalog_yaml_is_reported(self) -> None:
        self.fixture.write("data/textbook_catalog.yml", "subjects: [unterminated")
        report = self.validate()
        self.assertIn("catalog.parse", self.failure_codes(report))

    def test_duplicate_registry_id_is_rejected(self) -> None:
        self.fixture.write(
            "data/problem_registry.yml",
            RepositoryFixture.registry_entry()
            + RepositoryFixture.registry_entry(),
        )
        report = self.validate()
        self.assertIn("registry.schema", self.failure_codes(report))

    def test_missing_web_chapter_input_is_rejected(self) -> None:
        self.fixture.write(
            "main-web.tex",
            "\\input{tex/preamble_web.tex}",
        )
        report = self.validate()
        self.assertIn("entrypoint.main-web.tex", self.failure_codes(report))

    def test_registry_path_outside_catalog_is_rejected(self) -> None:
        registry = self.fixture.read("data/problem_registry.yml").replace(
            CHAPTER_FILE,
            "tex/chapters/calculus/99_missing.tex",
        )
        self.fixture.write("data/problem_registry.yml", registry)
        report = self.validate()
        self.assertIn("registry.schema", self.failure_codes(report))

    def test_missing_chapter_anchor_is_rejected(self) -> None:
        self.fixture.write(CHAPTER_FILE, "\\section{没有题目锚点}")
        report = self.validate()
        self.assertIn("problems.chapter_anchors", self.failure_codes(report))

    def test_dangling_problem_reference_is_rejected(self) -> None:
        self.fixture.write(
            "tex/indexes/method_index.tex",
            "\\problemRef{MATH1-CALC-9999}",
        )
        report = self.validate()
        self.assertIn("problems.dangling_refs", self.failure_codes(report))

    def test_missing_pyyaml_is_a_dependency_error(self) -> None:
        real_import = builtins.__import__

        def import_without_yaml(name: str, *args: object, **kwargs: object) -> object:
            if name == "yaml":
                raise ImportError("simulated missing PyYAML")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=import_without_yaml):
            with self.assertRaises(repo_model.RepositoryDependencyError):
                repo_model.load_registry(self.fixture.root)

    def test_missing_compiler_is_skip_not_pass(self) -> None:
        report = validator.Report()
        with mock.patch.object(validator.shutil, "which", return_value=None):
            validator._compile_pdf(self.fixture.root, report, enabled=True)
        self.assertEqual("SKIP", report.checks[-1].status)
        self.assertEqual("latex.compile", report.checks[-1].code)

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
    def test_current_repository_has_expected_catalog_and_problem_contract(self) -> None:
        report = validator.validate_repository(REPO_ROOT, compile_enabled=False)
        self.assertFalse(
            report.failures,
            "\n".join(
                f"{check.code}: {check.details or check.message}"
                for check in report.failures
            ),
        )
        self.assertEqual(37, len(repo_model.load_catalog(REPO_ROOT)))
        self.assertEqual(10, len(repo_model.load_registry(REPO_ROOT)))
        statuses = {check.code: check.status for check in report.checks}
        for code in (
            "catalog.documentation",
            "entrypoint.main.tex",
            "entrypoint.main-web.tex",
            "problems.chapter_anchors",
            "problems.registry_paths",
            "problems.index_anchors",
            "problems.dangling_refs",
        ):
            self.assertEqual("PASS", statuses[code], code)

    def test_behavior_case_manifest_covers_required_scenarios(self) -> None:
        cases_path = REPO_ROOT / "tests/skill/cases.yml"
        cases = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
        self.assertIsInstance(cases, list)
        expected_ids = {
            "simple_problem",
            "complex_problem",
            "wrong_solution",
            "ocr_ambiguity",
            "duplicate_problem",
            "concise_with_persistence",
            "chat_only",
            "non_math_meta",
        }
        self.assertEqual(expected_ids, {case["id"] for case in cases})
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["prompt"].strip())
                self.assertIn(
                    case["persistence"],
                    {"write", "write_when_resolved", "skip", "project_change"},
                )
                self.assertTrue(case["required_outcomes"])
                self.assertTrue(case["forbidden_outcomes"])


if __name__ == "__main__":
    unittest.main()
