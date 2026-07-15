# 考研数学一学习笔记与题解库

这个仓库用于长期维护考研数学一的题目、题解、知识点、错题、方法索引和公式索引。核心文档是 `main.tex`，章节内容按教材目录拆分到 `tex/chapters/` 下。

## 使用方式

1. Codex 进入仓库后读取根 `AGENTS.md`；数学题、知识点、错解、OCR 与章节整理任务由仓库级 `kaoyan-math1-fullscore-coach` Skill 处理。
2. 默认同时完成中文满分讲解与题库持久化；“简洁回答”只压缩聊天回复，只有明确说“只聊天不写文件”才跳过文件修改。
3. `data/textbook_catalog.yml` 是章节顺序与路径的唯一事实源，`docs/textbook_catalog.md` 是对应的人类可读视图。
4. 题目、知识点与错题模板以 `tex/templates/` 下的实时文件为准，不在 Skill 内维护副本。

## 仓库契约验证

验证脚本使用现有 `codex-tools` 环境，不新增项目生产依赖：

```powershell
$mamba = 'C:\Users\liuso\miniforge3\Library\bin\mamba.exe'
& $mamba run -n codex-tools python .agents/skills/kaoyan-math1-fullscore-coach/scripts/validate_math1_repo.py --no-compile
& $mamba run -n codex-tools python -m unittest discover -s tests/skill -p 'test_*.py' -v
```

移除 `--no-compile` 后，validator 会优先使用 `latexmk`，否则执行两次 `xelatex`；没有编译器时明确报告 `SKIP`。validator 支持 `--root`、`--format text|json`，退出码固定为 0（成功）、1（校验失败）、2（用法或依赖错误）。

## 编译 PDF

默认使用 XeLaTeX：

```powershell
xelatex -interaction=nonstopmode -file-line-error main.tex
```

如果本地暂时没有 XeLaTeX，请先继续维护 `.tex` 源文件，并在具备 LaTeX 环境后补跑编译验证。

## 网页笔记

网页版保持 TeX 为唯一内容源：`lwarp` 生成静态 HTML，构建后处理器再注入响应式阅读器、搜索、PWA 与自托管 MathJax 3.2.2。生产构建同时编译 PDF；任一内容链路失败都会使构建失败。

需要 Node.js 24。首次检出后先安装锁定依赖：

```powershell
npm ci
```

执行完整构建：

```powershell
npm run build:web
```

生成结果位于 `build/site/`，包含 53 个 canonical HTML 页面、搜索索引、离线资源、自托管 MathJax 和 `downloads/kaoyan-math1-notes.pdf`。本地检查：

```powershell
npm run test:static
npm run preview:web
```

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

当前公开访问地址：

```text
https://kaoyan-math1-notes.sorenliu.workers.dev
```

## 目录

```text
main.tex
main-web.tex
tex/preamble.tex
tex/preamble_web.tex
tex/styles/academic_old_money.tex
tex/styles/math1_web.tex
tex/chapters/calculus/
tex/chapters/linear_algebra/
tex/chapters/probability/
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
data/textbook_catalog.yml
data/web_pages.yml
tests/static/
tests/browser/
tests/skill/
docs/textbook_catalog.md
```
