"""Velora root launcher.

Single entry point for running Velora locally:

    python app.py             # default → frontend dev server (npm run dev)
    uv run python app.py      # same, inside the uv environment
    python app.py frontend    # explicit
    python app.py backend     # FastAPI API via uvicorn (web/backend)

The frontend launcher only needs Node/npm (no Python deps), so it works even
before `uv sync`. The backend target imports the FastAPI app factory from
web/backend and serves it with reload.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "web" / "frontend"
BACKEND = ROOT / "web" / "backend"


def run_frontend() -> int:
    """Start the Next.js dev server (`npm run dev`) in web/frontend."""
    npm = shutil.which("npm")
    if npm is None:
        print(
            "npm not found on PATH. Install Node.js (https://nodejs.org) to run the frontend.",
            file=sys.stderr,
        )
        return 1

    if not (FRONTEND / "node_modules").is_dir():
        print("Installing frontend dependencies (first run)…")
        result = subprocess.run([npm, "install"], cwd=FRONTEND)
        if result.returncode != 0:
            return result.returncode

    print("Starting Velora frontend — npm run dev (http://localhost:3000)\n")
    return subprocess.run([npm, "run", "dev"], cwd=FRONTEND).returncode


def run_backend() -> int:
    """Serve the FastAPI backend (web/backend) with uvicorn + reload."""
    try:
        import uvicorn
    except ModuleNotFoundError:
        print(
            "uvicorn not installed. Run `uv sync`, then `uv run python app.py backend`.",
            file=sys.stderr,
        )
        return 1

    # web/backend holds the `app` package (app.main:create_app).
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    print("Starting Velora backend — uvicorn (http://127.0.0.1:8000)\n")
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(BACKEND)],
    )
    return 0


def main(argv: list[str]) -> int:
    target = (argv[1] if len(argv) > 1 else "frontend").lower()
    if target in {"frontend", "fe", "dev", "web", "ui"}:
        return run_frontend()
    if target in {"backend", "be", "api"}:
        return run_backend()
    print(
        f"Unknown target {target!r}. Usage: python app.py [frontend|backend]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except KeyboardInterrupt:
        pass
