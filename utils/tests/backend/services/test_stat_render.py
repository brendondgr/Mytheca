"""stat_render — current-band resolution + {Character} substitution + block."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.stat_render import (
    current_band,
    render_character_stats,
    substitute_character,
)


def _def(key, display, mx, description="", bands=None):
    return SimpleNamespace(
        key=key, display_name=display, max=mx, description=description, bands=bands or []
    )


def test_substitute_both_token_cases_and_no_token():
    assert substitute_character("{Character} is tired", "Mara") == "Mara is tired"
    assert substitute_character("{character} rests", "Mara") == "Mara rests"
    assert substitute_character("no token here", "Mara") == "no token here"
    assert substitute_character("", "Mara") == ""
    assert substitute_character(None, "Mara") == ""


def test_current_band_boundaries_and_no_match():
    bands = [
        {"min": 0, "max": 20, "label": "Exhausted"},
        {"min": 21, "max": 60, "label": "Capable"},
    ]
    assert current_band(bands, 0)["label"] == "Exhausted"
    assert current_band(bands, 20)["label"] == "Exhausted"
    assert current_band(bands, 21)["label"] == "Capable"
    assert current_band(bands, 99) is None
    assert current_band(None, 5) is None
    # malformed bound rows are skipped, not fatal.
    assert current_band([{"min": "x", "max": 10, "label": "Bad"}], 5) is None


def test_render_picks_current_band_and_substitutes_name():
    stamina = _def(
        "stamina",
        "Stamina",
        100,
        description="{Character}'s capacity for sustained exertion.",
        bands=[
            {"min": 0, "max": 20, "label": "Exhausted", "description": "{Character} is exhausted."},
            {"min": 41, "max": 70, "label": "Capable", "description": "{Character} still has fight."},
        ],
    )
    block = render_character_stats([stamina], {"stamina": 45}, "Marethel")
    assert "Stamina 45/100 (Capable)" in block
    assert "Marethel still has fight." in block  # current band, name-substituted
    assert "Marethel's capacity for sustained exertion." in block  # general desc
    assert "is exhausted" not in block  # the non-current band is not shown
    assert "{Character}" not in block  # every token substituted


def test_render_skips_unset_and_handles_bandless_and_empty():
    a = _def("a", "Alpha", 10)  # no bands, no description
    b = _def("b", "Beta", 10, bands=[{"min": 0, "max": 10, "label": "Mid"}])
    block = render_character_stats([a, b], {"a": 3}, "Mara")  # only 'a' has a value
    assert "- Alpha 3/10" in block
    assert "Beta" not in block  # unset stat omitted
    # nothing to render → empty string.
    assert render_character_stats([a, b], {}, "Mara") == ""
