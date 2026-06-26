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
    monkeypatch.setenv("NEO4J_URI", "")  # graph disabled — no network in this unit test
    config.get_settings.cache_clear()
    try:
        report = bootstrap.run_preflight()
        assert report.ok
        names = {c.name for c in report.checks}
        assert {"database", "schema", "seed", "neo4j"} <= names

        # Second run is idempotent — schema + seed already present.
        assert bootstrap.run_preflight().ok
    finally:
        config.get_settings.cache_clear()


def test_preflight_neo4j_is_optional_and_does_not_gate(monkeypatch, tmp_path):
    # Graph configured but unreachable: the check is reported, optional, and never
    # blocks startup (best-effort posture).
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'velora.db'}")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:3349")
    config.get_settings.cache_clear()
    monkeypatch.setattr(bootstrap, "neo4j_ping", lambda: False)  # no real connection
    try:
        report = bootstrap.run_preflight()
        assert report.ok  # still passes — Neo4j is advisory
        neo4j_check = next(c for c in report.checks if c.name == "neo4j")
        assert neo4j_check.required is False
        assert neo4j_check.ok is False
    finally:
        config.get_settings.cache_clear()


def test_preflight_migrations_skipped_on_sqlite(monkeypatch, tmp_path):
    """run_preflight() on SQLite records migrations as skipped (not an error).

    This verifies three things:
    1. The ``migrations`` entry is present in the report.
    2. It is marked optional (required=False), consistent with best-effort posture.
    3. Its detail says "skipped (sqlite)" — the DB URL never sent to Alembic.
    The test is idempotent: a second run produces the same result.
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'velora.db'}")
    monkeypatch.setenv("NEO4J_URI", "")
    config.get_settings.cache_clear()
    try:
        report = bootstrap.run_preflight()
        assert report.ok

        mig = next((c for c in report.checks if c.name == "migrations"), None)
        assert mig is not None, "Expected a 'migrations' check in the report"
        assert mig.ok is True
        assert mig.required is False
        assert "skipped" in mig.detail and "sqlite" in mig.detail

        # Second run is idempotent.
        report2 = bootstrap.run_preflight()
        assert report2.ok
        mig2 = next(c for c in report2.checks if c.name == "migrations")
        assert mig2.ok is True and "skipped" in mig2.detail
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
