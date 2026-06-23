"""Velora root launcher.

Single entry point for running Velora locally:

    python app.py             # default → BOTH backend + frontend together
    uv run python app.py      # same, inside the uv environment (recommended)
    python app.py all         # explicit "run everything"
    python app.py frontend    # frontend dev server only (npm run dev)
    python app.py backend     # FastAPI API only via uvicorn (web/backend)

The default runs the backend (with its preflight: Postgres/Redis + schema +
seed) and the Next.js dev server at once, waiting for the backend to report
healthy before starting the frontend so the first API calls don't fail. Ctrl+C
stops both. The frontend-only target needs just Node/npm (no Python deps); the
backend target needs the uv environment (`uv sync`).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "web" / "frontend"
BACKEND = ROOT / "web" / "backend"

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 3345
FRONTEND_PORT = 3346
HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"


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

    # web/backend holds the `app` package (app.main:create_app).
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))

    # Preflight: bring up Postgres/Redis (via docker compose if available), check
    # connectivity, ensure the schema, and seed Embergate — before serving.
    from app.core.bootstrap import format_report, run_preflight

    report = run_preflight()
    print(format_report(report))
    if not report.ok:
        print("\nPreflight failed — backend not started.", file=sys.stderr)
        for check in report.checks:
            if not check.ok and check.required:
                print(check.detail, file=sys.stderr)
        return 1

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

    new_session = os.name == "posix"
    backend: subprocess.Popen | None = None
    frontend: subprocess.Popen | None = None
    try:
        print("Starting Velora backend (preflight + uvicorn)…\n")
        backend = subprocess.Popen(
            [sys.executable, str(ROOT / "app.py"), "backend"],
            start_new_session=new_session,
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


def main(argv: list[str]) -> int:
    target = (argv[1] if len(argv) > 1 else "all").lower()
    if target in {"all", "both", ""}:
        return run_all()
    if target in {"frontend", "fe", "dev", "web", "ui"}:
        return run_frontend()
    if target in {"backend", "be", "api"}:
        return run_backend()
    print(
        f"Unknown target {target!r}. Usage: python app.py [all|frontend|backend]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except KeyboardInterrupt:
        pass
