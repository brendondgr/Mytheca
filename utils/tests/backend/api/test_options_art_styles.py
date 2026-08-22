"""The art-style half of the ComfyUI settings: default style, per-style LoRA, resolution."""

from __future__ import annotations

from app.content import art_styles
from app.schemas.settings import ArtStyleOverride, ComfyConfigUpdate
from app.services import settings_store


# ---- the read payload ------------------------------------------------------


def test_defaults_expose_the_catalog_with_painted_selected(client):
    comfy = client.get("/api/options").json()["comfy"]
    assert comfy["artStyle"] == "painted"
    assert [s["id"] for s in comfy["styles"]] == ["painted", "anime", "photoreal"]


def test_only_painted_ships_with_its_lora_on(client):
    styles = {s["id"]: s for s in client.get("/api/options").json()["comfy"]["styles"]}
    assert styles["painted"]["loraEnabled"] is True
    assert styles["painted"]["loraName"] == "zit_watercolor.safetensors"
    assert styles["painted"]["loraStrength"] == 0.8
    # No anime LoRA is installed and the base checkpoint is realism-leaning, so both
    # non-painted styles bypass the workflow's LoRA node until an operator says otherwise.
    assert styles["anime"]["loraEnabled"] is False
    assert styles["photoreal"]["loraEnabled"] is False


def test_every_style_carries_a_label_and_blurb_for_the_picker(client):
    for style in client.get("/api/options").json()["comfy"]["styles"]:
        assert style["label"] and style["blurb"]


# ---- patching --------------------------------------------------------------


def test_patch_default_art_style_persists(client):
    patched = client.patch("/api/options/comfy", json={"artStyle": "anime"}).json()
    assert patched["artStyle"] == "anime"
    assert client.get("/api/options").json()["comfy"]["artStyle"] == "anime"


def test_an_unknown_style_falls_back_rather_than_failing_the_save(client):
    """A stale client must not be able to 400 the whole settings form."""
    res = client.patch("/api/options/comfy", json={"artStyle": "sepia-woodcut", "workflow": "X.json"})
    assert res.status_code == 200
    assert res.json()["artStyle"] == "painted"
    assert res.json()["workflow"] == "X.json"


def test_patch_a_style_lora(client):
    body = {"styles": {"anime": {"loraName": "my_anime.safetensors", "loraStrength": 0.65, "loraEnabled": True}}}
    styles = {s["id"]: s for s in client.patch("/api/options/comfy", json=body).json()["styles"]}
    assert styles["anime"]["loraEnabled"] is True
    assert styles["anime"]["loraName"] == "my_anime.safetensors"
    assert styles["anime"]["loraStrength"] == 0.65
    # The other styles are untouched by a single-style patch.
    assert styles["painted"]["loraName"] == "zit_watercolor.safetensors"


def test_a_style_lora_patch_is_a_merge_not_a_replace(client):
    client.patch("/api/options/comfy", json={"styles": {"anime": {"loraName": "my_anime.safetensors"}}})
    client.patch("/api/options/comfy", json={"styles": {"anime": {"loraStrength": 0.4}}})
    styles = {s["id"]: s for s in client.get("/api/options").json()["comfy"]["styles"]}
    assert styles["anime"]["loraName"] == "my_anime.safetensors"
    assert styles["anime"]["loraStrength"] == 0.4


def test_turning_painteds_lora_off_persists(client):
    body = {"styles": {"painted": {"loraEnabled": False}}}
    styles = {s["id"]: s for s in client.patch("/api/options/comfy", json=body).json()["styles"]}
    assert styles["painted"]["loraEnabled"] is False
    # The file is remembered, so switching back on does not mean retyping it.
    assert styles["painted"]["loraName"] == "zit_watercolor.safetensors"


def test_an_unknown_style_id_in_a_lora_patch_is_ignored(client):
    res = client.patch("/api/options/comfy", json={"styles": {"woodcut": {"loraEnabled": True}}})
    assert res.status_code == 200
    assert [s["id"] for s in res.json()["styles"]] == art_styles.ids()


def test_enabling_a_lora_with_no_file_stays_off(client):
    """There is nothing to load, so the render must fall back to the base checkpoint."""
    body = {"styles": {"photoreal": {"loraEnabled": True}}}
    styles = {s["id"]: s for s in client.patch("/api/options/comfy", json=body).json()["styles"]}
    assert styles["photoreal"]["loraEnabled"] is False


# ---- resolution (what the render services ask for) -------------------------


def test_resolve_falls_back_to_the_stored_default(db_session):
    settings_store.update_comfy(
        db_session, ComfyConfigUpdate(art_style="photoreal")
    )
    resolved = settings_store.resolve_art_style(db_session, None)
    assert resolved.style.id == "photoreal"
    assert resolved.lora_enabled is False


def test_an_explicit_style_overrides_the_stored_default(db_session):
    settings_store.update_comfy(db_session, ComfyConfigUpdate(art_style="anime"))
    resolved = settings_store.resolve_art_style(db_session, "painted")
    assert resolved.style.id == "painted"
    assert resolved.lora_enabled is True
    assert resolved.lora_name == "zit_watercolor.safetensors"


def test_resolve_reflects_a_stored_lora_override(db_session):
    settings_store.update_comfy(
        db_session,
        ComfyConfigUpdate(
            styles={
                "painted": ArtStyleOverride(
                    lora_name="zit_oilpainting.safetensors", lora_strength=0.5
                )
            }
        ),
    )
    resolved = settings_store.resolve_art_style(db_session, "painted")
    assert resolved.lora_name == "zit_oilpainting.safetensors"
    assert resolved.lora_strength == 0.5


def test_resolve_coerces_an_unknown_id(db_session):
    assert settings_store.resolve_art_style(db_session, "sepia-woodcut").style.id == "painted"


# ---- the LoRA listing route ------------------------------------------------


def test_list_loras_is_empty_when_comfy_is_unreachable(client, monkeypatch):
    from app.services import comfyui

    monkeypatch.setattr(comfyui, "list_loras", lambda base: [])
    res = client.get("/api/options/comfy/loras")
    assert res.status_code == 200
    assert res.json()["loras"] == []


def test_list_loras_passes_the_resolved_base_url(client, monkeypatch):
    from app.services import comfyui

    seen: dict[str, str] = {}

    def fake(base: str) -> list[str]:
        seen["base"] = base
        return ["zit_watercolor.safetensors"]

    monkeypatch.setattr(comfyui, "list_loras", fake)
    client.patch("/api/options/comfy", json={"baseUrl": "http://comfy.test:8199"})
    res = client.get("/api/options/comfy/loras")
    assert res.json()["loras"] == ["zit_watercolor.safetensors"]
    assert seen["base"] == "http://comfy.test:8199"
