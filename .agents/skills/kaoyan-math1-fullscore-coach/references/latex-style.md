# LaTeX 书写风格

默认使用 XeLaTeX，支持中文。

## 基本要求

1. 数学公式使用标准 LaTeX。
2. 中文说明清楚，不堆公式。
3. 每道题独立成块。
4. 不编造来源。
5. 不破坏已有结构。
6. 尽量保证 `main.tex` 可编译。

## 题目环境

使用：

- `problemBox`
- `solutionBox`
- `knowledgeBox`
- `mistakeBox`

## 编号规则

- 高数：`MATH1-CALC-0001`
- 线代：`MATH1-LA-0001`
- 概率：`MATH1-PROB-0001`

## 标题规则

小节标题尽量写成题型名称，例如：

```tex
\subsection{由复合函数表达式反求原函数}
```

不要写成“第 1 题”“例题 1”这种不可检索标题。

## 标签规则

若 TeX 中需要交叉引用，使用：

```tex
\label{prob:math1-calc-0001}
```

标签统一小写。

## 不确定题面

如果 OCR 不确定，写：

```tex
\textbf{题面说明：} 本题由 OCR 整理，符号存在不确定处，以下按 ... 版本处理。
```
