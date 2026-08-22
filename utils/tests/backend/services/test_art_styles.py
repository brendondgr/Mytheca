"""Art-style catalog: integrity, safe lookup, and what ``apply_style`` does to a prompt."""

from __future__ import annotations

import pytest

from app.content import art_styles


# ---- catalog integrity -----------------------------------------------------


def test_catalog_holds_the_three_styles_in_display_order():
    assert art_styles.ids() == ["painted", "anime", "photoreal"]


def test_default_is_painted_and_is_in_the_catalog():
    assert art_styles.DEFAULT_STYLE_ID == "painted"
    assert art_styles.get(art_styles.DEFAULT_STYLE_ID).id == "painted"


@pytest.mark.parametrize("style", art_styles.catalog(), ids=lambda s: s.id)
def test_every_style_is_fully_authored(style):
    assert style.label and style.blurb and style.model_hint
    for surface in ("portrait", "scene", "moment"):
        assert style.tags_for(surface).strip(), surface
    assert style.negative_tags.strip()


@pytest.mark.parametrize("style", art_styles.catalog(), ids=lambda s: s.id)
def test_every_moment_style_frames_landscape(style):
    """A portrait-orientation moment image is a bug in any look, so the tag is universal."""
    assert art_styles.LANDSCAPE_TAG in style.moment_tags


def test_only_painted_ships_with_a_lora():
    assert art_styles.PAINTED.default_lora == "zit_watercolor.safetensors"
    assert art_styles.ANIME.default_lora is None
    assert art_styles.PHOTOREAL.default_lora is None


def test_painted_tags_are_the_pre_style_wording():
    """The default render must be unchanged by the introduction of styles."""
    assert art_styles.PAINTED.portrait_tags.startswith("watercolor portrait, soft washes")
    assert art_styles.PAINTED.scene_tags.startswith("watercolor, soft washes, painterly")


# ---- lookup ----------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   ", "sepia-woodcut"])
def test_unknown_or_missing_ids_fall_back_to_the_default(value):
    """An image request must never fail because a stale client named a retired style."""
    assert art_styles.get(value).id == art_styles.DEFAULT_STYLE_ID


# ---- apply_style -----------------------------------------------------------


def test_apply_style_appends_missing_tags_to_a_bare_prompt():
    positive, negative = art_styles.apply_style(
        "a lone rider on a ridge", "", art_styles.ANIME, surface="moment"
    )
    assert "cel shaded" in positive
    assert positive.startswith("a lone rider on a ridge")
    assert "photorealistic" in negative


def test_apply_style_is_idempotent():
    once = art_styles.apply_style("a harbor at dawn", "blurry", art_styles.PAINTED, surface="scene")
    twice = art_styles.apply_style(*once, art_styles.PAINTED, surface="scene")
    assert twice == once


def test_apply_style_does_not_duplicate_a_tag_the_writer_already_used():
    positive, _ = art_styles.apply_style(
        "a harbor at dawn, Watercolor, soft washes", None, art_styles.PAINTED, surface="scene"
    )
    assert positive.lower().count("watercolor") == 1


def test_switching_style_drops_the_previous_style_tags():
    """A prompt stored while painted must not still say 'watercolor' when re-rendered photoreal."""
    stored, _ = art_styles.apply_style("an old sailor", None, art_styles.PAINTED, surface="portrait")
    assert "watercolor portrait" in stored

    switched, _ = art_styles.apply_style(stored, None, art_styles.PHOTOREAL, surface="portrait")
    assert "watercolor" not in switched.lower()
    assert "soft washes" not in switched.lower()
    assert "photorealistic portrait" in switched
    assert switched.startswith("an old sailor")


def test_switching_style_drops_a_contradicting_negative():
    """`painted` pushes photorealism away; a photoreal render must not inherit that."""
    _, painted_negative = art_styles.apply_style(
        "a harbor", "blurry, lowres", art_styles.PAINTED, surface="scene"
    )
    assert "photorealistic" in painted_negative

    _, switched = art_styles.apply_style(
        "a harbor", painted_negative, art_styles.PHOTOREAL, surface="scene"
    )
    assert "photorealistic" not in switched
    assert "blurry" in switched and "lowres" in switched
    assert "painting" in switched


def test_apply_style_keeps_tags_every_style_shares():
    """`3d render` is pushed away by all three, so a style switch must not strip it."""
    _, negative = art_styles.apply_style(
        "a face", "3d render, watermark", art_styles.PHOTOREAL, surface="portrait"
    )
    assert "3d render" in negative
    assert "watermark" in negative


def test_apply_style_keeps_the_writers_own_subject_phrases():
    positive, _ = art_styles.apply_style(
        "young orc warrior, scarred brow, iron collar",
        None,
        art_styles.ANIME,
        surface="portrait",
    )
    for phrase in ("young orc warrior", "scarred brow", "iron collar"):
        assert phrase in positive
