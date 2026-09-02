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

import logging
import re
from dataclasses import dataclass, field
from functools import partial

from sqlalchemy.orm import Session

from app.agents import reflection_agent
from app.agents._common import resolve_llm
from app.agents.reflection_agent import LlmConn
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import APIError
from app.memory import interior
from app.memory.interior import InteriorRecord
from app.models import Character, Setting
from app.rag import indexer
from app.services import concurrency, graph_writer, memory_cues, memory_store
from app.services.assembler import CastMember, TurnContext
from app.services.memory_store import MemoryDraft

logger = logging.getLogger("mytheca.memory")


@dataclass(frozen=True)
class MemoryContext:
    """Everything the memory write needs, resolved on the request thread.

    ``reflect_and_store`` is deliberately free of any request-bound ``Session`` so the whole
    interlude can run on a background thread. That is also why this exists: every value the
    write depends on is read up front and carried as plain data, and the background job opens
    its **own** short-lived session for the insert.
    """

    storyline_id: str
    scenario_id: str
    turn_seq: int
    #: Character ids in the room. Stored on the memory so the disclosure class in Phase 5 is
    #: a set comparison rather than a judgement call.
    participants: list[str] = field(default_factory=list)
    #: Prose this turn actually produced. A quote is verified against exactly this.
    verify_texts: list[str] = field(default_factory=list)
    #: ``(lowercased name, normalized tag)`` for every character and setting in the
    #: storyline — the deterministic half of subject extraction. Sourced from Postgres, not
    #: the graph, so subjects are identical on an install with Neo4j switched off.
    known_entities: list[tuple[str, str]] = field(default_factory=list)
    setting_tag: str = ""


def build_memory_context(db: Session, ctx: TurnContext, turn_beats: list[dict], seq: int) -> MemoryContext:
    """Resolve the memory write's inputs while a request Session is still in hand."""
    storyline_id = ctx.storyline_id
    known: list[tuple[str, str]] = []
    for row in db.query(Character).filter(Character.storyline_id == storyline_id).all():
        if row.name:
            known.append((row.name.lower(), memory_store.normalize_subject(row.name)))
    for row in db.query(Setting).filter(Setting.storyline_id == storyline_id).all():
        if row.name:
            known.append((row.name.lower(), memory_store.normalize_subject(row.name)))
    return MemoryContext(
        storyline_id=storyline_id,
        scenario_id=ctx.scenario.id,
        turn_seq=seq,
        participants=[m.id for m in ctx.cast if m.is_present],
        verify_texts=[str(b.get("text", "")) for b in turn_beats if str(b.get("text", "")).strip()],
        known_entities=known,
        setting_tag=memory_store.normalize_subject(ctx.setting.name) if ctx.setting else "",
    )


def derive_subjects(proposed: list[str], mem_ctx: MemoryContext) -> list[str]:
    """The union of what the model proposed and what can be read off the turn directly.

    Subjects are **text tags, not ids**, because Phase 5 finds a memory by scanning the live
    scene for them — an id never appears in prose. The deterministic half (the setting, and
    any known character or place actually named in the turn) means a memory is still findable
    when the model proposes no tags at all.
    """
    tags = list(proposed)
    if mem_ctx.setting_tag:
        tags.append(mem_ctx.setting_tag)
    haystack = " ".join(mem_ctx.verify_texts).lower()
    for name, tag in mem_ctx.known_entities:
        if name and re.search(rf"\b{re.escape(name)}\b", haystack):
            tags.append(tag)
    return memory_store.normalize_subjects(tags)


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
        mem_ctx=build_memory_context(db, ctx, turn_beats, seq),
    )


def dispatch_reflection(
    db: Session,
    ctx: TurnContext,
    characters: list[CastMember],
    turn_beats: list[dict],
    *,
    branches: list[dict] | None = None,
    seq: int = 0,
) -> None:
    """Reflect off the request path (§P11 async finalize).

    Pre-resolves everything the reflection needs on the request thread (the LLM
    connection, the rendered transcript, plain target tuples) and hands the
    self-contained :func:`reflect_and_store` to :func:`concurrency.submit_background`,
    so the HTTP stream can close the instant the last visible event is yielded. When
    ``TURN_ASYNC_FINALIZE`` is off (default) or on SQLite it runs inline — deterministic
    for the offline test/dev path.
    """
    if not characters or not get_settings().turn_reflection_enabled:
        return
    try:
        conn = resolve_llm(db)
    except APIError:
        return
    job = partial(
        reflect_and_store,
        conn,
        session_id=ctx.session_id,
        stable_prefix=ctx.stable_prefix,
        transcript=render_transcript(ctx, turn_beats),
        targets=[(c.id, c.name, c.role) for c in characters],
        branches=branches,
        seq=seq,
        # Resolved here, on the request thread, for the same reason the transcript and the
        # LLM connection are: the job that receives it may run after this Session is gone.
        mem_ctx=build_memory_context(db, ctx, turn_beats, seq),
    )
    concurrency.submit_background(job)


