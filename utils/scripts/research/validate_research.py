"""Enforce the research-record contract. Exit non-zero on any violation.

Implements every failure condition in ``docs/research/AGENT_INSTRUCTIONS.md`` §7.3:

  * missing ``manifest.yaml``, ``PROTOCOL.md`` or ``RESULTS.md``
  * manifest failing schema validation
  * ``status: complete`` with empty ``metrics.values``
  * a figure listed in the manifest with no file, or a figure file not listed
  * a figure folder with no generating script
  * a ``data/`` artifact pointer without a hash
  * a ``supports_claims`` ID absent from ``CLAIMS.md``
  * a stale ``INDEX.md``

Deliberately *permissive* about ``status: planned`` and ``status: failed`` having no
metrics. The contract requires failed experiments to stay on record (§3.4), and a
validator that forces a crashed run to invent numbers defeats the purpose.

Run via ``make validate-research``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from . import CLAIMS_PATH, EXPERIMENTS_DIR, RESEARCH_ROOT
from .gen_index import render_index
from .manifest_schema import Manifest, Status

REQUIRED_FILES = ("manifest.yaml", "PROTOCOL.md", "RESULTS.md")

# Figure stems the manifest must account for. PDF is an export of the SVG, so a
# figure is identified by stem and may legitimately exist in several formats.
FIGURE_SUFFIXES = (".svg", ".pdf", ".png")

# A generating script must sit beside the figures it produces. §4: "every figure has
# a generating script committed beside it".
GENERATOR_NAMES = ("make_figures.py", "make_figures.sh")

CLAIM_ID_RE = re.compile(r"\bC-\d{3}\b")
HASH_RE = re.compile(r"\b(sha256|md5|sha1|blake3):[0-9a-fA-F]{6,}", re.IGNORECASE)


class Findings:
    """Accumulates problems so one run reports everything, not just the first fault."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


def known_claim_ids() -> set[str]:
    if not CLAIMS_PATH.exists():
        return set()
    return set(CLAIM_ID_RE.findall(CLAIMS_PATH.read_text(encoding="utf-8")))


def _check_figures(folder: Path, manifest: Manifest, findings: Findings) -> None:
    where = folder.name
    figures_dir = folder / "figures"

    listed = set(manifest.figures)

    on_disk: set[str] = set()
    if figures_dir.is_dir():
        for path in figures_dir.iterdir():
            if path.suffix.lower() in FIGURE_SUFFIXES:
                on_disk.add(path.stem)

    for stem in sorted(listed - on_disk):
        findings.error(
            where,
            f"manifest lists figure {stem!r} but no figures/{stem}{{.svg,.pdf,.png}} exists",
        )

    for stem in sorted(on_disk - listed):
        findings.error(
            where,
            f"figures/{stem}.* exists but is not listed in the manifest's `figures:`",
        )

    if on_disk:
        has_generator = any((figures_dir / name).exists() for name in GENERATOR_NAMES)
        if not has_generator:
            findings.error(
                where,
                "figures/ contains figures but no generating script "
                f"({' or '.join(GENERATOR_NAMES)}) — a figure nobody can regenerate "
                "is a figure that rots",
            )

        # SVG is the required vector format; PDF is required for LaTeX. Raster-only
        # is allowed but called out, because it is almost always an accident.
        for stem in sorted(on_disk):
            if not (figures_dir / f"{stem}.svg").exists():
                findings.warn(where, f"figure {stem!r} has no .svg (vector) export")
            if not (figures_dir / f"{stem}.pdf").exists():
                findings.warn(where, f"figure {stem!r} has no .pdf (LaTeX) export")


