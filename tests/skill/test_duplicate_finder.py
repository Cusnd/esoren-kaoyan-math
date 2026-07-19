from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents/skills/kaoyan-math1-fullscore-coach/scripts/find_duplicate_problem.py"


class DuplicateFinderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "data").mkdir(parents=True)
        chapter = self.root / "tex/chapters/calculus/01.tex"
        chapter.parent.mkdir(parents=True)
        chapter.write_text(
            r"""
\problemAnchor{MATH1-CALC-0001}
\begin{problemBox}
求极限 $\lim_{x\to 0}\frac{\sin x}{x}$。
\end{problemBox}

\problemAnchor{MATH1-CALC-0002}
\begin{problemBox}
求矩阵 $A$ 的特征值。
\end{problemBox}
""".strip()
            + "\n",
            encoding="utf-8",
        )
        (self.root / "data/problem_registry.yml").write_text(
            """- id: MATH1-CALC-0001
  title: 正弦基本极限
  subject: 高等数学
  chapter_key: calc-01
  source: 用户提供 / 未注明来源
- id: MATH1-CALC-0002
  title: 矩阵特征值
  subject: 线性代数
  chapter_key: la-05
  source: 用户提供 / 未注明来源
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_finder(self, query: str, threshold: str = "0.22") -> dict[str, object]:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "--threshold",
                threshold,
                "--format",
                "json",
            ],
            input=query,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_cli_returns_the_matching_stable_problem_id(self) -> None:
        result = self.run_finder(r"求极限 \lim_{x\to 0}\frac{\sin x}{x}")

        matches = result["matches"]
        self.assertEqual([item["problem_id"] for item in matches], ["MATH1-CALC-0001"])
        self.assertEqual(matches[0]["file"], "tex/chapters/calculus/01.tex")

    def test_high_threshold_rejects_an_unrelated_query(self) -> None:
        result = self.run_finder("计算二重积分的交换积分次序", threshold="0.95")

        self.assertEqual(result["matches"], [])


if __name__ == "__main__":
    unittest.main()
