"""GET /scenarios/{id}/graph — the read path on scenario load.

Graceful by default (Neo4j disabled → ``available: false``); with an injected
fake session it returns the cast+setting subgraph.
"""

from __future__ import annotations

from contextlib import contextmanager


class _Result(list):
    def consume(self):
        return None


class _RecSession:
    def run(self, cypher: str, **params):
        return _Result()


class _FakeReadSession:
    def __init__(self, node_rows, edge_rows):
        self.node_rows, self.edge_rows = node_rows, edge_rows

    def run(self, cypher: str, **params):
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


def _make_scene(client, storyline_id):
    s = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Tavern"}).json()["id"]
    c1 = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    c2 = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "John"}).json()["id"]
    sc = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Plot", "castIds": [c1, c2], "settingId": s},
    ).json()["id"]
    return sc, s, c1, c2


def test_scenario_graph_unavailable_when_disabled(client, storyline_id):
    sc, *_ = _make_scene(client, storyline_id)
    res = client.get(f"/api/scenarios/{sc}/graph")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False
    assert body["scenarioId"] == sc
    assert body["nodes"] == [] and body["edges"] == []


def test_scenario_graph_unknown_scenario_404(client):
    assert client.get("/api/scenarios/ghost/graph").status_code == 404


def test_scenario_graph_returns_subgraph_when_enabled(client, storyline_id, monkeypatch):
    sc, s, c1, c2 = _make_scene(client, storyline_id)
    from app.services import graph_reader

    node_rows = [
        {"id": c1, "type": "Character", "label": "Mei", "storyline": storyline_id, "props": {"id": c1}},
        {"id": s, "type": "Setting", "label": "Tavern", "storyline": storyline_id, "props": {"id": s}},
    ]
    edge_rows = [{"source": c1, "target": s, "type": "present_at", "props": {"weight": 1.0}}]

    monkeypatch.setattr(graph_reader.neo4j, "is_enabled", lambda: True)
    monkeypatch.setattr(graph_reader.neo4j, "write_session", _cm_returning(_RecSession()))
    monkeypatch.setattr(
        graph_reader.neo4j, "read_session", _cm_returning(_FakeReadSession(node_rows, edge_rows))
    )

    res = client.get(f"/api/scenarios/{sc}/graph")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert {n["id"] for n in body["nodes"]} == {c1, s}
    assert body["edges"][0]["type"] == "present_at"
