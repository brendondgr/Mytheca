"""The free-text prompt: one cached prefix, one instruction per call.

Free-text makes four to six model calls for a single turn. Every one of them has to be
byte-identical up to its final block, or the mode costs more than the engine it replaces —
and a cache miss is invisible, because it is only ever slower and never wrong. So the
sharing is pinned here rather than left to be noticed in production latency.
"""

from __future__ import annotations

import pytest

from app.services import freetext_context
from app.services.assembler import CastMember, TurnContext


class FakeStatDef:
    def __init__(self, key, display_name, bands=None, description=""):
        self.key = key
        self.display_name = display_name
        self.min = 0
        self.max = 10
        self.bands = bands or []
        self.description = description


class FakeSetting:
    name = "The Drowned Lamp"
    atmosphere = "low ceilings, wet stone"
    current_state = ""
    desc = ""


class FakeScenario:
    title = "A Debt Comes Due"


def member(cid, name, **kwargs) -> CastMember:
    defaults = dict(
        role="smuggler",
        traits="watchful, slow to anger",
        speech="clipped, never explains twice",
        color="#fff",
        stats={"trust": 4},
    )
    return CastMember(id=cid, name=name, **{**defaults, **kwargs})


def context(**kwargs) -> TurnContext:
    defs = [
        FakeStatDef(
            "trust",
            "Trust",
            bands=[{"min": 0, "max": 5, "label": "Wary", "description": "{Character} keeps a hand free."}],
        )
    ]
    defaults = dict(
        scenario=FakeScenario(),
        session_id="s1",
        storyline_id="w1",
        directed_at=None,
        cast=[member("c1", "Mei"), member("c2", "Valdar")],
        setting=FakeSetting(),
        stat_defs=defs,
        stat_guidance={"trust": "How far they will let someone stand behind them."},
        recent_beats=[],
        subgraph={},
        world_primer="The harbour runs on favours nobody writes down.",
        stable_prefix="",
    )
    return TurnContext(**{**defaults, **kwargs})


# ---- the cached prefix -----------------------------------------------------


def test_the_system_message_is_identical_for_every_call_of_a_turn():
    """The whole economic argument for the mode rests on this one assertion."""
    ctx = context()
    prefixes = {
        freetext_context.messages(ctx, [], instruction=text)[0]["content"]
        for text in ("look things up", "write the checklist", "write the scene", "grade it")
    }
    assert len(prefixes) == 1


def test_a_stat_change_does_not_touch_the_system_message():
    """The point of splitting identity from values: the largest block must not move.

    A stat is the most frequently changing fact in the game. If its value lived in the
    cached block, the first time anyone was hurt the whole prefix would be re-read.
    """
    before = freetext_context.system_message(context())
    hurt = context(cast=[member("c1", "Mei", stats={"trust": 1}), member("c2", "Valdar")])
    assert freetext_context.system_message(hurt) == before


def test_the_live_values_are_in_the_tail_where_they_belong():
    ctx = context()
    tail = freetext_context.tail(ctx, instruction="write the scene")
    assert "Trust 4/10" in tail
    assert "Wary" in tail
    assert "Mei keeps a hand free." in tail  # {Character} is substituted per person


def test_the_whole_cast_is_in_the_prefix_with_identity_but_no_values():
    system = freetext_context.system_message(context())
    assert "Mei" in system and "Valdar" in system
    assert "watchful, slow to anger" in system
    assert "clipped, never explains twice" in system
    assert "Trust 4/10" not in system


def test_an_absent_character_stays_in_the_prefix_and_is_marked():
    """Dropping them would edit the cached block mid-scene and buy nothing.

    The scene still has to be able to talk *about* someone who walked out.
    """
    ctx = context(cast=[member("c1", "Mei"), member("c2", "Valdar", presence="left")])
    system = freetext_context.system_message(ctx)
    assert "Valdar" in system
    assert "NOT IN THE SCENE (left)" in system


def test_the_prefix_carries_the_world_the_place_and_what_the_stats_mean():
    system = freetext_context.system_message(context())
    assert "A Debt Comes Due" in system
    assert "favours nobody writes down" in system
    assert "The Drowned Lamp" in system
    assert "let someone stand behind them" in system


# ---- the tail --------------------------------------------------------------


def test_the_instruction_is_the_last_thing_in_the_prompt():
    """Last is both the cache-correct position and the strongest attention position."""
    tail = freetext_context.tail(context(), instruction="GRADE THE PASSAGE.")
    assert tail.rstrip().endswith("GRADE THE PASSAGE.")


def test_playwright_turns_state_that_there_is_nobody_to_address():
    tail = freetext_context.tail(context(), instruction="write")
    assert "nobody to address" in tail
    assert "Direction:" in tail


def test_a_pov_character_is_declared_off_limits():
    """The structured engine enforces this by dropping them from the roster.

    A free-text body has no roster to drop anyone from, so it is a prompt rule or nothing.
    """
    ctx = context()
    tail = freetext_context.tail(ctx, instruction="write", pov=ctx.cast[0])
    assert "Never write new dialogue or a new decision for Mei" in tail
    assert "nobody to address" not in tail  # the Playwright rule must not also fire


def test_the_addressed_character_is_named_in_the_tail():
    ctx = context(directed_at="c2")
    assert "aimed this turn at Valdar" in freetext_context.tail(ctx, instruction="write")


# ---- assembly --------------------------------------------------------------


def test_history_leads_the_user_message_and_the_instruction_closes_it():
    ctx = context(history_summary="They agreed a price in the spring.")
    msgs = freetext_context.messages(ctx, [], instruction="WRITE IT.")
    user = msgs[1]["content"]
    assert user.index("agreed a price") < user.index("WRITE IT.")


def test_a_scene_with_no_history_still_assembles():
    msgs = freetext_context.messages(context(), [], instruction="WRITE IT.")
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert msgs[1]["content"].strip().endswith("WRITE IT.")


@pytest.mark.parametrize("lore", ["", None])
def test_no_lore_adds_nothing(lore):
    tail = freetext_context.tail(context(), instruction="write", lore=lore)
    assert "Relevant established world lore" not in tail


def test_looked_up_lore_overrides_whatever_the_assembler_gated_in():
    """Free-text decides its own lookups; the keyword gate's answer must not leak in."""
    ctx = context(retrieved_lore="GATED BLOCK")
    tail = freetext_context.tail(ctx, instruction="write", lore="LOOKED-UP BLOCK")
    assert "LOOKED-UP BLOCK" in tail and "GATED BLOCK" not in tail
