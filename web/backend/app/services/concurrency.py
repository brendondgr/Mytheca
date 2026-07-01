"""Bounded concurrent execution for off-hot-path / independent turn work.

vLLM allows parallel inference (turn-loop plan D-C), so independent units — universal
reflection for the whole cast, the cascade disposition refresh, later batched work —
run **concurrently** via a small thread pool capped by ``TURN_MAX_CONCURRENCY``.
**Sequential speech stays sequential** (a later speaker reacts to an earlier one); this
helper is only for work whose units genuinely do not depend on one another.

Best-effort: a unit that raises yields ``None`` in its slot (a failed background unit
never fails the turn), and results are returned **in input order**.

Each thunk must be self-contained — it must **not** touch the request's SQLAlchemy
``Session`` (it is not thread-safe). Resolve shared state (the LLM connection, plain
context values) on the calling thread and close over the results.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from app.core.config import get_settings

logger = logging.getLogger("velora.turn")

T = TypeVar("T")


def _safe(thunk: Callable[[], T]) -> T | None:
    try:
        return thunk()
    except Exception as exc:  # pragma: no cover - defensive; a unit never fails the turn
        logger.debug("concurrency: unit failed: %s", exc)
        return None


def run_all(
    thunks: Sequence[Callable[[], T]],
    *,
    max_workers: int | None = None,
) -> list[T | None]:
    """Run each thunk concurrently (bounded), returning results in input order.

    Empty input → ``[]``. A single unit (or ``TURN_MAX_CONCURRENCY==1``) runs inline
    without a pool. A unit that raises resolves to ``None`` in its slot.
    """
    items = list(thunks)
    if not items:
        return []
    cap = max_workers if max_workers is not None else get_settings().turn_max_concurrency
    workers = max(1, min(cap, len(items)))
    if workers == 1:
        return [_safe(t) for t in items]

    results: list[T | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="velora-turn") as pool:
        futures = {pool.submit(_safe, thunk): i for i, thunk in enumerate(items)}
        for future, index in futures.items():
            results[index] = future.result()  # _safe never raises
    return results


def submit_background(job: Callable[[], None]) -> None:
    """Run ``job`` off the request path (fire-and-forget), best-effort.

    Used for the read-time finalize work (reflection interlude) so the HTTP stream can
    close the instant the last visible event is yielded — the player never waits on the
    next-turn interior refresh (turn-loop plan §P11). It runs on a daemon thread **only**
    when ``TURN_ASYNC_FINALIZE`` is on and the backend is not on SQLite; otherwise it
    runs **inline** (the default — deterministic for the offline test/dev path, and an
    in-memory SQLite has no independent connection to hand a worker thread).

    The job must be self-contained (no request Session, no request-bound ORM objects);
    turn-loop callers pre-resolve every input on the calling thread.
    """
    settings = get_settings()
    if not settings.turn_async_finalize or settings.is_sqlite:
        _safe(job)
        return
    threading.Thread(target=lambda: _safe(job), name="velora-finalize", daemon=True).start()
