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
    def __init__(self, node_rows, edge_rows, neighbour_rows=None):
        self.node_rows, self.edge_rows = node_rows, edge_rows
        self.neighbour_rows = neighbour_rows or []
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        if "count(DISTINCT a) AS anchors" in cypher:
            return _Result(self.neighbour_rows)
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


class _RelReadSession:
    """Returns direct-edge rows for _REL_DIRECT, 2-hop rows for _REL_INDIRECT."""

    def __init__(self, direct, indirect):
        self.direct, self.indirect = direct, indirect

    def run(self, cypher: str, **params):
        if "mid:Character" in cypher:
            return _Result(self.indirect)
        return _Result(self.direct)


def test_relationship_context_direct_and_indirect(monkeypatch):
    direct = [{"target": "beth", "name": "Beth", "type": "fears", "src": "mei", "props": {"reason": "old debt"}}]
    indirect = [{"target": "beth", "name": "Beth", "via": "Cy"}]
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "read_session", _cm_returning(_RelReadSession(direct, indirect)))
    ctx = graph_reader.relationship_context("mei", ["beth"])
    assert ctx["direct"][0]["type"] == "fears" and ctx["direct"][0]["outgoing"] is True
    assert ctx["direct"][0]["reason"] == "old debt"
    assert ctx["indirect"][0]["via"] == "Cy"


def test_relationship_context_marks_incoming_direction(monkeypatch):
    direct = [{"target": "beth", "name": "Beth", "type": "resents", "src": "beth", "props": {}}]
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "read_session", _cm_returning(_RelReadSession(direct, [])))
    ctx = graph_reader.relationship_context("mei", ["beth"])
    assert ctx["direct"][0]["outgoing"] is False  # Beth resents Mei (points at the speaker)


def test_relationship_context_empty_when_graph_disabled():
    # Neo4j disabled by the conftest fixture → empty, without opening a session.
    assert graph_reader.relationship_context("mei", ["beth"]) == {"direct": [], "indirect": []}


def test_relationship_context_no_others_is_empty(monkeypatch):
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    assert graph_reader.relationship_context("mei", ["mei"]) == {"direct": [], "indirect": []}


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
    assert result == {
        "available": False,
        "scenario_id": "sc1",
        "anchor_ids": [],
        "nodes": [],
        "edges": [],
    }


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


# ---- off-scene ties (the `world` tie scope) ---------------------------------


class _OffsceneReadSession:
    """Answers _REL_OFFSCENE, recording the parameters it was called with."""

    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return _Result(self.rows)


def _tie(target, name, src, rel="resents", reason=""):
    return {
        "target": target,
        "name": name,
        "type": rel,
        "src": src,
        "props": {"reason": reason} if reason else {},
    }


def test_offscene_ties_is_empty_with_the_graph_disabled(monkeypatch):
    """The whole degradation story: no graph means every tie scope behaves as today."""
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: False)
    assert graph_reader.offscene_ties("mei", ["mei", "kira"], "embergate") == []


def test_offscene_ties_is_empty_without_a_character(monkeypatch):
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    assert graph_reader.offscene_ties("", ["mei"], "embergate") == []


def test_offscene_ties_excludes_the_scene_and_scopes_to_the_storyline(monkeypatch):
    session = _OffsceneReadSession([_tie("corvin", "Corvin", "mei", "resents", "the ledger")])
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "read_session", _cm_returning(session))

    ties = graph_reader.offscene_ties("mei", ["mei", "kira"], "embergate")

    assert ties == [
        {
            "target": "corvin",
            "name": "Corvin",
            "type": "resents",
            "outgoing": True,
            "reason": "the ledger",
        }
    ]
    # The scene's cast is excluded IN the query, not filtered afterwards — a speaker with
    # thirty in-scene edges would otherwise fill the LIMIT with rows nobody wanted.
    cypher, params = session.calls[0]
    assert "NOT b.id IN $scene_ids" in cypher
    assert "LIMIT 8" in cypher
    assert params["scene_ids"] == ["mei", "kira"]
    assert params["storyline"] == "embergate"


def test_offscene_ties_marks_an_incoming_edge(monkeypatch):
    session = _OffsceneReadSession([_tie("corvin", "Corvin", "corvin")])
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "read_session", _cm_returning(session))

    assert graph_reader.offscene_ties("mei", ["mei"], "embergate")[0]["outgoing"] is False


