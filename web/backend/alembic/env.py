"""Alembic migration environment.

Supports both offline (SQL script generation) and online (direct DB connection)
modes. The database URL is always pulled from app.core.config so no credentials
live in alembic.ini.
"""

from __future__ import annotations

import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Ensure ``web/backend`` is on sys.path so ``import app.*`` resolves correctly
# regardless of the CWD from which alembic is invoked.
# ---------------------------------------------------------------------------
_backend_dir = str(Path(__file__).resolve().parents[1])
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# ---------------------------------------------------------------------------
# Import models to populate Base.metadata, then expose it to Alembic.
# ---------------------------------------------------------------------------
import app.models  # noqa: F401, E402 — side-effect: registers all tables
from app.core.db import Base  # noqa: E402
from app.core.config import get_settings  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to the .ini file values.
# ---------------------------------------------------------------------------
config = context.config

# Use the URL already set on the config (e.g. by the test harness or CLI
# ``-x sqlalchemy.url=…``), falling back to the application settings.
# This allows callers to inject a test URL without it being overridden here.
_configured_url = config.get_main_option("sqlalchemy.url") or ""
if not _configured_url:
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Logging — set up from the ini's [loggers] / [handlers] sections if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout/file).

    Alembic does not need a live connection; it emits SQL that can be
    reviewed and executed manually.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
