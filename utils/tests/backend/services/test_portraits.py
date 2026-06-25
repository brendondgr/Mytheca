"""Portrait service — ComfyUI→WebP conversion + persistence, fully offline.

``services.comfyui.generate`` is monkeypatched to return fake PNG bytes (no GPU,
no network) and the portraits directory is redirected to a tmp path, so these
exercise the conversion + save + URL contract without a live Comfy server.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.core.errors import APIError
from app.services import comfyui, portraits


def _png_bytes(color: str = "tomato", size: tuple[int, int] = (16, 24)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_to_webp_converts_png():
    webp = portraits._to_webp(_png_bytes())
    with Image.open(BytesIO(webp)) as im:
        assert im.format == "WEBP"


def test_to_webp_rejects_non_image():
    with pytest.raises(APIError) as exc:
        portraits._to_webp(b"not an image")
    assert exc.value.status_code == 502


def test_generate_portrait_writes_webp_and_returns_url(db_session, tmp_path, monkeypatch):
    captured: dict = {}

    def fake_generate(base, workflow, **kwargs):
        captured["base"] = base
        captured["workflow"] = workflow
        captured.update(kwargs)
        return _png_bytes(), {"filename": "out.png", "subfolder": "", "type": "output"}

    monkeypatch.setattr(comfyui, "generate", fake_generate)
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    result = portraits.generate_portrait(
        db_session, "young orc warrior, watercolor portrait, soft washes", "blurry, text"
    )

    url = result["portrait"]
    assert url.startswith("/media/portraits/")
    assert url.endswith(".webp")
    # The portrait was actually written and is a real WebP.
    written = tmp_path / url.rsplit("/", 1)[1]
    assert written.is_file()
    with Image.open(written) as im:
        assert im.format == "WEBP"
    # Prompts + a square 1024×1024 frame + a concrete seed reached the pipeline.
    assert captured["positive"].startswith("young orc warrior")
    assert captured["negative"] == "blurry, text"
    assert captured["width"] == captured["height"] == 1024
    assert isinstance(captured["seed"], int)


def test_generate_portrait_uses_a_fresh_seed_each_render(db_session, tmp_path, monkeypatch):
    """Re-rendering picks a new random seed (so ComfyUI re-executes, no cache stall)."""
    seeds: list[int] = []

    def fake_generate(base, workflow, **kwargs):
        seeds.append(kwargs["seed"])
        return _png_bytes(), {"filename": "out.png", "subfolder": "", "type": "output"}

    monkeypatch.setattr(comfyui, "generate", fake_generate)
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    for _ in range(3):
        portraits.generate_portrait(db_session, "a watercolor portrait")

    assert len(set(seeds)) == 3  # three distinct seeds across three renders


def test_generate_portrait_honors_an_explicit_seed(db_session, tmp_path, monkeypatch):
    captured: dict = {}

    def fake_generate(base, workflow, **kwargs):
        captured.update(kwargs)
        return _png_bytes(), {"filename": "out.png", "subfolder": "", "type": "output"}

    monkeypatch.setattr(comfyui, "generate", fake_generate)
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    portraits.generate_portrait(db_session, "a watercolor portrait", seed=42)
    assert captured["seed"] == 42


def test_generate_portrait_requires_a_positive_prompt(db_session):
    with pytest.raises(APIError) as exc:
        portraits.generate_portrait(db_session, "   ")
    assert exc.value.status_code == 400


def test_portrait_route_returns_url(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        comfyui,
        "generate",
        lambda base, workflow, **kw: (_png_bytes(), {"filename": "o.png", "subfolder": "", "type": "output"}),
    )
    monkeypatch.setattr(portraits, "_portraits_dir", lambda: tmp_path)

    res = client.post(
        "/api/characters/portrait",
        json={"positive": "elderly human oracle, watercolor portrait", "negative": "lowres"},
    )
    assert res.status_code == 200
    assert res.json()["portrait"].startswith("/media/portraits/")
