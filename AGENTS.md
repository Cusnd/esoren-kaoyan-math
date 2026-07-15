# 考研数学一满分学习笔记项目契约

本仓库用于长期维护考研数学一的题目、题解、知识点、错题、方法和公式，并同时生成 PDF 与网页笔记。目标是把每次学习输入沉淀为正确、可编译、可检索、可复盘的长期资产。

## Skill 路由

- 处理考研数学一题目、知识点、错解、OCR 题面、章节整理或数学内容归档时，使用仓库级 Skill：`$kaoyan-math1-fullscore-coach`。
- Git、构建、部署、网页样式、环境配置以及 `AGENTS.md` / Skill 自身维护属于工程任务，不套用数学教学结构或学习沉淀收尾。

## 默认结果

- 使用中文讲解，从识别信号和直觉入口走向严谨推导、考场写法与复盘。
- 保留决定正确性和满分书写的条件检查，不用“显然”“易得”跳过关键步骤。
- 回答结构随任务复杂度调整；简单题可以紧凑，复杂题、证明题和错解必须充分展开。
- 不编造题目来源、考试年份、真题身份或教材信息；来源不明时写“用户提供 / 未注明来源”。

## 授权与篇幅

- 用户提供数学学习内容，即授权在本仓库内进行相应的 TeX、索引和 registry 维护。
- “简洁回答”只降低聊天篇幅，不取消文件维护。
- 只有用户明确说“只聊天不写文件”“不要修改仓库”或同义表达时，才禁止本次数学内容写入。
- 审查、解释、诊断或规划类工程请求默认只检查并报告；除非用户同时要求修改，否则不实施工程变更。

## 唯一事实源

- 教材讲次与章节路径：`data/textbook_catalog.yml`。
- 人工可读目录：`docs/textbook_catalog.md`；必须与 YAML 保持一致。
- 题目登记：`data/problem_registry.yml`。
- 数学内容模板：`tex/templates/`。
- 视觉与环境实现：`tex/styles/`、`tex/preamble.tex`、`tex/preamble_web.tex`；章节文件只写数学内容和语义结构。
- PDF 与 Web 入口：`main.tex`、`main-web.tex`；两者必须包含 catalog 中同一组章节文件。

## 归档契约

### 新题

1. 先查重；疑似重复时补充原题的替代解法或说明，不分配新题号。
2. 用脚本生成 `MATH1-CALC/LA/PROB-000N` 题号。
3. 写入 catalog 指定的主考章节，并使用 `tex/templates/problem_template.tex` 的语义结构。
4. 必须同步题目索引和 `problem_registry.yml`。
5. 只有确实形成新方法、重要公式或错因时，才更新相应方法、公式或错题索引。

### 知识点

- 写入对应章节并按需更新方法或公式索引。
- 不创建虚假题号，也不写入 `problem_registry.yml`，除非同时新增了独立题目。

### 错解与疑问

- 先定位错误步骤和知识漏洞，再给出正确解法。
- 用户确有错误记录或该陷阱具有复盘价值时，更新 `mistake_index.tex`。

## 安全与一致性

- 修改前检查现有章节、索引和 registry，避免重复或覆盖用户内容。
- 跨章节题放入主考章节；需要时在索引中加入交叉引用。
- 使用定理、换元、极限替换、矩阵变换、概率独立性等方法时，只检查与本题相关的合法性条件。
- 保持 `problemBox`、`solutionBox`、`knowledgeBox`、`mistakeBox`、`problemMeta` 及现有跳转命令接口不变。
- 保留用户无关改动；不得为完成数学归档而重构视觉系统、网页阅读器或发布配置。

## 验证与收尾

在本机使用 `codex-tools` 运行仓库验证：

```powershell
& "$env:USERPROFILE\miniforge3\Library\bin\mamba.exe" run -n codex-tools python .agents/skills/kaoyan-math1-fullscore-coach/scripts/validate_math1_repo.py
```

- 普通数学内容修改至少运行仓库 validator；结构、catalog、模板或样式修改还要运行相关 Web 构建和静态测试。
- 明确报告 `PASS`、`FAIL` 或 `SKIP`；未运行的检查不得描述为通过。
- 数学任务结尾说明文件变化、验证结果、沉淀内容和复盘动作；非数学任务只报告工程结果、验证和真实阻塞。
