"""Style guide resolution + rendering.

The rules pinned here are the ones the prefix-cache placement depends on. A render that is
not byte-stable, or an absent block that emits scaffolding, silently costs the cache — and
nothing else in the system would fail loudly if it did.
"""

from __future__ import annotations

from app.content import style_blocks, style_presets
from app.services import style_guide


# ---- normalize --------------------------------------------------------------------


def test_normalize_is_byte_stable_across_cosmetic_differences():
    """Line endings, trailing spaces, blank-line runs and surrounding blanks all collapse."""
    a = style_guide.normalize("\n  Voice.  \r\n\r\n\r\nPeople talk around it.   \n\n")
    b = style_guide.normalize("  Voice.\n\nPeople talk around it.")
    assert a == b == "Voice.\n\nPeople talk around it."


def test_normalize_keeps_leading_indentation_inside_a_block():
    """Indentation can carry meaning (a hanging indent, a list); trailing space cannot.

    So it is preserved rather than stripped. Byte-stability means *the same stored value
    renders identically every time*, not that two differently-written blocks converge.
    """
    text = style_guide.normalize("Voice.\n  - plain\n  - short")
    assert text == "Voice.\n  - plain\n  - short"


def test_normalize_blank_becomes_empty_not_whitespace():
    for blank in ("", "   ", "\n\n", None):
        assert style_guide.normalize(blank) == ""


def test_normalize_blocks_drops_unknown_ids_and_blanks():
    cleaned = style_guide.normalize_blocks(
        {"attention": "Dwell on hands.", "not_a_block": "x", "voice": "   ", "never": None}
    )
    assert cleaned == {"attention": "Dwell on hands."}


# ---- resolve ----------------------------------------------------------------------


def test_blank_at_the_scenario_layer_means_inherit():
    resolved = style_guide.resolve({"voice": "Plain and short."}, {"voice": "   "})
    assert resolved.scenario == {}
    assert resolved.block("voice") == "Plain and short."


def test_scenario_override_wins_for_the_tail_signature():
    resolved = style_guide.resolve({"signature": "World line."}, {"signature": "Scene line."})
    assert resolved.render_signature().endswith("Scene line.")


def test_an_identical_scenario_value_is_not_an_override():
    """A scene that repeats the world's text verbatim must not fragment the cached prefix."""
    resolved = style_guide.resolve({"voice": "Plain."}, {"voice": "Plain."})
    assert resolved.scenario == {}
    assert style_guide._DELTA_HEADER not in resolved.render_prefix()


def test_empty_everywhere_renders_nothing():
    resolved = style_guide.resolve(None, None)
    assert resolved.is_empty
    assert resolved.render_prefix() == ""
    assert resolved.render_planner() == ""
    assert resolved.render_signature() == ""


# ---- render_prefix ----------------------------------------------------------------


def test_prefix_emits_fixed_order_regardless_of_stored_order():
    """Order comes from ``style_blocks.PREFIX_ORDER``, never from the stored dict."""
    forward = style_guide.resolve({"attention": "A.", "voice": "V.", "texture": "T.", "never": "N."})
    backward = style_guide.resolve({"never": "N.", "texture": "T.", "voice": "V.", "attention": "A."})
    assert forward.render_prefix() == backward.render_prefix()
    body = forward.render_prefix()
    assert body.index("Attention.") < body.index("Voice.") < body.index("Texture.") < body.index("Never.")


def test_absent_blocks_emit_nothing_at_all():
    body = style_guide.resolve({"voice": "Plain."}).render_prefix()
    assert "Attention" not in body and "Texture" not in body and "Never" not in body
    # No empty scaffolding, and no run of blank lines where a block was skipped.
    assert "\n\n\n" not in body


def test_pacing_never_reaches_the_prose_prefix():
    body = style_guide.resolve({"pacing": "End early.", "voice": "Plain."}).render_prefix()
    assert "End early." not in body


def test_signature_never_reaches_the_prose_prefix():
    """The signature rides the volatile tail; duplicating it into the prefix wastes cache."""
    body = style_guide.resolve({"signature": "Low and slow.", "voice": "Plain."}).render_prefix()
    assert "Low and slow." not in body


def test_render_is_byte_identical_across_calls():
    resolved = style_guide.resolve(dict(style_presets.ROMANCE.blocks))
    assert resolved.render_prefix() == resolved.render_prefix()
    assert resolved.render_planner() == resolved.render_planner()


# ---- the scenario delta -----------------------------------------------------------


def test_scenario_override_appends_a_delta_and_leaves_the_body_intact():
    """The override must not rewrite the block in place — that would move the cache break."""
    world = {"attention": "World attention.", "voice": "World voice."}
    resolved = style_guide.resolve(world, {"attention": "Scene attention."})
    body = resolved.render_prefix()

    without = style_guide.resolve(world).render_prefix()
    assert body.startswith(without), "the storyline guide must survive verbatim as the prefix"
    assert "World attention." in body
    assert body.index("World attention.") < body.index("Scene attention.")
    assert style_guide._DELTA_HEADER in body


def test_a_delta_for_a_block_the_world_never_set_still_carries_its_precedence_line():
    body = style_guide.resolve({"voice": "V."}, {"attention": "Scene only."}).render_prefix()
    assert style_guide._DELTA_HEADER in body and "Scene only." in body


# ---- render_planner ---------------------------------------------------------------


def test_planner_gets_pacing_and_never_but_not_voice():
    text = style_guide.resolve(dict(style_presets.ACTION.blocks)).render_planner()
    assert style_presets.ACTION.blocks["pacing"] in text
    assert style_presets.ACTION.blocks["never"] in text
    assert style_presets.ACTION.blocks["voice"] not in text


def test_planner_is_empty_when_only_prose_blocks_are_set():
    assert style_guide.resolve({"voice": "Plain."}).render_planner() == ""


# ---- render_signature -------------------------------------------------------------


def test_signature_renders_one_line_or_nothing():
    assert style_guide.resolve({}).render_signature() == ""
    line = style_guide.resolve({"signature": "Close and unsaid."}).render_signature()
    assert line.endswith("Close and unsaid.")
    assert "\n" not in line


# ---- resolve_for ------------------------------------------------------------------


def test_resolve_for_reads_orm_rows_and_tolerates_missing_attributes():
    from app.models.scenario import Scenario
    from app.models.storyline import Storyline

    storyline = Storyline(id="s1", title="W", style_blocks={"voice": "Plain."})
    scenario = Scenario(storyline_id="s1", title="Scene", style_blocks={"voice": "Clipped."})
    resolved = style_guide.resolve_for(storyline, scenario)
    assert resolved.block("voice") == "Clipped."
    assert style_guide.resolve_for(None, None).is_empty


def test_every_block_id_is_reachable_from_the_catalog():
    """A block nothing can render is a block the editor would show and the model never sees."""
    rendered = set(style_blocks.PREFIX_ORDER) | set(style_blocks.PLANNER_ORDER)
    rendered.add(style_blocks.SIGNATURE.id)
    assert rendered == set(style_blocks.ids())
