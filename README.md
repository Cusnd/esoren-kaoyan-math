# 考研数学一学习笔记与题解库

这个仓库用于长期维护考研数学一的题目、题解、知识点、错题、方法索引和公式索引。核心文档是 `main.tex`，章节内容按高等数学、线性代数、概率论与数理统计拆分到 `tex/chapters/` 下。

## 使用方式

1. 开始学习或整理前，先阅读 `AGENTS.md`。
2. 每次粘贴题目、知识点、错解或疑问时，按“讲解 + 写入 TeX + 更新索引”的流程维护。
3. 可复用的 Codex 总提示词保存在 `prompts/codex_math1_prompt.md`。

## 编译

默认使用 XeLaTeX：

```powershell
xelatex -interaction=nonstopmode -file-line-error main.tex
```

如果本地暂时没有 XeLaTeX，请先继续维护 `.tex` 源文件，并在具备 LaTeX 环境后补跑编译验证。

## 目录

```text
main.tex
tex/preamble.tex
tex/chapters/calculus/
tex/chapters/linear_algebra/
tex/chapters/probability/
tex/indexes/
tex/templates/problem_template.tex
data/problem_registry.yml
```
