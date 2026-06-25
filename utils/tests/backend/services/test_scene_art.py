"""Scene-art service — ComfyUI→WebP conversion + persistence, fully offline.

``services.comfyui.generate`` is monkeypatched to return fake PNG bytes (no GPU,
no network) and the scenes directory is redirected to a tmp path, mirroring
``test_portraits.py``.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.core.errors import APIError
from app.services import comfyui, scene_art


def _png_bytes(color: str = "slategray", size: tuple[int, int] = (32, 18)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_generate_scene_art_writes_webp_and_returns_url(db_session, tmp_path, monkeypatch):
    captured: dict = {}

    def fake_generate(base, workflow, **kwargs):
        captured["base"] = base
        captured["workflow"] = workflow
        captured.update(kwargs)
        return _png_bytes(), {"filename": "out.png", "subfolder": "", "type": "output"}

    monkeypatch.setattr(comfyui, "generate", fake_generate)
    monkeypatch.setattr(scene_art, "_scenes_dir", lambda: tmp_path)

    result = scene_art.generate_scene_art(
        db_session, "fog-bound harbor at dawn, watercolor, no people", "people, text"
    )

    url = result["image"]
    assert url.startswith("/media/scenes/")
    assert url.endswith(".webp")
    written = tmp_path / url.rsplit("/", 1)[1]
    assert written.is_file()
    with Image.open(written) as im:
        assert im.format == "WEBP"
    # Prompts + a landscape 16:9 frame + a concrete seed reached the pipeline.
    assert captured["positive"].startswith("fog-bound harbor")
    assert captured["negative"] == "people, text"
    assert captured["width"] == 1024 and captured["height"] == 576
    assert isinstance(captured["seed"], int)


def test_generate_scene_art_uses_a_fresh_seed_each_render(db_session, tmp_path, monkeypatch):
    seeds: list[int] = []

    def fake_generate(base, workflow, **kwargs):
        seeds.append(kwargs["seed"])
        return _png_bytes(), {"filename": "out.png", "subfolder": "", "type": "output"}

    monkeypatch.setattr(comfyui, "generate", fake_generate)
    monkeypatch.setattr(scene_art, "_scenes_dir", lambda: tmp_path)

    for _ in range(3):
        scene_art.generate_scene_art(db_session, "a watercolor vista")

    assert len(set(seeds)) == 3


def test_generate_scene_art_requires_a_positive_prompt(db_session):
    with pytest.raises(APIError) as exc:
        scene_art.generate_scene_art(db_session, "   ")
    assert exc.value.status_code == 400


def test_scene_art_route_returns_url(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        comfyui,
        "generate",
        lambda base, workflow, **kw: (_png_bytes(), {"filename": "o.png", "subfolder": "", "type": "output"}),
    )
    monkeypatch.setattr(scene_art, "_scenes_dir", lambda: tmp_path)

    res = client.post(
        "/api/settings/scene-art",
        json={"positive": "flooded stone undercroft, watercolor", "negative": "people"},
    )
    assert res.status_code == 200
    assert res.json()["image"].startswith("/media/scenes/")
