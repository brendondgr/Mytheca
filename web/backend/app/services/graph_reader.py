"""The Story-Graph read path on scenario load (§7.2 templates + §7.4 read-only).

The hot path is reads only (§8). When a Scenario is loaded, Velora:
  1. **materializes** the scenario's cast + setting from Postgres into Neo4j —
     an idempotent upsert (so the seeded world appears in the graph on first load,
     and the present_at "who's in this scene" edges (§4.3) are drawn);
  2. **reads** the resulting subgraph through pre-written, parameterized Cypher
     **templates** (§7.2) in a **read-only** transaction (§7.4 — a stray write is
     rejected by the server, not by convention).

Everything is best-effort: when Neo4j is disabled or unreachable the orchestrator
returns ``available: False`` with empty lists, so loading a scenario never breaks.
The vector entry-point (§7.1) and Text2Cypher (§7.3) for the long tail / user types
are deferred seams (their prerequisites — an embedding stack and a hot-path
consumer — don't exist yet); the registry's ``schema_blob`` is already compiled for
them (services/type_registry.schema_blob).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core import neo4j
from app.models import Character, Scenario, Setting
from app.services import crud, graph_writer

logger = logging.getLogger("velora.graph")

_STRUCTURAL_KEYS = {"id", "type", "label", "storyline"}

# Default metadata for the derived live-casting edge (§4.3 present_at).
_PRESENT_AT_META = {"weight": 1.0, "visibility": "public", "status": "active"}

# ---- parameterized templates (§7.2) — read-only --------------------------

_NODES_BY_ID = (
    "MATCH (n:Node) WHERE n.id IN $ids "
    "RETURN n.id AS id, n.type AS type, n.label AS label, "
    "n.storyline AS storyline, properties(n) AS props"
)
_EDGES_AMONG = (
    "MATCH (a:Node)-[r]->(b:Node) WHERE a.id IN $ids AND b.id IN $ids "
    "RETURN a.id AS source, b.id AS target, type(r) AS type, properties(r) AS props"
)
_PRESENCE_CASTING = (
    "MATCH (c:Character)-[:present_at]->(s:Setting {id: $setting_id}) "
    "RETURN c.id AS id, c.label AS label"
)
_SECRET_REACHABILITY = (
    "MATCH (c:Character {id: $character_id})-[:knows|suspects]->(sec:Secret) "
    "RETURN sec.id AS id, sec.label AS label"
)


def _node_from_row(row: Any) -> dict:
    props = dict(row["props"] or {})
    metadata = {k: v for k, v in props.items() if k not in _STRUCTURAL_KEYS}
    return {
        "id": row["id"],
        "type": row["type"],
        "label": row["label"],
        "storyline": row["storyline"],
        "metadata": metadata,
    }


def _edge_from_row(row: Any) -> dict:
    return {
        "source": row["source"],
        "target": row["target"],
        "type": row["type"],
        "metadata": dict(row["props"] or {}),
    }


def scenario_subgraph(session: Any, ids: list[str]) -> tuple[list[dict], list[dict]]:
    """The built-in traversal: every node in ``ids`` and every edge among them."""
    nodes = [_node_from_row(r) for r in session.run(_NODES_BY_ID, ids=ids)]
    edges = [_edge_from_row(r) for r in session.run(_EDGES_AMONG, ids=ids)]
    return nodes, edges


def presence_casting(session: Any, setting_id: str) -> list[dict]:
    """Who is present at a setting — the live casting query (§4.3/§9)."""
    return [{"id": r["id"], "label": r["label"]} for r in session.run(_PRESENCE_CASTING, setting_id=setting_id)]


def secret_reachability(session: Any, character_id: str) -> list[dict]:
    """Secrets a character knows/suspects — one-hop reachability (§5.4/§9)."""
    return [{"id": r["id"], "label": r["label"]} for r in session.run(_SECRET_REACHABILITY, character_id=character_id)]


# ---- materialize-on-load (idempotent upsert from Postgres) ----------------


def ensure_scenario_materialized(db: Session, scenario: Scenario) -> list[str]:
    """Upsert the scenario's cast + setting (and present_at edges) into Neo4j.

    Idempotent (MERGE). Returns the node ids that make up the scenario subgraph so
    the read step can scope to them. Best-effort at the orchestrator level.
    """
    ids: list[str] = []
    with neo4j.write_session() as session:
        setting = db.get(Setting, scenario.setting_id) if scenario.setting_id else None
        if setting is not None:
            graph_writer.upsert_node(
                session,
                node_id=setting.id,
                type_name="Setting",
                label=setting.name,
                storyline=setting.storyline_id,
                metadata=graph_writer.node_props_from_setting(setting),
            )
            ids.append(setting.id)
        for cid in scenario.cast_ids or []:
            char = db.get(Character, cid)
            if char is None:
                continue
            graph_writer.upsert_node(
                session,
                node_id=char.id,
                type_name="Character",
                label=char.name,
                storyline=char.storyline_id,
                metadata=graph_writer.node_props_from_character(char),
            )
            ids.append(char.id)
            if setting is not None:
                graph_writer.upsert_edge(
                    session,
                    source_id=char.id,
                    target_id=setting.id,
                    type_name="present_at",
                    metadata=dict(_PRESENT_AT_META),
                )
    return ids


# ---- orchestrator (what the route calls) ----------------------------------


def scenario_graph(db: Session, scenario_id: str) -> dict:
    """Load a scenario's subgraph: materialize from Postgres, then read (§7.2).

    Always returns a serializable dict. ``available`` is False (with empty lists)
    when the graph is disabled or unreachable — loading a scenario never fails on
    the graph.
    """
    scenario = crud.get_scenario(db, scenario_id)  # 404 if the scenario is unknown
    empty = {"available": False, "scenario_id": scenario_id, "nodes": [], "edges": []}
    if not neo4j.is_enabled():
        return empty
    try:
        ids = ensure_scenario_materialized(db, scenario)
        with neo4j.read_session() as session:  # READ access mode (§7.4)
            nodes, edges = scenario_subgraph(session, ids)
        return {"available": True, "scenario_id": scenario_id, "nodes": nodes, "edges": edges}
    except Exception as exc:
        logger.warning("scenario graph (%s) unavailable: %s", scenario_id, exc)
        return empty
