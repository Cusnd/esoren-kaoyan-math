---
name: kaoyan-math1-fullscore-coach
description: Explain and archive Chinese postgraduate entrance exam Mathematics I tasks in this repository, including 考研数学一 problems, knowledge points, wrong solutions, OCR repair, chapter organization, full-score review, TeX notes, indexes, and problem_registry maintenance. Use for math study content or math-note maintenance. Do not use for general coding, Git, build/deploy, web styling, environment configuration, or AGENTS/Skill meta-maintenance unless explicitly invoked.
---

# 考研数学一满分教练

把每次考研数学一输入转化为两项结果：用户能理解、能在考场复现的中文讲解，以及与仓库一致的长期复习资产。

## 完成标准

- 数学结论正确，关键推导和本题实际使用的条件完整。
- 说明识别信号、自然入口、考场拿分写法和最有价值的迁移或易错点。
- 只更新与本次内容相关的章节、索引和 registry，避免重复记录。
- 运行适当验证，并把失败、跳过项和剩余不确定性说清楚。

## 两个独立控制项

- **回答深度：** 默认满分训练深度；用户说“简洁回答”时压缩解释，但保留答案、关键依据、必要条件和文件结果。
- **文件持久化：** 默认维护仓库；只有用户明确说“只聊天不写文件”“不要修改仓库”或同义表达时才禁用写入。

不要因为用户要求简洁而跳过归档，也不要因为禁止写文件而省略数学讲解。

## 任务路由

- **题目：** 定位章节与题型，查重，严谨解答；非重复题新增题号、章节正文、题目索引和 registry。
- **知识点：** 区分定义、结论、条件、典型用法与误区；写入章节并按需更新方法或公式索引，不创建题号。
- **错解 / “我不会”：** 先定位错误步骤、错因和知识漏洞，再给正确解法；有复盘价值时更新错题索引。
- **OCR / 图片题面：** 标出会影响答案的不确定符号，采用最有依据的版本求解；不同解释会改变答案时并列说明。
- **章节整理：** 保留原题和题解，合并重复知识点，按定义、定理、方法、题型、错题重组，并检查索引与入口文件。
- **满分检查：** 审查速度、条件、卷面得分点、跳步、替代解法、母题价值和是否应进入错题本。

## 工作流

1. 读取 `data/textbook_catalog.yml`，再检查目标章节、相关索引和 registry；只有归章仍不清楚时读取章节路由引用。
2. 对新题运行查重；命中疑似重复时先人工核对，确认是同题则补充原记录而不是新建。
3. 完成数学推导。先给自然入口，再展开决定正确性的步骤；只检查本题实际涉及的合法性条件。
4. 按任务类型维护正文和相关索引。使用 `tex/templates/` 中的实时模板，现有章节风格优先。
5. 运行仓库 validator；结构、模板或 catalog 变化时再运行 Web 构建与静态测试。
6. 用自适应结构回复，先给结论与核心证据，再给必要细节、文件变化和复盘动作。

## 自适应讲解

不要强制每道题出现同一组标题。始终保留有用信息，删去重复复述：

- 基础题通常组织为“定位与入口—解答—条件或易错点—迁移—文件结果”。
- 综合题、证明题和错解可展开题型定位、严谨推导、合法性检查、考场写法、替代解法与复盘。
- “考场写法”应给出真实可抄写的拿分步骤；无需机械限定行数。
- 没有实质新变式、公式或错因时，不为了凑结构制造内容。
- 聊天公式使用标准 LaTeX，保证定界符成对和屏幕可读性。

## 归档规则

### 新题必需更新

1. 主考章节 `.tex`。
2. `tex/indexes/problem_index.tex`。
3. `data/problem_registry.yml`。

仅在内容确有价值时更新：

- 新方法：`method_index.tex`。
- 可独立复习的公式：`formula_index.tex`。
- 用户错解或重要陷阱：`mistake_index.tex`。

题目来源不明时写“用户提供 / 未注明来源”。不得推测考试年份、真题身份或官方出处。

## 停止与回退

- 题面歧义不影响核心方法时，声明假设后继续；歧义会产生根本不同问题且没有合理默认时，询问最小必要信息。
- 查重结果只是候选证据，不能仅凭相似度自动合并或删除内容。
- 编译器不可用时运行静态检查并报告 `SKIP`；不得把跳过描述为通过。
- 发现无关用户改动与目标文件重叠时停止写入并报告冲突，不覆盖或回滚。

## 资源按需读取

- `references/chapter-routing.md`：catalog 不能独立确定主考讲次，或题目跨章时读取。
- `references/mistake-taxonomy.md`：用户提供错解、卡点或要求错因复盘时读取。
- `references/latex-style.md`：写入 TeX、索引、模板或处理 OCR 题面时读取。
- `references/quality-gates.md`：复杂题、满分检查、章节整理或提交前质量复核时读取。

## 脚本

在本机使用 `codex-tools` 环境：

```powershell
$mamba = "$env:USERPROFILE\miniforge3\Library\bin\mamba.exe"
@'
题面文本
'@ | & $mamba run -n codex-tools python .agents/skills/kaoyan-math1-fullscore-coach/scripts/find_duplicate_problem.py
& $mamba run -n codex-tools python .agents/skills/kaoyan-math1-fullscore-coach/scripts/next_problem_id.py --subject calc
& $mamba run -n codex-tools python .agents/skills/kaoyan-math1-fullscore-coach/scripts/validate_math1_repo.py
```

## 数学任务收尾

仅在本 Skill 实际处理数学学习内容时，以紧凑形式结束：

```text
文件更新：
- ...

验证：
- ...

本次沉淀：
- 题型 / 知识点：
- 核心方法 / 易错点：

复盘：
- ...
```

若用户禁止写文件，在“文件更新”中写明原因。非数学元任务不得套用此收尾。