def test_offscene_ties_never_raises(monkeypatch):
    """Best-effort, like every other graph read: a turn must not die for a tie."""

    @contextmanager
    def _boom(**kwargs):
        raise RuntimeError("neo4j is on fire")
        yield  # pragma: no cover

    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "read_session", _boom)
    assert graph_reader.offscene_ties("mei", ["mei"], "embergate") == []


# ---- the one-hop expansion around a scene ----------------------------------


def test_neighbour_ids_scopes_to_the_storyline_and_caps():
    session = _FakeReadSession([], [], neighbour_rows=[{"id": "court"}, {"id": "harbor"}])

    ids = graph_reader.neighbour_ids(session, ["maerin", "saltworn"], "embergate", limit=5)

    assert ids == ["court", "harbor"]
    cypher, params = session.calls[0]
    # The anchors are excluded IN the query, so the cap applies to rows that will be used.
    assert "NOT b.id IN $ids" in cypher
    assert "b.storyline = $storyline" in cypher
    assert params == {"ids": ["maerin", "saltworn"], "storyline": "embergate", "limit": 5}


def test_neighbour_ids_is_empty_without_anchors_or_storyline():
    session = _FakeReadSession([], [])
    assert graph_reader.neighbour_ids(session, [], "embergate") == []
    assert graph_reader.neighbour_ids(session, ["maerin"], "") == []
    assert session.calls == []  # never runs an unscoped traversal


def test_scenario_graph_reads_the_cast_plus_one_hop(db_session, monkeypatch):
    """A seeded Faction is invisible without the expansion — both endpoints must be in $ids."""
    scenario = _seed_scene(db_session)
    node_rows = [
        {"id": "c1", "type": "Character", "label": "Mei", "storyline": "w1", "props": {"id": "c1"}},
        {"id": "s1", "type": "Setting", "label": "Tavern", "storyline": "w1", "props": {"id": "s1"}},
        {"id": "f1", "type": "Faction", "label": "The Court", "storyline": "w1", "props": {"id": "f1"}},
    ]
    edge_rows = [{"source": "c1", "target": "f1", "type": "member_of", "props": {}}]
    read_session = _FakeReadSession(node_rows, edge_rows, neighbour_rows=[{"id": "f1"}])

    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _cm_returning(_RecWriteSession()))
    monkeypatch.setattr(neo4j_mod, "read_session", _cm_returning(read_session))

    result = graph_reader.scenario_graph(db_session, scenario.id)

    assert {n["id"] for n in result["nodes"]} == {"c1", "s1", "f1"}
    # The anchors stay distinguishable from the context reached around them.
    assert set(result["anchor_ids"]) == {"c1", "c2", "s1"}
    # The node/edge read is scoped to anchors + neighbours, not to anchors alone.
    node_call = next(p for c, p in read_session.calls if "properties(n)" in c)
    assert "f1" in node_call["ids"]


def test_scenario_relationships_ignores_characters_reached_by_the_expansion(db_session, monkeypatch):
    """The panel answers 'who is in this room', so a one-hop character is not an entry."""
    scenario = _seed_scene(db_session)
    node_rows = [
        {"id": "c1", "type": "Character", "label": "Mei", "storyline": "w1", "props": {"id": "c1"}},
        {"id": "c2", "type": "Character", "label": "John", "storyline": "w1", "props": {"id": "c2"}},
        {"id": "c9", "type": "Character", "label": "Offscene", "storyline": "w1", "props": {"id": "c9"}},
    ]
    edge_rows = [
        {"source": "c1", "target": "c2", "type": "trusts", "props": {"reason": "years of it"}},
        {"source": "c1", "target": "c9", "type": "resents", "props": {}},
    ]
    read_session = _FakeReadSession(node_rows, edge_rows, neighbour_rows=[{"id": "c9"}])
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _cm_returning(_RecWriteSession()))
    monkeypatch.setattr(neo4j_mod, "read_session", _cm_returning(read_session))

    rels = graph_reader.scenario_relationships(db_session, scenario.id)

    assert [(r["sourceName"], r["type"], r["targetName"]) for r in rels] == [("Mei", "trusts", "John")]
