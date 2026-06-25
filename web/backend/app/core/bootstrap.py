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

import time
from dataclasses import dataclass, field

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 — registers all tables on Base.metadata
from app.core.config import Settings, get_settings
from app.core.db import Base, make_engine
from app.core.neo4j import is_enabled as neo4j_enabled
from app.core.neo4j import ping as neo4j_ping
from app.core.redis import ping as redis_ping
from app.core.seed import seed_if_empty


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


def _reconcile_additive_columns(engine: Engine, report: PreflightReport) -> None:
    """Add model columns that the existing tables are missing (additive only).

    ``create_all`` creates missing *tables* but never ALTERs existing ones, so a
    persistent dev DB drifts behind the models on every new column. This self-heals
    the safe case — **nullable** columns — with a plain ``ADD COLUMN`` (each guarded
    by an inspector check, so it's idempotent). Non-nullable additions on a
    populated table can't be done safely without a default/backfill, so those are
    *reported* for a real migration rather than attempted. Full migrations (Alembic)
    remain the standing follow-up; this just keeps day-to-day dev from breaking.
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
            if not column.nullable:
                manual.append(f"{table.name}.{column.name}")
                continue
            col_type = column.type.compile(engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
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
        report.add("neo4j", neo4j_ping(), settings.neo4j_uri, required=False)
    else:
        report.add("neo4j", True, "disabled (NEO4J_URI unset)", required=False)

    Base.metadata.create_all(engine)
    _reconcile_additive_columns(engine, report)
    report.add("schema", True, "tables ensured")

    if seed:
        with Session(engine) as session:
            created = seed_if_empty(session)
        report.add("seed", True, "seeded Embergate" if created else "already present")

    engine.dispose()
    return report


def format_report(report: PreflightReport) -> str:
    lines = ["Velora preflight:"]
    for c in report.checks:
        mark = "OK " if c.ok else "!! "
        opt = "" if c.required else " (optional)"
        lines.append(f"  [{mark}] {c.name}{opt}: {c.detail}")
    return "\n".join(lines)
