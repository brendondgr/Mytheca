"""Orphaned-media cleanup service — fully offline tests.

The portrait / scene directories are redirected to ``tmp_path`` subdirs via
monkeypatching (mirroring the approach in ``test_portraits.py``). No ComfyUI or
real media directory is needed.

Coverage
--------
1. A file referenced by ``Character.portrait`` is NOT an orphan and survives.
2. A file referenced by ``Setting.image`` is NOT an orphan and survives.
3. An unreferenced, grace-EXPIRED file is reported as eligible and deleted.
4. An unreferenced but RECENT file is reported as an orphan (count > 0) but
   NOT eligible, and is NOT deleted (protects in-flight drafts).
5. A non-``.webp`` file in the media dir is never touched.
6. ``GET /api/options/media/orphans`` returns the expected JSON shape.
7. ``POST /api/options/media/cleanup`` returns the expected shape and count.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.models.character import Character
from app.models.setting import Setting
from app.services import media_cleanup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "  # not a valid image, but good enough for size


def _write(directory: Path, filename: str, content: bytes = FAKE_WEBP) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / filename
    p.write_bytes(content)
    return p


def _age(path: Path, seconds: float) -> None:
    """Backdate a file's mtime by ``seconds``."""
    now = time.time()
    os.utime(path, (now - seconds, now - seconds))


# ---------------------------------------------------------------------------
# Service-level tests (direct calls, no HTTP)
# ---------------------------------------------------------------------------


