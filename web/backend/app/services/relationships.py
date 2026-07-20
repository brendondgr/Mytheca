"""Relationship seeding — populate character↔character graph edges from bios (P3).

Runs once per new play session (best-effort, off the hot path): if the cast has no
relationship edges in the graph yet, extract the initial ones from the authored bios
(:mod:`app.agents.relationship_agent`) and write them to Neo4j. Idempotent (skips when
edges already exist) and fully best-effort — a disabled/unreachable graph, an
unconfigured LLM, or fewer than two characters all yield a clean no-op. The cold path
then evolves these edges during play (see the P5 relational consequence).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agents import relationship_agent
from app.agents._common import resolve_llm
from app.agents.relationship_agent import RELATIONSHIP_TYPES
from app.core import neo4j
from app.core.errors import APIError
from app.models import Character, Scenario
from app.services import graph_reader, graph_writer

logger = logging.getLogger("mytheca.graph")

# Bio fields folded into the extractor's view of a character (authored, not stats).
_BIO_FIELDS = ("role", "background", "personality", "traits", "secret", "goal")


def _bio(char: Character) -> str:
    parts = [f"{f}: {v.strip()}" for f in _BIO_FIELDS if (v := getattr(char, f, None))]
    return "\n".join(parts)


def _already_seeded(ids: list[str]) -> bool:
    """True if the cast already has any character↔character relationship edge."""
    with neo4j.read_session() as session:
        _, edges = graph_reader.scenario_subgraph(session, ids)
    return any(e.get("type") in RELATIONSHIP_TYPES for e in edges)


def _edge_summary(names: dict[str, str], edge) -> str:
    """A human line for one seeded edge: ``"A <type> B — reason"`` (Graph trace detail)."""
    src = names.get(edge.source_id, edge.source_id)
    tgt = names.get(edge.target_id, edge.target_id)
    line = f"{src} {edge.type.replace('_', ' ')} {tgt}"
    return f"{line} — {edge.reason}" if edge.reason else line


def ensure_seeded(db: Session, scenario: Scenario) -> list[str]:
    """Seed initial relationship edges from the cast bios; return one summary per edge.

    Best-effort + idempotent: an empty list when the graph is off, the cast is too small,
    the edges already exist, the LLM is unconfigured, or the extractor found nothing. Each
    summary reads ``"A <type> B — reason"`` so the Inspector's Graph trace can show what
    was actually written, not just a count.
    """
    if not neo4j.is_enabled():
        return []
    cast = [c for cid in (scenario.cast_ids or []) if (c := db.get(Character, cid)) is not None]
    if len(cast) < 2:
        return []
    ids = [c.id for c in cast]
    try:
        if _already_seeded(ids):
            return []
    except Exception as exc:  # pragma: no cover - defensive; never blocks a turn
        logger.debug("relationship seed idempotency check skipped: %s", exc)
        return []

    try:
        conn = resolve_llm(db)
    except APIError:
        return []
    edges = relationship_agent.extract(
        conn, [{"id": c.id, "name": c.name, "bio": _bio(c)} for c in cast]
    )
    if not edges:
        return []

    try:
        with neo4j.write_session() as session:
            # Make sure the character nodes exist (usually already materialized on load).
            for c in cast:
                graph_writer.upsert_node(
                    session,
                    node_id=c.id,
                    type_name="Character",
                    label=c.name,
                    storyline=c.storyline_id,
                    metadata=graph_writer.node_props_from_character(c),
                )
            for edge in edges:
                graph_writer.upsert_edge(
                    session,
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    type_name=edge.type,
                    metadata={"weight": 1.0, "origin": "seed", "status": "active", "reason": edge.reason},
                )
    except Exception as exc:  # never surfaces to the player — the graph is best-effort
        logger.warning("relationship seed skipped (scenario %s): %s", scenario.id, exc)
        return []
    names = {c.id: c.name for c in cast}
    return [_edge_summary(names, edge) for edge in edges]
