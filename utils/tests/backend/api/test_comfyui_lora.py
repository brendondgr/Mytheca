"""ComfyUI LoRA control — patching node 72, bypassing it, and listing what is installed.

Offline: the workflow is the real bundled template on disk, and the one HTTP call
(``list_loras``) goes through a ``MockTransport``, matching ``test_comfyui.py``.
"""

from __future__ import annotations

import httpx

from app.services import comfyui


def _patch_http(monkeypatch, handler):
    monkeypatch.setattr(
        comfyui, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _refs_to(workflow: dict, node_id: str) -> list[tuple[str, str]]:
    """Every ``(node, input)`` still wired to ``node_id``'s output."""
    return [
        (nid, key)
        for nid, node in workflow.items()
        for key, value in (node.get("inputs") or {}).items()
        if isinstance(value, list) and len(value) == 2 and str(value[0]) == node_id
    ]


# ---- patching --------------------------------------------------------------


def test_build_prompt_patches_the_lora_name_and_strength():
    wf = comfyui.load_workflow("ZiT-Workflow.json")
    out = comfyui.build_prompt(
        wf, lora_name="zit_oilpainting.safetensors", lora_strength=0.55, lora_enabled=True
    )
    assert out[comfyui.LORA_NODE]["inputs"]["lora_name"] == "zit_oilpainting.safetensors"
    assert out[comfyui.LORA_NODE]["inputs"]["strength_model"] == 0.55
    # Still wired in — the sampler chain runs through it.
    assert _refs_to(out, comfyui.LORA_NODE)


def test_build_prompt_leaves_the_lora_alone_when_nothing_is_said():
    """The authored template is the fallback: no LoRA arguments, no LoRA change."""
    wf = comfyui.load_workflow("ZiT-Workflow.json")
    out = comfyui.build_prompt(wf, positive="a harbor at dawn")
    assert out[comfyui.LORA_NODE]["inputs"] == wf[comfyui.LORA_NODE]["inputs"]
    assert _refs_to(out, comfyui.LORA_NODE) == _refs_to(wf, comfyui.LORA_NODE)


def test_build_prompt_does_not_mutate_the_loaded_workflow():
    wf = comfyui.load_workflow("ZiT-Workflow.json")
    before = dict(wf[comfyui.LORA_NODE]["inputs"])
    comfyui.build_prompt(wf, lora_enabled=False)
    assert wf[comfyui.LORA_NODE]["inputs"] == before


# ---- bypassing -------------------------------------------------------------


def test_disabling_the_lora_routes_every_consumer_to_its_upstream_model():
    wf = comfyui.load_workflow("ZiT-Workflow.json")
    upstream = wf[comfyui.LORA_NODE]["inputs"]["model"]
    consumers = _refs_to(wf, comfyui.LORA_NODE)
    assert consumers, "the bundled workflow should feed the LoRA into the sampler chain"

    out = comfyui.build_prompt(wf, lora_enabled=False)

    assert _refs_to(out, comfyui.LORA_NODE) == [], "nothing may still read the LoRA output"
    for node_id, key in consumers:
        assert out[node_id]["inputs"][key] == upstream


def test_bypassing_leaves_the_node_in_the_graph():
    """Orphaned, so never executed — but the template stays intact rather than rebuilt."""
    out = comfyui.build_prompt(comfyui.load_workflow("ZiT-Workflow.json"), lora_enabled=False)
    assert comfyui.LORA_NODE in out


def test_bypassing_a_workflow_without_a_lora_node_is_a_no_op():
    wf = {"70": {"class_type": "KSampler", "inputs": {"model": ["69", 0], "seed": 1}}}
    out = comfyui.build_prompt(wf, lora_enabled=False, positive="ignored")
    assert out == wf


def test_bypassing_a_lora_with_no_upstream_link_leaves_the_graph_as_authored():
    wf = {
        "72": {"class_type": "LoraLoaderModelOnly", "inputs": {"lora_name": "x.safetensors"}},
        "70": {"class_type": "KSampler", "inputs": {"model": ["72", 0]}},
    }
    out = comfyui.build_prompt(wf, lora_enabled=False)
    assert out["70"]["inputs"]["model"] == ["72", 0]


# ---- listing ---------------------------------------------------------------


def test_list_loras_reads_the_object_info_enum(monkeypatch):
    payload = {
        "LoraLoaderModelOnly": {
            "input": {
                "required": {
                    "lora_name": [["zit_watercolor.safetensors", "zit_oilpainting.safetensors"], {}],
                    "strength_model": ["FLOAT", {"default": 1.0}],
                }
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/object_info/LoraLoaderModelOnly"
        return httpx.Response(200, json=payload)

    _patch_http(monkeypatch, handler)
    assert comfyui.list_loras("http://comfy.test") == [
        "zit_watercolor.safetensors",
        "zit_oilpainting.safetensors",
    ]


def test_list_loras_returns_empty_on_an_unexpected_shape(monkeypatch):
    _patch_http(monkeypatch, lambda request: httpx.Response(200, json={"nope": True}))
    assert comfyui.list_loras("http://comfy.test") == []


def test_list_loras_returns_empty_when_comfy_is_down(monkeypatch):
    """Best-effort: the Options page must still load with no image server running."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    _patch_http(monkeypatch, handler)
    assert comfyui.list_loras("http://comfy.test") == []


def test_list_loras_returns_empty_on_an_error_status(monkeypatch):
    _patch_http(monkeypatch, lambda request: httpx.Response(404, text="nope"))
    assert comfyui.list_loras("http://comfy.test") == []
