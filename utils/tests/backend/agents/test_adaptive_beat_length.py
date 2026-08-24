"""Beat length is adaptive: the prompt states a principle, never a number.

The three-tier `beat_length` control this file used to pin is gone. It worked — which was
the defect. A live smoke run over two turns produced character beats of 4, 3, 5, 5, 3, 3, 4,
3, 3 paragraphs: a tight band around whichever tier was set, on moments that plainly
differed. A count is the one thing a model can obey without judging, so a count in the prompt
makes length an input rather than a consequence of the beat.

These tests pin what replaced it:

1. no paragraph count reaches the prompt, from any direction,
2. both ends of the range are explicitly allowed, so the model cannot infer a safe middle,
3. the directive still lands in the recency TAIL, not the cacheable stable head, and
4. the prose token ceiling is ONE number for every beat, and still a runaway backstop rather
   than an editorial limit.
"""

from __future__ import annotations

import re

import pytest

from app.agents import character_turn_agent, prompt_registry
from app.models import Scenario
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



def _prompt(ctx, speaker) -> str:
    return character_turn_agent._build_user_prompt(ctx, speaker, turn_beats=[])


#: Every way a paragraph count has been spelled in this prompt's history, plus the shapes a
#: future edit would most likely reach for. The point is not that these exact strings are
#: banned — it is that a NUMBER of paragraphs must not appear at all.
_COUNT_PHRASES = (
    "one or two paragraphs",
    "two to four paragraphs",
    "five or six paragraphs",
    "three or four sentences",
    "two or three of them",
)


def test_no_paragraph_count_reaches_the_prompt(turn_context):
    """The whole prompt, not just the directive — a count anywhere binds just as hard."""
    body = _prompt(turn_context, turn_context.cast[0]).lower()
    for phrase in _COUNT_PHRASES:
        assert phrase not in body, f"a paragraph count came back: {phrase!r}"
    # And no numeral-plus-paragraphs of any wording, which is the general form a count takes.
    #
    # PLURAL only, deliberately. The singular "one paragraph" is the floor the directive has
    # to state out loud (see the next test) — it grants permission to be short rather than
    # setting a target, which is the opposite of a count. An earlier version of this pattern
    # matched it and failed on the very phrasing it exists to protect.
    counts = r"one|two|three|four|five|six|seven|eight|nine|ten|\d+"
    assert not re.search(
        rf"\b(?:{counts})\s+(?:(?:to|or)\s+(?:{counts})\s+)?paragraphs\b", body
    ), "a paragraph count came back"


def test_both_ends_of_the_range_are_explicitly_allowed(turn_context):
    """A model given only "as long as it needs" infers a safe middle and sits in it.

    The floor and the ceiling have to sound permitted in as many words, or the directive is
    just a vaguer version of the tier it replaced.
    """
    body = _prompt(turn_context, turn_context.cast[0]).lower()
    assert "one paragraph" in body  # the floor is a complete beat
    assert "as long as" in body  # the ceiling is not a stopping point


def test_padding_and_truncating_are_both_named(turn_context):
    """The two failure modes are opposite, and naming only one biases the other way."""
    body = _prompt(turn_context, turn_context.cast[0]).lower()
    assert "never pad" in body
    assert "never cut" in body


def test_no_word_count_ever(turn_context):
    """EXP-2026-08-007 measured a word target moving the average the WRONG way.

    A model cannot count words while writing, so "usually 80-200 words" reads to it as a
    description of the register — long, careful prose — and it obliges. Whatever this
    directive becomes, it must not reintroduce one.
    """
    body = _prompt(turn_context, turn_context.cast[0]).lower()
    assert not re.search(r"\b\d+\s*(?:-|to|–)\s*\d+\s+words\b", body)
    assert not re.search(r"\b\d+\s+words\b", body)


def test_the_directive_is_in_the_tail_not_the_cacheable_head(turn_context):
    """Per-beat values must not sit in the byte-stable prefix.

    `_build_user_prompt` emits stable / middle / volatile separated by blank lines, and the
    prompt cache matches from the first token. Length guidance in the head would change the
    prefix and throw away the reuse `test_prompt_cache_prefix.py` exists to protect.
    """
    body = _prompt(turn_context, turn_context.cast[0])
    head = body.split("\n\n")[0]
    assert "LENGTH:" not in head
    # After the transcript, which is the actual boundary between the append-only middle and
    # the volatile tail. A percentage of the prompt's length is not the property under test
    # and fails on a short fixture for reasons that have nothing to do with placement.
    assert body.rindex("LENGTH:") > body.index("Recent beats:")


def test_the_output_contract_states_form_and_never_amount():
    """The contract owns the FORM; the tail owns the AMOUNT. Neither owns a count."""
    contract = prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT).lower()
    assert "blank line between paragraphs" in contract  # the rule survives
    for phrase in _COUNT_PHRASES:
        assert phrase not in contract


def test_one_prose_allowance_for_every_beat():
    """The per-tier token table is gone, and must not come back.

    With length adaptive, a tier-shaped ceiling would be the only thing left telling a beat
    how long to be — and it would do it by cutting the prose off mid-sentence, which is the
    worst available way to shape writing.
    """
    baseline = character_turn_agent.prose_tokens_for()
    assert baseline == 2048
    # Every old tier name, and nonsense, all resolve to the same single number. The argument
    # is accepted and ignored so an old caller keeps working rather than raising.
    for stale in ("short", "medium", "long", "tiny", "", None):
        assert character_turn_agent.prose_tokens_for(stale) == baseline


def test_the_allowance_is_a_runaway_backstop_not_an_editorial_limit():
    """Sized against measurement, not caution.

    EXP-2026-08-007 measured a passage at 674 +/- 471 characters with a worst case of 1,923.
    At roughly four characters a token the ceiling sits about four times past the worst
    honest beat, so writing never reaches it — which is exactly what lets the directive above
    say "as long as it takes" and mean it.
    """
    chars = character_turn_agent.prose_tokens_for() * 4
    assert chars > 1_923 * 3


def test_the_thinking_budget_is_still_added_on_top():
    """Shrinking the COMBINED total is what starved a live beat into reasoning and no prose.

    The prose allowance and the scratchpad are separate budgets; this pins that they stay
    that way, because the failure it prevents produced an empty beat rather than a short one.
    """
    assert character_turn_agent._SCRATCHPAD_HEADROOM >= 1
