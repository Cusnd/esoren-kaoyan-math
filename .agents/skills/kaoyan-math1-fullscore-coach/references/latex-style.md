# LaTeX 内容与索引规范

## 权威位置

- 题目、知识点和错题模板：`tex/templates/`。
- PDF 样式：`tex/styles/academic_old_money.tex`。
- Web 样式：`tex/styles/math1_web.tex`。
- 章节、索引和模板只写数学内容与语义结构，不散落字体、颜色或版式定义。

## 稳定语义接口

保持以下环境和命令不变：

- `problemMeta`、`problemBox`、`solutionBox`、`knowledgeBox`、`mistakeBox`。
- `\problemAnchor`、`\problemRef`、`\problemIndexAnchor`、`\problemIndexRef`。
- `\knowledgeAnchor`、`\knowledgeRef`、`\knowledgeIndexAnchor`、`\knowledgeIndexRef`。

管理字段放入 `problemMeta`：题号、索引、来源、题型、难度和知识点。会影响求解条件的 OCR 校注、定义域和参数限制放在题面正文附近。

## 编号与跳转

- 高数：`MATH1-CALC-0001`。
- 线代：`MATH1-LA-0001`。
- 概率：`MATH1-PROB-0001`。
- 每道新题恰有一个 `\problemAnchor{ID}`，题目索引恰有一个 `\problemIndexAnchor{ID}`。
- 中文知识点使用可读标题，内部跳转 key 使用稳定的 ASCII kebab-case。

示例：

```tex
\problemAnchor{MATH1-CALC-0001}
\textbf{题目编号：} \problemRef{MATH1-CALC-0001} \quad
\textbf{索引：} \problemIndexRef{MATH1-CALC-0001}
```

## 内容规则

- 小节标题使用可检索的题型或知识点名称，不写“第 1 题”“例题 1”。
- 每道题独立成块；关键推导用标准 LaTeX，不堆砌公式。
- 现有章节写法优先于模板中的占位示例；模板字段没有实际内容时可以删去，不要填充空话。
- 新题、知识点和错题分别以对应实时模板为起点。
- 聊天与 TeX 都使用标准 LaTeX；聊天只额外保证定界符成对和屏幕可读性。

## OCR 不确定题面

在题面附近记录会影响解题的校注：

```tex
\textbf{题面说明：} 本题由 OCR 整理，符号存在不确定处，以下按……版本处理。
```

不得把题面不确定性藏入低视觉权重的管理元信息。
