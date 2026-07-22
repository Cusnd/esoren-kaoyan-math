# 考研数学一学习笔记与题解库

这个仓库用于长期维护考研数学一的母题、知识点、方法、真实错题与训练题，并把同一套内容生成主笔记、练习册、答案册和本地优先的静态网页。主库只保留长期精选资产，普通变式进入独立练习库；题目、知识节点和网页复习状态通过稳定 ID 串联。

## 使用方式

1. Codex 进入仓库后读取根 `AGENTS.md`；数学题、知识点、错解、OCR 与章节整理任务由仓库级 `kaoyan-math1-fullscore-coach` Skill 处理。
2. 默认同时完成中文讲解与有价值内容的持久化；母题、新方法、关键知识和真实错题进入主库，普通变式与训练进入练习库，重复或无新增价值的输入不会机械创建条目。
3. “简洁回答”只压缩聊天回复，只有明确说“只聊天不写文件”才跳过文件修改。
4. `data/textbook_catalog.yml` 是章节顺序、稳定章节键与路径的唯一事实源；`data/problem_registry.yml` 统一登记两库题目；`data/knowledge_registry.yml` 保存稳定知识节点和显式关系。
5. 数学内容结构以 `tex/templates/` 下的实时模板为准，不在 Skill 或复制提示词中维护镜像。
6. 显式输入“深度讲解 K031”或“生成满分级讲义 K031、K032”时，Skill 会把主讲义写入对应章节 TeX，并把已核验的 A/B/C/M 练习与答案分别写入练习册和答案册；普通“讲解 K031”仍按需回答。

## 仓库契约验证

验证脚本使用现有 `codex-tools` 环境，不新增项目生产依赖：

```powershell
$mamba = 'C:\Users\liuso\miniforge3\Library\bin\mamba.exe'
& $mamba run -n codex-tools python .agents/skills/kaoyan-math1-fullscore-coach/scripts/validate_math1_repo.py --no-compile
& $mamba run -n codex-tools python -m unittest discover -s tests/skill -p 'test_*.py' -v
```

移除 `--no-compile` 后，validator 会编译 `main.tex`、`practice.tex` 与 `practice-answers.tex`；没有编译器时逐项报告 `SKIP`。validator 支持 `--root`、`--format text|json`，退出码固定为 0（成功）、1（校验失败）、2（用法或依赖错误）。

前向评测默认只列出案例，不会调用模型。显式传入 `--run` 后，评测器会先冻结一次仓库快照，再为每个案例复制该不可变基底，并在应用 fixture 后建立一次性本地 Git 基线；`tests/skill/` 中的 manifest、oracle 与评测器不会复制给被测模型。Windows 默认在 WSL 中叠加 bubblewrap 读隔离：只把一次性 workspace 与独立空 output 绑定进命名空间；现存 `/mnt/[a-z]` Windows 盘符目录逐个由空 tmpfs 遮蔽，原仓库不可见，而 `/mnt/wsl` 保留以支持 WSL DNS，网络命名空间不隔离。每次运行只把真实 `.codex` 中存在的 `auth.json`、`config.toml` 复制进权限收紧、结束即删除的临时 Codex HOME，真实历史和数据库目录始终被遮蔽。缺少 `bwrap` 会在调用模型前直接失败。`--output-dir` 必须位于仓库外且预先不存在或为空，运行结果记录 `runner_isolation: bwrap-ro-root-hidden-windows-drives-v2`。Skill 未实际读取、token 用量缺失、越权 diff、机械结果门禁失败或虚假验证声明会阻止候选通过；输出正则和可恢复工具错误仍使该 run 的严格自动检查失败并进入人工/资源效率证据，但不会单独冒充计划中的致命失败。单次运行默认上限为 900 秒，超时不会自动重跑。

