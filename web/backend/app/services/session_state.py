"""History mutation — the one place a play-through's record is changed after the fact.

Rewind, branch, edit and re-roll are four faces of the same three operations: cut rows,
re-derive what was computed from them, and rebuild the caches that mirrored them. If each
endpoint implemented that itself they would drift, and the drift would be *silent* — a stale
Redis buffer feeding the model a beat the player deleted reads as the model ignoring them.

What each store does on a mutation:

* **Postgres** is canonical. Rows are cut here; everything else is re-derived from what
  survives.
* **Redis** holds two things and they need opposite treatment. The recent-turn buffer is a
  cache of the rows, so it is **rebuilt**. Per-character *interior state* is not derived from
  any surviving row — it is a stance a model formed from beats that are now gone — so it is
  **cleared**, and the next turn's reflection writes a fresh one. Without Redis both are
  no-ops and the turn still runs.
* **The session's outstanding direction** (``standing_direction``) is pruned to what turns
  that survived asked for. Each row carries the ``Event.seq`` of the turn that raised it, so
  the cut is exact; a debt owed to a deleted turn has the scene chasing something the player
  just un-asked-for, in the very next beat after a rewind.
* **Neo4j** holds one ``:Event`` node per consequence-bearing turn at a deterministic id, so
  those are pruned by id. Relationship *edges* written by cut turns are **not** rolled back —
  the graph is a best-effort accumulator with no per-turn provenance index, and inventing one
  is out of scope (recorded in ``docs/checklist.md``).
* **Session stats** are cleared and **replayed** from the surviving ``state_update`` events
  on top of the authored baseline (owner decision D-1). This needs no per-event provenance,
  which is why it also works for rows written before this program.
* **Qdrant is not involved.** Verified: nothing on the play path writes to the vector store
  (``rag.indexer`` is called only from ``crud``, ``storyline_apply``, ``routes/rag`` and
  ``bootstrap``). Transcript text is never indexed, so an edited beat has no stale embedding.

Presence needs no equivalent: ``presence.current_presence`` already derives from the
surviving ``character_status_change`` rows, so truncation re-derives it for free.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.core.ids import new_id
from app.memory import buffer, interior
from app.models import Event, PlaySession, TurnTrace
from app.services import graph_writer, history_compaction, session_stats

#: Event types that carry prose into the recent-turn buffer, and the role each is pushed as.
#: Mirrors what the live turn does (``turn_setup`` for the player's line, ``Emitter`` for the
#: rest) — the rebuild has to reproduce the same buffer the turn would have written.
#: ``internal_thought`` is deliberately absent: it is never buffered, so later speakers never
#: condition on another character's private deliberation.
_BUFFER_ROLES = {
    "narration": "narrator",
    "character_prose": "character",
    "character_dialogue": "character",
    "character_action": "character",
}


@dataclass
class TruncationResult:
    """What a cut removed, for the caller to report and for tests to assert on."""

    cut_seq: int
    removed_events: int = 0
    removed_traces: int = 0
    removed_turn_seqs: list[int] = field(default_factory=list)
    replayed_stat_keys: list[str] = field(default_factory=list)
    #: Interior-state keys dropped. Always 0 without Redis — diagnostics, never branched on.
    cleared_interior: int = 0
    #: Outstanding requirements dropped because the turn that raised them was cut.
    dropped_standing: int = 0


# ---- preconditions --------------------------------------------------------


def latest_seq(db: Session, session_id: str) -> int:
    """The highest ``seq`` in a session, or ``-1`` when it holds nothing yet."""
    current = db.scalar(select(func.max(Event.seq)).where(Event.session_id == session_id))
    return -1 if current is None else int(current)


def require_expected_seq(db: Session, session_id: str, expected: int | None) -> None:
    """Optimistic-concurrency precondition: 409 when the caller's view is stale.

    A lock would be worse. A ``busy`` column has to be cleared in a ``finally`` that a client
    abort can skip, which leaves a play-through permanently wedged; a stale precondition
    fails safe and needs no state. ``None`` skips the check, for callers that genuinely do
    not care (a fresh branch of an untouched session).
    """
    if expected is None:
        return
    actual = latest_seq(db, session_id)
    if actual != expected:
        raise APIError(
            409,
            "conflict",
            "This play-through moved on since you looked at it. Reload the scene and try again.",
            {"expectedSeq": expected, "actualSeq": actual},
        )


# ---- reading the shape of the history -------------------------------------


def turn_boundary(db: Session, session_id: str, event_id: str) -> Event:
    """The ``user_turn`` row that opened the turn containing ``event_id``.

    Rewind cuts at a **turn boundary**, not an arbitrary beat: ``turn_traces`` are keyed by
    the turn's opening seq, and presence and stats are re-derived per turn, so a mid-turn cut
    would leave half a trace describing beats that no longer exist. Beat-level surgery is
    still available — that is what edit and re-roll are for.
    """
    row = db.get(Event, event_id)
    if row is None or row.session_id != session_id:
        raise APIError(404, "invalid_reference", "Unknown event for this play-through.")
    opening = db.scalars(
        select(Event)
        .where(
            Event.session_id == session_id,
            Event.type == "user_turn",
            Event.seq <= row.seq,
        )
        .order_by(Event.seq.desc())
        .limit(1)
    ).first()
    if opening is None:
        raise APIError(400, "bad_request", "That beat is not part of a player turn.")
    return opening


# ---- the primitives -------------------------------------------------------


def rebuild_buffer(db: Session, session_id: str) -> int:
    """Rebuild the Redis recent-turn buffer from the surviving rows, oldest first.

    Returns the number of beats **offered** to the buffer, not the number stored: with no
    Redis, ``clear`` and ``push_turn`` are both silent no-ops, so the count is the same but
    nothing is written. That is deliberate — the return value is for diagnostics, and a
    caller must never branch on whether the cache happened to be available.
    """
    buffer.clear(session_id)
    pushed = 0
    for row in db.scalars(
        select(Event).where(Event.session_id == session_id).order_by(Event.seq)
    ):
        data = row.data if isinstance(row.data, dict) else {}
        text = str(data.get("text") or "").strip()
        if not text:
            continue
        if row.type == "user_turn":
            # Under POV the player's line was buffered as that character's own beat, so
            # later speakers react to "Mei said X" rather than to a disembodied player.
            pov = data.get("pov")
            if pov:
                buffer.push_turn(session_id, "character", text, character_id=str(pov))
            else:
                buffer.push_turn(session_id, "player", text)
            pushed += 1
            continue
        role = _BUFFER_ROLES.get(row.type)
        if role is None:
            continue
        buffer.push_turn(session_id, role, text, character_id=data.get("characterId"))
        pushed += 1
    return pushed


def buffered_rows_after(db: Session, session_id: str, seq: int) -> int:
    """How many of this session's buffered beats sit above ``seq``.

    The one caller is ``assembler.assemble_context``, trimming a **replay** window back to
    the beat before the one being re-rolled. It lives here so there is a single definition of
    "a row the buffer holds": this and ``rebuild_buffer`` have to agree exactly, or the trim
    cuts the wrong number of entries off the end of the window.
    """
    count = 0
    for row in db.scalars(
        select(Event).where(Event.session_id == session_id, Event.seq > seq)
    ):
        data = row.data if isinstance(row.data, dict) else {}
        if not str(data.get("text") or "").strip():
            continue
        if row.type == "user_turn" or row.type in _BUFFER_ROLES:
            count += 1
    return count


def standing_through(session: PlaySession, *, through_seq: int) -> list[dict]:
    """The session's outstanding direction, keeping only what turns up to ``through_seq``
    raised.

    ``fromTurn`` is the ``Event.seq`` of the turn that first asked for a requirement
    (``direction_runtime.to_standing``), so this is an exact cut and not a heuristic.

    A row with **no** usable ``fromTurn`` — written before the field existed, or hand-edited
    — is **kept**. That is the safe direction, and it is the asymmetry the direction system
    uses everywhere else: an un-cancelled requirement costs a beat and is reported as
    outstanding, while a wrongly-cancelled one silently loses what the player asked for.
    """
    rows = session.standing_direction if isinstance(session.standing_direction, list) else []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raised = row.get("fromTurn")
        if isinstance(raised, int) and raised > through_seq:
            continue
        out.append(row)
    return out


def replay_stats(db: Session, session_id: str, character_ids: list[str] | None = None) -> list[str]:
    """Re-derive this play-through's stat values from the surviving ``state_update`` rows.

    Clear, then walk the survivors in ``seq`` order applying each one's final ``value``. The
    authored baseline is the starting point, so a stat no surviving event touched simply
    reads through to it. Returns the ``characterId:key`` pairs that ended up set.

    This is why owner decision D-1 mattered: with values scoped to the play-through there is
    no need to record what each event changed *from*, so a rewind is correct even for rows
    written before any of this existed.
    """
    session_stats.clear(db, session_id, character_ids)
    latest: dict[tuple[str, str], int] = {}
    for row in db.scalars(
        select(Event)
        .where(Event.session_id == session_id, Event.type == "state_update")
        .order_by(Event.seq)
    ):
        data = row.data if isinstance(row.data, dict) else {}
        stat = data.get("stat") or {}
        cid = stat.get("characterId")
        key = stat.get("key")
        value = stat.get("value")
        if not cid or not key or value is None:
            continue
        if character_ids is not None and cid not in character_ids:
            continue
        latest[(str(cid), str(key))] = int(value)
    by_char: dict[str, dict[str, int]] = {}
    for (cid, key), value in latest.items():
        by_char.setdefault(cid, {})[key] = value
    for cid, values in by_char.items():
        session_stats.apply(db, session_id, cid, values)
    return [f"{cid}:{key}" for (cid, key) in latest]


#: Beat types whose prose the player may rewrite. Everything else is either machinery
#: (``state_update``, ``branch_choices``, ``character_status_change``) or a derived artefact
#: the text does not own (``scene_image`` — its caption is editable, its prose is not).
#: ``internal_thought`` is editable too: it is a beat the player reads, and a slip in one is
#: as visible as a slip in speech.
EDITABLE_TYPES = frozenset(
    {
        "narration",
        "character_prose",
        "character_dialogue",
        "character_action",
        "internal_thought",
        "user_turn",
    }
)


def edit_beat(db: Session, session_id: str, event_id: str, text: str) -> Event:
    """Rewrite one beat's prose in place, then rebuild the buffer.

    The rebuild is the point. Without it the model keeps reading the **old** wording out of
    Redis while the player reads the new one — the exact class of silent divergence this
    module exists to prevent, and one that would surface as the cast reacting to a line that
    is no longer on screen.

    Editing a ``user_turn`` is allowed for **any** player line, not just the most recent. The
    row is rewritten and play continues from wherever the player sends next; discarding what
    followed is what rewind is for, and conflating the two would make every edit destructive.
    """
    row = db.get(Event, event_id)
    if row is None or row.session_id != session_id:
        raise APIError(404, "invalid_reference", "Unknown beat for this play-through.")
    if row.type not in EDITABLE_TYPES:
        raise APIError(
            422,
            "unprocessable",
            f"A {row.type.replace('_', ' ')} beat has no prose to edit.",
            {"type": row.type},
        )
    data = dict(row.data) if isinstance(row.data, dict) else {}
    data["text"] = text
    #: Marks the row as player-authored, so an export or a later reader can tell the
    #: difference between what the model wrote and what the player rewrote.
    data["editedByPlayer"] = True
    row.data = data
    # The scene's memory may describe the wording that was just rewritten. It sits beside the
    # buffer rebuild on purpose: both answer "history changed under us", and splitting them
    # across two call sites is how one of them gets forgotten.
    history_compaction.invalidate_after(db, session_id, row.seq)
    db.commit()
    db.refresh(row)
    rebuild_buffer(db, session_id)
    return row


def prune_graph_events(session_id: str, removed_turn_seqs: list[int]) -> None:
    """Drop the ``:Event`` node each cut turn wrote. Best-effort; a disabled Neo4j no-ops."""
    for turn_seq in removed_turn_seqs:
        graph_writer.remove_node(f"evt_{session_id}_{turn_seq}")


def truncate_session(db: Session, session_id: str, *, after_seq: int) -> TruncationResult:
    """Cut everything after ``after_seq`` and re-derive what depended on it.

    ``after_seq`` is **inclusive of what stays**: rows with ``seq > after_seq`` go. Pass the
    opening ``user_turn``'s seq minus one to remove that whole turn.
    """
    doomed = list(
        db.scalars(
            select(Event)
            .where(Event.session_id == session_id, Event.seq > after_seq)
            .order_by(Event.seq)
        )
    )
    result = TruncationResult(cut_seq=after_seq)
    result.removed_turn_seqs = [e.seq for e in doomed if e.type == "user_turn"]
    result.removed_events = len(doomed)

    if doomed:
        db.query(Event).filter(
            Event.session_id == session_id, Event.seq > after_seq
        ).delete(synchronize_session=False)
    # Traces are keyed by their turn's opening seq, so they go with the turns they describe.
    result.removed_traces = int(
        db.query(TurnTrace)
        .filter(TurnTrace.session_id == session_id, TurnTrace.turn > after_seq)
        .delete(synchronize_session=False)
    )
    # A summary covering any of the cut beats now describes a scene that did not happen.
    # Clearing it is not tidiness: a stale summary is worse than none, because the cast would
    # confidently remember the very beats the player just removed.
    history_compaction.invalidate_after(db, session_id, after_seq + 1)
    session = db.get(PlaySession, session_id)
    if session is not None:
        surviving = standing_through(session, through_seq=after_seq)
        result.dropped_standing = len(session.standing_direction or []) - len(surviving)
        # Written straight onto the column rather than through
        # ``direction_runtime.save_standing``: importing that module here would close the
        # loop ``assembler -> session_state -> direction_runtime -> assembler``. Its one rule
        # — an empty list is stored as NULL, so "owes nothing" has a single representation —
        # is reproduced by the ``or None`` and asserted by a test.
        session.standing_direction = surviving or None
        db.add(session)
    db.commit()

    prune_graph_events(session_id, result.removed_turn_seqs)
    result.replayed_stat_keys = replay_stats(db, session_id)
    rebuild_buffer(db, session_id)
    # Cleared, not rebuilt: a character's stance was derived from beats that are now gone and
    # there is no surviving row to re-derive it from. It sits beside the buffer rebuild
    # because both answer "history changed under us", and splitting them across two call
    # sites is how one of them gets forgotten.
    result.cleared_interior = interior.clear_session(session_id)
    return result


def copy_history(
    db: Session, source_session_id: str, target_session_id: str, *, through_seq: int
) -> int:
    """Copy a play-through's history onto another, up to and including ``through_seq``.

    Rows get **fresh ids** (they are new events) but keep their **original ``seq``**, so
    ordering is preserved and ``UNIQUE (session_id, seq)`` still holds inside the new
    session. The source is untouched — that is what makes a branch a branch.
    """
    copied = 0
    for row in db.scalars(
        select(Event)
        .where(Event.session_id == source_session_id, Event.seq <= through_seq)
        .order_by(Event.seq)
    ):
        db.add(
            Event(
                id=new_id("ev"),
                type=row.type,
                seq=row.seq,
                scenario_id=row.scenario_id,
                session_id=target_session_id,
                ts=row.ts,
                visibility=row.visibility,
                data=dict(row.data) if isinstance(row.data, dict) else row.data,
            )
        )
        copied += 1
    for trace in db.scalars(
        select(TurnTrace)
        .where(TurnTrace.session_id == source_session_id, TurnTrace.turn <= through_seq)
        .order_by(TurnTrace.turn, TurnTrace.n)
    ):
        db.add(
            TurnTrace(
                session_id=target_session_id,
                scenario_id=trace.scenario_id,
                turn=trace.turn,
                n=trace.n,
                step=trace.step,
                title=trace.title,
                detail=trace.detail,
                data=trace.data,
            )
        )
    # A branch starts with no memory of its own. Copying the parent's summary would be
    # *nearly* right — it covers beats the fork inherited — but it would then go stale the
    # moment the branch diverged, with no seq to notice by. The fork simply re-compacts.
    #
    # The outstanding **direction** is the opposite case and IS carried: it is not a derived
    # record of what happened, it is what the player asked for and has not been given. A fork
    # that dropped it would make "branch here and try again" quietly different from carrying
    # on. Pruned to the fork point by the same rule a rewind uses.
    source = db.get(PlaySession, source_session_id)
    target = db.get(PlaySession, target_session_id)
    if target is not None:
        target.summary_text = None
        target.summary_through_seq = None
        target.summary_updated_at = None
        if source is not None:
            target.standing_direction = (
                standing_through(source, through_seq=through_seq) or None
            )
        db.add(target)
    db.commit()
    session_stats.copy(db, source_session_id, target_session_id)
    rebuild_buffer(db, target_session_id)
    return copied
