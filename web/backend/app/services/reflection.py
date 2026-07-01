"""Read-time reflection interlude (§10 / §P9) — orchestrates per-character reflection.

After a turn's stream is delivered, the characters reflect *while the player reads*:
each produces an interior record (disposition + retrospective + branch-keyed stances)
that Band-1 assembly reads back on the next turn. Reflection is **off the hot path** and
**best-effort** — it never blocks the stream and never fails the turn.

Because vLLM allows parallel inference (turn-loop plan D-C), the whole cast reflects
**concurrently** via the bounded pool in :mod:`app.services.concurrency`. The LLM
connection is resolved **once on the request thread** and the transcript is rendered to
a plain string up front, so the concurrent units touch no request-bound SQLAlchemy
state (which also lets P11 run the whole interlude on a background thread).
"""

from __future__ import annotations

from functools import partial

from sqlalchemy.orm import Session

from app.agents import reflection_agent
from app.agents._common import resolve_llm
from app.agents.reflection_agent import LlmConn
from app.core.config import get_settings
from app.core.errors import APIError
from app.memory import interior
from app.services import concurrency
from app.services.assembler import CastMember, TurnContext


def run_reflection(
    db: Session,
    ctx: TurnContext,
    characters: list[CastMember],
    turn_beats: list[dict],
    *,
    branches: list[dict] | None = None,
    seq: int = 0,
) -> None:
    """Resolve the LLM, render the transcript, and reflect the given characters.

    Request-thread entry point (P9): safe to call inline at the turn's tail. Skips
    cleanly when reflection is disabled, there is nothing to reflect, or the LLM is
    unconfigured.
    """
    if not characters or not get_settings().turn_reflection_enabled:
        return
    try:
        conn = resolve_llm(db)
    except APIError:
        return  # unconfigured LLM — keep last interior state
    reflect_and_store(
        conn,
        session_id=ctx.session_id,
        stable_prefix=ctx.stable_prefix,
        transcript=render_transcript(ctx, turn_beats),
        targets=[(c.id, c.name, c.role) for c in characters],
        branches=branches,
        seq=seq,
    )


def reflect_and_store(
    conn: LlmConn,
    *,
    session_id: str,
    stable_prefix: str,
    transcript: str,
    targets: list[tuple[str, str, str]],
    branches: list[dict] | None = None,
    seq: int = 0,
) -> None:
    """Reflect every target concurrently and write each interior record (best-effort).

    Fully self-contained (no ``Session``, no request-bound ORM) so it also runs on a
    background thread in P11.
    """
    if not targets:
        return

    def _one(target: tuple[str, str, str]) -> None:
        character_id, name, role = target
        record = reflection_agent.reflect(
            conn,
            name=name,
            role=role,
            character_id=character_id,
            stable_prefix=stable_prefix,
            transcript=transcript,
            branches=branches,
            seq=seq,
        )
        if record is not None:
            interior.set_interior(session_id, character_id, record)

    concurrency.run_all([partial(_one, target) for target in targets])


def render_transcript(ctx: TurnContext, turn_beats: list[dict]) -> str:
    """Render prior history + this-turn beats to a short transcript (chronological)."""
    names = {m.id: m.name for m in ctx.cast}
    lines: list[str] = []
    for beat in [*ctx.recent_beats, *turn_beats]:
        text = str(beat.get("text", "")).strip()
        if not text:
            continue
        role = beat.get("role")
        if role == "player":
            who = "Player"
        elif role == "narrator":
            who = "Narrator"
        else:
            cid = beat.get("characterId")
            who = names.get(cid, "Someone") if cid else "Someone"
        lines.append(f"{who}: {text}")
    return "\n".join(lines)
