"""The Embergate lore layer — the authored Story-Graph nodes and edges.

Offline: a fake Neo4j session records the Cypher it is handed, so the shape of the
authored world is checked without a graph running.
"""

from __future__ import annotations

from contextlib import contextmanager

from app.content.graph_registry import BUILTIN_EDGE_TYPES, BUILTIN_NODE_TYPES
from app.core import neo4j as neo4j_mod
from app.core import seed_graph
from app.core.seed import seed_if_empty
from app.models import Storyline


class _Result(list):
    def consume(self):
        return None


class _RecSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return _Result()

    def nodes(self) -> list[dict]:
        return [p for c, p in self.calls if c.startswith("MERGE (n:Node")]

    def edges(self) -> list[dict]:
        return [p for c, p in self.calls if "MERGE (a)-[r:$($type)]->(b)" in c]


def _cm_returning(obj):
    @contextmanager
    def _cm(**kwargs):
        yield obj

    return _cm


# ---- the authored data stands on its own -----------------------------------


def test_every_authored_type_is_in_the_builtin_registry():
    """An unregistered type is rejected by the writer's validation, so catch it here."""
    node_types = {t["type_name"] for t in BUILTIN_NODE_TYPES}
    edge_types = {t["type_name"] for t in BUILTIN_EDGE_TYPES}
    assert {n[1] for n in seed_graph._nodes()} <= node_types
    assert {e["type"] for e in seed_graph.EDGES} <= edge_types


def test_no_edge_dangles(db_session):
    """Every endpoint resolves to a seeded character, a seeded setting, or a lore node."""
    seed_if_empty(db_session)
    storyline = db_session.get(Storyline, seed_graph.SEED_STORYLINE_ID)
    known = {c.id for c in storyline.characters} | {s.id for s in storyline.settings}
    known |= {n[0] for n in seed_graph._nodes()}

    dangling = {
        end
        for edge in seed_graph.EDGES
        for end in (edge["source"], edge["target"])
        if end not in known
    }
    assert dangling == set()


def test_node_ids_are_unique():
    ids = [n[0] for n in seed_graph._nodes()]
    assert len(ids) == len(set(ids))


def test_edges_are_unique():
    """A MERGE would silently collapse a duplicate, hiding an authoring mistake."""
    keys = [(e["source"], e["target"], e["type"]) for e in seed_graph.EDGES]
    assert len(keys) == len(set(keys))


def test_authored_edges_carry_no_play_session_provenance():
    """Authored structure is the world before the first turn, not a turn's contribution."""
    for edge in seed_graph.EDGES:
        assert "session" not in edge["metadata"]
        assert "seq" not in edge["metadata"]
        assert edge["metadata"]["status"] == "active"


def test_subject_and_consequence_are_never_authored():
    """Both are created by the engine — seeding one would misreport how it got there."""
    assert {"Subject", "Consequence"}.isdisjoint({n[1] for n in seed_graph._nodes()})


# ---- writing it -------------------------------------------------------------


def test_write_lore_materializes_the_whole_cast_not_just_a_scene(db_session):
    """Off-scene characters must reach the graph or their ties are unreachable."""
    seed_if_empty(db_session)
    storyline = db_session.get(Storyline, seed_graph.SEED_STORYLINE_ID)
    rec = _RecSession()

    nodes, edges = seed_graph.write_lore(
        rec, characters=list(storyline.characters), settings=list(storyline.settings)
    )

    written = {p["id"] for p in rec.nodes()}
    assert "nyssa" in written and "grimm" in written  # neither is in the opening scene
    assert "chapel" in written and "customs" in written
    assert nodes == len(written)
    assert edges == len(seed_graph.EDGES)


def test_write_lore_labels_lore_nodes_by_type(db_session):
    rec = _RecSession()
    seed_graph.write_lore(rec)
    by_id = {p["id"]: p for p in rec.nodes()}
    assert by_id["fac-court"]["type"] == "Faction"
    assert by_id["sec-chapel-fire"]["type"] == "Secret"
    assert by_id["ev-chapel-fire"]["type"] == "Event"
    assert by_id["fac-court"]["storyline"] == seed_graph.SEED_STORYLINE_ID


def test_seed_embergate_lore_is_a_noop_without_the_graph(db_session):
    # The autouse fixture leaves Neo4j disabled.
    assert seed_graph.seed_embergate_lore(db_session) == (0, 0)


def test_seed_embergate_lore_is_a_noop_without_the_world(db_session, monkeypatch):
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _cm_returning(_RecSession()))
    assert seed_graph.seed_embergate_lore(db_session) == (0, 0)  # nothing seeded yet


def test_seed_embergate_lore_never_raises_into_startup(db_session, monkeypatch):
    seed_if_empty(db_session)
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)

    def _boom(**kwargs):
        raise RuntimeError("graph down")

    monkeypatch.setattr(neo4j_mod, "write_session", _boom)
    assert seed_graph.seed_embergate_lore(db_session) == (0, 0)


def test_seed_embergate_lore_is_idempotent(db_session, monkeypatch):
    """Every write is a MERGE, so a second boot converges instead of duplicating."""
    seed_if_empty(db_session)
    rec = _RecSession()
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "write_session", _cm_returning(rec))

    first = seed_graph.seed_embergate_lore(db_session)
    second = seed_graph.seed_embergate_lore(db_session)

    assert first == second
    assert all(c.startswith("MERGE") or "MERGE" in c for c, _ in rec.calls)
