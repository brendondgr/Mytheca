"""What the scene remembers after the window forgets it.

The transcript window fits itself to the model's context budget, and a scene that outgrows it
drops its oldest beats. This is the second half of that: the dropped beats are folded into a
**rolling per-session summary** so the cast still knows that someone confessed, that someone
left, that a debt is owed.

Three constraints shaped every decision here.

**Cost.** Summarisation is incremental and bounded to whole anchor blocks, so a long session
costs one cheap ``ReasoningEffort.LOW`` call roughly every twenty beats rather than a growing
re-summarisation every turn.

**Cache.** Compaction fires on exactly the turns the anchored window re-anchors, and the
summary is rendered immediately above the transcript. The two therefore invalidate the
prompt-cache prefix *together*, on the same turn, instead of on different ones.

**Truth.** A summary is a claim about what happened. A rewind, an edit or a re-roll at or below
``summary_through_seq`` means the summary describes a scene that no longer exists, so
:func:`invalidate_after` clears it. Leaving a stale summary in place would be worse than having
none: the cast would confidently remember a beat the player deliberately removed.

Nothing here may break a turn. Every failure path — no model, a raising agent, an empty reply,
the setting turned off — leaves the previous summary standing and returns a result the caller
can trace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import prompt_registry, recap_agent
from app.core.config import get_settings
from app.core.errors import APIError
from app.memory import buffer
from app.models import Event, PlaySession, Scenario, Storyline
from app.services import context_budget, settings_store

logger = logging.getLogger("mytheca.turn")

#: Beat types whose prose is worth remembering. A `state_update` or a set of `branch_choices`
#: has nothing to summarise, and a hidden `internal_thought` was never shared with the scene.
SUMMARISABLE = ("narration", "character_prose", "character_dialogue", "character_action")


@dataclass(frozen=True)
class CompactionResult:
    """What compaction did this turn — the payload the trace reports."""

    ran: bool = False
    beats_folded: int = 0
    through_seq: int | None = None
    summary_chars: int = 0
    #: Why it did not run, for the trace. Empty when it did.
    reason: str = ""


def summary_for(session: PlaySession) -> str:
    """The rendered memory block, or ``""`` when the scene has none."""
    return (session.summary_text or "").strip()


def invalidate_after(db: Session, session_id: str, seq: int) -> bool:
    """Clear a summary that covers ``seq`` or later. Returns whether anything was cleared.

    Called from every path that rewrites history — rewind, beat edit, beat re-roll — because
    all three can make the summary describe wording or events that no longer exist. It lives
    beside the Redis buffer rebuild in ``session_state`` for exactly that reason: the two
    must never diverge, so they are invoked from the same tested places.

    A summary that stops *before* ``seq`` is untouched: the beats it covers are still true.
    """
    session = db.get(PlaySession, session_id)
    if session is None or session.summary_text is None:
        return False
    through = session.summary_through_seq
    if through is not None and through < seq:
        return False
    session.summary_text = None
    session.summary_through_seq = None
    session.summary_updated_at = None
    db.add(session)
    db.flush()
    return True


def maybe_compact(
    db: Session, session: PlaySession, scenario: Scenario, *, stable_prefix: str = ""
) -> CompactionResult:
    """Fold whatever has fallen out of the window into the scene's memory.

    Called *before* ``assembler.assemble_context`` so the assembler stays read-only and the
    summary is already on the row by the time assembly reads it.
    """
    if not get_settings().turn_context_compaction:
        return CompactionResult(reason="off")
    if (scenario.context_policy or "auto").strip().lower() == "fixed":
        # The scene chose its own depth; it has not asked the app to manage its memory.
        return CompactionResult(reason="fixed")

    retained = buffer.recent_turns(session.id)
    if not retained:
        # No Redis means no buffer means no dropped beats means nothing to compact. Not an
        # error, and not something the player ever sees.
        return CompactionResult(reason="no-buffer")

    block = max(1, get_settings().turn_transcript_anchor_block)
    window = context_budget.resolve_window(db)
    budget = context_budget.transcript_budget(window, context_budget.reserve_for(stable_prefix))
    fit = context_budget.fit_window(
        [str(b.get("text") or "") for b in retained], budget, block
    )
    if fit.dropped_beats < block:
        # Bounded to whole blocks: compacting every turn a single beat falls off would cost a
        # call per turn AND move the summary line on a turn the window did not re-anchor,
        # breaking the prompt-cache prefix twice instead of once.
        return CompactionResult(reason="nothing-dropped")

    already = session.summary_through_seq
    fresh = _beats_to_fold(db, session.id, after_seq=already, limit=fit.dropped_beats)
    if not fresh:
        return CompactionResult(reason="already-covered")

    try:
        conn = _conn(db)
    except APIError:
        return CompactionResult(reason="no-model")
    if conn is None:
        return CompactionResult(reason="no-model")

    storyline = db.get(Storyline, scenario.storyline_id)
    prompts = prompt_registry.resolve_prompts(
        settings_store.get_prompts_overrides(db),
        (storyline.prompt_overrides if storyline else None) or {},
        scenario.prompt_overrides or {},
    )
    text = recap_agent.summarize_history(
        conn,
        previous_summary=summary_for(session),
        beats=[t for _seq, t in fresh],
        stable_prefix=stable_prefix,
        system=prompts.get(prompt_registry.RECAP_SUMMARIZE),
    )
    if not text:
        # The previous summary stands and the oldest beats drop as they did before. A scene
        # that cannot summarise forgets a little more; it does not fail.
        return CompactionResult(reason="agent-declined")

    session.summary_text = text
    session.summary_through_seq = fresh[-1][0]
    session.summary_updated_at = datetime.now(UTC)
    db.add(session)
    db.flush()
    return CompactionResult(
        ran=True,
        beats_folded=len(fresh),
        through_seq=session.summary_through_seq,
        summary_chars=len(text),
    )


def _beats_to_fold(
    db: Session, session_id: str, *, after_seq: int | None, limit: int
) -> list[tuple[int, str]]:
    """The oldest not-yet-summarised prose beats, `(seq, text)`, oldest first.

    Read from the **event log** rather than the Redis buffer: the buffer is a bounded recent
    window and the beats that need folding are by definition the ones falling off its far end,
    which it may no longer hold. The log is the record.
    """
    stmt = (
        select(Event.seq, Event.data)
        .where(Event.session_id == session_id, Event.type.in_(SUMMARISABLE))
        .order_by(Event.seq)
    )
    if after_seq is not None:
        stmt = stmt.where(Event.seq > after_seq)
    out: list[tuple[int, str]] = []
    for seq, data in db.execute(stmt.limit(max(1, limit))):
        text = str((data or {}).get("text") or "").strip()
        if text:
            out.append((int(seq), text))
    return out


def _conn(db: Session) -> recap_agent.LlmConn | None:
    """The resolved LLM connection, or ``None`` when nothing is configured."""
    cfg = settings_store.get_llm(db)
    base_url, api_key = settings_store.resolve_llm_credentials(db, None, None)
    if not base_url.strip() or not cfg.model:
        return None
    return (base_url, api_key, cfg.model, cfg.params)