```powershell
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --smoke
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --run --smoke --snapshot worktree --prompt-source head --runner wsl --model gpt-5.6-sol --effort max --output-dir C:\Temp\math1-baseline
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --run --smoke --snapshot worktree --prompt-source worktree --runner wsl --model gpt-5.6-sol --effort max --output-dir C:\Temp\math1-candidate
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --compare C:\Temp\math1-baseline\summary.json C:\Temp\math1-candidate\summary.json
```

新增的 K 编号深度讲义案例不进入日常 smoke；按相同模型、档位和基础树做定向 A/B：

```powershell
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --run --case deep_calculus_k031_persist --snapshot worktree --prompt-source head --runner wsl --model gpt-5.6-sol --effort max --output-dir C:\Temp\math1-deep-baseline
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --run --case deep_calculus_k031_persist --snapshot worktree --prompt-source worktree --runner wsl --model gpt-5.6-sol --effort max --output-dir C:\Temp\math1-deep-candidate
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --compare C:\Temp\math1-deep-baseline\summary.json C:\Temp\math1-deep-candidate\summary.json
```

若只调整了 automatic-fatal 分类政策，可对原始 summary 做确定性重分类，不重跑模型或覆盖原文件；新文件会记录来源 SHA-256、重分类时间和策略 ID，回答、diff、token 与 strict `automatic_pass` 保持不变：

```powershell
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --reclassify C:\Temp\math1-baseline\summary.json C:\Temp\math1-baseline\summary-reclassified.json
```

若评测案例唯一变化是 `file_expectations.allowed_changes`，可直接用原始完整 summary 中保存的 `changed_paths` 做离线重评分。评测器会逐 run 核对 prompt、fixture、oracle、rubric、checks、致命门禁与其余文件规则均未变化，只重新计算路径许可及其派生自动结论；任何其他案例字段漂移都会拒绝。输出必须是尚不存在的新文件，不覆盖来源；审计信息包含来源 summary SHA-256、旧/新 manifest SHA-256、时间与 automatic-fatal 策略 ID。该模式不会调用模型：

```powershell
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --manifest tests/skill/cases.yml --rescore-allowlist C:\Temp\math1-baseline\summary.json C:\Temp\math1-baseline\summary-allowlist-rescored.json
```

提示词 A/B 固定同一基础树、模型和推理档位，只替换根契约、Skill 与 references；比较器会拒绝案例集合、manifest、模型、档位、基础树或复核 run 集合不一致的结果。自动检查完成后仍不能直接通过：每个 run 都要由真实人工完成 fatal 复核，至少 20% 的 run 要完成五维评分且覆盖每个 slice；缺少人工 attestation、任一 slice 评分或完整 token 时，结果保持 `pending_human_review`。

盲审默认使用不进入共享包的随机私钥。生成后保留 `private/answer-key.json`，把 `share/` 交给不知道 A/B 身份的人工复核者；复核者复制并填写评分模板，不修改原始 package。每个 run 都必须按共享包顶层完整 `fatal_taxonomy` 检查致命失败，案例自己的 `hard_fail_if` 只作重点提示；抽样 run 另做全部五维评分。随后用私钥校验 package、fatal taxonomy、两份原始 summary 与全部评分，再映射为两份新 summary：

```powershell
& $mamba run -n codex-tools python tests/skill/prepare_blind_review.py C:\Temp\math1-baseline\summary.json C:\Temp\math1-candidate\summary.json --output-dir C:\Temp\math1-blind-review
Copy-Item C:\Temp\math1-blind-review\share\review-scores.template.json C:\Temp\math1-blind-review\share\review-scores.json
# 由真实人工填写 review-scores.json 后再执行：
& $mamba run -n codex-tools python tests/skill/apply_blind_review.py C:\Temp\math1-blind-review\share\review-package.json C:\Temp\math1-blind-review\private\answer-key.json C:\Temp\math1-blind-review\share\review-scores.json C:\Temp\math1-baseline\summary.json C:\Temp\math1-candidate\summary.json --baseline-output C:\Temp\math1-baseline-reviewed.json --candidate-output C:\Temp\math1-candidate-reviewed.json
& $mamba run -n codex-tools python tests/skill/run_forward_eval.py --compare C:\Temp\math1-baseline-reviewed.json C:\Temp\math1-candidate-reviewed.json
```

