"""Startup preflight.

``run_preflight()`` is what ``python app.py backend`` runs before serving. It:

1. waits for the database and pings Redis,
2. ensures the schema (``create_all``), and
3. seeds the Embergate world if empty.

Bringing the Postgres + Redis **containers** up is *not* done here — that is
owned entirely by ``app.py`` (``ensure_docker_services``), which runs before this
so the stores are already listening. This keeps Docker handling in one place.

It returns a structured ``PreflightReport`` (required checks gate startup; Redis
is advisory). Pure Python so it can be unit-tested against SQLite + a fake Redis.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 — registers all tables on Base.metadata
from app.core.config import Settings, get_settings
from app.core.db import Base, make_engine
from app.core.neo4j import is_enabled as neo4j_enabled
from app.core.neo4j import ping as neo4j_ping
from app.core.qdrant import is_enabled as qdrant_enabled
from app.core.qdrant import ping as qdrant_ping
from app.core.redis import ping as redis_ping
from app.core.seed import seed_if_empty
from app.services.type_registry import seed_builtin_types

log = logging.getLogger(__name__)

# Absolute path to the alembic.ini that ships alongside the backend package.
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    required: bool = True


@dataclass
class PreflightReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.required)

    def add(self, name: str, ok: bool, detail: str = "", required: bool = True) -> bool:
        self.checks.append(Check(name, ok, detail, required))
        return ok


def _db_label(settings: Settings) -> str:
    url = settings.database_url
    if "@" in url:
        scheme, _, rest = url.partition("://")
        _, _, host = rest.partition("@")
        return f"{scheme}://***@{host}"
    return url


def _db_remediation(settings: Settings) -> str:
    return (
        f"Database unreachable at {_db_label(settings)}. Start the services with:\n"
        f"    docker compose -f web/backend/docker-compose.yml up -d\n"
        f"  or point DATABASE_URL at a running Postgres instance."
    )


def add_column_ddl(dialect, table, column) -> str | None:
    """The ``ALTER TABLE … ADD COLUMN`` for one column, or ``None`` if it needs a migration.

    Split out of :func:`_reconcile_additive_columns` so it can be tested without a live
    engine — the bug this guards against was only reachable by starting the real backend
    against Postgres, and 1,200 passing tests said nothing about it.

    The default is rendered by the **dialect's own DDL compiler**, the same one
    ``CreateTable`` uses. The hand-rolled version this replaced str()-ed the clause straight
    into the DDL, so a plain-string ``server_default="medium"`` became ``DEFAULT medium`` — a
    column reference to Postgres, which refuses it with "cannot use column reference in
    DEFAULT expression". Numeric defaults survived only because a bare number is already a
    valid literal, and SQLite accepts either form.

    Returns ``None`` for a non-nullable column with no server default: that cannot be added
    to a populated table without a backfill, so it is reported for a real migration instead.
    """
    ddl = (
        f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
        f"{column.type.compile(dialect)}"
    )
    if column.nullable:
        return ddl
    if column.server_default is None:
        return None
    compiler = dialect.ddl_compiler(dialect, None)
    return f"{ddl} NOT NULL DEFAULT {compiler.get_column_default_string(column)}"


def _reconcile_additive_columns(engine: Engine, report: PreflightReport) -> None:
    """Add model columns that the existing tables are missing (additive only).

    ``create_all`` creates missing *tables* but never ALTERs existing ones, so a
    persistent dev DB drifts behind the models on every new column. This self-heals
    two safe cases with a guarded (idempotent) ``ADD COLUMN``:

    - **nullable** columns → plain ``ADD COLUMN``.
    - **non-nullable columns that carry a ``server_default``** → ``ADD COLUMN … NOT
      NULL DEFAULT <server_default>``, which Postgres backfills existing rows with.

    A non-nullable column with **no** server default can't be added to a populated
    table without a manual backfill, so those are still *reported* for a real
    migration rather than attempted. Full migrations (Alembic) remain authoritative;
    this just keeps a drifted dev DB from breaking at runtime when a migration
    hasn't been applied yet.
    """
    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []
    manual: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all just made it — fully in sync
        db_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in db_columns:
                continue
            ddl = add_column_ddl(engine.dialect, table, column)
            if ddl is None:
                manual.append(f"{table.name}.{column.name}")
                continue
            with engine.begin() as conn:
                conn.execute(text(ddl))
            added.append(f"{table.name}.{column.name}")
    if added:
        report.add("migrate", True, "added columns: " + ", ".join(added), required=False)
    if manual:
        report.add(
            "migrate",
            False,
            "non-nullable columns need a manual migration: " + ", ".join(manual),
            required=False,
        )


def _run_migrations(engine: Engine, report: PreflightReport) -> None:
    """Apply pending Alembic migrations (best-effort, Postgres-only).

    The posture mirrors the project's Neo4j approach: failures are logged and
    recorded in the report but never raise or block startup.

    On SQLite (tests / local dev without Postgres) we skip migrations entirely
    — ``create_all`` + the additive reconciler are sufficient there.

    On Postgres we distinguish two cases:
    - ``alembic_version`` absent → the DB was built by ``create_all``; we stamp
      it at ``head`` so Alembic starts tracking without re-running the baseline.
    - ``alembic_version`` present → Alembic is already tracking; run any pending
      upgrades.
    """
    settings = get_settings()
    if settings.is_sqlite:
        report.add("migrations", True, "skipped (sqlite)", required=False)
        return

    try:
        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig

        cfg = AlembicConfig(str(_ALEMBIC_INI))
        # Always supply the live URL so env.py's fallback is never needed here.
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "alembic"))

        inspector = sa_inspect(engine)
        if inspector.has_table("alembic_version"):
            alembic_command.upgrade(cfg, "head")
            report.add("migrations", True, "upgraded to head", required=False)
        else:
            alembic_command.stamp(cfg, "head")
            report.add("migrations", True, "stamped head (adopted create_all schema)", required=False)
    except Exception as exc:
        msg = str(exc).splitlines()[0]  # keep the report line short
        log.warning("Alembic migration step failed (non-fatal): %s", exc)
        report.add("migrations", False, f"error ({msg})", required=False)


def _wait_for_db(engine: Engine, attempts: int = 30, delay: float = 1.0) -> bool:
    for _ in range(attempts):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            time.sleep(delay)
    return False


def run_preflight(*, seed: bool = True) -> PreflightReport:
    """Check the data stores, ensure the schema, and seed. Idempotent.

    Assumes the containers are already running (``app.py`` brings them up first).
    """
    settings = get_settings()
    report = PreflightReport()

    engine = make_engine(settings)
    # SQLite (tests) connects instantly; give Postgres a moment to come up.
    attempts = 1 if settings.is_sqlite else 30
    if not _wait_for_db(engine, attempts=attempts):
        report.add("database", False, _db_remediation(settings))
        engine.dispose()
        return report
    report.add("database", True, _db_label(settings))

    report.add("redis", redis_ping(), settings.redis_url, required=False)

    # The Story Graph substrate is advisory: graph sync is best-effort and CRUD
    # never blocks on it (see app/core/neo4j.py). Report it, never gate on it.
    if neo4j_enabled():
        up = neo4j_ping()
        report.add("neo4j", up, settings.neo4j_uri, required=False)
        if up:
            # Create the graph's uniqueness/index scaffolding once at startup (§6.6).
            from app.services.graph_writer import ensure_constraints_safe

            ensure_constraints_safe()
    else:
        report.add("neo4j", True, "disabled (NEO4J_URI unset)", required=False)

    # The Hybrid RAG vector store (Qdrant) is advisory too: indexing/retrieval are
    # best-effort and CRUD never blocks on it (see app/core/qdrant.py).
    if qdrant_enabled():
        up = qdrant_ping()
        report.add("qdrant", up, settings.qdrant_url, required=False)
        if up:
            from app.core.qdrant import get_client
            from app.rag import store as rag_store

            try:
                client = get_client()
                if client is not None:
                    rag_store.ensure_collection(client)  # one-time scaffolding
            except Exception:
                pass
    else:
        report.add("qdrant", True, "disabled (QDRANT_URL unset)", required=False)

    Base.metadata.create_all(engine)
    _reconcile_additive_columns(engine, report)
    report.add("schema", True, "tables ensured")

    _run_migrations(engine, report)

    # The built-in Story-Graph type catalogue (§5) must exist on every DB — it is
    # the seed Type Registry, independent of whether the Embergate world is seeded.
    with Session(engine) as session:
        added_types = seed_builtin_types(session)
    report.add(
        "graph types",
        True,
        f"seeded {added_types} built-in types" if added_types else "already present",
        required=False,
    )

    if seed:
        with Session(engine) as session:
            created = seed_if_empty(session)
        report.add("seed", True, "seeded Embergate" if created else "already present")

    engine.dispose()
    return report


def format_report(report: PreflightReport) -> str:
    lines = ["Mytheca preflight:"]
    for c in report.checks:
        mark = "OK " if c.ok else "!! "
        opt = "" if c.required else " (optional)"
        lines.append(f"  [{mark}] {c.name}{opt}: {c.detail}")
    return "\n".join(lines)
