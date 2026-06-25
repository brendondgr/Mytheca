"""Preflight passes on SQLite and reports a clear failure when the DB is down."""

from __future__ import annotations

from app.core import bootstrap, config


def test_preflight_on_sqlite_seeds_and_passes(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'velora.db'}")
    config.get_settings.cache_clear()
    try:
        report = bootstrap.run_preflight()
        assert report.ok
        names = {c.name for c in report.checks}
        assert {"database", "schema", "seed"} <= names

        # Second run is idempotent — schema + seed already present.
        assert bootstrap.run_preflight().ok
    finally:
        config.get_settings.cache_clear()


def test_preflight_reports_db_failure(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:1/none")
    config.get_settings.cache_clear()
    monkeypatch.setattr(bootstrap, "_wait_for_db", lambda *a, **k: False)
    try:
        report = bootstrap.run_preflight()
        assert report.ok is False
        database = next(c for c in report.checks if c.name == "database")
        assert database.ok is False
        assert "docker compose" in database.detail  # remediation guidance
    finally:
        config.get_settings.cache_clear()
