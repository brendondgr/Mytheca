"""Alembic migration smoke tests.

Both tests run entirely on temporary on-disk SQLite databases — no Postgres
required. We deliberately avoid ``compare_metadata`` (Alembic's type/default
comparison produces SQLite false-positives for JSONB-vs-JSON and server
defaults); instead we assert structural completeness: correct table set and
matching column-name sets between the migration path and the ``create_all``
path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect as sa_inspect

# Ensure ``web/backend`` is importable (mirrors the pytest pythonpath setting).
_backend = str(Path(__file__).resolve().parents[4] / "web" / "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

import app.models  # noqa: F401, E402 — populate Base.metadata
from app.core.db import Base  # noqa: E402

_INI = str(Path(__file__).resolve().parents[4] / "web" / "backend" / "alembic.ini")


_ALEMBIC_DIR = str(Path(__file__).resolve().parents[4] / "web" / "backend" / "alembic")


def _make_alembic_cfg(db_path: str) -> AlembicConfig:
    """Return an AlembicConfig pointed at a temp SQLite file.

    We override ``script_location`` with an absolute path so the config works
    regardless of the CWD from which pytest is invoked.
    """
    cfg = AlembicConfig(_INI)
    cfg.set_main_option("script_location", _ALEMBIC_DIR)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


# ---------------------------------------------------------------------------
# Test A — alembic upgrade head builds all expected tables
# ---------------------------------------------------------------------------

def test_upgrade_builds_all_tables(tmp_path):
    """``alembic upgrade head`` creates exactly the tables defined by the models
    plus the ``alembic_version`` tracking table."""
    db_file = str(tmp_path / "alembic_test.db")
    cfg = _make_alembic_cfg(db_file)
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        actual_tables = set(sa_inspect(engine).get_table_names())
    finally:
        engine.dispose()

    expected_tables = set(Base.metadata.tables) | {"alembic_version"}
    assert actual_tables == expected_tables, (
        f"Table mismatch.\n"
        f"  Extra in DB:    {actual_tables - expected_tables}\n"
        f"  Missing in DB:  {expected_tables - actual_tables}"
    )


# ---------------------------------------------------------------------------
# Test B — baseline migration matches create_all (column-name level)
# ---------------------------------------------------------------------------

def test_baseline_columns_match_create_all(tmp_path):
    """The columns produced by ``alembic upgrade head`` match those produced by
    ``Base.metadata.create_all()`` for every model table.

    We compare column-name sets (not types or defaults) to stay robust under
    SQLite's limited type-reflection and Alembic's JSONB-vs-JSON variance.
    """
    # DB-1: built via Alembic migrations.
    migration_db = str(tmp_path / "migration.db")
    cfg = _make_alembic_cfg(migration_db)
    command.upgrade(cfg, "head")
    migration_engine = create_engine(f"sqlite:///{migration_db}")

    # DB-2: built via SQLAlchemy create_all.
    create_all_db = str(tmp_path / "create_all.db")
    create_all_engine = create_engine(f"sqlite:///{create_all_db}")
    Base.metadata.create_all(create_all_engine)

    try:
        migration_inspector = sa_inspect(migration_engine)
        create_all_inspector = sa_inspect(create_all_engine)

        mismatches: list[str] = []
        for table_name in Base.metadata.tables:
            migration_cols = {
                col["name"] for col in migration_inspector.get_columns(table_name)
            }
            create_all_cols = {
                col["name"] for col in create_all_inspector.get_columns(table_name)
            }
            if migration_cols != create_all_cols:
                mismatches.append(
                    f"  {table_name}:\n"
                    f"    extra in migration: {migration_cols - create_all_cols}\n"
                    f"    missing in migration: {create_all_cols - migration_cols}"
                )

        assert not mismatches, "Column-name mismatches between migration and create_all:\n" + "\n".join(mismatches)
    finally:
        migration_engine.dispose()
        create_all_engine.dispose()
