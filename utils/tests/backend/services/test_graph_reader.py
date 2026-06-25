"""The Story-Graph read path — subgraph serialization, materialize-on-load, and
the graceful/read-only orchestration. Offline: fake sessions stand in for Neo4j.
"""

from __future__ import annotations

from contextlib import contextmanager

from app.core import neo4j as neo4j_mod
from app.models import Character, Scenario, Setting, Storyline
from app.services import graph_reader


class _Result(list):
    def consume(self):
        return None


class _RecWriteSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return _Result()


class _FakeReadSession:
    def __init__(self, node_rows, edge_rows):
        self.node_rows, self.edge_rows = node_rows, edge_rows
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        if "properties(n)" in cypher:
            return _Result(self.node_rows)
        if "type(r)" in cypher:
            return _Result(self.edge_rows)
        return _Result()


def _cm_returning(obj):
    @contextmanager
    def _cm(**kwargs):
        yield obj

    return _cm


def test_scenario_subgraph_serializes_rows():
    node_rows = [
        {"id": "c1", "type": "Character", "label": "Mei", "storyline": "w1",
         "props": {"id": "c1", "type": "Character", "label": "Mei", "storyline": "w1", "appearance": "green eyes"}},
        {"id": "s1", "type": "Setting", "label": "Tavern", "storyline": "w1",
         "props": {"id": "s1", "type": "Setting", "label": "Tavern", "storyline": "w1", "atmosphere": "smoky"}},
    ]
    edge_rows = [{"source": "c1", "target": "s1", "type": "present_at", "props": {"weight": 1.0}}]
    session = _FakeReadSession(node_rows, edge_rows)

    nodes, edges = graph_reader.scenario_subgraph(session, ["c1", "s1"])
    mei = next(n for n in nodes if n["id"] == "c1")
    assert mei["type"] == "Character" and mei["label"] == "Mei"
    assert mei["metadata"] == {"appearance": "green eyes"}  # structural keys stripped
    assert edges[0] == {"source": "c1", "target": "s1", "type": "present_at", "metadata": {"weight": 1.0}}


def _seed_scene(db):
    db.add(Storyline(id="w1", title="W1"))
    db.add(Setting(id="s1", name="Tavern", type="Social Hub", storyline_id="w1"))
    db.add(Character(id="c1", name="Mei", storyline_id="w1"))
    db.add(Character(id="c2", name="John", storyline_id="w1"))
    db.add(Scenario(id="sc1", title="Plot", storyline_id="w1", cast_ids=["c1", "c2"], setting_id="s1"))
    db.commit()
    return db.get(Scenario, "sc1")


def test_ensure_scenario_materialized_upserts_cast_setting_and_edges(db_session, monkeypatch):
    scenario = _seed_scene(db_session)
    rec = _RecWriteSession()
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _cm_returning(rec))

    ids = graph_reader.ensure_scenario_materialized(db_session, scenario)
    assert set(ids) == {"s1", "c1", "c2"}

    merges = [c for c, _ in rec.calls if c.startswith("MERGE (n:Node")]
    edges = [c for c, _ in rec.calls if "MERGE (a)-[r:$($type)]->(b)" in c]
    assert len(merges) == 3  # setting + two characters
    assert len(edges) == 2  # present_at for each character → setting


def test_scenario_graph_unavailable_when_disabled(db_session):
    # autouse fixture leaves Neo4j disabled.
    scenario = _seed_scene(db_session)
    result = graph_reader.scenario_graph(db_session, scenario.id)
    assert result == {"available": False, "scenario_id": "sc1", "nodes": [], "edges": []}


def test_scenario_graph_reads_via_read_session(db_session, monkeypatch):
    scenario = _seed_scene(db_session)
    node_rows = [
        {"id": "c1", "type": "Character", "label": "Mei", "storyline": "w1", "props": {"id": "c1"}},
        {"id": "s1", "type": "Setting", "label": "Tavern", "storyline": "w1", "props": {"id": "s1"}},
    ]
    edge_rows = [{"source": "c1", "target": "s1", "type": "present_at", "props": {}}]
    read_session = _FakeReadSession(node_rows, edge_rows)

    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _cm_returning(_RecWriteSession()))
    # Reads go through read_session (READ access mode, §7.4) — not write_session.
    monkeypatch.setattr(neo4j_mod, "read_session", _cm_returning(read_session))

    result = graph_reader.scenario_graph(db_session, scenario.id)
    assert result["available"] is True
    assert {n["id"] for n in result["nodes"]} == {"c1", "s1"}
    assert result["edges"][0]["type"] == "present_at"
    assert read_session.calls  # the read template ran in the read session


def test_scenario_graph_graceful_when_read_raises(db_session, monkeypatch):
    scenario = _seed_scene(db_session)
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _cm_returning(_RecWriteSession()))

    def _boom(**kwargs):
        raise RuntimeError("graph down mid-read")

    monkeypatch.setattr(neo4j_mod, "read_session", _boom)
    result = graph_reader.scenario_graph(db_session, scenario.id)
    assert result["available"] is False  # never raises to the caller
