"""Consequences declared by a passage that belongs to nobody in particular.

The structured engine always knows whose beat it is applying a change to. A free-text body
has no speaker, so every block names its subject — and the resolution has one rule that
matters more than the rest: it never guesses. Applying a wound to the wrong character is
worse than applying it to nobody.
"""

from __future__ import annotations

import pytest

from app.services import freetext_effects
from app.services.assembler import CastMember, TurnContext


class FakeScenario:
    title = "A Debt Comes Due"


def member(cid, name, **kwargs) -> CastMember:
    defaults = dict(role="smuggler", traits="", speech="", color="#fff", stats={})
    return CastMember(id=cid, name=name, **{**defaults, **kwargs})


def context(cast=None) -> TurnContext:
    return TurnContext(
        scenario=FakeScenario(),
        session_id="s1",
        storyline_id="w1",
        directed_at=None,
        cast=cast if cast is not None else [member("c1", "Mei Aldren"), member("c2", "Valdar")],
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[],
        subgraph={},
        world_primer="",
        stable_prefix="",
    )


# ---- splitting the prose from the machinery --------------------------------


def test_the_prose_stops_at_the_first_tag():
    raw = 'She lets it sit.\n\n<type:state_update>\n{"character": "Mei", "key": "trust"}'
    assert freetext_effects.split_prose(raw) == "She lets it sit."


def test_a_passage_with_no_blocks_is_returned_whole():
    assert freetext_effects.split_prose("She lets it sit.") == "She lets it sit."


# ---- parsing ---------------------------------------------------------------


def test_every_block_is_found_with_its_payload():
    raw = (
        "prose\n"
        '<type:state_update>\n{"character": "Mei", "key": "trust", "delta": -1}\n'
        '<type:presence_change>\n{"character": "Valdar", "status": "left"}'
    )
    blocks = freetext_effects.parse_blocks(raw)
    assert [kind for kind, _ in blocks] == ["state_update", "presence_change"]
    assert blocks[0][1]["delta"] == -1


def test_a_closing_style_tag_parses_identically():
    """Models emit `</type:x>` as a delimiter often enough that the two must be one case."""
    raw = 'prose\n</type:state_update>\n{"character": "Mei", "key": "trust", "delta": 1}'
    assert freetext_effects.parse_blocks(raw)[0][0] == "state_update"


def test_a_malformed_block_does_not_take_its_siblings_with_it():
    raw = (
        "prose\n"
        "<type:state_update>\nnot json at all\n"
        '<type:presence_change>\n{"character": "Valdar", "status": "left"}'
    )
    blocks = freetext_effects.parse_blocks(raw)
    assert [kind for kind, _ in blocks] == ["presence_change"]


def test_nested_objects_and_braces_in_strings_survive():
    raw = '<type:state_update>\n{"character": "Mei", "reason": "she said {no}", "delta": -1}'
    assert freetext_effects.parse_blocks(raw)[0][1]["reason"] == "she said {no}"


def test_trailing_prose_after_the_json_is_ignored():
    raw = '<type:state_update>\n{"character": "Mei", "delta": -1}\nThat is all.'
    assert freetext_effects.parse_blocks(raw)[0][1]["delta"] == -1


# ---- resolving who ---------------------------------------------------------


@pytest.mark.parametrize("named", ["Valdar", "valdar", "  Valdar  ", "Valdar."])
def test_a_name_resolves_however_it_is_written(named):
    assert freetext_effects.resolve_character(context(), named) == "c2"


def test_a_first_name_resolves_to_the_character_it_starts():
    """Prose says "Mei", the cast sheet says "Mei Aldren"."""
    assert freetext_effects.resolve_character(context(), "Mei") == "c1"


def test_an_unknown_name_resolves_to_nobody():
    assert freetext_effects.resolve_character(context(), "Someone Else") is None
    assert freetext_effects.resolve_character(context(), "") is None
    assert freetext_effects.resolve_character(context(), None) is None


def test_an_ambiguous_first_name_is_refused_rather_than_guessed():
    """Applying a wound to the wrong character is worse than applying it to nobody."""
    ctx = context([member("c1", "Mei Aldren"), member("c2", "Mei Corran")])
    assert freetext_effects.resolve_character(ctx, "Mei") is None


def test_a_present_character_wins_over_an_absent_one_of_the_same_name():
    ctx = context([member("c1", "Mei", presence="left"), member("c2", "Mei")])
    assert freetext_effects.resolve_character(ctx, "Mei") == "c2"


def test_someone_who_has_left_can_still_be_named():
    """A passage may perfectly well record that a departed character is now feared."""
    ctx = context([member("c1", "Mei"), member("c2", "Valdar", presence="left")])
    assert freetext_effects.resolve_character(ctx, "Valdar") == "c2"
