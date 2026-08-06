"""Regenerate ``docs/research/INDEX.md`` from every experiment manifest.

Hand-maintained indexes go stale within three weeks, so this one is generated and
the validator fails if it is out of date. Run via ``make research-index``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from . import EXPERIMENTS_DIR, INDEX_PATH, RESEARCH_ROOT

HEADER = """# Experiment Index

<!-- GENERATED FILE — do not hand-edit. Regenerate with `make research-index`. -->

Every experiment on record. `make validate-research` fails if this file is stale.
"""

EMPTY_NOTE = """
_No experiments recorded yet._

This is not the same as "no experiments have been run" — see
[`README.md`](README.md). Mytheca had no evaluation of any kind before this record
existed, so there was nothing to back-fill. Every claim in
[`CLAIMS.md`](CLAIMS.md) is currently unsupported.
"""


def _primary_metric(manifest: dict) -> str:
    metrics = manifest.get("metrics") or {}
    primary = metrics.get("primary")
    values = metrics.get("values") or {}
    if not primary:
        return "—"
    cell = values.get(primary)
    if not isinstance(cell, dict) or "mean" not in cell:
        return f"{primary} (pending)"
    mean = cell["mean"]
    std = cell.get("std")
    n = cell.get("n")
    if std is None:
        return f"{primary} = {mean:g} (n={n})"
    return f"{primary} = {mean:g} ± {std:g} (n={n})"


def _row(folder: Path, manifest: dict) -> str:
    claims = manifest.get("supports_claims") or []
    return " | ".join(
        [
            "",
            str(manifest.get("id", "?")),
            str(manifest.get("date_started", "—")),
            str(manifest.get("title", "—")),
            f"`{manifest.get('status', '?')}`",
            _primary_metric(manifest),
            ", ".join(claims) if claims else "—",
            f"[{folder.name}](experiments/{folder.name}/)",
            "",
        ]
    ).strip()


def render_index() -> str:
    """Build the INDEX.md body. Pure — takes no arguments, touches no state but the
    filesystem read, so the test can compare it against the committed file."""
    folders = sorted(p for p in EXPERIMENTS_DIR.glob("EXP-*") if p.is_dir())

    rows: list[str] = []
    for folder in folders:
        manifest_path = folder / "manifest.yaml"
        if not manifest_path.exists():
            # The validator reports this properly; the index just refuses to invent a row.
            rows.append(f"| {folder.name} | — | **manifest.yaml missing** | — | — | — | — |")
            continue
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        rows.append(_row(folder, manifest))

    if not rows:
        return HEADER + EMPTY_NOTE

    table = [
        "",
        "| ID | Started | Title | Status | Primary metric | Claims | Link |",
        "|----|---------|-------|--------|----------------|--------|------|",
        *rows,
        "",
    ]
    return HEADER + "\n".join(table)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    check_only = "--check" in argv

    content = render_index()
    current = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else None

    if current == content:
        if not check_only:
            print(f"INDEX.md up to date ({INDEX_PATH.relative_to(RESEARCH_ROOT.parent.parent)})")
        return 0

    if check_only:
        print("INDEX.md is stale — run `make research-index`", file=sys.stderr)
        return 1

    INDEX_PATH.write_text(content, encoding="utf-8")
    print(f"wrote {INDEX_PATH.relative_to(RESEARCH_ROOT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
