"""Who speaks next with planning off — deterministic, and no model call.

The point of this path is that it costs nothing, so the most important assertion in this
file is the negative one: with no endpoint configured at all, every decision still comes
back. If any of these ever needs an LLM fixture, the feature has stopped being what it
claims to be.
"""

from __future__ import annotations

from app.agents.direction_agent import DirectionRequirement, SceneDirection
from app.agents.intent_agent import TurnIntent
from app.models import Scenario
from app.services import assembler, beat_order


def _cast(*ids: str, absent: dict[str, str] | None = None) -> list[assembler.CastMember]:
    absent = absent or {}
    return [
        assembler.CastMember(
            id=i, name=i.title(), role="X", traits="", speech="", color="#000",
            stats={}, presence=absent.get(i, "present"),
        )
        for i in ids
    ]


def _ctx(cast) -> assembler.TurnContext:
    return assembler.TurnContext(
        scenario=Scenario(storyline_id="e", title="S", cast_ids=[c.id for c in cast], setting_id=""),
        session_id="ps1",
        storyline_id="e",
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


def test_the_cast_answers_in_order_then_the_turn_ends():
    """The round-robin. Without it, planning-off would give one line per message."""
    ctx = _ctx(_cast("mei", "kira", "wren"))
    acted: list[str] = []
    picked = []
    for _ in range(4):
        d = beat_order.next_beat(ctx, TurnIntent(), acted, beats_left=5)
        if d.action == "end":
            break
        picked.append(d.actor_id)
        acted.append(d.actor_id)
    assert picked == ["mei", "kira", "wren"]
    assert beat_order.next_beat(ctx, TurnIntent(), acted, beats_left=5).action == "end"


def test_the_pov_character_is_never_selected():
    """The player voices them; the model must never produce a second beat for them."""
    ctx = _ctx(_cast("mei", "kira"))
    d = beat_order.next_beat(ctx, TurnIntent(), [], locked_id="mei", beats_left=5)
    assert d.actor_id == "kira"

    d2 = beat_order.next_beat(ctx, TurnIntent(), ["kira"], locked_id="mei", beats_left=5)
    assert d2.action == "end"


def test_an_absent_character_is_skipped():
    ctx = _ctx(_cast("mei", "kira", "wren", absent={"kira": "departed"}))
    acted: list[str] = []
    picked = []
    for _ in range(4):
        d = beat_order.next_beat(ctx, TurnIntent(), acted, beats_left=5)
        if d.action == "end":
            break
        picked.append(d.actor_id)
        acted.append(d.actor_id)
    assert picked == ["mei", "wren"]


def test_an_outstanding_direction_outranks_the_rotation():
    """What the player asked for is owed before whose turn it happens to be."""
    ctx = _ctx(_cast("mei", "kira"))
    direction = SceneDirection(
        text="wren confesses",
        requirements=[DirectionRequirement(id="r1", text="kira admits it", actor_id="kira")],
    )
    d = beat_order.next_beat(ctx, TurnIntent(), [], direction=direction, beats_left=5)
    assert d.action == "speak" and d.actor_id == "kira"


def test_a_narrator_owned_requirement_narrates():
    ctx = _ctx(_cast("mei"))
    direction = SceneDirection(
        text="the lamp goes over",
        requirements=[DirectionRequirement(id="r1", text="the lamp goes over", actor_id=None)],
    )
    d = beat_order.next_beat(ctx, TurnIntent(), [], direction=direction, beats_left=5)
    assert d.action == "narrate"


def test_the_rotation_respects_the_remaining_budget():
    """`beats_left` is the engine's cap, and this must not argue with it."""
    ctx = _ctx(_cast("mei", "kira"))
    assert beat_order.next_beat(ctx, TurnIntent(), ["mei"], beats_left=0).action == "end"


def test_a_cold_scene_open_still_ends_without_forcing_a_speaker():
    """The narrator sets the moment; characters would be talking into an empty room."""
    ctx = _ctx(_cast("mei", "kira"))
    d = beat_order.next_beat(ctx, TurnIntent(), [], scene_opening=True, beats_left=5)
    assert d.action == "end"


def test_no_register_or_stakes_ever():
    """Nobody read the moment, so the character prompt must fall back to its generic cue
    rather than being told a register that was never computed."""
    ctx = _ctx(_cast("mei", "kira"))
    for acted in ([], ["mei"]):
        d = beat_order.next_beat(ctx, TurnIntent(), list(acted), beats_left=5)
        assert d.register is None
        assert d.stakes == ""


def test_an_empty_scene_ends():
    ctx = _ctx(_cast("mei", absent={"mei": "dead"}))
    assert beat_order.next_beat(ctx, TurnIntent(), [], beats_left=5).action == "end"


def test_a_group_scoped_line_still_walks_the_whole_cast():
    """Inherited from `scripted_beat`, and worth pinning: the round-robin must not have
    replaced the behaviour it sits behind."""
    ctx = _ctx(_cast("mei", "kira"))
    d = beat_order.next_beat(ctx, TurnIntent(scope="all"), [], beats_left=5)
    assert d.action == "speak" and d.reason == "next in the group"
