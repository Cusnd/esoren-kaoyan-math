# 归档与两库判定

持久化授权和内容价值是两个独立判断。允许写入不代表必须新增条目；选择能保留长期价值的最小动作。

## 判定顺序

1. 用户明确禁止写文件时，只完成数学讲解并说明没有文件修改。
2. 写题前运行查重并人工核对候选。相同题只补充原条目的新解法、关系或说明，不创建新题号。
3. 判断内容是否值得独立保存；普通问答、无新信息的重复讲解或低质量生成结果可以不入库。
4. 需要保存时，在主库和练习库之间分流，并同步正文、索引、registry 与知识关系。

## 两库边界

- **主库 `core`：** 代表性母题、形成新可复用方法或公式的题、关键知识载体、用户真实错题。
- **练习库 `practice`：** 普通变式、程序熟练训练、近迁移、远迁移和交错练习。
- 两库共用 `data/problem_registry.yml` 和同一 `MATH1-{CALC|LA|PROB}-NNNN` 命名空间。
- 经验证的练习可以晋升为主库；保留原 ID，将正文迁入最接近的既有主库小节并把 `collection` 改为 `core`，不得复制题目或重编号。只有内容本身值得成为独立可检索母题页时才新增 `\studySubsection`。
- 自动生成的练习先标为 `verification_status: draft`；独立核验题面与答案后才改为 `verified` 并进入公开构建。

## Registry 与关系

- 所有题使用公共字段：`id`、`collection`、`origin`、`subject`、`chapter_key`、`title`、`file`、`source`、`difficulty`、`knowledge_ids`、`method_ids`、`pitfall_ids`、`verification_status`。
- 练习题另记录 `answer_file`、`practice_stage`、`task_type`、`estimated_minutes`；确为变式时才写 `variant_of`。
- `knowledge_ids`、`method_ids`、`pitfall_ids` 只引用 `data/knowledge_registry.yml` 中存在的稳定 ID，不以自由文本标签替代关系。
- 关系只使用 `prerequisite_for`、`generalizes_to`、`contrasts_with`、`same_structure_as`；对称关系只登记一次。

## 来源与错误

- `origin` 记录条目形成方式；`source` 保存可展示的具体来源。来源不明使用“用户提供 / 未注明来源”，不得为了填字段猜测出处。
- `pitfall_ids` 表示任何学习者都可能遇到的通用陷阱，不证明用户犯过该错。
- 只有用户实际出现且具有复盘价值的错误才进入真实错题正文与 `mistake_index.tex`。
- 个人复习日期、掌握感、薄弱状态和作答历史只属于浏览器本地状态，不写入内容 registry。
