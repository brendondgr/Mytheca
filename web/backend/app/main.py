"""FastAPI application factory.

Builds the Velora API: CORS for the frontend origin, the contract error envelope,
a health check, and the CRUD routers under the ``/api`` prefix. The multi-agent
brain and event stream are added in later phases (see docs/checklist.md).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.core.errors import register_error_handlers
from app.routes import (
    characters,
    context_documents,
    graph,
    options,
    rag,
    scenarios,
    settings,
    stats,
    storylines,
)
from app.services import llm_backend

logger = logging.getLogger("velora")


def _refresh_backend_once() -> None:
    """Re-probe the configured LLM endpoint and refresh the detection cache.

    Best-effort and synchronous (run in a thread by the poller): any failure is
    swallowed so a down/misconfigured endpoint never disturbs the app.
    """
    try:
        with SessionLocal() as db:
            llm_backend.refresh_for_config(db)
    except Exception as exc:  # pragma: no cover - defensive; never crash the poller
        logger.debug("LLM backend detection refresh failed: %s", exc)


async def _poll_backend(stop: asyncio.Event) -> None:
    """Periodically refresh the inference-engine detection so the app adapts.

    Interval is ``LLM_BACKEND_POLL_SECONDS``; the loop wakes early on shutdown via
    ``stop``. Probing runs in a worker thread (the detector uses a sync HTTP client).
    """
    interval = max(5, get_settings().llm_backend_poll_seconds)
    while not stop.is_set():
        await asyncio.to_thread(_refresh_backend_once)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Verify the DB connection on startup and run the engine-detection poller.

    The poller keeps the vLLM/llama.cpp detection fresh so the backend-controlled
    reasoning budget tracks engine swaps. It is **skipped under SQLite** (the test /
    offline profile) so the suite never touches the network.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection OK.")
    except Exception as exc:  # pragma: no cover - exercised by the live app
        logger.warning("Database connection check failed: %s", exc)

    stop = asyncio.Event()
    poller: asyncio.Task[None] | None = None
    if not get_settings().is_sqlite:
        poller = asyncio.create_task(_poll_backend(stop))

    try:
        yield
    finally:
        if poller is not None:
            stop.set()
            poller.cancel()
            try:
                await poller
            except (asyncio.CancelledError, Exception):  # pragma: no cover - shutdown
                pass


def create_app() -> FastAPI:
    """Build and return the Velora FastAPI application."""
    config = get_settings()
    app = FastAPI(title="Velora", version="0.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    api = APIRouter(prefix="/api")
    for module in (
        storylines,
        characters,
        context_documents,
        settings,
        scenarios,
        stats,
        options,
        graph,
        rag,
    ):
        api.include_router(module.router)
    app.include_router(api)

    # Generated media (character portraits) served read-only. ``check_dir=False``
    # so the app boots before the directory is first written; it is created lazily
    # by the portrait service on the first generation.
    app.mount("/media", StaticFiles(directory=str(config.media_dir), check_dir=False), name="media")

    return app
