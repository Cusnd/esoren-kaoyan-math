# Decisions

## 2026-06-28

- 使用 `article` 文档类配合 `ctex` 包，保持与 `AGENTS.md` 中“XeLaTeX + 中文支持”的要求一致。
- 初始版本使用彩色题目/题解/知识点/易错点容器；后续在 2026-06-29 改为无边框、无底色的语义段落环境。
- 章节文件先放置轻量占位说明，后续新增题目或知识点时直接追加到对应章节。
- 将可复用的 Codex 总提示词保存到 `prompts/codex_math1_prompt.md`，便于每次开启学习会话时复制使用。
- 教材目录成为当前归章主线：高数、线代、概率均按教材“第几讲”拆分；`docs/textbook_catalog.md` 供人工查看，`data/textbook_catalog.yml` 供后续检索或自动化使用。
- 详细输出规则固化到 `AGENTS.md` 与 `prompts/codex_math1_prompt.md`，以后默认按任务判断、严谨讲解、合法性检查、考场写法、迁移模板、易错点和文件更新闭环输出。
- 将复杂流程封装为仓库级 Skill `.agents/skills/kaoyan-math1-fullscore-coach`，并在根 `AGENTS.md` 顶部加入显式调用提示；Skill references 适配当前教材讲次目录。

## 2026-06-29

- LaTeX 内容与样式分离：`tex/preamble.tex` 保持轻量入口，视觉模板集中到 `tex/styles/academic_old_money.tex`。
- 采用克制学术风格作为默认 PDF 视觉方向：深墨绿、暖灰、古金棕和低饱和酒红只用于标题与强调，正文不再被彩色框包裹。
- 题目、题解、知识点和易错点环境名称保持不变，但呈现为普通可分页段落块；章节 TeX 只写数学内容与语义结构。
