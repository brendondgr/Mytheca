"""FastAPI application factory.

Builds the Velora API: CORS for the frontend origin, the contract error envelope,
a health check, and the CRUD routers under the ``/api`` prefix. The multi-agent
brain and event stream are added in later phases (see docs/checklist.md).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine
from app.core.errors import register_error_handlers
from app.routes import characters, scenarios, settings, stats, storylines

logger = logging.getLogger("velora")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Verify the DB connection on startup (schema/seed happen in preflight)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection OK.")
    except Exception as exc:  # pragma: no cover - exercised by the live app
        logger.warning("Database connection check failed: %s", exc)
    yield


def create_app() -> FastAPI:
    """Build and return the Velora FastAPI application."""
    config = get_settings()
    app = FastAPI(title="Velora", version="0.0.0", lifespan=lifespan)

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
