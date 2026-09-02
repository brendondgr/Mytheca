"""Choosing which memories reach a beat. Deterministic, and once per turn.

Storing memories is easy; choosing two out of four hundred is the whole problem. This
module is that choice, and it is **arithmetic** — given the same rows and the same turn it
returns the same memories, so an odd line can be reproduced in a debugger rather than
argued about.

**Once per turn, not once per beat.** The turn is planned up front and the plan is binding
(``services/turn_plan.py``), so every speaker is known before the first beat runs. One call
to :func:`recall_for_turn` in ``turn_setup.prepare_turn`` covers all of them with one
database query; each beat then picks off a pre-computed shortlist and touches nothing. A
per-beat design would have re-run the same lookup twenty-plus times a turn to retrieve
material that barely changed between one beat and the next.

Three things decide a memory's score, and the third matters more than it looks:

*Salience* is how much the moment mattered when it was formed. *Fade* and *reinforcement*
make a grudge behave like a grudge — a wound that keeps getting picked at stays hot, a
slight nobody mentions again sinks to the floor. And *cooldown* suppresses anything
surfaced in the last few turns, because recall is not only about finding the right memory:
without it the same memory wins every beat and the character becomes someone who can only
say one thing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import CharacterMemory, PlaySession
from app.services import memory_cues, memory_store

logger = logging.getLogger("mytheca.memory")

#: Turn-relative half-life, mirroring the `half_life_turns` the graph registry has declared
#: on every feeling edge since it was written and nothing has ever computed.
FADE_HALF_LIFE_TURNS = 40.0
#: Fade never reaches zero — a faded memory lingers rather than being forgotten, which is
#: also the registry's stated intent for a decayed edge.
FADE_FLOOR = 0.05

#: Attenuation for a memory formed in a **different play-session**. Deliberately a flat
#: nudge and not a decay curve: seq numbers are per-session, so "how many turns ago" is
#: undefined across a scenario boundary, and inventing a global clock to answer it would be
#: a fabricated number driving real behaviour. A curve would also fight the whole feature —
#: recalling scene one during scene four is the point, not an edge case to decay away.
CROSS_SESSION_FADE = 0.85

#: Each re-living makes a memory harder to displace, up to a ceiling so a much-reinforced
#: memory cannot monopolise every slot forever.
REINFORCE_BONUS = 0.15
REINFORCE_BONUS_CAP = 0.45

#: Someone in the memory is in the room.
PARTICIPANT_BONUS = 0.30
#: The live scene names something the memory is about (Phase 5 supplies the cues).
CUE_BONUS = 0.25
CUE_HITS_CONSIDERED = 3

#: Surfaced within this many turns → heavily penalised.
COOLDOWN_TURNS = 6
COOLDOWN_PENALTY = 0.5

#: Rank-fusion constant for the semantic channel (the RRF `k` the hybrid retriever uses).
#: Fused by RANK, never by adding scores: a recall score and a cosine similarity are on
#: incomparable scales, which is exactly why `rag/retriever.rrf_fuse` exists.
RRF_K = 60
#: What a top semantic hit can add. Capped low on purpose — this channel is the safety net
#: for what the exact tags missed, not a second opinion on memories the tags already found.
SEMANTIC_WEIGHT = 0.35

#: A memory has to be worth the prompt space it takes.
MIN_SCORE = 0.15
#: How many reach one speaker's beat. Two, because a third is almost never the reason a line
#: works and every one of them displaces live scene context.
PER_SPEAKER_LIMIT = 2


@dataclass(frozen=True)
class Recalled:
    """One memory offered to one speaker this turn, with the score that chose it."""

    memory: CharacterMemory
    score: float
    #: Which cues fired, for the trace and the provenance panel.
    cue_hits: list[str] = field(default_factory=list)
    #: Whether this may be said aloud in front of the people currently in the room —
    #: ``quotable`` / ``shared`` / ``private``. A property of the memory **and** the room.
    disclosure: str = memory_cues.QUOTABLE
    #: Who is here now and was not at the source event. Named in the prompt so "do not tell
    #: this" is an instruction rather than an abstraction.
    outsiders: list[str] = field(default_factory=list)


def _fade(memory: CharacterMemory, *, session_id: str, now_seq: int) -> float:
    """How much this memory has cooled since it was last lived or last recalled."""
    if memory.session_id != session_id:
        return CROSS_SESSION_FADE
    last_touch = int(memory.turn_seq or 0)
    # A recall only counts as a touch when it happened in THIS play-through. Seq numbers are
    # per-session, so a recall in a sibling branch is a number from a different clock — and
    # taking the max regardless made a memory surfaced in the timeline the player abandoned
    # read as freshly-lived here. Same reasoning as the session check in ``_cooldown``.
    if memory.last_recalled_session_id == session_id and memory.last_recalled_seq is not None:
        last_touch = max(last_touch, int(memory.last_recalled_seq))
    elapsed = max(0, now_seq - last_touch)
    return max(FADE_FLOOR, 0.5 ** (elapsed / FADE_HALF_LIFE_TURNS))


def _cooldown(memory: CharacterMemory, *, session_id: str, now_seq: int) -> bool:
    """True when this memory was surfaced too recently to surface again."""
    if memory.last_recalled_seq is None:
        return False
    if memory.last_recalled_session_id != session_id:
        return False
    return (now_seq - int(memory.last_recalled_seq)) < COOLDOWN_TURNS


def score(
    memory: CharacterMemory,
    *,
    session_id: str,
    now_seq: int,
    present_ids: set[str],
    cues: set[str],
) -> tuple[float, list[str]]:
    """This memory's score right now, and which cues fired. Pure — no I/O, no clock."""
    base = float(memory.salience or 0.0)
    base *= _fade(memory, session_id=session_id, now_seq=now_seq)
    base *= 1.0 + min(REINFORCE_BONUS_CAP, REINFORCE_BONUS * int(memory.reinforcements or 0))

    if present_ids & {p for p in (memory.participants or [])}:
        base += PARTICIPANT_BONUS

    hits = sorted(cues & {s for s in (memory.subjects or [])})
    if hits:
        base += CUE_BONUS * (min(len(hits), CUE_HITS_CONSIDERED) / CUE_HITS_CONSIDERED)

    if _cooldown(memory, session_id=session_id, now_seq=now_seq):
        base -= COOLDOWN_PENALTY
    return base, hits


