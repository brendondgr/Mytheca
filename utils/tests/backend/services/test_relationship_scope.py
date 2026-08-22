"""How much of a speaker's history reaches their beat — the three tie scopes.

Two of the three stops are pure re-parameterisation of a call the engine already makes every
beat, so the assertions that matter are about **which ids are asked for**: that is the entire
difference between `addressed` and `scene`, and it is invisible from the rendered note alone.
"""

from __future__ import annotations

import re

from app.models import Scenario
from app.services import assembler, beat_runner, graph_reader


def _cast(*ids: str, absent: tuple[str, ...] = ()) -> list[assembler.CastMember]:
    return [
        assembler.CastMember(
            id=i, name=i.title(), role="X", traits="", speech="", color="#000",
            stats={}, presence="departed" if i in absent else "present",
        )
        for i in ids
    ]


def _ctx(cast, storyline_id: str = "embergate") -> assembler.TurnContext:
    return assembler.TurnContext(
        scenario=Scenario(storyline_id=storyline_id, title="S", cast_ids=[c.id for c in cast], setting_id=""),
        session_id="ps1",
        storyline_id=storyline_id,
        directed_at=None,
        cast=cast,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer=None,
        stable_prefix="",
    )


def _capture(monkeypatch, *, direct=(), offscene=()):
    """Record the ids each scope asks the graph for, and answer with fixed rows."""
    asked: dict[str, list] = {}

    def context(character_id, other_ids):
        asked["others"] = list(other_ids)
        return {"direct": list(direct), "indirect": []}

    def ties(character_id, scene_ids, storyline_id):
        asked["scene_ids"] = list(scene_ids)
        asked["storyline"] = storyline_id
        return list(offscene)

    monkeypatch.setattr(graph_reader, "relationship_context", context)
    monkeypatch.setattr(graph_reader, "offscene_ties", ties)
    return asked


def _edge(name, rel="resents", outgoing=True, reason=""):
    return {"target": name.lower(), "name": name, "type": rel, "outgoing": outgoing, "reason": reason}


def _entries(note: str) -> int:
    """How many relationship lines the note actually holds.

    Counting "." would count the full stops inside a tie's `reason` too, which is how a cap
    assertion passes while the cap is broken.
    """
    return len(re.findall(r"\b(?:In|Out|Corvin)\d*\b", note))


def test_addressed_asks_only_for_the_caller_s_ids(monkeypatch):
    """What shipped before the control: the planner narrows this to just the addressee."""
    asked = _capture(monkeypatch)
    ctx = _ctx(_cast("mei", "kira", "wren"))

    beat_runner.relationship_note(ctx, "mei", ["kira"], scope="addressed")

    assert asked["others"] == ["kira"]


def test_scene_widens_to_everyone_present_regardless_of_the_caller(monkeypatch):
    """The default. Zero new queries — the same call with a wider id list."""
    asked = _capture(monkeypatch)
    ctx = _ctx(_cast("mei", "kira", "wren"))

    beat_runner.relationship_note(ctx, "mei", ["kira"], scope="scene")

    assert sorted(asked["others"]) == ["kira", "wren"]
    assert "scene_ids" not in asked  # `scene` must not reach the off-scene query at all


def test_scene_skips_a_character_who_is_not_present(monkeypatch):
    asked = _capture(monkeypatch)
    ctx = _ctx(_cast("mei", "kira", "wren", absent=("wren",)))

    beat_runner.relationship_note(ctx, "mei", ["kira"], scope="scene")

    assert asked["others"] == ["kira"]


def test_world_adds_the_off_scene_query_scoped_to_the_storyline(monkeypatch):
    asked = _capture(monkeypatch, offscene=[_edge("Corvin")])
    ctx = _ctx(_cast("mei", "kira"))

    note = beat_runner.relationship_note(ctx, "mei", ["kira"], scope="world")

    assert sorted(asked["scene_ids"]) == ["kira", "mei"]
    assert asked["storyline"] == "embergate"
    assert "Elsewhere: you resents Corvin, who is not in this scene." in note


