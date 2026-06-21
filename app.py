"""Velora root entrypoint.

Exposes the FastAPI application from ``web/backend`` so it can be launched from
the repository root, e.g.::

    uv run uvicorn app:app --reload

The backend package (``app``) lives in ``web/backend``; this shim adds it to the
import path and re-exports the application object. Real backend wiring is built
in the scaffolding phase — see docs/checklist.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the backend package (web/backend/app) importable from the repo root.
_BACKEND = Path(__file__).resolve().parent / "web" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.main import create_app  # noqa: E402  (path set up above)

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
