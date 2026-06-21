"""FastAPI application factory.

This is an initialization stub: it creates the app and a health check so the
backend is runnable after ``uv sync``. Routes, agents, services, persistence,
and the event stream are added in the scaffolding phase (see docs/checklist.md
and docs/api-contract.md).
"""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build and return the Velora FastAPI application."""
    app = FastAPI(title="Velora", version="0.0.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # TODO(scaffolding): register routers from app.routes (auth, characters,
    # scenes, play, stream, graph), configure CORS, and wire core services.

    return app
