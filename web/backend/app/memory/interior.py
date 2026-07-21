"""Per-character interior state (Redis, best-effort).

The read-time reflection interlude (turn-loop plan §10 / §P9) writes each character's
*interior state* here after a turn: a short, **overridable disposition** (their current
stance/intent), a one-line retrospective (how the beat landed from their POV), and —
when the turn offered a fork — a **branch-keyed** anticipated stance per option. Band-1
assembly reads it back on the next turn so a character re-enters the scene already
carrying the shift, instead of re-deriving it from the transcript each time.

It mirrors the recent-turn :mod:`app.memory.buffer` posture: one JSON value per
character under ``interior:{session_id}:{character_id}`` with a day TTL; when Redis is
unset/unreachable every helper no-ops (writes) or returns ``None`` (reads), so the turn
still runs. Interior state is deliberately **volatile** — it is never written to the
Story Graph (only durable consequences are; see ``services.turn_writer``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

import redis as redis_lib

from app.core.config import get_settings
from app.core.redis import get_redis

logger = logging.getLogger("mytheca.memory")

_KEY = "interior:{session_id}:{character_id}"
# Interior state outlives a turn but not a session; expire stale keys after a day.
_TTL_SECONDS = 60 * 60 * 24


@dataclass
class InteriorRecord:
    """One character's post-turn interior state (read back into the next turn)."""

    character_id: str
    disposition: str = ""  # mutable current stance/intent — overrides the previous one
    retrospective: str = ""  # one line: how the beat landed, this character's POV
    # Anticipated stance per offered branch, keyed by the branch's outcome tag.
    branch_dispositions: dict[str, str] = field(default_factory=dict)
    seq: int = 0  # the turn seq this was computed after (staleness / ordering)


def _redis() -> redis_lib.Redis | None:
    """Return the Redis client, or ``None`` when disabled/unreachable (best-effort)."""
    if not get_settings().redis_configured:
        return None
    try:
        return get_redis()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("interior: redis unavailable: %s", exc)
        return None


def set_interior(session_id: str, character_id: str, record: InteriorRecord) -> None:
    """Persist a character's interior state (overwrites the previous), best-effort."""
    client = _redis()
    if client is None:
        return
    key = _KEY.format(session_id=session_id, character_id=character_id)
    try:
        client.set(key, json.dumps(asdict(record)), ex=_TTL_SECONDS)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("interior.set_interior failed: %s", exc)


def get_interior(session_id: str, character_id: str) -> InteriorRecord | None:
    """Return a character's interior state, or ``None`` when absent/unavailable."""
    client = _redis()
    if client is None:
        return None
    key = _KEY.format(session_id=session_id, character_id=character_id)
    try:
        raw = client.get(key)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("interior.get_interior failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return InteriorRecord(
        character_id=str(data.get("character_id", character_id)),
        disposition=str(data.get("disposition", "")),
        retrospective=str(data.get("retrospective", "")),
        branch_dispositions={
            str(k): str(v) for k, v in (data.get("branch_dispositions") or {}).items()
        },
        seq=int(data.get("seq", 0) or 0),
    )