def rank(
    memories: list[CharacterMemory],
    *,
    session_id: str,
    now_seq: int,
    present_ids: set[str],
    cues: set[str],
    boosts: dict[str, float] | None = None,
    limit: int = PER_SPEAKER_LIMIT,
) -> list[Recalled]:
    """Score, threshold and cut one character's candidates. Ties break on id, not row order.

    Deterministic ordering matters more than it sounds: two memories scoring identically
    would otherwise surface in whatever order the database returned, and the same scene
    replayed would read differently for no reason anyone could find.
    """
    scored: list[Recalled] = []
    for memory in memories:
        value, hits = score(
            memory, session_id=session_id, now_seq=now_seq, present_ids=present_ids, cues=cues
        )
        value += (boosts or {}).get(memory.id, 0.0)
        if value >= MIN_SCORE:
            scored.append(
                Recalled(
                    memory=memory,
                    score=value,
                    cue_hits=hits,
                    disclosure=memory_cues.disclosure(
                        memory.participants, others_present=present_ids
                    ),
                    outsiders=sorted(
                        memory_cues.outsiders(memory.participants, others_present=present_ids)
                    ),
                )
            )
    scored.sort(key=lambda r: (-r.score, r.memory.id))
    return scored[:limit]


def semantic_boosts(
    db: Session, *, storyline_id: str, query: str, candidate_ids: set[str]
) -> dict[str, float]:
    """Rank-fused boosts for memories the hybrid corpus surfaces for ``query``.

    **Gated by the caller**, and the gate is the point: this is the only channel with a real
    cost (an embedding plus a vector search), and it exists for what the exact tag scan
    cannot reach — "the water's high tonight" finding the night someone nearly drowned with
    the word *drowning* nowhere in the scene. When the tags already fired, running it would
    be paying for a second opinion on memories that were found.

    Best-effort → ``{}``: Qdrant off, unreachable, or holding nothing leaves recall exactly
    as it was without this phase.
    """
    if not query.strip() or not candidate_ids:
        return {}
    try:
        from app.rag import retriever

        hits = retriever.retrieve(db, storyline_id, query, k=8)
    except Exception as exc:  # pragma: no cover - defensive; a turn never fails on recall
        logger.debug("semantic memory recall unavailable: %s", exc)
        return {}
    boosts: dict[str, float] = {}
    for rank_index, hit in enumerate(hits):
        # A memory entry's `entry_id` IS the memory id (`entries.entry_from_memory` sets the
        # front-matter id to it). The corpus also holds characters, settings and documents,
        # so intersecting with this turn's candidates is what keeps a setting's description
        # from boosting anything.
        memory_id = str(getattr(hit, "entry_id", "") or "")
        if memory_id in candidate_ids:
            boosts[memory_id] = SEMANTIC_WEIGHT * (RRF_K / (RRF_K + rank_index + 1))
    return boosts


