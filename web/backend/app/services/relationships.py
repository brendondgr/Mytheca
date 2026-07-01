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

logger = logging.getLogger("velora.graph")

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


def ensure_seeded(db: Session, scenario: Scenario) -> int:
    """Seed initial relationship edges from the cast bios; return how many were written.

    Best-effort + idempotent: ``0`` when the graph is off, the cast is too small, the
    edges already exist, the LLM is unconfigured, or the extractor found nothing.
    """
    if not neo4j.is_enabled():
        return 0
    cast = [c for cid in (scenario.cast_ids or []) if (c := db.get(Character, cid)) is not None]
    if len(cast) < 2:
        return 0
    ids = [c.id for c in cast]
    try:
        if _already_seeded(ids):
            return 0
    except Exception as exc:  # pragma: no cover - defensive; never blocks a turn
        logger.debug("relationship seed idempotency check skipped: %s", exc)
        return 0

    try:
        conn = resolve_llm(db)
    except APIError:
        return 0
    edges = relationship_agent.extract(
        conn, [{"id": c.id, "name": c.name, "bio": _bio(c)} for c in cast]
    )
    if not edges:
        return 0

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
        return 0
    return len(edges)
