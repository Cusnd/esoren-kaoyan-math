#!/usr/bin/env python3
"""Return the next Math I problem id."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path.cwd()
PREFIX = {
    "calc": "MATH1-CALC",
    "la": "MATH1-LA",
    "prob": "MATH1-PROB",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", choices=sorted(PREFIX), required=True)
    args = parser.parse_args()
    prefix = PREFIX[args.subject]
    pattern = re.compile(re.escape(prefix) + r"-(\d{4})")

    max_seen = 0
    for path in [ROOT / "data/problem_registry.yml", *list((ROOT / "tex/chapters").rglob("*.tex"))]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in pattern.finditer(text):
            max_seen = max(max_seen, int(match.group(1)))

    print(f"{prefix}-{max_seen + 1:04d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
