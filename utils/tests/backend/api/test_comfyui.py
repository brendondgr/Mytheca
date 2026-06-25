"""ComfyUI client service — offline tests.

No real network or GPU: ``app.services.comfyui.get_http_client`` is patched to a
``MockTransport``-backed client and ``open_ws`` to a scripted fake WebSocket, so
the full pipeline (queue → wait → history → download) is exercised deterministically.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.errors import APIError
from app.services import comfyui


def _patch_http(monkeypatch, handler):
    monkeypatch.setattr(
        comfyui, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


class _FakeWS:
    """A WebSocket that yields a scripted list of messages, then blocks (raises)."""

    def __init__(self, messages):
        self._messages = list(messages)
        self.closed = False

    def recv(self):
        if self._messages:
            return self._messages.pop(0)
        raise TimeoutError("no more messages")

    def close(self):
        self.closed = True


# ---- step 2/3: workflows + prompt building (real files on disk) ------------


def test_list_workflows_includes_bundled():
    assert "ZiT-Workflow.json" in comfyui.list_workflows()


def test_load_workflow_missing_is_404():
    with pytest.raises(APIError) as exc:
        comfyui.load_workflow("does-not-exist.json")
    assert exc.value.status_code == 404


def test_build_prompt_patches_only_given_fields():
    wf = comfyui.load_workflow("ZiT-Workflow.json")
    original_neg = wf[comfyui.NEGATIVE_NODE]["inputs"]["text"]
    out = comfyui.build_prompt(wf, positive="a cat", seed=7, steps=8, width=512)

    assert out[comfyui.POSITIVE_NODE]["inputs"]["text"] == "a cat"
    assert out[comfyui.SAMPLER_NODE]["inputs"]["seed"] == 7
    assert out[comfyui.SAMPLER_NODE]["inputs"]["steps"] == 8
    assert out[comfyui.LATENT_NODE]["inputs"]["width"] == 512
    # Untouched fields keep their authored values; the template is not mutated.
    assert out[comfyui.NEGATIVE_NODE]["inputs"]["text"] == original_neg
    assert wf[comfyui.POSITIVE_NODE]["inputs"]["text"] != "a cat"


# ---- step 1: connection ----------------------------------------------------


def test_check_connection_returns_stats(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "http://localhost:8199/system_stats"
        return httpx.Response(200, json={"system": {"comfyui_version": "0.25.0"}})

    _patch_http(monkeypatch, handler)
    stats = comfyui.check_connection("http://localhost:8199/")
    assert stats["system"]["comfyui_version"] == "0.25.0"


def test_check_connection_transport_error_maps_to_bad_gateway(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _patch_http(monkeypatch, handler)
    with pytest.raises(APIError) as exc:
        comfyui.check_connection("http://localhost:8199")
    assert exc.value.status_code == 502
    assert exc.value.code == "bad_gateway"


def test_missing_base_url_is_bad_request():
    with pytest.raises(APIError) as exc:
        comfyui.check_connection("")
    assert exc.value.status_code == 400


# ---- step 4: queue ---------------------------------------------------------


def test_queue_prompt_returns_id(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        body = json.loads(request.content)
        assert body["client_id"] == "cid"
        assert "prompt" in body
        return httpx.Response(200, json={"prompt_id": "abc-123"})

    _patch_http(monkeypatch, handler)
    assert comfyui.queue_prompt("http://localhost:8199", {"1": {}}, "cid") == "abc-123"


def test_queue_prompt_error_body_is_bad_request(monkeypatch):
    # ComfyUI returns HTTP 200 with an error body for a bad workflow.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"message": "node 99 missing"}})

    _patch_http(monkeypatch, handler)
    with pytest.raises(APIError) as exc:
        comfyui.queue_prompt("http://localhost:8199", {}, "cid")
    assert exc.value.status_code == 400


# ---- step 5: wait ----------------------------------------------------------


def test_wait_for_completion_returns_on_node_null(monkeypatch):
    messages = [
        b"\x00\x00binarypreview",  # a live preview frame — skipped
        json.dumps({"type": "executing", "data": {"node": "70", "prompt_id": "p1"}}),
        json.dumps({"type": "executing", "data": {"node": None, "prompt_id": "p1"}}),
    ]
    ws = _FakeWS(messages)
    monkeypatch.setattr(comfyui, "open_ws", lambda url: ws)
    comfyui.wait_for_completion("http://localhost:8199", "p1", "cid")
    assert ws.closed is True


def test_wait_for_completion_execution_error_raises(monkeypatch):
    messages = [json.dumps({"type": "execution_error", "data": {"prompt_id": "p1"}})]
    monkeypatch.setattr(comfyui, "open_ws", lambda url: _FakeWS(messages))
    with pytest.raises(APIError) as exc:
        comfyui.wait_for_completion("http://localhost:8199", "p1", "cid")
    assert exc.value.code == "upstream_error"


# ---- step 6: output info ---------------------------------------------------


def test_get_output_info_parses_save_node(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/history/p1")
        return httpx.Response(
            200,
            json={
                "p1": {
                    "status": {"status_str": "success"},
                    "outputs": {
                        comfyui.SAVE_NODE: {
                            "images": [
                                {"filename": "ComfyUI_001.png", "subfolder": "", "type": "output"}
                            ]
                        }
                    },
                }
            },
        )

    _patch_http(monkeypatch, handler)
    info = comfyui.get_output_info("http://localhost:8199", "p1")
    assert info[0]["filename"] == "ComfyUI_001.png"


def test_get_output_info_no_images_is_upstream_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"p1": {"status": {}, "outputs": {}}})

    _patch_http(monkeypatch, handler)
    with pytest.raises(APIError):
        comfyui.get_output_info("http://localhost:8199", "p1")


# ---- step 7 + orchestrator -------------------------------------------------


def test_generate_runs_the_full_pipeline(monkeypatch):
    png = b"\x89PNG\r\n\x1a\nfakebytes"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/system_stats":
            return httpx.Response(200, json={"system": {}})
        if path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "p1"})
        if path == "/history/p1":
            return httpx.Response(
                200,
                json={
                    "p1": {
                        "status": {"status_str": "success"},
                        "outputs": {
                            comfyui.SAVE_NODE: {
                                "images": [{"filename": "out.png", "subfolder": "", "type": "output"}]
                            }
                        },
                    }
                },
            )
        if path == "/view":
            return httpx.Response(200, content=png)
        return httpx.Response(404)

    _patch_http(monkeypatch, handler)
    done = json.dumps({"type": "executing", "data": {"node": None, "prompt_id": "p1"}})
    monkeypatch.setattr(comfyui, "open_ws", lambda url: _FakeWS([done]))

    image, info = comfyui.generate("http://localhost:8199", "ZiT-Workflow.json", positive="a cat")
    assert image == png
    assert info["filename"] == "out.png"


# ---- routes (Options surface) ----------------------------------------------


def test_route_list_workflows(client):
    res = client.get("/api/options/comfy/workflows")
    assert res.status_code == 200
    assert "ZiT-Workflow.json" in res.json()["workflows"]


def test_route_patch_comfy_persists(client):
    res = client.patch(
        "/api/options/comfy",
        json={
            "baseUrl": "http://localhost:8199/",
            "workflow": "ZiT-Workflow.json",
            "params": {"steps": 6, "width": 768, "negativePrompt": "blurry"},
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["baseUrl"] == "http://localhost:8199"  # trailing slash trimmed
    assert data["params"]["steps"] == 6
    # Persists across a fresh GET on the aggregate document.
    assert client.get("/api/options").json()["comfy"]["params"]["width"] == 768


def test_route_status_ok(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system_stats"
        return httpx.Response(
            200,
            json={
                "system": {"comfyui_version": "0.25.0", "python_version": "3.13.11"},
                "devices": [{"name": "AMD Radeon"}],
            },
        )

    _patch_http(monkeypatch, handler)
    res = client.post("/api/options/comfy/status", json={"baseUrl": "http://localhost:8199"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["comfyuiVersion"] == "0.25.0"
    assert data["device"] == "AMD Radeon"


def test_route_status_unreachable_maps_to_envelope(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _patch_http(monkeypatch, handler)
    res = client.post("/api/options/comfy/status", json={"baseUrl": "http://localhost:8199"})
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "bad_gateway"
