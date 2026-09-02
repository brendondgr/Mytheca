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


# ---- provenance: reason, session/turn stamps, and who was in the room -------


def test_play_written_edge_carries_its_reason(monkeypatch):
    """The bug this closes: a tie formed in play reached the next scene as a bare verb.

    ``relationships.ensure_seeded`` has always written ``reason`` at seed time, so
    ``graph_reader.relationship_context`` renders it — but the play path dropped it, and a
    model given "You resent Mara" with no why invents one, routinely contradicting the
    scene the player actually played.
    """
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=6, summary="x",
        consequences=[
            Consequence(
                id="cons_9", summary="Kira turns on the player", source_id="ch_kira",
                target_id="player", edge_type="resents", weight=0.7,
                reason="she went back for the cargo while you were under the water",
            )
        ],
    )
    edges = [p for c, p in rec.calls if "MERGE (a)-[r:$($type)]->(b)" in c]
    resents = next(p for p in edges if p["type"] == "resents")
    assert resents["metadata"]["reason"] == "she went back for the cargo while you were under the water"
    assert resents["metadata"]["origin"] == "play"


def test_edge_reason_falls_back_to_the_summary(monkeypatch):
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=6, summary="x",
        consequences=[
            Consequence(id="c1", summary="Kira stops trusting the player", source_id="ch_kira",
                        target_id="player", edge_type="resents", weight=0.4)
        ],
    )
    edges = [p for c, p in rec.calls if "MERGE (a)-[r:$($type)]->(b)" in c]
    resents = next(p for p in edges if p["type"] == "resents")
    assert resents["metadata"]["reason"] == "Kira stops trusting the player"


def test_edges_and_consequences_are_stamped_with_session_and_turn(monkeypatch):
    """Provenance is what makes a rewind able to delete what it invalidated."""
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=6, summary="x",
        consequences=[
            Consequence(id="c1", summary="s", source_id="ch_kira", target_id="player",
                        edge_type="resents", weight=0.4)
        ],
    )
    edges = [p for c, p in rec.calls if "MERGE (a)-[r:$($type)]->(b)" in c]
    resents = next(p for p in edges if p["type"] == "resents")
    assert resents["session"] == "ps1" and resents["seq"] == 6
    assert resents["metadata"]["session"] == "ps1" and resents["metadata"]["seq"] == 6
    cons = next(p for c, p in rec.calls if "CREATE (c:" in c)
    assert cons["session"] == "ps1" and cons["seq"] == 6


def test_derived_edges_are_not_stamped(monkeypatch):
    """``occurred_at``/``involved`` belong to the Event node, which a rewind prunes whole."""
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=6, summary="x",
        consequences=[Consequence(id="c1", summary="s", source_id="ch_kira")],
        present_ids=["ch_kira"],
    )
    edges = [p for c, p in rec.calls if "MERGE (a)-[r:$($type)]->(b)" in c]
    for edge in edges:
        if edge["type"] in ("occurred_at", "involved"):
            assert edge["session"] is None and edge["seq"] is None


def test_event_links_to_the_people_in_it(monkeypatch):
    """``involved`` is a built-in edge type nothing had ever written.

    Without it an event is reachable only from its *setting*, so "what has happened
    between these two people" is a question the graph has no path to answer.
    """
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=3, summary="A tense beat",
        consequences=[Consequence(id="c1", summary="s", source_id="ch_kira")],
        present_ids=["ch_kira", "ch_dell"],
    )
    involved = [
        p for c, p in rec.calls
        if "MERGE (a)-[r:$($type)]->(b)" in c and p["type"] == "involved"
    ]
    assert [p["tgt"] for p in involved] == ["ch_kira", "ch_dell"]
    assert all(p["src"] == "evt_ps1_3" for p in involved)


def test_absent_cast_gets_no_involved_edge(monkeypatch):
    rec = _RecSession()
    _enable(monkeypatch, rec)
    turn_writer.write_turn(
        None, scenario=_scenario(), session_id="ps1", turn_seq=3, summary="x",
        consequences=[Consequence(id="c1", summary="s", source_id="ch_kira")],
        present_ids=[],
    )
    involved = [p for c, p in rec.calls if p.get("type") == "involved"]
    assert involved == []
