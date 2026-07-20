"""Scene presence — who is in the scene, derived from the event log.

Mytheca's cast (``Scenario.cast_ids``) is static, but a scene is *live*: a character can
die, be knocked out, or leave. This module gives the turn loop a first-class notion of
**presence** without a new table or a Redis dependency — presence is the fold of the
session's ``character_status_change`` events (latest per character wins, default
``present``). That store is durable (Postgres/SQLite), survives reload, works in tests
with no Redis, and rehydrates through the same reducer pipeline the transcript uses.

Only ``present`` characters are **selectable** (the planner may pick them to speak); every
other status keeps the character in the cast for context/reference but out of the speaking
pool — which is what stops a dead or departed character from continuing to chat.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event
from app.models.stat import StatDefinition
from app.schemas.base import PresenceStatus

# Every valid runtime status and the single selectable one.
STATUSES: frozenset[str] = frozenset(
    ("present", "unconscious", "departed", "left", "dead")
)
SELECTABLE: frozenset[str] = frozenset(("present",))
DEFAULT_STATUS = "present"
# Terminal — a character can only leave this status by an explicit player override (undo).
_TERMINAL: frozenset[str] = frozenset(("dead",))
# The stat key whose exhaustion knocks a character out deterministically.
_VITAL_KEY = "health"


def normalize_status(raw: object) -> str | None:
    """Return a canonical status for a caller-supplied value, or ``None`` if unknown."""
    status = str(raw or "").strip().lower()
    return status if status in STATUSES else None


def is_selectable(status: str) -> bool:
    """True when a character with this status may be chosen to take a beat."""
    return status in SELECTABLE


def is_terminal(status: str) -> bool:
    """True for a status the engine must never auto-transition out of (``dead``)."""
    return status in _TERMINAL


def can_transition(current: str, target: str) -> bool:
    """Whether an **engine/character-driven** presence change is legal.

    Rejects a no-op (same status), leaving a terminal status (``dead`` — only a manual
    player override may resurrect), and any unknown target. A manual player override goes
    through the endpoint and is intentionally NOT bound by this (the player has final say).
    """
    if target not in STATUSES or current == target:
        return False
    return current not in _TERMINAL


def vital_status_for(definition: StatDefinition, value: int) -> str | None:
    """Deterministic presence trigger from a clamped stat change.

    A ``health``-keyed stat hitting its floor knocks the character ``unconscious`` (the
    reversible, body-stays lane — never auto-``dead``; a terminal death is a narrative
    or player call). Returns ``None`` for any other stat or a non-floored value.
    """
    if definition.key != _VITAL_KEY:
        return None
    return "unconscious" if value <= definition.min else None


def current_presence(db: Session, session_id: str) -> dict[str, str]:
    """Fold the session's ``character_status_change`` events into a presence map.

    Latest event per character wins (ordered by ``seq``); characters with no status event
    are simply absent from the map and default to ``present`` at the read site. Best-effort
    on malformed rows — a bad payload is skipped, never fatal to a turn.
    """
    rows = db.scalars(
        select(Event)
        .where(
            Event.session_id == session_id,
            Event.type == "character_status_change",
        )
        .order_by(Event.seq)
    )
    presence: dict[str, str] = {}
    for row in rows:
        data = row.data or {}
        cid = str(data.get("characterId") or data.get("character_id") or "")
        status = normalize_status(data.get("status"))
        if cid and status:
            presence[cid] = status
    return presence


def status_for(presence: dict[str, str], character_id: str) -> PresenceStatus:
    """The character's current status (``present`` when it has no status event)."""
    return presence.get(character_id, DEFAULT_STATUS)  # type: ignore[return-value]