def reflect_and_store(
    conn: LlmConn,
    *,
    session_id: str,
    stable_prefix: str,
    transcript: str,
    targets: list[tuple[str, str, str]],
    branches: list[dict] | None = None,
    seq: int = 0,
    mem_ctx: MemoryContext | None = None,
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
        if record is None:
            return
        interior.set_interior(session_id, character_id, record)
        if record.memory and mem_ctx is not None:
            store_memory(session_id, character_id, record.memory, mem_ctx)

    concurrency.run_all([partial(_one, target) for target in targets])


def store_memory(
    session_id: str, character_id: str, proposed: dict, mem_ctx: MemoryContext
) -> None:
    """Persist one proposed memory in its **own** database session. Never raises.

    The own-session part is not incidental. ``reflect_and_store`` is built to run on a
    background thread after the HTTP stream has closed, so there is no request-bound
    ``Session`` to borrow and borrowing one would be a use-after-close waiting for a busy
    scene. A failure here costs one memory and nothing else — the turn is long since
    delivered.
    """
    db = SessionLocal()
    try:
        draft = MemoryDraft(
            storyline_id=mem_ctx.storyline_id,
            character_id=character_id,
            session_id=session_id,
            scenario_id=mem_ctx.scenario_id,
            turn_seq=mem_ctx.turn_seq,
            gloss=str(proposed.get("gloss") or ""),
            quote=proposed.get("quote"),
            quote_speaker_id=None,  # a name, not an id, at this point — resolved below
            valence=str(proposed.get("valence") or ""),
            salience=float(proposed.get("salience") or 0.0),
            participants=list(mem_ctx.participants),
            subjects=derive_subjects(list(proposed.get("subjects") or []), mem_ctx),
        )
        draft.quote_speaker_id = _resolve_speaker(
            db, mem_ctx.storyline_id, proposed.get("quoteSpeaker")
        )
        row = memory_store.write(db, draft, verify_texts=mem_ctx.verify_texts)
        if row is None:
            db.rollback()
            return
        db.commit()
        # Into the hybrid corpus, so the memory is findable by MEANING when the exact tag
        # scan misses. Best-effort and after the commit, exactly like the graph mirror.
        indexer.sync_memory(row, owner_name=_character_name(db, character_id))
        graph_writer.mirror_memory_safe(
            memory_id=row.id,
            character_id=character_id,
            event_node_id=f"evt_{session_id}_{mem_ctx.turn_seq}",
            storyline_id=mem_ctx.storyline_id,
            gloss=row.gloss,
            salience=row.salience,
            turn_seq=mem_ctx.turn_seq,
            summary=row.gloss,
        )
        _promote_subjects(db, mem_ctx.storyline_id, row)
    except Exception as exc:  # pragma: no cover - defensive; the turn is already delivered
        logger.warning("memory write skipped (character %s): %s", character_id, exc)
        db.rollback()
    finally:
        db.close()


def _promote_subjects(db: Session, storyline_id: str, row) -> None:
    """Promote this memory's subject tags to graph nodes once they have recurred enough.

    Scoped to the tags **this** memory carries: promotion can only ever be triggered by a new
    mention, so re-evaluating the whole world's tag space on every write would be the same
    answer at a higher price. Cold path, best-effort, and worth nothing on the hot path —
    the cue scan matches tags straight off the memory rows, so a `:Subject` node buys
    traversal ("who fears ogres") and nothing recall depends on.
    """
    tags = set(row.subjects or [])
    if not tags:
        return
    corpus = memory_store.all_for_storyline(db, storyline_id)
    promoted = {t: n for t, n in memory_cues.promotable(corpus).items() if t in tags}
    if not promoted:
        return
    links = {
        tag: [m.id for m in corpus if tag in (m.subjects or [])] for tag in promoted
    }
    graph_writer.promote_subjects_safe(storyline_id, promoted, links)


def _character_name(db: Session, character_id: str) -> str:
    """The remembering character's name, for the corpus entry. Falls back rather than raises."""
    row = db.get(Character, character_id)
    return (row.name if row is not None else "") or "Someone"


def _resolve_speaker(db: Session, storyline_id: str, name: object) -> str | None:
    """Map the quoted speaker's *name* to a character id, or ``None``.

    The model answers with a name because that is what it sees in the transcript. An
    unmatched name is not an error — the narrator and the player both say quotable things
    and neither is a ``Character`` row.
    """
    label = str(name or "").strip().lower()
    if not label:
        return None
    for row in db.query(Character).filter(Character.storyline_id == storyline_id).all():
        if (row.name or "").strip().lower() == label:
            return row.id
    return None


def refresh_dispositions(
    db: Session,
    ctx: TurnContext,
    members: list[CastMember],
    turn_beats: list[dict],
    *,
    seq: int = 0,
) -> None:
    """Cascade refresh: recompute the given (not-yet-spoken) members' dispositions mid-turn.

    Called by the live speaker queue (§P10) after a high-impact beat: the affected
    members reflect on the shift *now* so their upcoming line reacts to it, instead of
    waiting for the next turn. Each fresh disposition is written **in place** onto its
    ``CastMember`` (so ``character_turn_agent`` picks it up this turn) and persisted to
    interior state (so it also carries forward). Best-effort; concurrent; the reflect
    calls touch no request Session (the mutation happens after they join).
    """
    if not members or not get_settings().turn_reflection_enabled:
        return
    try:
        conn = resolve_llm(db)
    except APIError:
        return
    transcript = render_transcript(ctx, turn_beats)

    def _one(member: CastMember) -> tuple[CastMember, object]:
        record = reflection_agent.reflect(
            conn,
            name=member.name,
            role=member.role,
            character_id=member.id,
            stable_prefix=ctx.stable_prefix,
            transcript=transcript,
            seq=seq,
        )
        return member, record

    for result in concurrency.run_all([partial(_one, m) for m in members]):
        if result is None:
            continue
        member, record = result
        if isinstance(record, InteriorRecord) and record.disposition:
            member.disposition = record.disposition  # live: this turn's later beat sees it
            interior.set_interior(ctx.session_id, member.id, record)


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
