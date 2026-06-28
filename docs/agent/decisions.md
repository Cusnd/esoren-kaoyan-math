# Decisions

## 2026-06-28

- 使用 `article` 文档类配合 `ctex` 包，保持与 `AGENTS.md` 中“XeLaTeX + 中文支持”的要求一致。
- 使用 `tcolorbox` 的 `most` 选项，以支持可分页题目框、题解框、知识点框和易错点框。
- 章节文件先放置轻量占位说明，后续新增题目或知识点时直接追加到对应章节。
- 将可复用的 Codex 总提示词保存到 `prompts/codex_math1_prompt.md`，便于每次开启学习会话时复制使用。
- 教材目录成为当前归章主线：高数、线代、概率均按教材“第几讲”拆分；`docs/textbook_catalog.md` 供人工查看，`data/textbook_catalog.yml` 供后续检索或自动化使用。
