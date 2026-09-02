"""The Story-Graph write path (§6.5 / §8 authoring side).

The authoring write path is the only hand-curated write into the graph. When a
Character or Setting is created/edited, its node is upserted into Neo4j; on delete
the node is removed. Everything here is **best-effort**: it no-ops when Neo4j is
disabled and swallows+logs any failure, so CRUD (and the no-Docker test suite)
never break because the graph is down (the confirmed graceful posture).

Two load-bearing techniques from the brief:
  * **Dynamic labels (§6.2):** the node's ``type`` becomes a Neo4j *label* via a
    *bound* parameter — ``MERGE (n:Node {id}) SET n:$($type)`` — so built-in and
    user-defined types alike travel the indexed label path with no injection risk.
  * **Registry validation (§6.5):** before writing, the proposed instance is
    validated against the Type Registry (required fields present; an edge's type is
    known and carries a valence). The registry's field schema *is* the validation.

Two consumers write through this module. ``services/crud.py`` syncs Character and
Setting **nodes** on create/edit/delete (the authoring path above). ``services/
turn_writer.py`` writes **edges** and the reified ``:Consequence`` node (§6.4) on
the cold path after each turn, and ``services/relationships.py`` seeds character
edges on a session's first turn.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core import neo4j
from app.models import Character, Setting
from app.models.graph_type import KIND_EDGE, KIND_NODE
from app.services import type_registry

logger = logging.getLogger("mytheca.graph")

# Base label every node carries (§6.1) so generic machinery has one handle.
BASE_LABEL = "Node"
CONSEQUENCE_LABEL = "Consequence"

# The metadata fields mirrored onto each node type (kept in sync with the registry
# field schema in content/graph_registry.py). Values are written even when None so
# an update that *clears* a field removes the property (Neo4j ``+=`` drops nulls).
_CHARACTER_FIELDS = ("appearance", "background", "personality", "traits", "speech", "goal", "secret")
_SETTING_FIELDS = ("desc", "atmosphere", "features", "current_state", "image")


# ---- ORM → node metadata ----------------------------------------------------


def node_props_from_character(char: Character) -> dict[str, Any]:
    meta = {f: getattr(char, f, None) for f in _CHARACTER_FIELDS}
    return meta


def node_props_from_setting(setting: Setting) -> dict[str, Any]:
    meta = {f: getattr(setting, f, None) for f in _SETTING_FIELDS}
    # Setting's own type (e.g. "Social Hub") rides as the "kind" metadata field so it
    # doesn't collide with the node's ``type`` property ("Setting").
    meta["kind"] = setting.type
    return meta


# ---- registry validation (§6.5) --------------------------------------------


def _validate(db: Session, kind: str, type_name: str, metadata: dict, storyline_id: str | None):
    t = type_registry.resolve_type(db, kind, type_name, storyline_id)
    if t is None:
        raise ValueError(f"unknown {kind} type '{type_name}' (not in the registry)")
    if kind == KIND_EDGE and not t.valence:
        raise ValueError(f"edge type '{type_name}' has no declared valence")
    for field in t.field_schema:
        if field.get("required") and metadata.get(field.get("name")) is None:
            raise ValueError(f"'{type_name}' is missing required field '{field.get('name')}'")
    return t


# ---- low-level Cypher (operate on a given session; unit-testable) -----------


def ensure_constraints(session: Any) -> None:
    """Create the uniqueness/index scaffolding (§6.6). Idempotent (IF NOT EXISTS)."""
    session.run(
        f"CREATE CONSTRAINT node_id_unique IF NOT EXISTS "
        f"FOR (n:{BASE_LABEL}) REQUIRE n.id IS UNIQUE"
    ).consume()
    session.run(
        f"CREATE INDEX node_storyline IF NOT EXISTS FOR (n:{BASE_LABEL}) ON (n.storyline)"
    ).consume()


def upsert_node(
    session: Any,
    *,
    node_id: str,
    type_name: str,
    label: str,
    storyline: str | None,
    metadata: dict[str, Any],
) -> None:
    """MERGE a ``:Node`` keyed on id, add the dynamic type label, set properties."""
    session.run(
        f"MERGE (n:{BASE_LABEL} {{id: $id}}) "
        "SET n:$($type) "
        "SET n.type = $type, n.label = $label, n.storyline = $storyline "
        "SET n += $metadata",
        id=node_id,
        type=type_name,
        label=label,
        storyline=storyline,
        metadata=metadata,
    ).consume()


def delete_node(session: Any, node_id: str) -> None:
    """Remove a node and its relationships (and any attached consequences)."""
    session.run(
        f"MATCH (n:{BASE_LABEL} {{id: $id}}) "
        f"OPTIONAL MATCH (n)-[:HAS_CONSEQUENCE]->(c:{CONSEQUENCE_LABEL}) "
        "DETACH DELETE n, c",
        id=node_id,
    ).consume()


def upsert_edge(
    session: Any,
    *,
    source_id: str,
    target_id: str,
    type_name: str,
    metadata: dict[str, Any],
    session_id: str | None = None,
    turn_seq: int | None = None,
) -> None:
    """MERGE a directed relationship of the given (dynamic) type between two nodes.

    ``session_id``/``turn_seq`` stamp **provenance**: ``created_session``/``created_seq`` are
    written once, on creation, and ``session``/``seq`` track the last touch. Only the
    create-time pair is authoritative for rollback — see :func:`remove_edges_after` for what
    that does and does not recover. Both are omitted entirely when not supplied, so the
    authoring path and the derived ``present_at``/``occurred_at`` edges are unchanged.
    """
    props = dict(metadata)
    if session_id is not None:
        props["session"] = session_id
    if turn_seq is not None:
        props["seq"] = turn_seq
    session.run(
        f"MATCH (a:{BASE_LABEL} {{id: $src}}), (b:{BASE_LABEL} {{id: $tgt}}) "
        "MERGE (a)-[r:$($type)]->(b) "
        "ON CREATE SET r.created_session = $session, r.created_seq = $seq "
        "SET r += $metadata",
        src=source_id,
        tgt=target_id,
        type=type_name,
        metadata=props,
        session=session_id,
        seq=turn_seq,
    ).consume()


def remove_edges_after(session: Any, *, session_id: str, after_seq: int) -> None:
    """Delete edges and consequences a play-session **created** after ``after_seq``.

    The rollback a rewind needs, and an honest half of one. An edge whose ``created_seq``
    is above the cut never existed before the removed turns, so deleting it is exact —
    that is the case the checklist described as "a rewound scene can leave a relationship
    the transcript no longer explains", because a relationship *formed* by cut turns is
    precisely an edge created by them.

    What it does **not** recover: an edge that already existed before the cut and was
    merely reinforced afterwards keeps its post-cut ``weight``. Reverting that would mean
    replaying the surviving ``:Consequence`` contributions to recompute the weight, which
    needs a contribution log this schema does not keep in a queryable form (``origin`` is
    JSON-encoded prose). The residue is a number being too high, not a relationship that
    has no story behind it.
    """
    session.run(
        f"MATCH (a:{BASE_LABEL})-[r]->(b:{BASE_LABEL}) "
        "WHERE r.created_session = $session AND r.created_seq > $seq "
        "DELETE r",
        session=session_id,
        seq=after_seq,
    ).consume()
    session.run(
        f"MATCH (c:{CONSEQUENCE_LABEL}) "
        "WHERE c.session = $session AND c.seq > $seq "
        "DETACH DELETE c",
        session=session_id,
        seq=after_seq,
    ).consume()


def remove_edges_after_safe(session_id: str, after_seq: int) -> None:
    """Best-effort :func:`remove_edges_after` — no-ops when the graph is off/unreachable."""
    if not neo4j.is_enabled():
        return
    try:
        with neo4j.write_session() as session:
            remove_edges_after(session, session_id=session_id, after_seq=after_seq)
    except Exception as exc:  # pragma: no cover - defensive; a rewind never fails on the graph
        logger.warning("graph edge rollback (%s > %s) skipped: %s", session_id, after_seq, exc)


def attach_consequence(
    session: Any,
    *,
    target_id: str,
    record: dict[str, Any],
    session_id: str | None = None,
    turn_seq: int | None = None,
) -> None:
    """Attach a reified ``:Consequence`` node (§6.4) to a target node.

    Neo4j can't hang data off a relationship, so the recurring consequence record
    (reason / origin / delta / status) is its own node, linked from whatever it
    modified — giving every change uniform decay/audit/status, queryable in
    aggregate. ``origin`` is JSON-encoded (nested maps aren't valid properties).

    ``session_id``/``turn_seq`` are written as flat, **queryable** properties beside the
    JSON ``origin``. The origin blob has carried the same two values since this was
    written, but as encoded prose no Cypher predicate can filter on — which is why a
    rewind could not delete the consequences it invalidated.
    """
    origin = record.get("origin")
    session.run(
        f"MATCH (t:{BASE_LABEL} {{id: $target}}) "
        f"CREATE (c:{BASE_LABEL}:{CONSEQUENCE_LABEL} "
        "{id: $cid, reason: $reason, origin: $origin, delta: $delta, status: $status, "
        "session: $session, seq: $seq}) "
        "MERGE (t)-[:HAS_CONSEQUENCE]->(c)",
        target=target_id,
        cid=record.get("id"),
        reason=record.get("reason", ""),
        origin=origin if isinstance(origin, str) or origin is None else json.dumps(origin),
        delta=record.get("delta"),
        status=record.get("status", "active"),
        session=session_id,
        seq=turn_seq,
    ).consume()


# ---- best-effort top level (what CRUD calls) --------------------------------


def sync_character(db: Session, char: Character) -> None:
    """Upsert a Character node. Best-effort: no-ops/logs when the graph is absent."""
    if not neo4j.is_enabled():
        return
    try:
        _validate(db, KIND_NODE, "Character", node_props_from_character(char), char.storyline_id)
        with neo4j.write_session() as session:
            upsert_node(
                session,
                node_id=char.id,
                type_name="Character",
                label=char.name,
                storyline=char.storyline_id,
                metadata=node_props_from_character(char),
            )
    except Exception as exc:  # never break CRUD on a graph hiccup
        logger.warning("graph sync (character %s) skipped: %s", char.id, exc)


def sync_setting(db: Session, setting: Setting) -> None:
    """Upsert a Setting node. Best-effort."""
    if not neo4j.is_enabled():
        return
    try:
        _validate(db, KIND_NODE, "Setting", node_props_from_setting(setting), setting.storyline_id)
        with neo4j.write_session() as session:
            upsert_node(
                session,
                node_id=setting.id,
                type_name="Setting",
                label=setting.name,
                storyline=setting.storyline_id,
                metadata=node_props_from_setting(setting),
            )
    except Exception as exc:
        logger.warning("graph sync (setting %s) skipped: %s", setting.id, exc)


def remove_node(node_id: str) -> None:
    """Remove a node from the graph. Best-effort."""
    if not neo4j.is_enabled():
        return
    try:
        with neo4j.write_session() as session:
            delete_node(session, node_id)
    except Exception as exc:
        logger.warning("graph node removal (%s) skipped: %s", node_id, exc)


def ensure_constraints_safe() -> None:
    """Best-effort constraint bootstrap, called from preflight when Neo4j is up."""
    if not neo4j.is_enabled():
        return
    try:
        with neo4j.write_session() as session:
            ensure_constraints(session)
    except Exception as exc:
        logger.warning("graph constraint bootstrap skipped: %s", exc)
