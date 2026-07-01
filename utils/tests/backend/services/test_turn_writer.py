"""Cold-path turn-writer: '…toward whom?' routing, :Event append, best-effort posture.

Offline: a recording fake session captures the Cypher; the Neo4j ``write_session``
context manager is monkeypatched, so no container is touched.
"""

from __future__ import annotations

from contextlib import contextmanager

from app.core import neo4j as neo4j_mod
from app.models import Scenario
from app.services import turn_writer
from app.services.turn_writer import Consequence


class _Result:
    def consume(self):
        return None


class _RecSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return _Result()


def _ws(rec: _RecSession):
    @contextmanager
    def _w(**kwargs):
        yield rec

    return _w


def _scenario() -> Scenario:
    return Scenario(id="sc1", storyline_id="w1", title="S", cast_ids=["ch_kira"], setting_id="set_hearth")


def _enable(monkeypatch, rec: _RecSession):
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _ws(rec))


def test_noop_when_no_consequences(monkeypatch):
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(None, scenario=_scenario(), session_id="ps1", turn_seq=3, summary="x", consequences=[])
    assert rec.calls == []  # the cold path runs on consequence turns only


def test_noop_when_graph_disabled(monkeypatch):
    opened = {"n": 0}
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: False)
    monkeypatch.setattr(neo4j_mod, "write_session", lambda **k: opened.__setitem__("n", opened["n"] + 1))
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=3, summary="x",
        consequences=[Consequence(id="c1", summary="s", source_id="ch_kira")],
    )
    assert opened["n"] == 0  # never opened a session


def test_stat_consequence_reifies_consequence_node_no_edge(monkeypatch):
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=3, summary="Player named the fire",
        consequences=[Consequence(id="cons_88", summary="suspicion +12", source_id="ch_kira", reason="old guilt")],
    )
    cons_params = [p for c, p in rec.calls if "CREATE (c:" in c]
    assert cons_params and cons_params[0]["reason"] == "old guilt"
    # stat-only (no relational target) → the only edge is the :Event→setting occurred_at.
    edge_types = [p["type"] for c, p in rec.calls if "MERGE (a)-[r:$($type)]->(b)" in c]
    assert edge_types == ["occurred_at"]


def test_relational_consequence_writes_edge(monkeypatch):
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=3, summary="x",
        consequences=[
            Consequence(id="cons_88", summary="Kira links player to the fire", source_id="ch_kira",
                        target_id="player", edge_type="wary_of", weight=0.2)
        ],
    )
    edges = [p for c, p in rec.calls if "MERGE (a)-[r:$($type)]->(b)" in c]
    types = [p["type"] for p in edges]
    assert "wary_of" in types and "occurred_at" in types
    wary = next(p for p in edges if p["type"] == "wary_of")
    assert wary["src"] == "ch_kira" and wary["tgt"] == "player"
    assert wary["metadata"]["via"] == "cons_88" and wary["metadata"]["weight"] == 0.2


def test_event_node_appended_and_tied_to_setting(monkeypatch):
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=3, summary="A tense beat",
        consequences=[Consequence(id="c1", summary="s", source_id="ch_kira")],
    )
    nodes = [p for c, p in rec.calls if "MERGE (n:Node {id: $id})" in c]
    event_node = next(p for p in nodes if p["type"] == "Event")
    assert event_node["id"] == "evt_ps1_3"
    assert event_node["metadata"]["scenario"] == "sc1" and event_node["metadata"]["seq"] == 3
    occurred = [p for c, p in rec.calls if "MERGE (a)-[r:$($type)]->(b)" in c and p["type"] == "occurred_at"]
    assert occurred and occurred[0]["tgt"] == "set_hearth"
