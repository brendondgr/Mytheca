"""The per-scene beat length reaches the character prompt, and says the right thing.

`beat_length` is the owner's control over how much a character says in one beat. It is
useless if it does not reach the prompt, and *worse* than useless if it reaches it while the
output contract is simultaneously asserting a different paragraph count — two instructions
disagreeing inside one prompt is how a setting comes to look like it does nothing.

These tests pin four things:

1. each tier puts its own paragraph count in the prompt,
2. the shape rule (3-4 sentences, quotes exempt) rides along at every tier,
3. an unknown or missing tier falls back to `medium` rather than dropping the block, and
4. the tier lands in the recency TAIL, not the cacheable stable head.
"""

from __future__ import annotations

import pytest

from app.agents import character_turn_agent, prompt_registry
from app.models import Scenario
from app.schemas.base import BEAT_LENGTHS, DEFAULT_BEAT_LENGTH
from app.services import assembler


@pytest.fixture
def turn_context() -> assembler.TurnContext:
    """A minimal context, built here rather than imported from a sibling test module.

    Deliberately constructed straight from the dataclass and NOT through
    `assemble_context`: that is the path a puppet beat and a fixture take, and it is where
    an absent `beat_length` would show up as a missing block rather than a default.
    """
    mei = assembler.CastMember(
        id="c_mei",
        name="Mei",
        role="Cautious smuggler",
        traits="cautious, wary",
        speech="short, clipped lines",
        color="#3A5A78",
        stats={"trust": 38},
        recent_lines=["You always pay twice on these docks."],
    )
    return assembler.TurnContext(
        scenario=Scenario(
            storyline_id="embergate", title="Standoff", cast_ids=["c_mei"], setting_id=""
        ),
        session_id="ps1",
        storyline_id="embergate",
        directed_at="c_mei",
        cast=[mei],
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[{"role": "player", "text": "I sat down.", "characterId": None}],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer="Embergate is a rain-soaked harbor city.",
        stable_prefix="WORLD PRIMER\nEmbergate is a rain-soaked harbor city.",
    )


def _prompt(ctx, speaker) -> str:
    return character_turn_agent._build_user_prompt(ctx, speaker, turn_beats=[])


@pytest.mark.parametrize(
    ("tier", "phrase"),
    [
        ("short", "one or two paragraphs"),
        ("medium", "two to four paragraphs"),
        ("long", "five or six paragraphs"),
    ],
)
def test_each_tier_states_its_own_paragraph_count(turn_context, tier, phrase):
    turn_context.beat_length = tier
    body = _prompt(turn_context, turn_context.cast[0]).lower()
    assert phrase in body
    # ...and only its own. A prompt carrying two counts is the failure this guards, and it
    # is exactly what the output contract used to cause.
    all_counts = {"one or two paragraphs", "two to four paragraphs", "five or six paragraphs"}
    present = {count for count in all_counts if count in body}
    assert present == {phrase}, f"expected only {phrase!r}, found {sorted(present)}"


@pytest.mark.parametrize("tier", BEAT_LENGTHS)
def test_the_shape_rule_rides_along_at_every_tier(turn_context, tier):
    """3-4 sentences per paragraph, with quoted dialogue explicitly exempt.

    The exemption is load-bearing: without it the instruction trades spoken lines against
    description, and speech is the thing the prose work was for.
    """
    turn_context.beat_length = tier
    body = _prompt(turn_context, turn_context.cast[0]).lower()
    assert "three or four sentences" in body
    assert "spoken dialogue do not count" in body


@pytest.mark.parametrize("bad", ["", "tiny", "SHORT", None, "extra-long"])
def test_an_unknown_tier_falls_back_to_the_default(turn_context, bad):
    """A legacy row or a hand-edited database must not silently drop the block."""
    turn_context.beat_length = bad
    body = _prompt(turn_context, turn_context.cast[0]).lower()
    assert "two to four paragraphs" in body


def test_a_context_that_never_set_it_still_gets_a_length(turn_context):
    """The dataclass default is `medium` — a puppet beat or a test context is not lengthless."""
    assert turn_context.beat_length == DEFAULT_BEAT_LENGTH
    assert "two to four paragraphs" in _prompt(turn_context, turn_context.cast[0]).lower()


def test_the_directive_is_in_the_tail_not_the_cacheable_head(turn_context):
    """Per-scenario values must not sit in the byte-stable prefix.

    `_build_user_prompt` emits stable / middle / volatile separated by blank lines, and the
    prompt cache matches from the first token. A tier in the head would change the prefix
    whenever the owner touched the dropdown, throwing away the reuse
    `test_prompt_cache_prefix.py` exists to protect.
    """
    turn_context.beat_length = "long"
    body = _prompt(turn_context, turn_context.cast[0])
    head = body.split("\n\n")[0]
    assert "five or six paragraphs" not in head
    # Present overall, and in the final third of the prompt.
    assert body.lower().rindex("five or six paragraphs") > len(body) * 0.5


def test_the_output_contract_no_longer_fixes_a_paragraph_count():
    """The contract owns the FORM; the tail owns the AMOUNT.

    The contract used to say "Two or three of them", which is a hardcoded `medium` and
    contradicts `short` and `long` in the same prompt.
    """
    contract = prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT).lower()
    assert "blank line between paragraphs" in contract  # the rule survives
    assert "two or three of them" not in contract  # the count does not