def recall_for_turn(
    db: Session,
    *,
    storyline_id: str,
    session: PlaySession,
    speaker_ids: list[str],
    present_ids: list[str],
    now_seq: int,
    cues: set[str] | None = None,
    scene_texts: list[str] | None = None,
    semantic: bool = True,
    limit: int = PER_SPEAKER_LIMIT,
) -> dict[str, list[Recalled]]:
    """Every planned speaker's shortlist, from **one** query. Best-effort → ``{}``.

    ``speaker_ids`` comes from the bound plan. When the planner falls back to its adaptive
    path there is no plan to read, and the caller passes the present cast instead: one
    slightly larger query, still one round trip.
    """
    ids = [cid for cid in dict.fromkeys(speaker_ids) if cid]
    if not ids:
        return {}
    try:
        rows = memory_store.visible_for(
            db, storyline_id=storyline_id, session=session, character_ids=ids
        )
    except Exception as exc:  # pragma: no cover - defensive; a turn never fails on recall
        logger.warning("memory recall unavailable (session %s): %s", session.id, exc)
        return {}

    by_character: dict[str, list[CharacterMemory]] = {cid: [] for cid in ids}
    for row in rows:
        by_character.setdefault(row.character_id, []).append(row)

    present = set(present_ids or [])

    # The cue vocabulary is built from the candidates themselves, not from a storyline-wide
    # lexicon. Cues only ever matter by intersecting a memory's own subjects, so scanning the
    # scene for tags no candidate carries could not change any score — and the rows are
    # already in hand, which is why the whole cue channel costs no second query.
    cues = set(cues or set())
    if scene_texts:
        cues |= memory_cues.scan(
            scene_texts, {t for row in rows for t in (row.subjects or [])}
        )

    # The semantic channel fires only when the exact tags found NOTHING. That is the whole
    # gate, and it is stricter than a heuristic about the player's phrasing would be: the
    # question this channel answers is "did the dictionary miss?", and the dictionary having
    # matched is a direct answer to it.
    boosts: dict[str, float] = {}
    if not cues and semantic and scene_texts:
        boosts = semantic_boosts(
            db,
            storyline_id=storyline_id,
            query=" ".join(t for t in scene_texts if t)[-600:],
            candidate_ids={row.id for row in rows},
        )

    return {
        cid: rank(
            rows_for,
            session_id=session.id,
            now_seq=now_seq,
            # A speaker is not "present" to their own memory — counting them would give every
            # memory they own the participant bonus, which is the same as giving it to none.
            present_ids=present - {cid},
            cues=cues,
            boosts=boosts,
            limit=limit,
        )
        for cid, rows_for in by_character.items()
    }
