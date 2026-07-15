#!/usr/bin/env python3
"""Find likely duplicate Math I problems using one candidate per problem ID."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

from repo_model import (
    RepositoryDataError,
    RepositoryDependencyError,
    load_registry,
    problem_blocks,
    registry_search_text,
)


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
    return {text[index : index + n] for index in range(len(text) - n + 1)}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def score(left: str, right: str) -> float:
    normalized_left, normalized_right = normalize(left), normalize(right)
    if not normalized_left or not normalized_right:
        return 0.0
    sequence = difflib.SequenceMatcher(
        None, normalized_left, normalized_right
    ).ratio()
    characters = jaccard(char_ngrams(left), char_ngrams(right))
    tokens = jaccard(set(normalized_left.split()), set(normalized_right.split()))
    return max(sequence, characters, tokens)


def probability(value: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return number


def likely_duplicates(
    root: Path, query: str, threshold: float, limit: int
) -> list[dict[str, object]]:
    registry = {
        entry.get("id"): entry
        for entry in load_registry(root)
        if isinstance(entry.get("id"), str)
    }
    matches: list[dict[str, object]] = []
    for block in problem_blocks(root):
        extra = registry_search_text(registry.get(block.problem_id, {}))
        value = score(query, f"{block.text} {extra}")
        if value >= threshold:
            matches.append(
                {
                    "score": round(value, 6),
                    "problem_id": block.problem_id,
                    "file": block.file,
                }
            )
    matches.sort(key=lambda item: (-float(item["score"]), str(item["problem_id"])))
    return matches[:limit]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="*", help="Problem text. Reads stdin when omitted.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--threshold", type=probability, default=0.22)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    query = " ".join(args.text).strip() or sys.stdin.read().strip()
    if not query:
        print("No problem text provided.", file=sys.stderr)
        return 2

    root = args.root.resolve()
    try:
        matches = likely_duplicates(root, query, args.threshold, args.limit)
    except (RepositoryDependencyError, RepositoryDataError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(
            json.dumps(
                {
                    "query": query,
                    "threshold": args.threshold,
                    "matches": matches,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not matches:
        print("No likely duplicates found.")
        return 0
    for match in matches:
        print(
            f"{float(match['score']):.3f}\t{match['problem_id']}\t{match['file']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
