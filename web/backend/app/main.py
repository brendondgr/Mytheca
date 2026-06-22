"""FastAPI application factory.

Builds the Velora API: CORS for the frontend origin, the contract error envelope,
a health check, and the CRUD routers under the ``/api`` prefix. The multi-agent
brain and event stream are added in later phases (see docs/checklist.md).
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.routes import characters, scenarios, settings, stats, storylines


def create_app() -> FastAPI:
    """Build and return the Velora FastAPI application."""
    config = get_settings()
    app = FastAPI(title="Velora", version="0.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    api = APIRouter(prefix="/api")
    for module in (storylines, characters, settings, scenarios, stats):
        api.include_router(module.router)
    app.include_router(api)

    return app