def _check_pointers(folder: Path, findings: Findings) -> None:
    """Every large-artifact pointer needs a hash, or it is not a pointer, it is a
    hope. Only lines that actually reference a path are checked."""
    pointers = folder / "data" / "POINTERS.md"
    if not pointers.exists():
        return
    for lineno, line in enumerate(pointers.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ">", "|--", "<!--")):
            continue
        # Heuristic: a table row or bullet naming a path-like token is a pointer.
        if not re.search(r"[\w./-]+/[\w.-]+", stripped):
            continue
        if stripped.startswith("|") and set(stripped) <= set("|- :"):
            continue
        if not HASH_RE.search(stripped):
            findings.error(
                folder.name,
                f"data/POINTERS.md:{lineno} names an artifact with no hash — "
                "a pointer without a hash cannot be verified",
            )


def validate_experiment(folder: Path, claim_ids: set[str], findings: Findings) -> None:
    where = folder.name

    for name in REQUIRED_FILES:
        if not (folder / name).exists():
            findings.error(where, f"missing required file {name}")

    manifest_path = folder / "manifest.yaml"
    if not manifest_path.exists():
        return

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        findings.error(where, f"manifest.yaml is not valid YAML: {exc}")
        return

    if not isinstance(raw, dict):
        findings.error(where, "manifest.yaml did not parse to a mapping")
        return

    try:
        manifest = Manifest.model_validate(raw)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "<root>"
            findings.error(where, f"manifest.{loc}: {err['msg']}")
        return

    # The ID is the only handle used in code, figures, commit messages and drafts, so
    # a folder whose name disagrees with its manifest breaks every cross-reference.
    if not folder.name.startswith(manifest.id + "-"):
        findings.error(
            where,
            f"folder name must start with '{manifest.id}-' to match the manifest id",
        )
    elif folder.name != f"{manifest.id}-{manifest.slug}":
        findings.error(
            where,
            f"folder name should be '{manifest.id}-{manifest.slug}' to match id + slug",
        )

    for message in manifest.cross_field_errors():
        findings.error(where, message)

    for claim in manifest.supports_claims:
        if claim not in claim_ids:
            findings.error(
                where,
                f"supports_claims references {claim!r}, which is not in CLAIMS.md — "
                "no orphan claims",
            )

    _check_figures(folder, manifest, findings)
    _check_pointers(folder, findings)

    if manifest.status is Status.COMPLETE and not (folder / "data").is_dir():
        findings.warn(where, "status is 'complete' but there is no data/ directory")


def validate_all(paths: list[Path] | None = None) -> Findings:
    findings = Findings()

    if not RESEARCH_ROOT.is_dir():
        findings.error("docs/research", "directory does not exist")
        return findings

    if not CLAIMS_PATH.exists():
        findings.error("docs/research", "CLAIMS.md is missing — claims cannot be checked")

    claim_ids = known_claim_ids()

    folders = paths if paths is not None else sorted(
        p for p in EXPERIMENTS_DIR.glob("EXP-*") if p.is_dir()
    )
    for folder in folders:
        validate_experiment(folder, claim_ids, findings)

    # Index staleness is a whole-directory property, so it is only checked on a full run.
    if paths is None:
        index_path = RESEARCH_ROOT / "INDEX.md"
        expected = render_index()
        current = index_path.read_text(encoding="utf-8") if index_path.exists() else None
        if current != expected:
            findings.error(
                "docs/research/INDEX.md",
                "stale — run `make research-index`",
            )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="specific experiment folders to check (default: all, plus INDEX.md staleness)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as errors",
    )
    args = parser.parse_args(argv)

    findings = validate_all([p.resolve() for p in args.paths] if args.paths else None)

    for warning in findings.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in findings.errors:
        print(f"ERROR: {error}", file=sys.stderr)

    failed = bool(findings.errors) or (args.strict and bool(findings.warnings))
    if failed:
        print(
            f"\nvalidate-research FAILED — {len(findings.errors)} error(s), "
            f"{len(findings.warnings)} warning(s)",
            file=sys.stderr,
        )
        return 1

    count = len(args.paths) if args.paths else len(
        [p for p in EXPERIMENTS_DIR.glob("EXP-*") if p.is_dir()]
    )
    print(f"validate-research OK — {count} experiment(s), {len(findings.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
