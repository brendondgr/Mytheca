"""Preflight passes on SQLite and reports a clear failure when the DB is down."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.core import bootstrap, config


def test_reconcile_adds_missing_nullable_column():
    # An "old" storylines table predating the nullable world_primer column.
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE storylines (id VARCHAR PRIMARY KEY, title VARCHAR, "
                "genre VARCHAR, tagline VARCHAR, premise TEXT, symbol VARCHAR, "
                "symbol_color VARCHAR, position INTEGER)"
            )
        )

    report = bootstrap.PreflightReport()
    bootstrap._reconcile_additive_columns(engine, report)

    columns = {c["name"] for c in inspect(engine).get_columns("storylines")}
    assert "world_primer" in columns  # auto-added
    migrate = next(c for c in report.checks if c.name == "migrate")
    assert migrate.ok and "storylines.world_primer" in migrate.detail
    engine.dispose()


def test_reconcile_flags_nonnullable_column_for_manual_migration():
    # Missing the NOT NULL `symbol` column — can't be auto-added on a populated
    # table without a default, so it must be reported, not attempted.
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE storylines (id VARCHAR PRIMARY KEY, title VARCHAR, "
                "genre VARCHAR, tagline VARCHAR, premise TEXT, world_primer TEXT, "
                "symbol_color VARCHAR, position INTEGER)"
            )
        )

    report = bootstrap.PreflightReport()
    bootstrap._reconcile_additive_columns(engine, report)

    columns = {c["name"] for c in inspect(engine).get_columns("storylines")}
    assert "symbol" not in columns  # not auto-added
    manual = next(c for c in report.checks if c.name == "migrate" and not c.ok)
    assert "storylines.symbol" in manual.detail
    engine.dispose()


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