def test_the_off_scene_clause_says_they_are_elsewhere(monkeypatch):
    """Without the marker a speaker reads these as people in the room, and answers them."""
    _capture(monkeypatch, offscene=[_edge("Corvin", outgoing=False)])
    ctx = _ctx(_cast("mei"))

    note = beat_runner.relationship_note(ctx, "mei", [], scope="world")

    assert note.startswith("Elsewhere:")
    assert "is not in this scene" in note


def test_an_off_scene_reason_is_carried(monkeypatch):
    _capture(monkeypatch, offscene=[_edge("Corvin", reason="the ledger")])
    ctx = _ctx(_cast("mei"))

    assert "(the ledger)" in beat_runner.relationship_note(ctx, "mei", [], scope="world")


def test_the_eight_line_cap_holds_at_world(monkeypatch):
    """The off-scene tail must not push the prompt past the budget the in-scene ties live in."""
    _capture(
        monkeypatch,
        direct=[_edge(f"In{i}") for i in range(6)],
        offscene=[_edge(f"Out{i}") for i in range(8)],
    )
    ctx = _ctx(_cast("mei", "kira"))

    note = beat_runner.relationship_note(ctx, "mei", ["kira"], scope="world")

    assert _entries(note) <= beat_runner._NOTE_LINES
    assert "In0" in note  # the people actually in the room come first
    assert note.count("Elsewhere:") <= beat_runner._NOTE_ELSEWHERE


def test_a_dense_scene_cannot_crowd_the_world_out_entirely(monkeypatch):
    """The bug a live run found: appending the off-scene ties and trimming to 8 meant a world
    with a busy in-scene graph filled the budget and the `world` stop did nothing at all —
    silently, and exactly on the worlds rich enough to want it."""
    _capture(
        monkeypatch,
        direct=[_edge(f"In{i}") for i in range(12)],
        offscene=[_edge("Corvin")],
    )
    ctx = _ctx(_cast("mei", "kira"))

    note = beat_runner.relationship_note(ctx, "mei", ["kira"], scope="world")

    assert "Elsewhere:" in note
    assert _entries(note) <= beat_runner._NOTE_LINES


def test_the_reservation_is_not_taken_when_there_is_nothing_to_put_in_it(monkeypatch):
    """No off-scene ties must mean a byte-identical note to `scene` — the reservation is a
    ceiling on what elsewhere MAY take, not a hole punched in the in-scene lines."""
    _capture(monkeypatch, direct=[_edge(f"In{i}") for i in range(12)], offscene=[])
    ctx = _ctx(_cast("mei", "kira"))

    world = beat_runner.relationship_note(ctx, "mei", ["kira"], scope="world")
    scene = beat_runner.relationship_note(ctx, "mei", ["kira"], scope="scene")

    assert world == scene
    assert _entries(world) == beat_runner._NOTE_LINES


def test_an_unknown_scope_falls_back_to_the_default(monkeypatch):
    """A hand-edited row must not produce a beat with nobody's history in it."""
    asked = _capture(monkeypatch)
    ctx = _ctx(_cast("mei", "kira", "wren"))

    beat_runner.relationship_note(ctx, "mei", ["kira"], scope="nonsense")

    assert sorted(asked["others"]) == ["kira", "wren"]


def test_the_default_scope_is_scene(monkeypatch):
    asked = _capture(monkeypatch)
    ctx = _ctx(_cast("mei", "kira", "wren"))

    beat_runner.relationship_note(ctx, "mei", ["kira"])

    assert sorted(asked["others"]) == ["kira", "wren"]


def test_no_graph_is_the_same_empty_note_at_every_scope(monkeypatch):
    """The degradation that makes this shippable: an install without Neo4j is unchanged."""
    monkeypatch.setattr(graph_reader, "relationship_context", lambda *a, **k: {"direct": [], "indirect": []})
    monkeypatch.setattr(graph_reader, "offscene_ties", lambda *a, **k: [])
    ctx = _ctx(_cast("mei", "kira"))

    for scope in ("addressed", "scene", "world"):
        assert beat_runner.relationship_note(ctx, "mei", ["kira"], scope=scope) == ""
