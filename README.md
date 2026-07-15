# 考研数学一学习笔记与题解库

这个仓库用于长期维护考研数学一的题目、题解、知识点、错题、方法索引和公式索引。核心文档是 `main.tex`，章节内容按教材目录拆分到 `tex/chapters/` 下。

## 使用方式

1. 开始学习或整理前，先阅读 `AGENTS.md`。
2. 每次粘贴题目、知识点、错解或疑问时，按“讲解 + 写入 TeX + 更新索引”的流程维护。
3. 可复用的 Codex 总提示词保存在 `prompts/codex_math1_prompt.md`。
4. 教材目录映射保存在 `docs/textbook_catalog.md` 和 `data/textbook_catalog.yml`，新增内容优先按教材“第几讲”归档。

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
docs/textbook_catalog.md
```
