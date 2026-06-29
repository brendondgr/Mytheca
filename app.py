"""Velora root launcher.

Single entry point for running Velora locally:

    python app.py             # default → BOTH backend + frontend together
    uv run python app.py      # same, inside the uv environment (recommended)
    python app.py all         # explicit "run everything"
    python app.py frontend    # frontend dev server only (npm run dev)
    python app.py backend     # FastAPI API only via uvicorn (web/backend)
    python app.py stop        # forcibly end any running frontend/backend processes

The default runs the backend (with its preflight: Postgres/Redis + schema +
seed) and the Next.js dev server at once, waiting for the backend to report
healthy before starting the frontend so the first API calls don't fail. Ctrl+C
stops both. The frontend-only target needs just Node/npm (no Python deps); the
backend target needs the uv environment (`uv sync`).

Every launch first **forcibly frees its ports** — any process still bound to the
backend (3345) or frontend (3346) port, typically a leftover ``next dev`` /
uvicorn from a previous run, is terminated (SIGTERM, then SIGKILL) so a fresh
start never dies on ``EADDRINUSE``. ``python app.py stop`` does only that and
exits (it leaves the Docker data containers running).

Docker is handled here, in one place: every backend launch first verifies Docker
is installed and its daemon is running, downloads the Postgres + Redis images and
builds the custom Neo4j image (only when missing — visible progress on first run),
and starts the containers defined in ``web/backend/docker-compose.yml``. You never
run ``docker compose`` yourself. Set ``DATABASE_URL`` to a SQLite URL (or export
``VELORA_SKIP_DOCKER=1``) to skip the containers and use an external/embedded
database instead.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "web" / "frontend"
BACKEND = ROOT / "web" / "backend"
COMPOSE_FILE = BACKEND / "docker-compose.yml"

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 3345
FRONTEND_PORT = 3346
HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"

# When run_all has already brought the containers up in the parent process, the
# spawned `app.py backend` skips re-doing it (idempotent, but avoids the noise).
SKIP_DOCKER_ENV = "VELORA_SKIP_DOCKER"


def _load_dotenv() -> None:
    """Best-effort load of the repo-root ``.env`` into ``os.environ``.

    ``app.py`` reads a couple of vars directly (``DATABASE_URL`` for the
    SQLite/Docker decision, ``VELORA_SKIP_DOCKER``), so it must honor ``.env`` the
    same way the backend's pydantic ``Settings`` does. Real environment variables
    win (``setdefault``); pydantic still reads ``.env`` itself, so values stay
    consistent. Deliberately tiny + dependency-free (the frontend path has no deps).
    """
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _daemon_running(docker: str) -> bool:
    """True when the Docker daemon answers (CLI present but daemon down is common)."""
    try:
        return subprocess.run(
            [docker, "info"], capture_output=True, timeout=20
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _images_present(docker: str, compose: list[str]) -> bool:
    """True when every image the compose file references is already pulled.

    Lets us show an explicit download step only on first run, instead of hitting
    the registry on every launch. Image refs come from the compose file itself
    (``compose config --images``) so there's no second copy of the tags here.
    """
    res = subprocess.run(compose + ["config", "--images"], capture_output=True, text=True)
    if res.returncode != 0:
        return False  # older compose / parse issue → fall back to pulling
    images = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    if not images:
        return False
    return all(
        subprocess.run([docker, "image", "inspect", img], capture_output=True).returncode == 0
        for img in images
    )


def ensure_docker_services() -> bool:
    """Verify Docker, download the images, and start Postgres + Redis.

    The single home for Velora's container handling. Returns ``False`` only on a
    hard failure (Docker is present and usable but the pull/up command failed) so
    the caller can abort. Missing Docker / a stopped daemon prints loud, actionable
    guidance and returns ``True`` — the backend preflight's DB-connectivity check
    is the real gate, so external/embedded databases still work.
    """
    if os.environ.get(SKIP_DOCKER_ENV) == "1":
        return True  # parent process already handled it
    if os.environ.get("DATABASE_URL", "").startswith("sqlite"):
        print("DATABASE_URL is SQLite — skipping Docker (no containers needed).")
        return True
    if not COMPOSE_FILE.exists():
        print(f"No compose file at {COMPOSE_FILE} — skipping Docker.", file=sys.stderr)
        return True

    docker = shutil.which("docker")
    if docker is None:
        print(
            "\n⚠  Docker is not installed (no `docker` on PATH).\n"
            "   Velora's Postgres + Redis run as Docker containers. Install Docker:\n"
            "       https://docs.docker.com/get-docker/\n"
            "   …then re-launch. (Or point DATABASE_URL/REDIS_URL at services you\n"
            "   already run, or use a sqlite:// DATABASE_URL, to skip Docker.)\n",
            file=sys.stderr,
        )
        return True  # let the DB check decide; don't block external-DB setups
    if not _daemon_running(docker):
        start_cmd = (
            "open Docker Desktop"
            if sys.platform == "darwin"
            else "start Docker Desktop"
            if os.name == "nt"
            else "run `sudo systemctl start docker`"
        )
        print(
            "\n⚠  Docker is installed but its daemon isn't responding.\n"
            f"   Please {start_cmd}, then re-launch.\n",
            file=sys.stderr,
        )
        return True

    compose = [docker, "compose", "-f", str(COMPOSE_FILE)]
    if not _images_present(docker, compose):
        print(
            "Docker ✓  Downloading the Postgres + Redis + Neo4j images (first run —\n"
            "this can take a few minutes)…"
        )
        # `--ignore-buildable` skips the custom Neo4j service (built below from
        # docker/neo4j/Dockerfile); only the image-only services are pulled.
        if subprocess.run(compose + ["pull", "--ignore-buildable"]).returncode != 0:
            print(
                "Failed to download the container images. Check your network/Docker "
                "and retry.",
                file=sys.stderr,
            )
            return False
    else:
        print("Docker ✓  Container images already present.")

    print("Starting Velora data containers (Postgres + Redis + Neo4j)…")
    # `--build` builds the custom Neo4j image (cached/near-instant when unchanged)
    # before bringing everything up; `--wait` blocks on each service's healthcheck.
    if subprocess.run(compose + ["up", "-d", "--build", "--wait"]).returncode != 0:
        print(
            "Docker could not start the containers — see the output above.",
            file=sys.stderr,
        )
        return False
    print("Data containers healthy ✓\n")
    return True


def _ensure_frontend_deps(npm: str) -> bool:
    """Install node_modules on first run. Returns False on failure."""
    if (FRONTEND / "node_modules").is_dir():
        return True
    print("Installing frontend dependencies (first run)…")
    return subprocess.run([npm, "install"], cwd=FRONTEND).returncode == 0


def run_frontend() -> int:
    """Start the Next.js dev server (`npm run dev`) in web/frontend."""
    npm = shutil.which("npm")
    if npm is None:
        print(
            "npm not found on PATH. Install Node.js (https://nodejs.org) to run the frontend.",
            file=sys.stderr,
        )
        return 1
    if not _ensure_frontend_deps(npm):
        return 1
    _free_port(FRONTEND_PORT, "frontend")  # kill any leftover next dev

    print(f"Starting Velora frontend — npm run dev (http://localhost:{FRONTEND_PORT})\n")
    return subprocess.run([npm, "run", "dev"], cwd=FRONTEND).returncode


def run_backend() -> int:
    """Serve the FastAPI backend (web/backend) with uvicorn + reload."""
    try:
        import uvicorn
    except ModuleNotFoundError:
        print(
            "uvicorn not installed. Run `uv sync`, then `uv run python app.py`.",
            file=sys.stderr,
        )
        return 1

    # Make sure the data containers exist and are running before anything tries
    # to connect. Docker is owned entirely here (see ensure_docker_services).
    if not ensure_docker_services():
        return 1

    # web/backend holds the `app` package (app.main:create_app).
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    # Preflight: check DB/Redis connectivity, ensure the schema, and seed
    # Embergate — the containers are already up from ensure_docker_services.
    from app.core.bootstrap import format_report, run_preflight

    report = run_preflight()
    print(format_report(report))
    if not report.ok:
        print("\nPreflight failed — backend not started.", file=sys.stderr)
        for check in report.checks:
            if not check.ok and check.required:
                print(check.detail, file=sys.stderr)
        return 1

    _free_port(BACKEND_PORT, "backend")  # kill any leftover uvicorn on the port

    print(f"\nStarting Velora backend — uvicorn (http://{BACKEND_HOST}:{BACKEND_PORT})\n")
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=True,
        reload_dirs=[str(BACKEND)],
    )
    return 0


def _port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """True when something is already listening on ``host:port``.

    The Next.js dev server binds ``::`` (all interfaces) and dies with a bare
    ``EADDRINUSE`` when the port is taken — usually a leftover ``next dev`` from a
    previous run. We probe with a quick connect so we can catch that *before*
    bringing the backend all the way up only to tear it straight back down.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _pids_on_port(port: int) -> set[int]:
    """Best-effort set of PIDs listening on ``port`` (cross-platform, no deps).

    Tries ``lsof`` → ``ss`` → ``fuser`` on posix, ``netstat -ano`` on Windows;
    returns an empty set if none can identify the owner.
    """
    pids: set[int] = set()
    if os.name == "posix":
        lsof = shutil.which("lsof")
        if lsof:
            res = subprocess.run(
                [lsof, "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                capture_output=True, text=True,
            )
            pids.update(int(p) for p in res.stdout.split() if p.strip().isdigit())
            if pids:
                return pids
        ss = shutil.which("ss")
        if ss:
            res = subprocess.run(
                [ss, "-ltnpH", f"sport = :{port}"], capture_output=True, text=True
            )
            pids.update(int(m) for m in re.findall(r"pid=(\d+)", res.stdout))
            if pids:
                return pids
        fuser = shutil.which("fuser")
        if fuser:
            res = subprocess.run(
                [fuser, f"{port}/tcp"], capture_output=True, text=True
            )
            pids.update(
                int(tok) for tok in (res.stdout + " " + res.stderr).split()
                if tok.strip().isdigit()
            )
        return pids
    netstat = shutil.which("netstat")  # Windows
    if netstat:
        res = subprocess.run([netstat, "-ano"], capture_output=True, text=True)
        for line in res.stdout.splitlines():
            parts = line.split()
            if (
                len(parts) >= 5
                and parts[0].upper() == "TCP"
                and parts[3].upper() == "LISTENING"
                and parts[1].rsplit(":", 1)[-1] == str(port)
                and parts[-1].isdigit()
            ):
                pids.add(int(parts[-1]))
    return pids


def _kill_pid(pid: int, sig: int) -> None:
    """Send ``sig`` to ``pid`` — its whole process group on posix (so npm/uvicorn
    workers die too), but never our own group (don't kill the launcher)."""
    try:
        if os.name == "posix":
            pgid = os.getpgid(pid)
            if pgid != os.getpgrp():
                os.killpg(pgid, sig)
            else:
                os.kill(pid, sig)
        else:
            os.kill(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _free_port(port: int, label: str) -> None:
    """Forcibly stop whatever is bound to ``host:port`` — SIGTERM, then SIGKILL.

    Velora launches free their ports first so a leftover ``next dev`` / uvicorn
    from a previous run never blocks a fresh start (EADDRINUSE).
    """
    if not _port_in_use(port):
        return
    pids = _pids_on_port(port)
    if not pids:
        print(
            f"⚠  Port {port} ({label}) is in use but the owning process couldn't "
            f"be identified — close it manually if startup fails.",
            file=sys.stderr,
        )
        return
    print(f"Freeing {label} port {port} — stopping process(es) {sorted(pids)}…")
    for pid in pids:
        _kill_pid(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and _port_in_use(port):
        time.sleep(0.2)
    if _port_in_use(port):  # didn't go quietly — escalate
        for pid in _pids_on_port(port):
            _kill_pid(pid, signal.SIGKILL)
        time.sleep(0.4)
    if _port_in_use(port):
        print(
            f"⚠  Port {port} ({label}) is still in use after SIGKILL — a process "
            f"outside this user may own it.",
            file=sys.stderr,
        )


def _wait_for_health(proc: subprocess.Popen, timeout: float = 120.0) -> bool:
    """Poll the backend /health until it answers 200, the child dies, or we time out."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False  # backend exited during preflight/startup
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass  # not up yet
        time.sleep(0.5)
    return False


def _terminate(proc: subprocess.Popen | None) -> None:
    """Stop a child process (and its group, so uvicorn's reloader / npm workers die)."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except (ProcessLookupError, PermissionError):
        return
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError):
            pass


def run_all() -> int:
    """Run the backend and frontend together; stop both on exit/Ctrl+C."""
    npm = shutil.which("npm")
    if npm is None:
        print(
            "npm not found on PATH. Install Node.js (https://nodejs.org) to run Velora.",
            file=sys.stderr,
        )
        return 1
    if not _ensure_frontend_deps(npm):
        return 1
    # Forcibly free both ports up front so a leftover `next dev` / uvicorn from a
    # previous run can't block this start (the backend child rebinds 3345 cleanly,
    # and freeing now means the health-wait below never latches onto a stale API).
    _free_port(BACKEND_PORT, "backend")
    _free_port(FRONTEND_PORT, "frontend")

    # Bring Docker up here in the foreground (visible first-run download) so the
    # backend subprocess starts against ready containers — and isn't racing the
    # health-wait below while a multi-minute image pull is in flight.
    if not ensure_docker_services():
        return 1

    new_session = os.name == "posix"
    backend: subprocess.Popen | None = None
    frontend: subprocess.Popen | None = None
    try:
        print("Starting Velora backend (preflight + uvicorn)…\n")
        backend = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py"), "backend"],
            start_new_session=new_session,
            env={**os.environ, SKIP_DOCKER_ENV: "1"},  # parent already did Docker
        )
        if not _wait_for_health(backend):
            print(
                "\nBackend did not become healthy — not starting the frontend. "
                "See the backend output above (is Docker/Postgres available?).",
                file=sys.stderr,
            )
            return 1

        print(
            f"\nBackend healthy ✓  Starting frontend — npm run dev "
            f"(http://localhost:{FRONTEND_PORT})\n"
        )
        frontend = subprocess.Popen(
            [npm, "run", "dev"],
            cwd=FRONTEND,
            start_new_session=new_session,
        )

        # Wait until either side exits, then tear the other down.
        while True:
            if backend.poll() is not None:
                print("\nBackend exited — shutting down the frontend.", file=sys.stderr)
                return backend.returncode or 1
            if frontend.poll() is not None:
                print("\nFrontend exited — shutting down the backend.", file=sys.stderr)
                return frontend.returncode or 0
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nShutting down Velora…")
        return 0
    finally:
        _terminate(frontend)
        _terminate(backend)


def stop_all() -> int:
    """Forcibly end any running Velora frontend/backend processes (free both ports).

    Leaves the Docker data containers running — this only stops the app processes
    bound to the backend (3345) and frontend (3346) ports.
    """
    print("Stopping any running Velora frontend/backend processes…")
    busy = _port_in_use(BACKEND_PORT) or _port_in_use(FRONTEND_PORT)
    _free_port(BACKEND_PORT, "backend")
    _free_port(FRONTEND_PORT, "frontend")
    print("Nothing was running." if not busy else "Done.")
    return 0


def main(argv: list[str]) -> int:
    _load_dotenv()  # so DATABASE_URL / VELORA_SKIP_DOCKER from .env are honored here
    target = (argv[1] if len(argv) > 1 else "all").lower()
    if target in {"all", "both", ""}:
        return run_all()
    if target in {"frontend", "fe", "dev", "web", "ui"}:
        return run_frontend()
    if target in {"backend", "be", "api"}:
        return run_backend()
    if target in {"stop", "kill", "down"}:
        return stop_all()
    print(
        f"Unknown target {target!r}. Usage: python app.py [all|frontend|backend|stop]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except KeyboardInterrupt:
        pass
