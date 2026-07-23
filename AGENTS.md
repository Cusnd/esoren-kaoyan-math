# 考研数学一学习仓库契约

本仓库把考研数学一的学习输入沉淀为正确、可编译、可检索、可串联和可复习的长期资产，并同时生成 PDF 与本地优先的静态网页。

## 路由与授权

- 题目、知识点、错解、OCR 题面、复习、训练生成或数学内容归档，统一使用仓库 Skill：`$kaoyan-math1-fullscore-coach`。
- Git、构建、部署、网页样式、环境配置及 `AGENTS.md` / Skill 自身维护是工程任务，不套用数学教学或归档流程。
- 用户提供数学学习内容，即授权在本仓库内做必要的 TeX、索引与 registry 维护；只有明确说“只聊天不写文件”“不要修改仓库”或同义表达时才禁止写入。
- “简洁回答”只压缩聊天篇幅，不改变持久化授权。审查、解释、诊断或规划类工程请求默认只读。

## 稳定边界

- 题目只登记在 `data/problem_registry.yml`，以 `collection: core | practice` 区分主库与练习库；两库共享同一题号命名空间，移动库别时不得更换题号。
- 主库保存母题、新方法、关键知识与真实错题；练习库保存普通变式、程序训练、迁移训练与交错训练。
- 通用陷阱不是用户真实错题；个人复习日期、薄弱状态和阅读进度不得写入公开内容 registry。
- 主笔记 PDF 只包含主库；练习册与答案册单独生成；Web 统一展示两库与知识关系。
- Web 保持纯静态、本地优先：不得增加账号、鉴权、后端写入、网页模型调用或答题评分。

## 唯一事实源

- 教材讲次、稳定章节键与章节路径：`data/textbook_catalog.yml`；人工目录 `docs/textbook_catalog.md` 必须与其一致。
- 题目与两库归属：`data/problem_registry.yml`；知识节点与显式关系：`data/knowledge_registry.yml`；Web 页面顺序、slug 与源 TeX 映射：`data/web_pages.yml`。
- 数学内容结构：`tex/templates/`；视觉与环境：`tex/styles/`、`tex/preamble.tex`、`tex/preamble_web.tex`。
- PDF 与 Web 入口：`main.tex`、`practice.tex`、`practice-answers.tex`、`main-web.tex`。

## 兼容与验证

- 保持 `problemBox`、`solutionBox`、`knowledgeBox`、`mistakeBox`、`problemMeta` 及现有跳转接口兼容；章节文件只写数学内容和语义结构。
- 修改前查重并保留无关用户改动；不得为数学归档顺带重构视觉系统、阅读器或发布配置。
- 数学内容修改至少运行仓库 validator；结构、catalog、模板或样式变化还要运行相关 PDF、Web 与静态测试。
- 除非用户在当前请求中明确特许，不得运行 Web 构建；仍应维护必要的 TeX 入口与 `data/web_pages.yml` 映射，并把原本需要的 Web 构建验证如实报告为 `SKIP（用户未授权）`。
- 验证结果只可报告真实的 `PASS`、`FAIL` 或 `SKIP`；不得把未运行或跳过的检查描述为通过。
