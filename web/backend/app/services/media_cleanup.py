"""Orphaned-media cleanup service.

Generated portrait/scene-art WebPs are written immediately, but cancelled drafts
and deleted entities leave files on disk with no DB row referencing them. This
service scans for those orphans, reports them (dry-run), and optionally deletes
only the ones that are old enough to fall outside the in-flight-draft grace period.

Safety guarantees
-----------------
- Only files whose basename is **not** referenced by any ``Character.portrait``
  or ``Setting.image`` DB row are candidates.
- Only files with an mtime **older than** ``min_age_hours`` are eligible for
  deletion (protects drafts that are generated but not yet saved).
- Only ``.webp`` files are ever examined; the rest of the directory is untouched.
- Only the configured ``portraits_dir`` and ``scenes_dir`` are touched; nothing
  outside those two subdirectories.
- Every unlink is individually guarded with ``try/except`` so one failure does not
  abort the batch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.character import Character
from app.models.setting import Setting


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _portraits_dir() -> Path:
    """Character portraits directory (monkeypatched in tests)."""
    return get_settings().portraits_dir


def _scenes_dir() -> Path:
    """Setting scene-art directory (monkeypatched in tests)."""
    return get_settings().scenes_dir


def _referenced_basenames(db: Session) -> set[str]:
    """Return the set of WebP basenames currently referenced by any DB row.

    Collects ``Character.portrait`` and ``Setting.image`` values (non-null),
    extracts the final path component (the filename), and returns them as a
    set.  Only ``.webp`` names survive — other formats would be safe to ignore
    in practice, but the cleanup only touches ``.webp`` files anyway.
    """
    basenames: set[str] = set()

    for (value,) in db.query(Character.portrait).filter(Character.portrait.isnot(None)):
        basename = value.rsplit("/", 1)[-1]
        if basename.endswith(".webp"):
            basenames.add(basename)

    for (value,) in db.query(Setting.image).filter(Setting.image.isnot(None)):
        basename = value.rsplit("/", 1)[-1]
        if basename.endswith(".webp"):
            basenames.add(basename)

    return basenames


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class DirOrphanStats:
    """Orphan summary for a single directory."""

    orphan_count: int = 0
    eligible_count: int = 0
    total_bytes: int = 0
    eligible_bytes: int = 0


@dataclass
class OrphanReport:
    """Full scan report returned by ``scan_orphans``."""

    portraits: DirOrphanStats = field(default_factory=DirOrphanStats)
    scenes: DirOrphanStats = field(default_factory=DirOrphanStats)
    orphan_count: int = 0
    eligible_count: int = 0
    total_bytes: int = 0
    eligible_bytes: int = 0
    min_age_hours: float = 24.0


@dataclass
class CleanupResult:
    """Result returned by ``delete_orphans``."""

    deleted_count: int = 0
    freed_bytes: int = 0
    skipped_recent_count: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_orphans(db: Session, *, min_age_hours: float = 24.0) -> OrphanReport:
    """Scan portrait and scene-art directories for orphaned WebP files.

    A file is an orphan if its basename is not referenced by any DB row.  An
    orphan is *eligible* for deletion when its mtime is older than
    ``min_age_hours``.  Missing directories are treated as empty (they are
    created lazily on first use).

    No files are modified by this function.
    """
    referenced = _referenced_basenames(db)
    cutoff = time.time() - min_age_hours * 3600.0

    report = OrphanReport(min_age_hours=min_age_hours)

    dirs = [
        (_portraits_dir(), report.portraits),
        (_scenes_dir(), report.scenes),
    ]

    for directory, stats in dirs:
        if not directory.exists():
            continue
        for path in directory.glob("*.webp"):
            if not path.is_file():
                continue
            if path.name in referenced:
                continue  # referenced — not an orphan
            try:
                size = path.stat().st_size
                mtime = path.stat().st_mtime
            except OSError:
                continue  # file disappeared between glob and stat

            stats.orphan_count += 1
            stats.total_bytes += size
            if mtime < cutoff:
                stats.eligible_count += 1
                stats.eligible_bytes += size

    # Aggregate totals
    report.orphan_count = report.portraits.orphan_count + report.scenes.orphan_count
    report.eligible_count = report.portraits.eligible_count + report.scenes.eligible_count
    report.total_bytes = report.portraits.total_bytes + report.scenes.total_bytes
    report.eligible_bytes = report.portraits.eligible_bytes + report.scenes.eligible_bytes

    return report


def delete_orphans(db: Session, *, min_age_hours: float = 24.0) -> CleanupResult:
    """Delete eligible (grace-expired) orphan WebP files.

    Re-scans the directories inside this call so the eligible set is always
    fresh (no trust in a previously computed list).  Each unlink is guarded
    individually; one failure does not abort the batch.

    Safety:
    - Only deletes files whose basename is NOT referenced in the DB.
    - Only deletes files older than ``min_age_hours`` (grace period).
    - Only deletes ``.webp`` files.
    - Only operates within ``portraits_dir`` / ``scenes_dir``.
    """
    referenced = _referenced_basenames(db)
    cutoff = time.time() - min_age_hours * 3600.0

    result = CleanupResult()

    for directory in (_portraits_dir(), _scenes_dir()):
        if not directory.exists():
            continue
        for path in directory.glob("*.webp"):
            if not path.is_file():
                continue
            if path.name in referenced:
                continue  # safety: never delete a referenced file

            try:
                stat = path.stat()
            except OSError:
                continue  # disappeared between glob and stat

            if stat.st_mtime >= cutoff:
                result.skipped_recent_count += 1
                continue

            size = stat.st_size
            try:
                path.unlink()
                result.deleted_count += 1
                result.freed_bytes += size
            except OSError:
                # Log-worthy but must not abort the batch
                pass

    return result
