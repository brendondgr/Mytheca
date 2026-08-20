"""Recent-turn buffer (Redis, best-effort).

The volatile recent-turn buffer for a play session: the last few beats (player,
narrator, and character lines) that Band-1 assembly reads back for short-horizon
continuity and in-voice anchors (the turn-loop plan §3 Step 1/3). It mirrors the
Neo4j/Qdrant best-effort posture — when Redis is unset or unreachable, every
helper no-ops (writes) or returns empty (reads), so the turn still runs and
persists to Postgres.

Stored as a capped Redis list ``buffer:{session_id}`` (newest first via ``LPUSH`` +
``LTRIM``); :func:`recent_turns` returns it oldest→newest for prompt assembly, and
:func:`anchored_turns` returns a window whose **start moves in blocks** so the rendered
transcript keeps a byte-stable prefix from turn to turn (see its docstring).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis as redis_lib

from app.core.config import get_settings
from app.core.redis import get_redis

logger = logging.getLogger("mytheca.memory")

_KEY = "buffer:{session_id}"
# Buffer entries outlive a turn but not a session; expire stale keys after a day.
_TTL_SECONDS = 60 * 60 * 24


def _redis() -> redis_lib.Redis | None:
    """Return the Redis client, or ``None`` when disabled/unreachable (best-effort)."""
    if not get_settings().redis_configured:
        return None
    try:
        return get_redis()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("buffer: redis unavailable: %s", exc)
        return None


def push_turn(
    session_id: str,
    role: str,
    text: str,
    *,
    character_id: str | None = None,
) -> None:
    """Append one beat to the session buffer (newest first), best-effort.

    ``role`` ∈ ``player | narrator | character``; ``character_id`` is set for
    character lines so in-voice anchors can be pulled per speaker later.
    """
    client = _redis()
    if client is None:
        return
    entry = json.dumps({"role": role, "text": text, "characterId": character_id})
    key = _KEY.format(session_id=session_id)
    cap = max(1, get_settings().turn_buffer_size)
    try:
        client.lpush(key, entry)
        client.ltrim(key, 0, cap - 1)
        client.expire(key, _TTL_SECONDS)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("buffer.push_turn failed: %s", exc)


def recent_turns(session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Return the last beats oldest→newest, best-effort (``[]`` when unavailable)."""
    client = _redis()
    if client is None:
        return []
    cap = limit if limit is not None else max(1, get_settings().turn_buffer_size)
    key = _KEY.format(session_id=session_id)
    try:
        raw = client.lrange(key, 0, cap - 1)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("buffer.recent_turns failed: %s", exc)
        return []
    beats: list[dict[str, Any]] = []
    for item in raw:
        try:
            beats.append(json.loads(item))
        except (ValueError, TypeError):
            continue
    beats.reverse()  # stored newest-first; return chronological
    return beats


def anchored_turns(
    session_id: str,
    window: int,
    block: int,
) -> list[dict[str, Any]]:
    """Return a recent-beat window whose **start advances in blocks of ``block``**.

    A plain "last N beats" window is the quiet killer of prompt-cache reuse. Once a scene
    is longer than the window, every new beat drops the oldest one, which changes the
    first token of the rendered transcript — and a prefix cache matches from the first
    token, so the whole transcript has to be re-read even though it only grew at the end.

    Anchoring the start to a multiple of ``block`` means the window's first beat stays put
    for ``block`` turns at a time: the transcript grows at the tail (fully reusable) and
    re-anchors once every ``block`` beats, paying one cold prefill instead of every turn.
    The returned window therefore holds between ``window`` and ``window + block`` beats.

    Falls back to plain :func:`recent_turns` behaviour when the buffer holds no more than
    the window — there is nothing to slide yet — and when Redis is unavailable.
    """
    client = _redis()
    if client is None:
        return []
    window = max(1, window)
    block = max(1, block)
    key = _KEY.format(session_id=session_id)
    try:
        total = int(client.llen(key))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("buffer.anchored_turns llen failed: %s", exc)
        return recent_turns(session_id, limit=window)
    if total <= window:
        return recent_turns(session_id, limit=total or window)
    # ``start`` counts from the OLDEST beat; quantising it is what holds the prefix still.
    start = ((total - window) // block) * block
    return recent_turns(session_id, limit=total - start)


def clear(session_id: str) -> None:
    """Drop a session's buffer, best-effort."""
    client = _redis()
    if client is None:
        return
    try:
        client.delete(_KEY.format(session_id=session_id))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("buffer.clear failed: %s", exc)
