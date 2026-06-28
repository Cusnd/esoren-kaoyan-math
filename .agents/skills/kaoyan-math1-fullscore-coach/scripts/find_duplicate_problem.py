#!/usr/bin/env python3
"""Coarse duplicate search for Math I problems."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path


ROOT = Path.cwd()


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact(text: str) -> str:
    return normalize(text).replace(" ", "")


def char_ngrams(text: str, n: int = 2) -> set[str]:
    text = compact(text)
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    chars = jaccard(char_ngrams(a), char_ngrams(b))
    tokens = jaccard(set(na.split()), set(nb.split()))
    return max(seq, chars, tokens)


def tex_chunks(text: str) -> list[str]:
    chunks = re.split(r"(?=\\subsection\{)", text)
    chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
    if chunks:
        return chunks
    return [text]


def registry_entries() -> list[tuple[str, str]]:
    path = ROOT / "data/problem_registry.yml"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    entries = []
    for block in re.split(r"\n(?=- id: )", text):
        pid = re.search(r"id:\s*([A-Z0-9-]+)", block)
        title = re.search(r'title:\s*"?([^"\n]+)"?', block)
        tags = re.findall(r"^\s*-\s*([^\n]+)", block, flags=re.MULTILINE)
        label = pid.group(1) if pid else "registry"
        content = " ".join([title.group(1) if title else "", *tags])
        if content.strip():
            entries.append((label, content))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="*", help="Problem text. Reads stdin when omitted.")
    parser.add_argument("--threshold", type=float, default=0.22)
    args = parser.parse_args()
    query = " ".join(args.text).strip() or sys.stdin.read().strip()
    if not query:
        print("No problem text provided.", file=sys.stderr)
        return 2

    candidates: list[tuple[float, str, str]] = []
    for path in (ROOT / "tex/chapters").rglob("*.tex"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for index, chunk in enumerate(tex_chunks(text), start=1):
            label = f"{path.relative_to(ROOT)}#chunk-{index}"
            candidates.append((score(query, chunk), label, "chapter tex"))
    for label, content in registry_entries():
        candidates.append((score(query, content), label, "registry"))

    matches = sorted((item for item in candidates if item[0] >= args.threshold), reverse=True)[:10]
    if not matches:
        print("No likely duplicates found.")
        return 0
    for value, where, kind in matches:
        print(f"{value:.3f}\t{kind}\t{where}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
