#!/usr/bin/env python3
"""Validate a Kaoyan Math I TeX notes repository."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path.cwd()
REQUIRED = [
    "main.tex",
    "tex/preamble.tex",
    "tex/indexes/problem_index.tex",
    "tex/indexes/method_index.tex",
    "tex/indexes/mistake_index.tex",
    "tex/indexes/formula_index.tex",
    "data/problem_registry.yml",
]


def status(kind: str, message: str) -> None:
    print(f"{kind}: {message}")


def check_yaml(path: Path) -> bool:
    try:
        import yaml  # type: ignore
    except Exception:
        status("WARN", "PyYAML is not installed; skipped registry YAML parsing.")
        return True
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        status("FAIL", f"Cannot parse {path}: {exc}")
        return False
    status("PASS", f"Parsed {path}.")
    return True


def run_compile() -> bool:
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    latexmk = shutil.which("latexmk")
    xelatex = shutil.which("xelatex")
    if latexmk:
        cmd = [latexmk, "-xelatex", "-interaction=nonstopmode", "-halt-on-error", f"-outdir={build}", "main.tex"]
    elif xelatex:
        cmd = [xelatex, "-interaction=nonstopmode", "-halt-on-error", f"-output-directory={build}", "main.tex"]
    else:
        status("WARN", "Neither latexmk nor xelatex found; skipped compile check.")
        return True
    status("INFO", "Running " + " ".join(str(part) for part in cmd))
    result = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode == 0:
        status("PASS", "LaTeX compile completed.")
        return True
    status("FAIL", "LaTeX compile failed.")
    print(result.stdout[-4000:])
    return False


def main() -> int:
    ok = True
    for rel in REQUIRED:
        path = ROOT / rel
        if path.exists():
            status("PASS", f"Found {rel}.")
        else:
            status("FAIL", f"Missing {rel}.")
            ok = False

    main_tex = ROOT / "main.tex"
    if main_tex.exists():
        text = main_tex.read_text(encoding="utf-8", errors="replace")
        if r"\input{tex/preamble.tex}" in text:
            status("PASS", "main.tex inputs tex/preamble.tex.")
        else:
            status("FAIL", "main.tex does not input tex/preamble.tex.")
            ok = False
        inputs = re.findall(r"\\input\{([^}]+)\}", text)
        chapter_inputs = [item for item in inputs if item.startswith("tex/chapters/")]
        if chapter_inputs:
            status("PASS", f"main.tex has {len(chapter_inputs)} chapter inputs.")
        else:
            status("FAIL", "main.tex has no chapter inputs.")
            ok = False
        for rel in inputs:
            if not (ROOT / rel).exists():
                status("FAIL", f"main.tex input target missing: {rel}")
                ok = False

    registry = ROOT / "data/problem_registry.yml"
    if registry.exists():
        ok = check_yaml(registry) and ok

    ok = run_compile() and ok
    status("PASS" if ok else "FAIL", "Repository validation complete.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
