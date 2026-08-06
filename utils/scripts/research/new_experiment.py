"""Scaffold a new experiment folder from ``docs/research/templates/experiment/``.

Allocates the next ``EXP-<YYYY>-<MM>-<NNN>`` id and pre-fills the fields that can be
captured mechanically — date, git commit, branch, and a real dirty-tree check. Fields
that require a human to think (purpose, hypothesis, metrics) are left as template
placeholders on purpose: a scaffolder that guesses them produces a manifest that
looks filled in and is not.

Run via ``make new-experiment SLUG=my-slug``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import EXPERIMENTS_DIR, REPO_ROOT, TEMPLATE_DIR

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _git(*args: str) -> str:
    """Run a git command, returning empty string on failure rather than raising —
    scaffolding must work outside a git checkout, it just records less."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def git_state() -> dict[str, object]:
    commit = _git("rev-parse", "HEAD") or "unknown"
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    # `git status --porcelain` is empty exactly when the tree is clean. Recording
    # this honestly matters: a result produced from a dirty tree is not reproducible
    # from its commit, and the contract wants that stated, not hidden.
    dirty = bool(_git("status", "--porcelain"))
    return {"commit": commit, "branch": branch, "dirty": dirty}


def next_id(today: date | None = None) -> str:
    """Allocate the next sequence number for the current year and month.

    Sequence is per year-month, matching the contract's EXP-YYYY-MM-NNN format.
    """
    today = today or date.today()
    prefix = f"EXP-{today.year:04d}-{today.month:02d}-"
    existing = [p.name for p in EXPERIMENTS_DIR.glob(f"{prefix}*") if p.is_dir()]
    used = []
    for name in existing:
        tail = name[len(prefix) :]
        seq = tail.split("-", 1)[0]
        if seq.isdigit():
            used.append(int(seq))
    return f"{prefix}{(max(used) + 1) if used else 1:03d}"


def _prefill_manifest(text: str, exp_id: str, slug: str, today: date) -> str:
    state = git_state()
    substitutions = {
        "id: EXP-YYYY-MM-NNN": f"id: {exp_id}",
        "slug: <kebab-slug>": f"slug: {slug}",
        "date_started: YYYY-MM-DD": f"date_started: {today.isoformat()}",
        "  commit: <sha>": f"  commit: {state['commit']}",
        "  branch: <branch>": f"  branch: {state['branch']}",
        "  dirty: false": f"  dirty: {str(state['dirty']).lower()}",
    }
    for old, new in substitutions.items():
        text = text.replace(old, new, 1)
    return text


def _prefill_markdown(text: str, exp_id: str, title: str) -> str:
    return text.replace("<EXP-ID>", exp_id).replace("<title>", title)


def scaffold(
    slug: str,
    title: str | None = None,
    today: date | None = None,
    _force_id: str | None = None,
) -> Path:
    """Create the experiment folder. ``_force_id`` exists only to exercise the
    collision guard in tests; normal callers let ``next_id`` allocate."""
    if not SLUG_RE.match(slug):
        raise ValueError(
            f"slug must be lowercase kebab-case (got {slug!r}) — it becomes part of a "
            "permanent, never-renamed directory name"
        )
    if not TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(f"template directory missing: {TEMPLATE_DIR}")

    today = today or date.today()
    exp_id = _force_id or next_id(today)
    title = title or slug.replace("-", " ").capitalize()
    target = EXPERIMENTS_DIR / f"{exp_id}-{slug}"

    if target.exists():
        raise FileExistsError(f"{target} already exists")

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE_DIR, target)

    manifest = target / "manifest.yaml"
    manifest.write_text(
        _prefill_manifest(manifest.read_text(encoding="utf-8"), exp_id, slug, today),
        encoding="utf-8",
    )

    for name in ("PROTOCOL.md", "RESULTS.md", "ISSUES.md"):
        path = target / name
        if path.exists():
            path.write_text(
                _prefill_markdown(path.read_text(encoding="utf-8"), exp_id, title),
                encoding="utf-8",
            )

    # The contract's §3 directory shape. Created empty so the layout is obvious
    # before anything is written into it.
    for sub in ("data", "env", "logs", "tables"):
        (target / sub).mkdir(exist_ok=True)
        (target / sub / ".gitkeep").touch()

    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="kebab-case slug, e.g. baseline-retrieval")
    parser.add_argument("--title", default=None, help="human-readable title")
    args = parser.parse_args(argv)

    try:
        target = scaffold(args.slug, args.title)
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    rel = target.relative_to(REPO_ROOT)
    print(f"scaffolded {rel}")
    print()
    print("Next, in order:")
    print(f"  1. Fill {rel}/PROTOCOL.md — BEFORE running anything.")
    print("  2. Run via the recorded entrypoint so the manifest captures state at write-time.")
    print(f"  3. Fill {rel}/RESULTS.md and regenerate figures.")
    print("  4. make validate-research && make research-index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