候选提示词确定后，可用相同 `prompt-source` 分别运行 `max` 与 `xhigh`；生成盲审包和最终比较时都传 `--comparison-mode effort`。模型与档位只存在于评测命令和结果中，不写入项目提示词。

## 编译 PDF

优先使用完整 validator。需要单独编译时，三个入口均使用 XeLaTeX：

```powershell
xelatex -interaction=nonstopmode -file-line-error main.tex
xelatex -interaction=nonstopmode -file-line-error practice.tex
xelatex -interaction=nonstopmode -file-line-error practice-answers.tex
```

如果本地暂时没有 XeLaTeX，请先继续维护 `.tex` 源文件，并在具备 LaTeX 环境后补跑编译验证。

## 网页笔记

网页版保持 TeX 为唯一正文源：`lwarp` 生成静态 HTML，构建后处理器再注入响应式阅读器、两库统一搜索、显式知识关系、今日复习、PWA 与自托管 MathJax 3.2.2。网页不包含账号、后端、模型调用或答题评分；个人复习状态只保存在浏览器的 `math1.reader.reviews.v1`，可导入导出。

需要 Node.js 24。首次检出后先安装锁定依赖：

```powershell
npm ci
```

执行完整构建：

```powershell
npm run build:web
```

发布根目录是 `build/site/`：Cloudflare 的 `_headers`、`_redirects` 位于该层，canonical HTML 页面、学习项搜索索引、关系索引、离线资源、自托管 MathJax 和三份 PDF 均位于 `build/site/math/`；页面和重定向数量由清单推导，不在代码中写死。本地检查：

```powershell
npm run test:static
npm run preview:web
```

本地预览入口为 `http://127.0.0.1:8787/math/`。

浏览器验收使用 Playwright，覆盖 Edge、Chrome、Firefox 以及 360/390/768/1280/1440 响应式宽度：

```powershell
npm run test:browser
```

Cloudflare Workers Static Assets 发布命令仍保留，但发布前应先完成完整构建与测试：

```powershell
npm run preview:web
npm run deploy:web:dry-run
npm run deploy:web
```

网页入口是 `main-web.tex`，PDF 入口仍是 `main.tex`。

生产站点由两个 Worker 组合提供：独立的 `pee-gateway` 通过 Custom Domain 接管主机首页，数学站由本仓库的 `kaoyan-math1-notes` Worker 通过更具体的 `/math/*` Route 提供。当前公开访问地址：

```text
https://pee.esoren.com/math/
```

`kaoyan-math1-notes.sorenliu.workers.dev` 已关闭。数学站的 canonical、搜索、PDF、静态资源和 PWA 均以 `/math/` 为作用域；Cloudflare Web Analytics 不得改写 HTML，以保持网关无脚本和数学站资源完全自托管。

## 目录

```text
main.tex
practice.tex
practice-answers.tex
main-web.tex
tex/preamble.tex
tex/preamble_web.tex
tex/styles/academic_old_money.tex
tex/styles/math1_web.tex
tex/chapters/calculus/
tex/chapters/linear_algebra/
tex/chapters/probability/
tex/practice/
tex/indexes/
tex/templates/problem_template.tex
tex/templates/knowledge_template.tex
tex/templates/mistake_template.tex
web/math1-web.css
web/reader/
web/pwa/
scripts/build_web.ps1
scripts/postprocess_web.mjs
data/problem_registry.yml
data/knowledge_registry.yml
data/textbook_catalog.yml
data/web_pages.yml
tests/static/
tests/browser/
tests/skill/
docs/textbook_catalog.md
```