class TestScanOrphans:
    def test_referenced_portrait_not_in_orphan_report(
        self, db_session, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        filename = "aabbccdd" * 4 + ".webp"
        p = _write(portraits, filename)
        _age(p, 100 * 3600)  # old enough to be eligible

        # Seed DB with a character referencing this portrait
        char = Character(
            storyline_id="sl-1",
            name="Hero",
            portrait=f"/media/portraits/{filename}",
        )
        db_session.add(char)
        db_session.commit()

        report = media_cleanup.scan_orphans(db_session, min_age_hours=1.0)
        assert report.orphan_count == 0
        assert report.eligible_count == 0
        assert report.total_bytes == 0

    def test_referenced_scene_not_in_orphan_report(
        self, db_session, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        filename = "11223344" * 4 + ".webp"
        p = _write(scenes, filename)
        _age(p, 100 * 3600)

        setting = Setting(
            storyline_id="sl-1",
            name="The Void",
            image=f"/media/scenes/{filename}",
        )
        db_session.add(setting)
        db_session.commit()

        report = media_cleanup.scan_orphans(db_session, min_age_hours=1.0)
        assert report.orphan_count == 0
        assert report.eligible_count == 0

    def test_expired_orphan_is_reported_as_eligible(
        self, db_session, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        p = _write(portraits, "deadbeef" * 4 + ".webp", content=b"x" * 500)
        _age(p, 48 * 3600)  # 48 h old, well outside the grace period

        report = media_cleanup.scan_orphans(db_session, min_age_hours=24.0)
        assert report.orphan_count == 1
        assert report.eligible_count == 1
        assert report.total_bytes == 500
        assert report.eligible_bytes == 500
        # Breakdown check
        assert report.portraits.orphan_count == 1
        assert report.portraits.eligible_count == 1

    def test_recent_orphan_counted_but_not_eligible(
        self, db_session, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        # Brand-new file (mtime = now) — within any reasonable grace period
        _write(portraits, "cafe1234" * 4 + ".webp", content=b"y" * 200)

        report = media_cleanup.scan_orphans(db_session, min_age_hours=24.0)
        assert report.orphan_count == 1
        assert report.eligible_count == 0  # too new → not eligible
        assert report.total_bytes == 200
        assert report.eligible_bytes == 0

    def test_non_webp_file_ignored(self, db_session, tmp_path, monkeypatch):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        portraits.mkdir(parents=True)
        (portraits / "notes.txt").write_bytes(b"should not appear")
        (portraits / "image.png").write_bytes(b"also ignored")

        report = media_cleanup.scan_orphans(db_session, min_age_hours=0.0)
        assert report.orphan_count == 0

    def test_missing_directory_treated_as_empty(
        self, db_session, tmp_path, monkeypatch
    ):
        # Neither directory exists
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: tmp_path / "nope1")
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: tmp_path / "nope2")

        report = media_cleanup.scan_orphans(db_session, min_age_hours=24.0)
        assert report.orphan_count == 0


class TestDeleteOrphans:
    def test_expired_orphan_deleted_and_bytes_reported(
        self, db_session, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        p = _write(portraits, "feedface" * 4 + ".webp", content=b"z" * 1024)
        _age(p, 48 * 3600)

        result = media_cleanup.delete_orphans(db_session, min_age_hours=24.0)
        assert result.deleted_count == 1
        assert result.freed_bytes == 1024
        assert result.skipped_recent_count == 0
        assert not p.exists()

    def test_referenced_file_never_deleted(
        self, db_session, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        filename = "00112233" * 4 + ".webp"
        p = _write(portraits, filename)
        _age(p, 100 * 3600)

        char = Character(
            storyline_id="sl-2",
            name="Survivor",
            portrait=f"/media/portraits/{filename}",
        )
        db_session.add(char)
        db_session.commit()

        result = media_cleanup.delete_orphans(db_session, min_age_hours=0.0)
        assert result.deleted_count == 0
        assert p.exists()

    def test_recent_orphan_skipped_not_deleted(
        self, db_session, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        p = _write(portraits, "babe1234" * 4 + ".webp")
        # File is brand new — within grace period

        result = media_cleanup.delete_orphans(db_session, min_age_hours=24.0)
        assert result.deleted_count == 0
        assert result.skipped_recent_count == 1
        assert p.exists()

    def test_non_webp_file_untouched(self, db_session, tmp_path, monkeypatch):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        portraits.mkdir(parents=True)
        txt = portraits / "readme.txt"
        txt.write_bytes(b"do not touch")

        result = media_cleanup.delete_orphans(db_session, min_age_hours=0.0)
        assert result.deleted_count == 0
        assert txt.exists()

    def test_mixed_eligible_recent_and_referenced(
        self, db_session, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        # 1. Referenced (portrait) — must survive
        ref_name = "aaaaaaaabbbbbbbbccccccccdddddddd.webp"
        ref_p = _write(portraits, ref_name, content=b"a" * 100)
        _age(ref_p, 100 * 3600)
        char = Character(
            storyline_id="sl-3",
            name="Ref",
            portrait=f"/media/portraits/{ref_name}",
        )
        db_session.add(char)

        # 2. Expired orphan — must be deleted
        exp_name = "eeeeeeeeffffffff0000000011111111.webp"
        exp_p = _write(portraits, exp_name, content=b"b" * 200)
        _age(exp_p, 48 * 3600)

        # 3. Recent orphan — must be skipped (brand-new mtime)
        rec_name = "2222222233333333444444445555555f.webp"
        rec_p = _write(portraits, rec_name, content=b"c" * 50)

        db_session.commit()

        result = media_cleanup.delete_orphans(db_session, min_age_hours=24.0)
        assert result.deleted_count == 1
        assert result.freed_bytes == 200
        assert result.skipped_recent_count == 1
        assert ref_p.exists()
        assert not exp_p.exists()
        assert rec_p.exists()


# ---------------------------------------------------------------------------
# Route-level tests (via TestClient)
# ---------------------------------------------------------------------------


class TestOrphansRoutes:
    """HTTP route integration — same monkeypatching approach, via ``client``."""

    def test_get_orphans_returns_expected_shape(
        self, client, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        p = _write(portraits, "route0000" * 4 + ".webp", content=b"x" * 300)
        _age(p, 48 * 3600)

        res = client.get("/api/options/media/orphans", params={"min_age_hours": 24})
        assert res.status_code == 200
        body = res.json()

        assert body["orphanCount"] == 1
        assert body["eligibleCount"] == 1
        assert body["totalBytes"] == 300
        assert body["eligibleBytes"] == 300
        assert body["minAgeHours"] == 24.0
        # Per-directory breakdown
        assert body["portraits"]["orphanCount"] == 1
        assert body["scenes"]["orphanCount"] == 0

    def test_post_cleanup_deletes_eligible_returns_shape(
        self, client, tmp_path, monkeypatch
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        p = _write(portraits, "routeaabb" * 4 + ".webp", content=b"y" * 512)
        _age(p, 48 * 3600)

        res = client.post("/api/options/media/cleanup", params={"min_age_hours": 24})
        assert res.status_code == 200
        body = res.json()

        assert body["deletedCount"] == 1
        assert body["freedBytes"] == 512
        assert body["skippedRecentCount"] == 0
        assert not p.exists()

    def test_get_orphans_zero_when_all_referenced(
        self, client, tmp_path, monkeypatch, storyline_id
    ):
        portraits = tmp_path / "portraits"
        scenes = tmp_path / "scenes"
        monkeypatch.setattr(media_cleanup, "_portraits_dir", lambda: portraits)
        monkeypatch.setattr(media_cleanup, "_scenes_dir", lambda: scenes)

        filename = "referencedxx" * 2 + "aabb1122.webp"
        p = _write(portraits, filename)
        _age(p, 100 * 3600)

        # Create a character via the API so it lands in the test DB
        char_res = client.post(
            f"/api/storylines/{storyline_id}/characters",
            json={
                "name": "Tested Hero",
                "portrait": f"/media/portraits/{filename}",
            },
        )
        assert char_res.status_code in (200, 201)

        res = client.get("/api/options/media/orphans", params={"min_age_hours": 1})
        assert res.status_code == 200
        assert res.json()["orphanCount"] == 0
        assert res.json()["eligibleCount"] == 0
