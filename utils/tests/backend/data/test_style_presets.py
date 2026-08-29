"""The built-in style presets, and the one rule they must never break.

The no-counts rule is not stylistic. The three-tier ``beatLength`` control and the
``maxTurns`` cap were removed because they worked exactly as instructed — beats clustered
regardless of the moment — and ``EXP-2026-08-007`` measured a *word* count moving the average
the wrong way. A preset is prose an author reads and copies, so a count smuggled into one
would spread further than a constant ever did.
"""

from __future__ import annotations

import re

from app.content import style_blocks, style_presets
from app.services import style_guide

#: A length instruction expressed as a quantity, in either digits or words. Deliberately
#: broad: it is easier to reword an innocent match than to notice a real one shipping.
_COUNT = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)[\s-]+"
    r"(to[\s-]+\w+[\s-]+)?"
    r"(word|words|sentence|sentences|paragraph|paragraphs|line|lines|beat|beats|turn|turns)\b",
    re.I,
)
#: Interpolation would make a block volatile and destroy its place in the cached prefix.
_TEMPLATE = re.compile(r"[{}]")


def test_three_presets_in_picker_order():
    assert style_presets.ids() == ["mystery", "romance", "action"]


def test_every_preset_fills_every_block():
    for preset in style_presets.STYLE_PRESETS:
        assert set(preset.blocks) == set(style_blocks.ids()), preset.id
        for block_id, text in preset.blocks.items():
            assert text.strip(), f"{preset.id}.{block_id} is blank"


def test_no_preset_contains_a_length_count():
    for preset in style_presets.STYLE_PRESETS:
        for block_id, text in preset.blocks.items():
            match = _COUNT.search(text)
            assert match is None, (
                f"{preset.id}.{block_id} contains a length count: {match.group(0)!r}. "
                "Counts are why beatLength and maxTurns were removed (EXP-2026-08-007)."
            )


def test_no_preset_contains_an_interpolation_token():
    for preset in style_presets.STYLE_PRESETS:
        for block_id, text in preset.blocks.items():
            assert not _TEMPLATE.search(text), f"{preset.id}.{block_id} looks templated"


def test_signatures_stay_one_short_line():
    """The signature is the only block re-read on every beat — it has to stay cheap."""
    for preset in style_presets.STYLE_PRESETS:
        signature = preset.blocks["signature"]
        assert "\n" not in signature
        assert len(signature) < 120, preset.id


def test_presets_are_already_normalised():
    """Shipped text must render to itself, or the built-ins would fight byte-stability."""
    for preset in style_presets.STYLE_PRESETS:
        for block_id, text in preset.blocks.items():
            assert style_guide.normalize(text) == text, f"{preset.id}.{block_id}"


def test_get_falls_back_rather_than_raising():
    assert style_presets.get("romance") is style_presets.ROMANCE
    assert style_presets.get("nope") is None
    assert style_presets.get(None) is None


def test_romance_preset_matches_the_measured_text():
    """``EXP-2026-08-018`` measured this exact wording; drift must be deliberate.

    Pinned on the opening clause of each block rather than the whole text, so ordinary
    copy-editing is possible but a wholesale rewrite trips.
    """
    blocks = style_presets.ROMANCE.blocks
    assert blocks["attention"].startswith("Spend the prose on proximity")
    assert blocks["voice"].startswith("People say slightly less than they mean")
    assert blocks["texture"].startswith("Shared objects carry the history")
    assert blocks["never"].startswith("Never narrate a feeling a character could show")
    assert blocks["signature"].startswith("Close and unsaid")
