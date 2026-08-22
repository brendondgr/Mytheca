"""The Story-Graph read path on scenario load (§7.2 templates + §7.4 read-only).

The hot path is reads only (§8). When a Scenario is loaded, Mytheca:
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

logger = logging.getLogger("mytheca.graph")

_STRUCTURAL_KEYS = {"id", "type", "label", "storyline"}

# Character↔character edge types surfaced as "relationships" (mirrors the registry /
# relationship_agent; kept local to avoid an agents→services import cycle).
_RELATIONSHIP_TYPES = frozenset(
    {"loves", "trusts", "fears", "resents", "allied_with", "at_war_with", "knows", "suspects"}
)

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
# A speaker's relationships to the others in scene: direct edges (either direction) and
# 2-hop shared connections through a third character. Used to ground a response in how
# the speaker actually relates to whoever they are addressing (Reactive Turn Director D4).
_REL_DIRECT = (
    "MATCH (a:Character {id: $id})-[r]-(b:Character) WHERE b.id IN $others "
    "RETURN b.id AS target, b.label AS name, type(r) AS type, "
    "startNode(r).id AS src, properties(r) AS props"
)
#: A speaker's direct ties to characters who are NOT in this scene.
#:
#: The scene's own cast is excluded rather than filtered afterwards, so the LIMIT applies to
#: the rows that will actually be used — a speaker with thirty in-scene edges would otherwise
#: return thirty rows and none of them off-scene. Storyline-scoped, so a tie cannot reach
#: across worlds. Read-only, parameterised, and capped: this is the only query the tie-scope
#: feature adds, and it runs at most once per beat and only at the `world` stop.
_REL_OFFSCENE = (
    "MATCH (a:Character {id: $id})-[r]-(b:Character) "
    "WHERE NOT b.id IN $scene_ids AND b.id <> $id AND b.storyline = $storyline "
    "RETURN DISTINCT b.id AS target, b.label AS name, type(r) AS type, "
    "startNode(r).id AS src, properties(r) AS props LIMIT 8"
)
_REL_INDIRECT = (
    "MATCH (a:Character {id: $id})-[]-(mid:Character)-[]-(b:Character) "
    "WHERE b.id IN $others AND mid.id <> $id AND NOT mid.id IN $others AND a.id <> b.id "
    "RETURN DISTINCT b.id AS target, b.label AS name, mid.label AS via LIMIT 25"
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


def relationship_context(character_id: str, other_ids: list[str]) -> dict:
    """A speaker's relationships to ``other_ids``: direct edges + 2-hop shared links.

    Best-effort (Reactive Turn Director D4): returns ``{"direct": [...], "indirect": [...]}``,
    empty when the graph is disabled/unreachable or there is no one to relate to. ``direct``
    entries carry ``outgoing`` (True = the speaker feels toward the other; False = the other
    feels toward the speaker); ``indirect`` entries are shared connections through a third
    character (undirected — a "you both know X" signal).
    """
    empty: dict = {"direct": [], "indirect": []}
    others = [cid for cid in other_ids if cid and cid != character_id]
    if not others or not neo4j.is_enabled():
        return empty
    try:
        with neo4j.read_session() as session:
            direct = [
                {
                    "target": r["target"],
                    "name": r["name"],
                    "type": r["type"],
                    "outgoing": r["src"] == character_id,
                    "reason": (dict(r["props"] or {})).get("reason", ""),
                }
                for r in session.run(_REL_DIRECT, id=character_id, others=others)
            ]
            indirect = [
                {"target": r["target"], "name": r["name"], "via": r["via"]}
                for r in session.run(_REL_INDIRECT, id=character_id, others=others)
            ]
        return {"direct": direct, "indirect": indirect}
    except Exception as exc:  # pragma: no cover - defensive; never blocks a turn
        logger.debug("relationship_context (%s) unavailable: %s", character_id, exc)
        return empty


def offscene_ties(character_id: str, scene_ids: list[str], storyline_id: str) -> list[dict]:
    """A speaker's direct ties to characters **not** in this scene.

    Best-effort in exactly the shape :func:`relationship_context` uses — the graph being off
    or unreachable returns ``[]`` and the beat is byte-identical to one with no ties at all.
    That is the whole degradation story for the tie-scope feature: an install without Neo4j
    behaves today's way at every stop.

    Entries carry ``outgoing`` (True = the speaker feels toward the other) so the caller can
    render direction, matching ``relationship_context``'s ``direct`` rows.
    """
    if not character_id or not neo4j.is_enabled():
        return []
    try:
        with neo4j.read_session() as session:
            return [
                {
                    "target": r["target"],
                    "name": r["name"],
                    "type": r["type"],
                    "outgoing": r["src"] == character_id,
                    "reason": (dict(r["props"] or {})).get("reason", ""),
                }
                for r in session.run(
                    _REL_OFFSCENE,
                    id=character_id,
                    scene_ids=list(scene_ids or []),
                    storyline=storyline_id,
                )
            ]
    except Exception as exc:  # pragma: no cover - defensive; never blocks a turn
        logger.debug("offscene_ties (%s) unavailable: %s", character_id, exc)
        return []


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


def scenario_relationships(db: Session, scenario_id: str) -> list[dict]:
    """The scenario's character↔character relationships, resolved to names (best-effort).

    Returns ``[{source, sourceName, type, target, targetName, reason}]`` — empty when the
    graph is off/unreachable. Powers the story player's live Relationships panel (P6),
    replacing the seed placeholder when the graph actually has edges.
    """
    graph = scenario_graph(db, scenario_id)
    if not graph.get("available"):
        return []
    names = {n["id"]: n["label"] for n in graph.get("nodes", [])}
    out: list[dict] = []
    for edge in graph.get("edges", []):
        if edge.get("type") not in _RELATIONSHIP_TYPES:
            continue
        source, target = edge.get("source"), edge.get("target")
        if source not in names or target not in names:
            continue
        out.append(
            {
                "source": source,
                "sourceName": names[source],
                "type": edge["type"],
                "target": target,
                "targetName": names[target],
                "reason": (edge.get("metadata") or {}).get("reason", ""),
            }
        )
    return out


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
