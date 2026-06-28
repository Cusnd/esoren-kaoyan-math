#!/usr/bin/env python3
"""Idempotently bootstrap a Kaoyan Math I TeX notes repository."""

from __future__ import annotations

from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_DIR / "assets"
ROOT = Path.cwd()

CHAPTERS = [
    ("tex/chapters/calculus/01_function_limit_continuity.tex", "第 1 讲 函数极限与连续"),
    ("tex/chapters/calculus/02_sequence_limit.tex", "第 2 讲 数列极限"),
    ("tex/chapters/calculus/03_one_variable_differential_concepts.tex", "第 3 讲 一元函数微分学的概念"),
    ("tex/chapters/calculus/04_one_variable_differential_calculation.tex", "第 4 讲 一元函数微分学的计算"),
    ("tex/chapters/calculus/05_differential_applications_geometry.tex", "第 5 讲 一元函数微分学的应用（一）——几何应用"),
    ("tex/chapters/calculus/06_differential_applications_mvt_equations_inequalities.tex", "第 6 讲 一元函数微分学的应用（二）——中值定理、微分等式与微分不等式"),
    ("tex/chapters/calculus/07_differential_applications_physics_economics.tex", "第 7 讲 一元函数微分学的应用（三）——物理应用与经济应用"),
    ("tex/chapters/calculus/08_one_variable_integral_concepts_properties.tex", "第 8 讲 一元函数积分学的概念与性质"),
    ("tex/chapters/calculus/09_one_variable_integral_calculation.tex", "第 9 讲 一元函数积分学的计算"),
    ("tex/chapters/calculus/10_integral_applications_geometry.tex", "第 10 讲 一元函数积分学的应用（一）——几何应用"),
    ("tex/chapters/calculus/11_integral_applications_equations_inequalities.tex", "第 11 讲 一元函数积分学的应用（二）——积分等式与积分不等式"),
    ("tex/chapters/calculus/12_integral_applications_physics_economics.tex", "第 12 讲 一元函数积分学的应用（三）——物理应用与经济应用"),
    ("tex/chapters/calculus/13_multivariable_differential_calculus.tex", "第 13 讲 多元函数微分学"),
    ("tex/chapters/calculus/14_double_integrals.tex", "第 14 讲 二重积分"),
    ("tex/chapters/calculus/15_differential_equations.tex", "第 15 讲 微分方程"),
    ("tex/chapters/calculus/16_infinite_series.tex", "第 16 讲 无穷级数（仅数学一、数学三）"),
    ("tex/chapters/calculus/17_multivariable_integral_preliminaries_math1.tex", "第 17 讲 多元函数积分学的预备知识（仅数学一）"),
    ("tex/chapters/calculus/18_multivariable_integral_calculus_math1.tex", "第 18 讲 多元函数积分学（仅数学一）"),
    ("tex/chapters/linear_algebra/00_linear_algebra_intro.tex", "第 0 讲 零基础课——线性代数入门"),
    ("tex/chapters/linear_algebra/01_determinants.tex", "第 1 讲 行列式"),
    ("tex/chapters/linear_algebra/02_matrices.tex", "第 2 讲 矩阵"),
    ("tex/chapters/linear_algebra/03_vector_groups.tex", "第 3 讲 向量组"),
    ("tex/chapters/linear_algebra/04_linear_equations.tex", "第 4 讲 线性方程组"),
    ("tex/chapters/linear_algebra/05_eigenvalues_eigenvectors.tex", "第 5 讲 特征值与特征向量"),
    ("tex/chapters/linear_algebra/06_quadratic_forms.tex", "第 6 讲 二次型"),
    ("tex/chapters/probability/01_random_events_probability.tex", "第 1 讲 随机事件与概率"),
    ("tex/chapters/probability/02_one_dimensional_random_variables_distributions.tex", "第 2 讲 一维随机变量及其分布"),
    ("tex/chapters/probability/03_multidimensional_random_variables_distributions.tex", "第 3 讲 多维随机变量及其分布"),
    ("tex/chapters/probability/04_numerical_characteristics.tex", "第 4 讲 随机变量的数字特征"),
    ("tex/chapters/probability/05_law_large_numbers_clt.tex", "第 5 讲 大数定律与中心极限定理"),
    ("tex/chapters/probability/06_mathematical_statistics.tex", "第 6 讲 数理统计"),
]

INDEXES = [
    ("tex/indexes/problem_index.tex", "题目索引", "暂无题目。"),
    ("tex/indexes/method_index.tex", "方法索引", "暂无方法条目。"),
    ("tex/indexes/mistake_index.tex", "错题与错因索引", "暂无错题。"),
    ("tex/indexes/formula_index.tex", "公式索引", "暂无公式条目。"),
]


def write_if_missing(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return "exists"
    path.write_text(content, encoding="utf-8")
    return "created"


def asset_text(name: str) -> str:
    return (ASSETS_DIR / name).read_text(encoding="utf-8")


def chapter_stub(title: str) -> str:
    return (
        "% Auto-created by kaoyan-math1-fullscore-coach\n"
        f"\\subsection{{{title}}}\n\n"
        "\\begin{knowledgeBox}\n"
        "本讲尚未整理内容。\n"
        "\\end{knowledgeBox}\n"
    )


def index_stub(title: str, body: str) -> str:
    return f"\\subsection{{{title}}}\n\n\\begin{{knowledgeBox}}\n{body}\n\\end{{knowledgeBox}}\n"


def main() -> int:
    dirs = [
        "tex/chapters/calculus",
        "tex/chapters/linear_algebra",
        "tex/chapters/probability",
        "tex/indexes",
        "tex/templates",
        "data",
    ]
    for rel in dirs:
        (ROOT / rel).mkdir(parents=True, exist_ok=True)
        print(f"DIR    {rel}")

    actions = []
    actions.append(("main.tex", write_if_missing(ROOT / "main.tex", asset_text("main-template.tex"))))
    actions.append(("tex/preamble.tex", write_if_missing(ROOT / "tex/preamble.tex", asset_text("preamble-template.tex"))))
    actions.append(("tex/templates/problem_template.tex", write_if_missing(ROOT / "tex/templates/problem_template.tex", asset_text("problem-template.tex"))))
    actions.append(("data/problem_registry.yml", write_if_missing(ROOT / "data/problem_registry.yml", "[]\n")))

    for rel, title in CHAPTERS:
        actions.append((rel, write_if_missing(ROOT / rel, chapter_stub(title))))

    for rel, title, body in INDEXES:
        actions.append((rel, write_if_missing(ROOT / rel, index_stub(title, body))))

    for rel, action in actions:
        print(f"{action.upper():7} {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
