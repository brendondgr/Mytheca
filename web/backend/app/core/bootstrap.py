"""Startup preflight.

``run_preflight()`` is what ``python app.py backend`` runs before serving. It:

1. optionally brings up Postgres + Redis via the local ``docker-compose.yml``
   (only if Docker is present — non-fatal otherwise),
2. waits for the database and pings Redis,
3. ensures the schema (``create_all``), and
4. seeds the Embergate world if empty.

It returns a structured ``PreflightReport`` (required checks gate startup; Redis
is advisory). Pure Python so it can be unit-tested against SQLite + a fake Redis.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 — registers all tables on Base.metadata
from app.core.config import Settings, get_settings
from app.core.db import Base, make_engine
from app.core.redis import ping as redis_ping
from app.core.seed import seed_if_empty

COMPOSE_FILE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


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


def _maybe_start_services(report: PreflightReport) -> None:
    docker = shutil.which("docker")
    if docker is None or not COMPOSE_FILE.exists():
        report.add(
            "docker",
            True,
            "skipped (docker or compose file not found) — using external services",
            required=False,
        )
        return
    try:
        # --wait blocks until the healthchecks pass, so the DB is ready by the
        # time we probe it. Generous timeout for a first-run image pull.
        result = subprocess.run(
            [docker, "compose", "-f", str(COMPOSE_FILE), "up", "-d", "--wait"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        ok = result.returncode == 0
        detail = "compose up -d --wait" if ok else (result.stderr.strip()[:200] or "compose failed")
        report.add("docker", ok, detail, required=False)
    except Exception as exc:  # pragma: no cover - environment dependent
        report.add("docker", False, f"compose error: {exc}", required=False)


def _wait_for_db(engine: Engine, attempts: int = 30, delay: float = 1.0) -> bool:
    for _ in range(attempts):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            time.sleep(delay)
    return False


def run_preflight(*, start_services: bool = True, seed: bool = True) -> PreflightReport:
    """Bring up + check the data stores, ensure schema, and seed. Idempotent."""
    settings = get_settings()
    report = PreflightReport()

    if start_services and not settings.is_sqlite:
        _maybe_start_services(report)

    engine = make_engine(settings)
    # SQLite (tests) connects instantly; give Postgres a moment to come up.
    attempts = 1 if settings.is_sqlite else 30
    if not _wait_for_db(engine, attempts=attempts):
        report.add("database", False, _db_remediation(settings))
        engine.dispose()
        return report
    report.add("database", True, _db_label(settings))

    report.add("redis", redis_ping(), settings.redis_url, required=False)

    Base.metadata.create_all(engine)
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
