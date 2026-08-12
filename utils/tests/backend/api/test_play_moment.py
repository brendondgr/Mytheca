"""POST /api/play/{scenarioId}/moment/stream — the player's Create image action.

The scene is played through the real turn route (stubbed LLM) so the moment has
genuine beats to depict; the prompt writer and ComfyUI are stubbed, and the media
directory is redirected to a tmp path. Under test: the frame order on the wire,
the pre-stream error envelopes, and the terminal in-band error frame.
"""

from __future__ import annotations

import json
from io import BytesIO

import httpx
from PIL import Image

from app.core.errors import APIError
from app.schemas.play import MomentPromptResponse
from app.services import comfyui, events_store, llm, scene_moment


def _patch_llm(monkeypatch, content: str = '<speaker:1>\n<type:character_dialogue>\n"Hm."'):
    def handler(request: httpx.Request) -> httpx.Response:
        # Path-aware: the engine probes GET /version and /props on some backends.
        if request.method == "GET":
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _configure(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )
    client.patch("/api/options/comfy", json={"baseUrl": "http://comfy.test:8199"})


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (32, 18), "slategray").save(buf, format="PNG")
    return buf.getvalue()


def _stub_generation(monkeypatch, tmp_path, *, caption="Two figures at a lamplit table."):
    monkeypatch.setattr(
        scene_moment.moment_agent,
        "write_moment_prompt",
        lambda db, **kw: MomentPromptResponse(
            positive="two figures at a lamplit table, wide landscape composition",
            negative="text, watermark",
            caption=caption,
        ),
    )
    monkeypatch.setattr(
        comfyui,
        "generate",
        lambda base, workflow, **kw: (_png(), {"filename": "out.png", "subfolder": "", "type": "output"}),
    )
    monkeypatch.setattr(scene_moment, "_moments_dir", lambda: tmp_path)


def _scene(client, storyline_id):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters",
        json={"name": "Mei", "appearance": "Tall, close-cropped hair."},
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "suggestionsCount": 0},
    ).json()["id"]
    return cid, scid


def _play(client, scid, cid) -> str:
    resp = client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid})
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()][0]["sessionId"]


def _frames(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_moment_stream_yields_both_stages_then_the_persisted_event(
    client, storyline_id, monkeypatch, tmp_path
):
    _configure(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)
    _stub_generation(monkeypatch, tmp_path)

    resp = client.post(f"/api/play/{scid}/moment/stream", json={"sessionId": session_id})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")

    frames = _frames(resp)
    assert [f["type"] for f in frames] == ["moment_stage", "moment_stage", "scene_image"]
    assert [f["stage"] for f in frames[:2]] == ["prompt", "render"]
    assert frames[1]["positive"].startswith("two figures")

    event = frames[-1]
    assert event["sessionId"] == session_id and event["scenarioId"] == scid
    assert event["data"]["url"].startswith("/media/moments/")
    assert event["data"]["caption"] == "Two figures at a lamplit table."
    assert (tmp_path / event["data"]["url"].rsplit("/", 1)[1]).is_file()


def test_the_picture_rejoins_the_session_history(client, storyline_id, monkeypatch, tmp_path):
    _configure(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)
    _stub_generation(monkeypatch, tmp_path)

    client.post(f"/api/play/{scid}/moment/stream", json={"sessionId": session_id})

    history = client.get(f"/api/play/{scid}/sessions/{session_id}").json()
    images = [e for e in history["events"] if e["type"] == "scene_image"]
    assert len(images) == 1
    assert images[0]["data"]["url"].startswith("/media/moments/")

    # …and into the Markdown export, as a real image reference.
    export = client.get(f"/api/play/{scid}/sessions/{session_id}/export?format=md").text
    assert "![Two figures at a lamplit table.](/media/moments/" in export


def test_unknown_scenario_and_session_fail_before_the_stream_opens(
    client, storyline_id, monkeypatch, tmp_path
):
    _configure(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)
    _stub_generation(monkeypatch, tmp_path)

    assert client.post("/api/play/sc-nope/moment/stream", json={"sessionId": session_id}).status_code == 404
    assert client.post(f"/api/play/{scid}/moment/stream", json={"sessionId": "ps-nope"}).status_code == 404


def test_unplayed_scene_is_a_pre_stream_400(
    client, db_session, storyline_id, monkeypatch, tmp_path
):
    """A session that exists but has said nothing yet has no moment to paint."""
    _configure(client)
    _patch_llm(monkeypatch)
    _cid, scid = _scene(client, storyline_id)
    _stub_generation(monkeypatch, tmp_path)
    session = events_store.create_session(db_session, scid)

    resp = client.post(f"/api/play/{scid}/moment/stream", json={"sessionId": session.id})
    assert resp.status_code == 400
    assert "beat" in resp.json()["error"]["message"].lower()


def test_unconfigured_comfyui_is_a_pre_stream_400(client, storyline_id, monkeypatch, tmp_path):
    _configure(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)
    _stub_generation(monkeypatch, tmp_path)
    client.patch("/api/options/comfy", json={"baseUrl": ""})

    resp = client.post(f"/api/play/{scid}/moment/stream", json={"sessionId": session_id})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


def test_a_render_failure_is_the_terminal_error_frame(client, storyline_id, monkeypatch, tmp_path):
    _configure(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id)
    session_id = _play(client, scid, cid)
    _stub_generation(monkeypatch, tmp_path)

    def boom(*_a, **_kw):
        raise APIError(502, "upstream_error", "ComfyUI never returned an image.")

    monkeypatch.setattr(comfyui, "generate", boom)

    frames = _frames(client.post(f"/api/play/{scid}/moment/stream", json={"sessionId": session_id}))
    assert frames[-1] == {"type": "error", "message": "ComfyUI never returned an image."}
    # Nothing half-written: no scene_image row was persisted.
    history = client.get(f"/api/play/{scid}/sessions/{session_id}").json()
    assert not [e for e in history["events"] if e["type"] == "scene_image"]
