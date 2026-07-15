#!/usr/bin/env python3
"""Return the next Math I problem ID from registry and chapter anchors."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from repo_model import (
    RepositoryDataError,
    RepositoryDependencyError,
    existing_problem_ids,
)


PREFIX = {
    "calc": "MATH1-CALC",
    "la": "MATH1-LA",
    "prob": "MATH1-PROB",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", choices=sorted(PREFIX), required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    prefix = PREFIX[args.subject]
    pattern = re.compile(re.escape(prefix) + r"-(\d{4})$")
    try:
        ids = existing_problem_ids(args.root.resolve())
    except (RepositoryDependencyError, RepositoryDataError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    numbers = [int(match.group(1)) for value in ids if (match := pattern.fullmatch(value))]
    next_number = max(numbers, default=0) + 1
    print(f"{prefix}-{next_number:04d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
