"""Cold-path turn-writer (Band 3) — durable consequences, off the hot path.

After the stream is delivered, the turn-writer reifies the turn's durable
consequences into the Story Graph: each is routed by the **"…toward whom?" rule** —
a change *with* a relational target becomes an **edge** (with a reified
``:Consequence`` node as its shared provenance), one *without* is a **stat** (already
applied + clamped on the hot path, recorded here only for audit) — and an ``:Event``
node is appended so the moment is traversable (and RAG-indexable) later.

It **never blocks the player** (it runs after the last event is yielded) and is
**best-effort**: with Neo4j disabled/down, or no consequences this turn, it is a clean
no-op. Postgres stays canonical — a graph outage degrades to "writes replayed later,"
not a lost turn. (Per-character interior state from §10 is volatile Redis state and is
deliberately *not* written here.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core import neo4j
from app.services import graph_writer

logger = logging.getLogger("mytheca.turn")


@dataclass
class Consequence:
    """One durable change implied by the turn, routed by the '…toward whom?' rule."""

    id: str
    summary: str
    source_id: str  # whose change this is (the character)
    reason: str = ""
    target_id: str | None = None  # the relational target → edge; None → stat-only
    edge_type: str | None = None  # the relationship type when relational (e.g. "wary_of")
    weight: float | None = None
    origin: dict | None = None


def write_turn(
    db,
    *,
    scenario,
    session_id: str,
    turn_seq: int,
    summary: str,
    consequences: list[Consequence],
    present_ids: list[str] | None = None,
) -> None:
    """Reify the turn's consequences + append an :Event node (best-effort, non-blocking).

    No-op when there are no consequences (the cold path runs on *consequence turns*
    only) or when the graph is disabled/unreachable. ``present_ids`` are the characters
    in the room, linked to the turn's ``:Event`` so the moment is reachable from the
    people in it and not only from the place it happened.
    """
    if not consequences:
        return
    if not neo4j.is_enabled():
        return
    try:
        with neo4j.write_session() as session:
            for cons in consequences:
                _write_consequence(session, scenario.storyline_id, cons, session_id, turn_seq)
            _append_event(
                session, scenario, session_id, turn_seq, summary, present_ids or []
            )
    except Exception as exc:  # never surfaces to the player — Postgres stays canonical
        logger.warning("cold-path turn-writer skipped (session %s): %s", session_id, exc)


def _write_consequence(
    session, storyline_id: str, cons: Consequence, session_id: str, turn_seq: int
) -> None:
    """Reify the shared :Consequence node; add the edge when the change is relational."""
    graph_writer.attach_consequence(
        session,
        target_id=cons.source_id,
        record={
            "id": cons.id,
            "reason": cons.reason or cons.summary,
            "origin": cons.origin,
            "delta": cons.weight,
            "status": "active",
        },
        session_id=session_id,
        turn_seq=turn_seq,
    )
    # "…toward whom?": a relational target makes it an edge; otherwise it was a stat
    # (already applied + clamped on the hot path during validation).
    if cons.target_id and cons.edge_type:
        graph_writer.upsert_edge(
            session,
            source_id=cons.source_id,
            target_id=cons.target_id,
            type_name=cons.edge_type,
            # ``reason`` matches the shape ``relationships.ensure_seeded`` writes at seed
            # time, so ``graph_reader.relationship_context`` renders a tie formed in play
            # and a tie read off a bio identically. Without it every relationship the
            # story itself created arrived at the next scene as a bare verb and a weight,
            # and the model invented a reason for it — routinely one contradicting the
            # scene the player had actually played.
            metadata={
                "via": cons.id,
                "weight": cons.weight,
                "reason": cons.reason or cons.summary,
                "origin": "play",
                "status": "active",
            },
            session_id=session_id,
            turn_seq=turn_seq,
        )


def _append_event(
    session,
    scenario,
    session_id: str,
    turn_seq: int,
    summary: str,
    present_ids: list[str],
) -> None:
    """Append an :Event node for the turn, tied to its setting and to who was there."""
    event_id = f"evt_{session_id}_{turn_seq}"
    graph_writer.upsert_node(
        session,
        node_id=event_id,
        type_name="Event",
        label=summary[:80],
        storyline=scenario.storyline_id,
        metadata={
            "summary": summary,
            "scenario": scenario.id,
            "session": session_id,
            "seq": turn_seq,
        },
    )
    if scenario.setting_id:
        graph_writer.upsert_edge(
            session,
            source_id=event_id,
            target_id=scenario.setting_id,
            type_name="occurred_at",
            metadata={},
        )
    # Who was in the room. ``involved`` has been a built-in edge type since the registry was
    # written and nothing had ever written one, so an event was reachable only from its
    # *setting* — "what has happened between these two people" was a question the graph had
    # no path to answer. Deliberately not provenance-stamped: these edges belong to the
    # Event node, and pruning that node on rewind takes them with it.
    for character_id in present_ids:
        graph_writer.upsert_edge(
            session,
            source_id=event_id,
            target_id=character_id,
            type_name="involved",
            metadata={},
        )
