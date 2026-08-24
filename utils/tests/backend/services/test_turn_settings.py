"""What one turn runs with: the scene's controls, with this turn's overrides on top.

The resolver is four lines of arithmetic, and every one of them is a place a per-turn
control could silently stop working — so each is pinned here rather than left to the API
test, which can only see the consequences.
"""

from __future__ import annotations

import pytest

from app.models import Scenario
from app.schemas.play import TurnOverrides
from app.services import turn_settings


def scene(**kwargs) -> Scenario:
    """A scenario row with the play controls set. Not persisted — the resolver is pure."""
    defaults = {"suggestions_count": 4}
    return Scenario(**{**defaults, **kwargs})


def test_no_envelope_is_the_scenario():
    assert turn_settings.resolve(scene(suggestions_count=2)).suggestions_count == 2


def test_empty_envelope_is_identical_to_none():
    """The whole feature is additive only if these two are the same answer."""
    scenario = scene(suggestions_count=1)
    assert turn_settings.resolve(scenario, TurnOverrides()) == turn_settings.resolve(scenario)


def test_override_wins_per_field():
    resolved = turn_settings.resolve(
        scene(suggestions_count=4), TurnOverrides(suggestions_count=1)
    )
    assert resolved.suggestions_count == 1


def test_the_retired_controls_are_ignored_rather_than_rejected():
    """`maxTurns` and `beatLength` are gone as controls, and an old client must not break.

    Pacing is the scene's business now: how many beats a message makes and how long a beat
    is are decided by the planner and the moment, not set once in a popover. A saved client
    or a bookmarked request still sending the old fields gets them **ignored** — pydantic
    drops unknown keys — rather than a 422, which is the right outcome for a control that no
    longer exists.
    """
    envelope = TurnOverrides.model_validate({"maxTurns": 2, "beatLength": "long",
                                             "suggestionsCount": 1})
    assert not hasattr(envelope, "max_turns")
    assert not hasattr(envelope, "beat_length")
    assert envelope.suggestions_count == 1
    # And nothing about them reaches the resolved settings.
    resolved = turn_settings.resolve(scene(), envelope)
    assert not hasattr(resolved, "max_turns")
    assert not hasattr(resolved, "beat_length")


def test_zero_suggestions_is_a_request_not_an_absence():
    """`0` is falsy and means *silence the follow-ups*. A truthiness test loses it."""
    resolved = turn_settings.resolve(scene(suggestions_count=4), TurnOverrides(suggestions_count=0))
    assert resolved.suggestions_count == 0


@pytest.mark.parametrize(
    ("column", "value", "field", "expected"),
    [
        ("suggestions_count", -3, "suggestions_count", 0),
        ("suggestions_count", 40, "suggestions_count", turn_settings.MAX_SUGGESTIONS),
    ],
)
def test_a_hand_edited_row_is_re_clamped(column, value, field, expected):
    """The schema guards the request boundary; this guards the data behind it."""
    assert getattr(turn_settings.resolve(scene(**{column: value})), field) == expected


def test_settings_are_frozen():
    resolved = turn_settings.resolve(scene())
    with pytest.raises(Exception):
        resolved.suggestions_count = 99  # type: ignore[misc]


def test_applied_is_empty_for_nothing_overridden():
    assert turn_settings.applied(None) == {}
    assert turn_settings.applied(TurnOverrides()) == {}


def test_applied_is_the_non_null_map_in_wire_case():
    """It is written to a JSON column and read by the frontend, so it is camelCase."""
    assert turn_settings.applied(TurnOverrides(suggestions_count=0)) == {
        "suggestionsCount": 0,
    }


# ---- the register pin: who decides how a beat is pitched -------------------


class _Decision:
    """Just enough of a `BeatDecision` for `pitch` — it reads one attribute."""

    def __init__(self, register: str | None):
        self.register = register


def test_a_pinned_register_outranks_the_planner():
    """The player is looking at the scene; the planner is inferring it."""
    resolved = turn_settings.resolve(scene(), TurnOverrides(register="grave"))
    assert turn_settings.pitch(resolved, _Decision("light")) == ("grave", "player")


def test_the_planner_decides_when_nothing_is_pinned():
    assert turn_settings.pitch(turn_settings.resolve(scene()), _Decision("tense")) == (
        "tense",
        "planner",
    )


def test_neither_is_a_real_third_case():
    """With planning off nobody reads the moment — which is exactly when a pin is the only
    source of a register there is."""
    assert turn_settings.pitch(turn_settings.resolve(scene()), _Decision(None)) == (None, "")
    assert turn_settings.pitch(turn_settings.resolve(scene()), None) == (None, "")


def test_a_pin_survives_a_beat_that_had_no_decision_at_all():
    """The puppet, forced-direction and silent-turn paths pass `None` — they never consult
    the planner, and before this phase they carried no register whatsoever."""
    resolved = turn_settings.resolve(scene(), TurnOverrides(register="light"))
    assert turn_settings.pitch(resolved, None) == ("light", "player")


def test_the_register_is_per_turn_only():
    """There is no scenario column, deliberately: how tense a beat is belongs to a moment."""
    assert turn_settings.resolve(scene()).register is None
    assert not hasattr(scene(), "register")
