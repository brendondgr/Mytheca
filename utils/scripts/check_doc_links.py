#!/usr/bin/env python3
"""Fail if a Markdown link or image points at a path that does not exist.

Internal links only. Nothing is fetched, so this runs offline and in CI without
network flakiness deciding whether a build is green.

Why this exists: documentation rots because nothing re-runs it. Mytheca has already
shipped a Quickstart whose first command could not execute and an `.env.example`
default that contradicted the code; both were found by hand, months late. A link that
resolves is the cheapest slice of that problem to automate.

Historical records are skipped. A write-up under `docs/research/experiments/` or
`docs/plans/archive/` describes the repository as it WAS. Rewriting one to match the
current tree turns a true record into a claim that a command was run at a commit
where it did not exist, so a stale path in there is not a defect to fix.

Usage:
    uv run python utils/scripts/check_doc_links.py [root]

Exit 0 if every internal link resolves, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

#: Paths that describe the repository as it was. See the module docstring.
HISTORICAL = ("docs/research/experiments/", "docs/plans/archive/")

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "__pycache__", ".next", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".cache", "media",
}

#: [text](target) and ![alt](target), tolerating a "title" after the target.
LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)<>\s]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def is_external(target: str) -> bool:
    return bool(urlparse(target).scheme) or target.startswith("//")


def resolve(doc: Path, target: str, root: Path) -> Path:
    """Resolve a link target the way GitHub does: '/' from the repo root, else relative."""
    path = unquote(target.split("#", 1)[0]).strip()
    if path.startswith("/"):
        return root / path.lstrip("/")
    return doc.parent / path


def check(root: Path) -> list[str]:
    broken: list[str] = []
    for doc in sorted(root.rglob("*.md")):
        rel = doc.relative_to(root).as_posix()
        if any(part in SKIP_DIRS for part in doc.relative_to(root).parts):
            continue
        if rel.startswith(HISTORICAL):
            continue
        in_fence = False
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            # A fenced block holds examples, not links. Checking inside one reports the
            # sample link a doc is teaching you to write as though it were broken.
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for target in LINK.findall(line):
                # A pure anchor (#section) has no path to resolve.
                if is_external(target) or target.startswith("#"):
                    continue
                if not resolve(doc, target, root).exists():
                    broken.append(f"{rel}:{lineno}  ->  {target}")
    return broken


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    broken = check(root)
    if broken:
        print(f"{len(broken)} broken internal link(s):\n")
        for entry in broken:
            print(f"  {entry}")
        print(f"\nHistorical records were skipped: {', '.join(HISTORICAL)}")
        return 1
    print("All internal documentation links resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
