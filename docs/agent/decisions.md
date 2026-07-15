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
- PDF 内部跳转采用 `hyperref` 的轻量命令封装：题目编号使用原始题号作为 ASCII 目标名；中文知识点显示中文，但内部目标名使用显式 ASCII key，避免中文 destination 在 PDF 中不稳定。

## 2026-07-03

- 新增网页输出作为 PDF 之外的第二发布目标：`main-web.tex` 使用 `lwarp`、MathJax CDN 和网页专用样式，不复用 PDF 版式文件。
- 网页构建输出统一进入 `build/site/`，Cloudflare Workers Static Assets 通过 `wrangler.jsonc` 发布该目录；当前站点先保持纯静态，不写 Worker 脚本。

## 2026-07-15

- 2026-07-03 的 MathJax CDN 方案被本决策取代：网页公式固定使用自托管 MathJax 3.2.2，构建从 `lwarp_mathjax.txt` 提取 ASCII 配置，并校验扩展资源与实际渲染。
- `data/web_pages.yml` 是 Web 页面顺序、slug、旧编号和源文件的唯一清单；TeX 使用 `\studySection` / `\studySubsection` 保持 PDF 中文标题与 Web ASCII 文件名并存。
- 阅读器采用原生 ES Modules、CSS 和 Cheerio/YAML 构建后处理，不建立客户端路由或后端服务；canonical 路由使用无扩展名 URL。
- 桌面阅读器使用贴边三栏壳层和约 720px 阅读列；中宽隐藏右栏，800px 以下使用顶部栏、显式进度与焦点管理目录抽屉。
- Service Worker 只在新版本资源完整缓存后提供刷新确认；确认更新后，所有已受控标签页在新 Worker 接管时统一刷新，首次安装不强制刷新；缓存按 `buildId` 隔离并在激活时清理旧版本，未知 HTML 路由回退离线页。
- `buildId` 只由稳定内容与阅读器资源决定，避免 PDF 时间戳制造虚假升级；PDF 使用独立 SHA-256 并设置重新验证缓存策略。
- Playwright 默认最多 3 个 worker，避免 Windows 设备在 Edge、Chrome、Firefox 并发启动时耗尽软件渲染资源。
