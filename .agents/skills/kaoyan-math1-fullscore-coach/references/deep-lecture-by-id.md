# 按 K 编号生成高数深度讲义

只在用户显式要求“深度讲解”“生成深度讲义”“满分级讲义”等，并同时给出一个或多个 `Kxxx` 时执行本流程。普通“讲解 K031”继续按一般教学协议回答，不自动生成长讲义或四层练习。

## 一次取证

1. 从用户输入中提取并大写规范化全部 `Kxxx`；重复编号视为输入错误，不擅自去重。
2. 在任何写入前，一次运行：

   ```powershell
   & $mamba run -n codex-tools python .agents/skills/kaoyan-math1-fullscore-coach/scripts/extract_calculus_knowledge.py K031 K032 --format json
   ```

3. 任一编号不存在、映射不唯一、资源哈希漂移或已声明锚点缺失时，停止且保持仓库零修改；明确报告具体编号或数据问题，不猜测相近编号。
4. 使用每个 `item.source_records[*].teaching_evidence` 和 `checklist_evidence` 写讲义；同一位置的 `research_planning` 与 `checklist_research_planning` 只控制篇幅、难度和练习分配，不复制到公开 TeX。研究包的 `authority` 是 `non_authoritative_research`：把“官方明确”等写成“研究包标注为官方明确”，除非另行核验了官方原文。
5. 不公开 `source_refs`、资源哈希、考频、趋势、研究重要度或任何个人学习状态。不得把研究包中的年份写成确定的真题归属。

## 编号组织与落位

- 按提取结果的 `ordered_ids` 组织内容；它优先采用 registry 中显式的 `prerequisite_for` 关系，互不依赖时保持用户顺序。一个稳定节点可能承载多个 K 编号，此时提取结果会把它们合并到同一 `item.source_ids`；只编辑该稳定锚点一次，并分别吸收 `source_records` 中的教学证据。
- 同章且形成同一知识链的编号写成一份连贯讲义，并为每个稳定节点保留独立 `\knowledgeAnchor`；弱关联或跨章编号分别落位，不强行拼成一篇。
- 已有 `tex_anchor` 时原位深化，保留稳定 ID、现有引用和所在小节，不复制第二个锚点。
- 没有 `tex_anchor` 时，以 `textbook_catalog.yml` 返回的目标章节为准，按实时 `tex/templates/knowledge_template.tex` 建立专用 `\studySubsection`，再补齐 registry 的 `tex_anchor`、必要索引和 `data/web_pages.yml`。不得把研究包路径当作构建事实源。
- 先读取目标锚点附近内容；已有高质量定义、证明、例题或关系只增补缺口，不整段重复或无提示覆盖。

## 主讲义质量

根据知识点的概念、公式、定理、方法或大纲边界属性自然组织，不机械输出固定标题；数学上适用的下列内容必须全部闭合：

- **定位与路线：** 解决什么问题、必要前置、后续用途和本讲顺序。
- **直觉与严格核心：** 先给最小具体情形，再给正式定义、定理或公式；解释新符号、量词和关键词。
- **条件与推导：** 在使用前写清对象、条件及当前为何满足；展开决定结论的中间步骤，并说明条件失效时的反例或后果。
- **方法选择：** 使用相关 T 题型的识别信号、首选流程、切换条件和真正有价值的备用方法；不要为展示多解而堆积同质方法。
- **例题梯度：** 配置 3--5 道高价值例题，覆盖概念或基础、标准流程、方法选择，以及反例或综合迁移。每题写明题面信号、分析、方法选择、完整解答、条件检查、易错点和至少一种结果核验；备用方法仅在更稳、更快或揭示新结构时加入。这些例题是 `knowledgeBox` 内不独立编号的讲解示范，不使用 `problemBox`，不与 A/B/C/M 重复，也不设计成脱离正文仍可独立作答的正式任务；若确需正式自足题目，按归档政策进入统一题库和 registry。
- **失分防线：** 给出具体错误写法、失效原因、最小反例、正确判据和考场快速检查动作。
- **考场表达与掌握标准：** 给出可誊写的得分步骤，并用可观察行为描述基础过关、130 分以上和满分能力，避免“熟练掌握”等空话。
- **总结与连接：** 收束最重要条件、首选方法、危险错误和下一步稳定知识节点；不简单重复标题。

按类型调整重心：定义型突出量词、正反边界例；计算型突出结构识别、合法变形和回代；定理型突出完整条件、证明逻辑与误用；证明方法型突出由目标反推及辅助构造；大纲边界型突出研究包口径与不必扩展的高级内容。没有数学内容的模块不要生成空标题。

## A/B/C/M 配套练习

每个连贯知识组生成一个练习集，不把每道子题机械拆成独立 problem ID：

- `A` 至少一题：定义辨析或基础计算；
- `B` 至少一题：标准题型和完整流程；
- `C` 至少一题：综合、方法选择或近远迁移；
- `M` 至少一题：参数、证明、退化、反例或陌生外观迁移。

默认共 4--6 题；只有增加的题能覆盖不同能力时才超过每层一题。所有题必须原创或充分改写，题面自足，答案唯一或评分条件明确，不冒充真题。

1. 先运行查重脚本并人工核对候选；再用编号脚本取得一个练习集 ID。
2. 先把题面与答案的 TeX 草稿对写入 `tex/practice/drafts/`；registry 条目始终只写在唯一事实源 `data/problem_registry.yml`，以草稿路径登记，并使用 `origin: generated`、`collection: practice`、`practice_stage: interleaved`、`task_type: comprehensive` 和 `verification_status: draft`。不得在 drafts 中创建 registry 副本。
3. 把请求的 K 节点和直接相关的 `problem_family` 节点放入 `knowledge_ids`；只有 `kind: method` 的稳定节点可以放入 `method_ids`。来源写“Codex 原创 / Kxxx 深度讲义配套练习（非真题）”。
4. 不看草稿答案，从头独立复算每题；逐项检查题面、条件、分层目标、答案、证明闭合和核验，并在工作记录中明确完成这一步。任一题失败时保留整组为 draft，不接入任何入口；不得因最终 diff 只保留 live 文件而省略这道草稿门禁。
5. 全部通过后，把同一 ID 的题面和答案迁入 `tex/practice/calculus/{chapter_key}-problems.tex` 与配对的 `-answers.tex`，更新 registry 为 `verified`。题面用一个 `\problemAnchor`，答案用一个 `\answerAnchor`，内部以 A/B/C/M 标签区分子题。
6. 目标讲次没有 live 文件对时，创建成对文件：题面文件声明 `practice-{chapter_key}` 小节，答案册入口声明对应答案小节；同步 `practice.tex`、`practice-answers.tex`、`main-web.tex` 和 `data/web_pages.yml`。已有文件对时只追加闭合条目，不重复入口。

## 授权、验证与回复

- 用户明确“只聊天不写文件”时，在聊天中交付完整深度讲义，但不创建主 TeX、练习、答案或 registry 条目。
- 其他显式深度请求默认完成主 TeX 与已核验的四层副 TeX；不要另建“知识点讲义”Markdown 目录。
- 按 `archive-policy.md` 和 `repository-editing.md` 完成最小修改集。普通内容至少运行仓库 validator；新增练习文件对、Web 页面或结构时再运行对应 PDF、Web 与静态检查。
- 聊天只简要报告编号、主讲义位置、练习集 ID、覆盖的相关 T 题型、验证状态和来源冲突；不要再次粘贴已写入的整篇讲义。
