"""The Story-Graph write path — Cypher shape, registry validation, and the
best-effort posture (graph down/disabled never breaks CRUD).

Fully offline: a recording fake session captures the Cypher + params; the Neo4j
``write_session`` context manager is monkeypatched, so no container is touched.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.core import neo4j as neo4j_mod
from app.models import Character, GraphTypeDefinition, Setting, Storyline
from app.schemas.graph_type import GraphTypeCreate
from app.services import graph_writer, type_registry


class _Result:
    def consume(self):
        return None


class _RecSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return _Result()


def _ws_returning(rec: _RecSession):
    @contextmanager
    def _ws(**kwargs):
        yield rec

    return _ws


# ---- ORM → metadata mapping -------------------------------------------------


def test_node_props_from_character():
    char = Character(
        id="c1", name="Mei", appearance="green eyes", background="dockside", personality="wry"
    )
    props = graph_writer.node_props_from_character(char)
    assert props["appearance"] == "green eyes"
    assert set(props) == set(graph_writer._CHARACTER_FIELDS)


def test_node_props_from_setting_carries_kind_not_timeline():
    setting = Setting(id="s1", name="Tavern", type="Social Hub", desc="lamplit")
    props = graph_writer.node_props_from_setting(setting)
    assert props["kind"] == "Social Hub"  # the setting's type rides as metadata "kind"
    assert "timeline" not in props  # nested list is not a valid Neo4j property


# ---- low-level Cypher -------------------------------------------------------


def test_upsert_node_uses_dynamic_label_and_merges_on_id():
    rec = _RecSession()
    graph_writer.upsert_node(
        rec, node_id="c1", type_name="Character", label="Mei", storyline="w1",
        metadata={"appearance": "green eyes"},
    )
    cypher, params = rec.calls[0]
    assert "MERGE (n:Node {id: $id})" in cypher
    assert "SET n:$($type)" in cypher  # dynamic label (§6.2)
    assert params["type"] == "Character"
    assert params["label"] == "Mei"
    assert params["storyline"] == "w1"
    assert params["metadata"] == {"appearance": "green eyes"}


def test_upsert_edge_uses_dynamic_relationship_type():
    rec = _RecSession()
    graph_writer.upsert_edge(
        rec, source_id="a", target_id="b", type_name="loves", metadata={"weight": 0.8}
    )
    cypher, params = rec.calls[0]
    assert "MERGE (a)-[r:$($type)]->(b)" in cypher
    assert params["type"] == "loves" and params["metadata"]["weight"] == 0.8


def test_attach_consequence_serializes_origin_dict():
    rec = _RecSession()
    graph_writer.attach_consequence(
        rec, target_id="a",
        record={"id": "x1", "reason": "betrayal", "origin": {"scenario": "sc1", "turn": 4}, "delta": -0.3},
    )
    _, params = rec.calls[0]
    assert params["origin"] == '{"scenario": "sc1", "turn": 4}'  # JSON-encoded (no nested maps)
    assert params["reason"] == "betrayal"


def test_ensure_constraints_creates_unique_id():
    rec = _RecSession()
    graph_writer.ensure_constraints(rec)
    joined = " ".join(c for c, _ in rec.calls)
    assert "CONSTRAINT node_id_unique IF NOT EXISTS" in joined
    assert "n.id IS UNIQUE" in joined


# ---- registry validation (§6.5) --------------------------------------------


def test_validate_rejects_unknown_type(db_session):
    type_registry.seed_builtin_types(db_session)
    with pytest.raises(ValueError, match="unknown node type"):
        graph_writer._validate(db_session, "node", "Ghost", {}, None)


def test_validate_rejects_missing_required_field(db_session):
    type_registry.seed_builtin_types(db_session)
    db_session.add(Storyline(id="w1", title="W1"))
    db_session.commit()
    type_registry.create_user_type(
        db_session, "w1",
        GraphTypeCreate(
            kind="node", type_name="Ritual",
            field_schema=[{"name": "potency", "kind": "numeric", "required": True}],
        ),
    )
    with pytest.raises(ValueError, match="missing required field"):
        graph_writer._validate(db_session, "node", "Ritual", {}, "w1")


def test_validate_rejects_edge_without_valence(db_session):
    db_session.add(Storyline(id="w1", title="W1"))
    db_session.add(GraphTypeDefinition(storyline_id="w1", kind="edge", type_name="weird", valence=None))
    db_session.commit()
    with pytest.raises(ValueError, match="no declared valence"):
        graph_writer._validate(db_session, "edge", "weird", {}, "w1")


# ---- best-effort sync -------------------------------------------------------


def test_sync_character_noops_when_disabled(db_session, monkeypatch):
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: False)
    opened = {"n": 0}
    monkeypatch.setattr(neo4j_mod, "write_session", lambda **k: opened.__setitem__("n", opened["n"] + 1))
    char = Character(id="c1", name="Mei", storyline_id="w1")
    graph_writer.sync_character(db_session, char)  # must not raise, must not open a session
    assert opened["n"] == 0


def test_sync_character_writes_when_enabled(db_session, monkeypatch):
    type_registry.seed_builtin_types(db_session)
    db_session.add(Storyline(id="w1", title="W1"))
    db_session.commit()
    char = Character(id="c1", name="Mei", storyline_id="w1", appearance="green eyes")
    db_session.add(char)
    db_session.commit()

    rec = _RecSession()
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _ws_returning(rec))
    graph_writer.sync_character(db_session, char)

    cypher, params = rec.calls[0]
    assert params["type"] == "Character" and params["label"] == "Mei"
    assert params["metadata"]["appearance"] == "green eyes"


def test_sync_character_graceful_when_session_raises(db_session, monkeypatch):
    type_registry.seed_builtin_types(db_session)
    db_session.add(Storyline(id="w1", title="W1"))
    db_session.commit()
    char = Character(id="c1", name="Mei", storyline_id="w1")
    db_session.add(char)
    db_session.commit()

    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)

    def _boom(**kwargs):
        raise RuntimeError("graph down")

    monkeypatch.setattr(neo4j_mod, "write_session", _boom)
    # The exception is swallowed + logged; CRUD callers never see it.
    graph_writer.sync_character(db_session, char)


# ---- edge provenance + rewind rollback --------------------------------------


def test_upsert_edge_without_provenance_writes_no_stamps():
    """The authoring path and the derived edges are unchanged by the rollback feature."""
    rec = _RecSession()
    graph_writer.upsert_edge(
        rec, source_id="a", target_id="b", type_name="knows", metadata={"weight": 1.0}
    )
    _, params = rec.calls[0]
    assert "session" not in params["metadata"] and "seq" not in params["metadata"]
    assert params["session"] is None and params["seq"] is None


def test_upsert_edge_stamps_creation_and_last_touch():
    rec = _RecSession()
    graph_writer.upsert_edge(
        rec, source_id="a", target_id="b", type_name="resents", metadata={"weight": 0.4},
        session_id="ps1", turn_seq=7,
    )
    cypher, params = rec.calls[0]
    assert "ON CREATE SET r.created_session = $session, r.created_seq = $seq" in cypher
    assert params["session"] == "ps1" and params["seq"] == 7
    assert params["metadata"]["session"] == "ps1" and params["metadata"]["seq"] == 7


def test_remove_edges_after_deletes_by_creation_seq_not_last_touch():
    """Deleting on ``created_seq`` is the exact half of the rollback.

    An edge created after the cut never existed before the removed turns, so deleting it
    is precise. An edge created *before* the cut and merely reinforced afterwards is
    deliberately left alone — over-deleting it would erase a relationship the surviving
    transcript still explains.
    """
    rec = _RecSession()
    graph_writer.remove_edges_after(rec, session_id="ps1", after_seq=12)
    edge_cypher, edge_params = rec.calls[0]
    assert "r.created_session = $session AND r.created_seq > $seq" in edge_cypher
    assert "r.seq >" not in edge_cypher  # last-touch must not drive deletion
    assert edge_params == {"session": "ps1", "seq": 12}


def test_remove_edges_after_also_drops_the_consequences():
    rec = _RecSession()
    graph_writer.remove_edges_after(rec, session_id="ps1", after_seq=12)
    cons_cypher, cons_params = rec.calls[1]
    assert "MATCH (c:Consequence)" in cons_cypher and "DETACH DELETE c" in cons_cypher
    assert cons_params == {"session": "ps1", "seq": 12}


def test_attach_consequence_writes_queryable_provenance():
    """``origin`` carried the same values as JSON prose, which no predicate can filter on."""
    rec = _RecSession()
    graph_writer.attach_consequence(
        rec, target_id="ch_kira", record={"id": "c1", "reason": "r"},
        session_id="ps1", turn_seq=6,
    )
    cypher, params = rec.calls[0]
    assert "session: $session, seq: $seq" in cypher
    assert params["session"] == "ps1" and params["seq"] == 6


def test_remove_edges_after_safe_noops_when_disabled(monkeypatch):
    opened = {"n": 0}
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: False)
    monkeypatch.setattr(neo4j_mod, "write_session", lambda **k: opened.__setitem__("n", 1))
    graph_writer.remove_edges_after_safe("ps1", 3)
    assert opened["n"] == 0


def test_remove_edges_after_safe_swallows_a_graph_failure(monkeypatch):
    """A rewind must never fail on the graph — Postgres stays canonical."""

    class _Boom:
        def run(self, *a, **k):
            raise RuntimeError("neo4j down")

    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _ws_returning(_Boom()))
    graph_writer.remove_edges_after_safe("ps1", 3)  # must not raise
