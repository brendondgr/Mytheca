"""The one owner of episodic memory persistence (Postgres canonical).

Everything that writes, reads back, reinforces or deletes a :class:`CharacterMemory`
goes through here. Four rules live in this module and nowhere else:

**A quote must be real.** :func:`write` refuses to persist a ``quote`` that is not a
substring of prose the turn actually produced. A model asked for a verbatim line will
sometimes compose a plausible one instead, and a character quoting a line nobody said is
a worse failure than a character with no memory at all — it is indistinguishable from the
engine losing track, and it is the failure a player would report as a bug.

**Reinforce, don't duplicate.** A moment the cast keeps returning to is *one* memory that
keeps getting hotter, not forty near-identical rows. This is what bounds growth and it is
also what makes the fade model behave like a grudge rather than a log.

**Recall is lineage-scoped.** A forked play-through inherits its ancestors only up to the
point it branched away from them. Without this a branch remembers the timeline the player
deliberately abandoned — the same class of leak the rewind path already had to close.

**A rewind forgets transactionally.** :func:`delete_after` is a plain SQL delete in the
caller's session, not a best-effort side effect. This is the reason memory is canonical in
Postgres rather than in the graph.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.models import CharacterMemory, PlaySession, Scenario

logger = logging.getLogger("mytheca.memory")

#: Below this a moment is not worth carrying between scenes. Most turns are not
#: memorable, and a store full of shrugs makes recall worse, not richer — every low-value
#: row is another candidate the scorer has to beat.
SALIENCE_FLOOR = 0.35

#: How alike two glosses must read before the newer one is treated as the same moment
#: recurring. Two measures, because each has a blind spot the other covers: character
#: sequence similarity collapses on a **clause swap** ("she went back for the cargo and
#: left me under the water" vs the same two clauses reversed scores 0.49, and those are
#: plainly one memory), while word-set overlap scores that pair 1.0. Either clearing its
#: threshold is a match.
#:
#: **Both thresholds are deliberately conservative, and the reason is a measured limit.**
#: Lexical similarity cannot separate "she chose the cargo over me" / "she picked the cargo
#: over me" (0.873 — one moment, reworded) from "he lied to me about the gate" / "…about
#: the coin" (0.857 — two different lies). Sixteen thousandths apart, opposite answers
#: wanted. No threshold resolves that, so the tie is broken toward **not** merging: an
#: unmerged duplicate costs a redundant row that cooldown will suppress anyway, while a
#: wrong merge destroys a memory outright. Same reason the equally-valid rephrasing "an
#: ogre killed Sera in front of me" / "…while I watched" (0.696 / 0.364) is left as two
#: rows rather than chasing it with a looser bar.
#:
#: Known residue: word-set overlap is blind to direction, so "Dell left Mara" and "Mara
#: left Dell" would score 1.0. In practice a gloss is written first-person from the
#: character's own POV — they are always "me" — so the subject/object swap this would
#: mishandle is not a shape the writing agent produces.
_GLOSS_SEQUENCE_MATCH = 0.90
_GLOSS_TOKEN_MATCH = 0.85

#: Ceiling on one recall query. Rows are small; this exists so a heavily-played world
#: loads a salience-ordered slice rather than a character's entire history.
DEFAULT_RECALL_LIMIT = 240

#: Cycle guard when walking ``parent_session_id``. Fork chains are short in practice.
_MAX_LINEAGE_DEPTH = 64

_SUBJECT_STRIP = re.compile(r"[^a-z0-9]+")


def normalize_subject(raw: str) -> str:
    """Fold a subject to its stored form: lowercase, kebab, no punctuation.

    ``"the Flooded Tunnel"`` and ``"flooded tunnel!"`` must land on one tag, because the
    cue scan in Phase 5 matches stored tags against scene text and a tag nobody can spell
    twice is a tag that never fires.
    """
    return _SUBJECT_STRIP.sub("-", (raw or "").strip().lower()).strip("-")


def normalize_subjects(raws: list[str] | None) -> list[str]:
    """Normalize, drop blanks, dedupe, preserve first-seen order."""
    out: list[str] = []
    for raw in raws or []:
        tag = normalize_subject(str(raw))
        if tag and tag not in out:
            out.append(tag)
    return out


@dataclass
class MemoryDraft:
    """One proposed memory, before the write rules have had a say."""

    storyline_id: str
    character_id: str
    session_id: str
    scenario_id: str
    turn_seq: int
    gloss: str
    salience: float
    event_id: str | None = None
    quote: str | None = None
    quote_speaker_id: str | None = None
    valence: str = ""
    participants: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)


def quote_is_real(quote: str | None, verify_texts: list[str]) -> bool:
    """True when ``quote`` appears verbatim in prose the turn actually produced.

    Whitespace is collapsed on both sides before comparing: a model reproducing a line
    faithfully still tends to normalise a line break into a space, and rejecting that
    would throw away correct quotes to catch nothing.
    """
    if not quote:
        return False
    needle = " ".join(quote.split()).strip().strip('"“”').lower()
    if not needle:
        return False
    return any(needle in " ".join((t or "").split()).lower() for t in verify_texts)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9']+", text.lower()) if t}


def _same_moment(a: str, b: str) -> bool:
    """Whether two glosses describe the same moment. See the threshold constants."""
    if not a or not b:
        return False
    if SequenceMatcher(None, a.lower(), b.lower()).ratio() >= _GLOSS_SEQUENCE_MATCH:
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= _GLOSS_TOKEN_MATCH


def _find_recurrence(db: Session, draft: MemoryDraft) -> CharacterMemory | None:
    """An existing memory of the same moment for this character, or ``None``.

    Scoped to the same character *and the same scenario*: the tunnel recurring within one
    scene is the same wound, while the tunnel being brought up again three scenarios later
    is a genuinely separate moment (the bringing-up) and deserves its own row.
    """
    rows = db.scalars(
        select(CharacterMemory).where(
            CharacterMemory.character_id == draft.character_id,
            CharacterMemory.scenario_id == draft.scenario_id,
        )
    ).all()
    subjects = set(draft.subjects)
    for row in rows:
        row_subjects = set(row.subjects or [])
        # Subjects **narrow** a gloss match, they do not gate it. Requiring an overlap
        # outright meant one untagged side could never match anything, so a memory written
        # before subject extraction settled would fork into a duplicate rather than
        # reinforce. Two moments that read the same and share no subject at all are still
        # treated as distinct.
        if subjects and row_subjects and not (subjects & row_subjects):
            continue
        if _same_moment(row.gloss or "", draft.gloss):
            return row
    return None


def reinforce(db: Session, memory: CharacterMemory, *, turn_seq: int) -> CharacterMemory:
    """Mark a memory as lived through again: hotter, and more recent."""
    memory.reinforcements = int(memory.reinforcements or 0) + 1
    memory.turn_seq = max(int(memory.turn_seq or 0), turn_seq)
    db.add(memory)
    return memory


def write(db: Session, draft: MemoryDraft, *, verify_texts: list[str]) -> CharacterMemory | None:
    """Persist one memory, or ``None`` when the write rules reject it.

    ``verify_texts`` is the prose this turn actually produced, passed in by the caller
    rather than re-queried here. The caller (the post-turn interlude) already holds the
    turn's beats; re-reading them would be a second query for bytes we were handed.

    A draft whose ``quote`` fails verification is **not** discarded — it is stored without
    the quote. The gloss is still the character's own reading of the moment and is worth
    keeping; only the claim to have heard specific words is unsupported.
    """
    if draft.salience < SALIENCE_FLOOR:
        return None
    if not (draft.gloss or "").strip():
        return None

    draft.subjects = normalize_subjects(draft.subjects)
    if draft.quote and not quote_is_real(draft.quote, verify_texts):
        logger.debug(
            "memory quote rejected (character %s, turn %s): not in this turn's prose",
            draft.character_id,
            draft.turn_seq,
        )
        draft.quote = None
        draft.quote_speaker_id = None

    existing = _find_recurrence(db, draft)
    if existing is not None:
        reinforce(db, existing, turn_seq=draft.turn_seq)
        # A recurrence that finally produced a usable quote upgrades the row it matched;
        # one that did not must never blank a quote already earned.
        if draft.quote and not existing.quote:
            existing.quote = draft.quote
            existing.quote_speaker_id = draft.quote_speaker_id
        if draft.salience > (existing.salience or 0.0):
            existing.salience = draft.salience
        return existing

    row = CharacterMemory(
        storyline_id=draft.storyline_id,
        character_id=draft.character_id,
        session_id=draft.session_id,
        scenario_id=draft.scenario_id,
        turn_seq=draft.turn_seq,
        event_id=draft.event_id,
        gloss=draft.gloss.strip(),
        quote=draft.quote,
        quote_speaker_id=draft.quote_speaker_id,
        valence=draft.valence or "",
        salience=float(draft.salience),
        participants=list(draft.participants or []),
        subjects=list(draft.subjects),
    )
    db.add(row)
    return row


# ---- lineage -----------------------------------------------------------------


def lineage_caps(db: Session, session: PlaySession) -> list[tuple[str, int | None]]:
    """``(session_id, max_turn_seq)`` for this session and every ancestor.

    ``None`` means uncapped (the current session). An ancestor is capped at the
    ``fork_seq`` of the child that branched from it, so a fork inherits everything up to
    the moment it diverged and nothing after — which is the whole point: the parent kept
    playing down a road this play-through did not take.
    """
    chain: list[tuple[str, int | None]] = [(session.id, None)]
    seen = {session.id}
    current = session
    for _ in range(_MAX_LINEAGE_DEPTH):
        parent_id = current.parent_session_id
        if not parent_id or parent_id in seen:
            break
        parent = db.get(PlaySession, parent_id)
        if parent is None:
            break
        chain.append((parent.id, current.fork_seq))
        seen.add(parent.id)
        current = parent
    return chain


def _other_scenario_sessions(db: Session, storyline_id: str, exclude_scenario_id: str) -> list[str]:
    """One session id per *other* scenario in the storyline: the most recently updated.

    **This rule is an interim answer, not a settled one** (plan gap G2). A scenario played
    twice to different outcomes leaves two incompatible pasts under one storyline, and
    "the last time you played that scene is what happened" is the cheapest defensible
    reading of which one is history. The considered alternative is an explicit
    "this play-through is canon" marker on ``PlaySession``; it would replace this function
    and nothing else.
    """
    rows = db.execute(
        select(PlaySession.id, PlaySession.scenario_id, PlaySession.updated_at)
        .join(Scenario, Scenario.id == PlaySession.scenario_id)
        .where(
            Scenario.storyline_id == storyline_id,
            PlaySession.scenario_id != exclude_scenario_id,
        )
        .order_by(PlaySession.updated_at.desc())
    ).all()
    best: dict[str, str] = {}
    for session_id, scenario_id, _updated in rows:
        best.setdefault(scenario_id, session_id)
    return list(best.values())


def visible_for(
    db: Session,
    *,
    storyline_id: str,
    session: PlaySession,
    character_ids: list[str],
    limit: int = DEFAULT_RECALL_LIMIT,
) -> list[CharacterMemory]:
    """Every memory these characters may recall right now, salience-ordered.

    **One query**, for every planned speaker at once — the recall path calls this once per
    turn, not once per beat, which is only possible because the turn is planned up front
    and the plan is binding.

    Visibility is the union of two rules: within the *current* scenario, branch lineage
    (:func:`lineage_caps`); for every *other* scenario in the storyline, the most recently
    updated play-through (:func:`_other_scenario_sessions`).
    """
    ids = [cid for cid in character_ids if cid]
    if not ids:
        return []

    scopes = []
    for session_id, cap in lineage_caps(db, session):
        if cap is None:
            scopes.append(CharacterMemory.session_id == session_id)
        else:
            scopes.append(
                and_(CharacterMemory.session_id == session_id, CharacterMemory.turn_seq <= cap)
            )
    others = _other_scenario_sessions(db, storyline_id, session.scenario_id)
    if others:
        scopes.append(CharacterMemory.session_id.in_(others))

    return list(
        db.scalars(
            select(CharacterMemory)
            .where(
                CharacterMemory.storyline_id == storyline_id,
                CharacterMemory.character_id.in_(ids),
                or_(*scopes),
            )
            .order_by(CharacterMemory.salience.desc(), CharacterMemory.turn_seq.desc())
            .limit(limit)
        )
    )


# ---- recall bookkeeping + rewind ---------------------------------------------


def mark_recalled(db: Session, memory_ids: list[str], *, session_id: str, seq: int) -> None:
    """Record that these memories were surfaced, so cooldown and fade have a clock."""
    if not memory_ids:
        return
    for row in db.scalars(
        select(CharacterMemory).where(CharacterMemory.id.in_(memory_ids))
    ):
        row.last_recalled_seq = seq
        row.last_recalled_session_id = session_id
        db.add(row)


def delete_after(db: Session, session_id: str, *, after_seq: int) -> int:
    """Forget everything this session formed after ``after_seq``. Returns the row count.

    Runs inside the caller's transaction, unlike the graph's best-effort prune: a rewound
    scene that still remembers what it removed is the exact defect the record controls
    exist to prevent.
    """
    result = db.execute(
        delete(CharacterMemory).where(
            CharacterMemory.session_id == session_id,
            CharacterMemory.turn_seq > after_seq,
        )
    )
    return int(result.rowcount or 0)
