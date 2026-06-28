# 考研数学一章节路由规则

优先读取仓库中的 `data/textbook_catalog.yml` 或 `docs/textbook_catalog.md`。当前仓库按教材讲次组织，而不是按通用大纲的 10 个高数章节组织。

当题目涉及多个章节时，放入主考章节，并在索引中补交叉引用。

## 高等数学 Calculus

| 讲次 | 标题 | 路径 | 识别信号 |
|---:|---|---|---|
| 1 | 函数极限与连续 | `tex/chapters/calculus/01_function_limit_continuity.tex` | 函数、复合函数、反函数、极限、无穷小、无穷大、连续、间断点、渐近线、\(f(\varphi(x))\) 反求 \(f(x)\) |
| 2 | 数列极限 | `tex/chapters/calculus/02_sequence_limit.tex` | 数列极限、递推数列、单调有界、夹逼、Stolz |
| 3 | 一元函数微分学的概念 | `tex/chapters/calculus/03_one_variable_differential_concepts.tex` | 导数定义、左右导数、可导、微分、连续与可导关系 |
| 4 | 一元函数微分学的计算 | `tex/chapters/calculus/04_one_variable_differential_calculation.tex` | 求导法则、高阶导数、隐函数求导、参数方程求导 |
| 5 | 微分学几何应用 | `tex/chapters/calculus/05_differential_applications_geometry.tex` | 切线法线、单调性、极值、最值、凹凸性、拐点 |
| 6 | 中值定理、微分等式与不等式 | `tex/chapters/calculus/06_differential_applications_mvt_equations_inequalities.tex` | 罗尔、拉格朗日、柯西、泰勒、存在 \(\xi\)、不等式证明 |
| 7 | 微分学物理与经济应用 | `tex/chapters/calculus/07_differential_applications_physics_economics.tex` | 变化率、边际、弹性、优化模型 |
| 8 | 积分学概念与性质 | `tex/chapters/calculus/08_one_variable_integral_concepts_properties.tex` | 原函数、定积分定义、变上限积分、反常积分概念 |
| 9 | 一元积分计算 | `tex/chapters/calculus/09_one_variable_integral_calculation.tex` | 换元、分部、有理函数积分、定积分技巧、反常积分计算 |
| 10 | 积分几何应用 | `tex/chapters/calculus/10_integral_applications_geometry.tex` | 面积、体积、弧长、旋转体 |
| 11 | 积分等式与不等式 | `tex/chapters/calculus/11_integral_applications_equations_inequalities.tex` | 积分中值定理、积分放缩、积分不等式 |
| 12 | 积分物理与经济应用 | `tex/chapters/calculus/12_integral_applications_physics_economics.tex` | 功、水压力、引力、平均值、总量积累 |
| 13 | 多元函数微分学 | `tex/chapters/calculus/13_multivariable_differential_calculus.tex` | 多元极限、偏导、全微分、方向导数、梯度、条件极值 |
| 14 | 二重积分 | `tex/chapters/calculus/14_double_integrals.tex` | 二重积分、换序、极坐标、积分区域 |
| 15 | 微分方程 | `tex/chapters/calculus/15_differential_equations.tex` | 可分离变量、一阶线性、齐次方程、二阶常系数 |
| 16 | 无穷级数 | `tex/chapters/calculus/16_infinite_series.tex` | 数项级数、幂级数、收敛半径、端点、傅里叶级数 |
| 17 | 多元积分预备知识 | `tex/chapters/calculus/17_multivariable_integral_preliminaries_math1.tex` | 空间解析几何、平面直线、曲面曲线、投影区域 |
| 18 | 多元函数积分学 | `tex/chapters/calculus/18_multivariable_integral_calculus_math1.tex` | 三重积分、曲线积分、曲面积分、格林、高斯、斯托克斯 |

## 线性代数 Linear Algebra

| 讲次 | 标题 | 路径 | 识别信号 |
|---:|---|---|---|
| 0 | 线性代数入门 | `tex/chapters/linear_algebra/00_linear_algebra_intro.tex` | 基本符号、线性组合、初等概念 |
| 1 | 行列式 | `tex/chapters/linear_algebra/01_determinants.tex` | 行列式、展开、性质、余子式、范德蒙德 |
| 2 | 矩阵 | `tex/chapters/linear_algebra/02_matrices.tex` | 矩阵运算、逆矩阵、伴随矩阵、初等变换、秩、分块 |
| 3 | 向量组 | `tex/chapters/linear_algebra/03_vector_groups.tex` | 线性相关、线性无关、极大无关组、秩、向量空间 |
| 4 | 线性方程组 | `tex/chapters/linear_algebra/04_linear_equations.tex` | 齐次、非齐次、基础解系、通解、秩判定 |
| 5 | 特征值与特征向量 | `tex/chapters/linear_algebra/05_eigenvalues_eigenvectors.tex` | 特征值、特征向量、相似、对角化、实对称矩阵 |
| 6 | 二次型 | `tex/chapters/linear_algebra/06_quadratic_forms.tex` | 二次型、合同、正定、标准形、规范形、惯性指数 |

## 概率论与数理统计 Probability

| 讲次 | 标题 | 路径 | 识别信号 |
|---:|---|---|---|
| 1 | 随机事件与概率 | `tex/chapters/probability/01_random_events_probability.tex` | 随机事件、古典概型、几何概型、条件概率、全概率、贝叶斯、独立性 |
| 2 | 一维随机变量及其分布 | `tex/chapters/probability/02_one_dimensional_random_variables_distributions.tex` | 分布函数、离散型、连续型、密度函数、常见分布 |
| 3 | 多维随机变量及其分布 | `tex/chapters/probability/03_multidimensional_random_variables_distributions.tex` | 联合分布、边缘分布、条件分布、独立性、函数分布 |
| 4 | 数字特征 | `tex/chapters/probability/04_numerical_characteristics.tex` | 期望、方差、协方差、相关系数、矩 |
| 5 | 大数定律与中心极限定理 | `tex/chapters/probability/05_law_large_numbers_clt.tex` | 切比雪夫、大数定律、中心极限定理、正态近似 |
| 6 | 数理统计 | `tex/chapters/probability/06_mathematical_statistics.tex` | 样本、统计量、抽样分布、点估计、矩估计、最大似然、置信区间 |
