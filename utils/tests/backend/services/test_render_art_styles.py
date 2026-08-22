"""Art styles reaching the three render paths: portraits, scene art, and in-play moments.

Every image the product generates goes through one of these three functions, so this is
where "the style is obeyed everywhere" is actually pinned down. ComfyUI is stubbed — what
is under test is the *arguments* the pipeline is handed, not the picture.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.schemas.settings import ArtStyleOverride, ComfyConfigUpdate
from app.services import comfyui, portraits, scene_art, settings_store


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), (120, 90, 60)).save(buf, format="PNG")
    return buf.getvalue()


def _capture(monkeypatch) -> dict:
    captured: dict = {}

    def fake_generate(base, workflow, **kwargs):
        captured.update(kwargs)
        return _png_bytes(), {"filename": "out.png", "subfolder": "", "type": "output"}

    monkeypatch.setattr(comfyui, "generate", fake_generate)
    return captured


# ---- portraits -------------------------------------------------------------


def test_default_portrait_render_keeps_the_painted_lora(db_session, tmp_path, monkeypatch):
    """The pre-style behaviour is the default: watercolor LoRA on, at its authored strength."""
    captured = _capture(monkeypatch)
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    portraits.generate_portrait(db_session, "young orc warrior")

    assert captured["lora_enabled"] is True
    assert captured["lora_name"] == "zit_watercolor.safetensors"
    assert captured["lora_strength"] == 0.8
    assert "watercolor portrait" in captured["positive"]


def test_a_photoreal_portrait_bypasses_the_lora_and_restyles_the_prompt(
    db_session, tmp_path, monkeypatch
):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    portraits.generate_portrait(
        db_session, "young orc warrior, watercolor portrait, soft washes", style="photoreal"
    )

    assert captured["lora_enabled"] is False
    assert "photorealistic portrait" in captured["positive"]
    assert "watercolor" not in captured["positive"].lower()
    # The contradiction that would otherwise survive: painted pushes photorealism away.
    assert "photorealistic" not in captured["negative"]


def test_an_anime_portrait_carries_anime_tags(db_session, tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    portraits.generate_portrait(db_session, "young orc warrior", style="anime")

    assert "cel shaded" in captured["positive"]
    assert captured["lora_enabled"] is False


def test_a_portrait_uses_the_stored_default_when_none_is_asked_for(
    db_session, tmp_path, monkeypatch
):
    settings_store.update_comfy(db_session, ComfyConfigUpdate(art_style="anime"))
    captured = _capture(monkeypatch)
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    portraits.generate_portrait(db_session, "young orc warrior")

    assert "cel shaded" in captured["positive"]


def test_a_portrait_honours_an_operator_lora_override(db_session, tmp_path, monkeypatch):
    """Pointing a style at a different LoRA is an Options change, not a code change."""
    settings_store.update_comfy(
        db_session,
        ComfyConfigUpdate(
            styles={
                "painted": ArtStyleOverride(
                    lora_name="zit_oilpainting.safetensors", lora_strength=0.6
                )
            }
        ),
    )
    captured = _capture(monkeypatch)
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    portraits.generate_portrait(db_session, "young orc warrior", style="painted")

    assert captured["lora_name"] == "zit_oilpainting.safetensors"
    assert captured["lora_strength"] == 0.6


def test_turning_the_painted_lora_off_bypasses_it(db_session, tmp_path, monkeypatch):
    settings_store.update_comfy(
        db_session, ComfyConfigUpdate(styles={"painted": ArtStyleOverride(lora_enabled=False)})
    )
    captured = _capture(monkeypatch)
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    portraits.generate_portrait(db_session, "young orc warrior", style="painted")

    assert captured["lora_enabled"] is False


# ---- scene art (settings AND scenarios share this function) ----------------


def test_scene_art_applies_the_scene_tags_not_the_portrait_ones(
    db_session, tmp_path, monkeypatch
):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(scene_art, "_scenes_dir", lambda: tmp_path)

    scene_art.generate_scene_art(db_session, "a fog-bound harbor at dawn", style="anime")

    assert "anime background art" in captured["positive"]
    assert "anime portrait" not in captured["positive"]
    assert captured["lora_enabled"] is False


def test_scene_art_defaults_to_painted_with_its_lora(db_session, tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(scene_art, "_scenes_dir", lambda: tmp_path)

    scene_art.generate_scene_art(db_session, "a fog-bound harbor at dawn")

    assert captured["lora_name"] == "zit_watercolor.safetensors"
    assert "watercolor" in captured["positive"]


def test_an_unknown_style_renders_rather_than_failing(db_session, tmp_path, monkeypatch):
    """An image request must never 400 because a stale client named a retired style."""
    captured = _capture(monkeypatch)
    monkeypatch.setattr(scene_art, "_scenes_dir", lambda: tmp_path)

    result = scene_art.generate_scene_art(db_session, "a harbor", style="sepia-woodcut")

    assert result["image"].startswith("/media/scenes/")
    assert "watercolor" in captured["positive"]
