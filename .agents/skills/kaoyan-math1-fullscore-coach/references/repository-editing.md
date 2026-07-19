# 仓库编辑与验证

## 编辑前取证

1. 从 `data/textbook_catalog.yml` 取得 `chapter_key` 与目标文件；以最终要求和决定解法的核心定理确定主考讲次，跨章知识用显式关系或索引连接。
2. 读取目标章节、相关索引、`data/problem_registry.yml`、`data/knowledge_registry.yml` 和 `tex/templates/` 中的实时模板。
3. 新题先运行查重脚本；确认不是已有题后再运行编号脚本。不得手工猜下一个 ID。

## 最小修改集

- **主库新题：** 主考章节、题目索引、problem registry；按题目模板新建 `\studySubsection` 时还要同步 `data/web_pages.yml`，使该小节进入统一 Web，若明确归入既有小节则不新增页面；只有确有新方法、独立公式或真实错因时才更新相应索引。
- **练习库新题：** 对应讲次的练习题面与答案文件、problem registry；未核验条目成对放在 `tex/practice/drafts/`，验证通过并迁出该目录后才进入练习册、答案册与 Web。
- **纯知识点：** 对应章节、knowledge registry 与必要索引；不得创建虚假题号。
- **真实错题：** 先保留错误步骤与纠正判据，再更新相关正文和 `mistake_index.tex`；通用陷阱只连接 pitfall 节点。

## TeX 与入口约定

- 小节统一使用 `\studySubsection{ASCII-slug}{可检索中文标题}`；每个新增 slug 必须在 `data/web_pages.yml` 中有且仅有一条同源映射；章节内容不写字体、颜色或版式定义。
- 保持 `problemMeta`、`problemBox`、`solutionBox`、`knowledgeBox`、`mistakeBox` 与现有引用命令兼容；练习答案使用 `\answerAnchor{ID}`。
- 每道题恰有一个 `\problemAnchor{ID}`；主库题另有且仅有一个题目索引锚点，练习题另有且仅有一个配对的 `\answerAnchor{ID}`。中文知识标题使用稳定的 registry ID 作为内部目标。
- `main.tex` 只输入主库；`practice.tex` 与 `practice-answers.tex` 分别生成练习册和答案册；`main-web.tex` 统一展示已验证的两库内容。
- 影响答案的定义域、参数限制与 OCR 校注写在题面附近，不能藏在低权重元信息中。

## 验证与收尾

在仓库根目录运行最小充分检查：

```powershell
& "$env:USERPROFILE\miniforge3\Library\bin\mamba.exe" run -n codex-tools python .agents/skills/kaoyan-math1-fullscore-coach/scripts/validate_math1_repo.py
```

- 普通数学内容至少运行 validator。
- 首次运行前把 validator 当作稳定黑盒；只有它真实失败且错误信息不足时，才读取对应实现或测试。普通内容通过后立即停止，不继续探测构建工具或运行静态/Web 检查。
- catalog、模板、入口、知识关系或结构变化时，额外编译受影响的 PDF，并运行 Web 构建与静态测试。
- Web 行为或本地复习状态变化时，额外运行浏览器测试；验证旧 URL、离线、导入失败零修改和无外部写请求。
- 完成前检查完整 diff，确认没有重复 ID、悬空关系、主库 PDF 混入练习、草稿发布或无关改动。
- 回复依次说明数学结论、文件变化、验证的 `PASS` / `FAIL` / `SKIP`、本次沉淀和一个复盘动作；未运行的检查不得宣称通过。
