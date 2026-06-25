"""ComfyUI image-generation client — drive a local Comfy server from the backend.

ComfyUI speaks its own protocol (not OpenAI-compatible): an HTTP API for queuing
prompts / reading history / downloading images, plus a WebSocket that streams
execution progress. This module wraps the seven-step pipeline:

1. ``check_connection`` — ``GET /system_stats`` (fail loudly before queuing).
2. ``load_workflow`` — read a saved workflow JSON off disk (kept as a template).
3. ``build_prompt`` — ``deepcopy`` + surgically patch only the nodes we care about.
4. ``queue_prompt`` — ``POST /prompt`` (Comfy returns 200 even on bad workflows,
   so the JSON body is checked for an ``error``).
5. ``wait_for_completion`` — block on the WebSocket until ``executing`` reports
   ``node: null`` for our ``prompt_id`` (binary preview frames are skipped).
6. ``get_output_info`` — ``GET /history/{id}`` → ``filename/subfolder/type`` from
   the ``SaveImage`` node.
7. ``download_image`` — ``GET /view`` → raw image ``bytes``.

``generate`` chains them. HTTP and WebSocket clients are built by injectable
factories (``get_http_client`` / ``open_ws``) so tests run fully offline, mirroring
``services/llm.py``.

**Node map for the bundled ``ZiT-Workflow.json``:**

| Node | Class | Patched field(s) |
| --- | --- | --- |
| ``67`` | CLIPTextEncode | positive prompt (``inputs.text``) |
| ``71`` | CLIPTextEncode | negative prompt (``inputs.text``) |
| ``70`` | KSampler | ``seed``, ``steps``, ``cfg`` |
| ``68`` | EmptySD3LatentImage | ``width``, ``height``, ``batch_size`` |
| ``77`` | SaveImage | output read from here |

Any field not passed keeps whatever was authored in the workflow JSON.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import APIError

_TIMEOUT = httpx.Timeout(60.0, connect=5.0)
_WS_TIMEOUT = 5.0  # per-recv socket timeout (seconds)
_DEFAULT_DEADLINE = 300.0  # overall wait_for_completion budget (seconds)

# Node ids in the bundled workflow (see the module docstring's node map).
POSITIVE_NODE = "67"
NEGATIVE_NODE = "71"
SAMPLER_NODE = "70"
LATENT_NODE = "68"
SAVE_NODE = "77"


# ---- injectable transports (patched in tests) ------------------------------


def get_http_client() -> httpx.Client:
    """Return an HTTP client. Patched in tests to use a MockTransport."""
    return httpx.Client(timeout=_TIMEOUT)


class WSConnection(Protocol):
    """The slice of ``websocket-client``'s connection that we use."""

    def recv(self) -> str | bytes: ...
    def close(self) -> None: ...


def open_ws(url: str) -> WSConnection:
    """Open a blocking WebSocket connection. Patched in tests with a fake."""
    import websocket  # imported lazily so the module loads without the dep present

    return websocket.create_connection(url, timeout=_WS_TIMEOUT)


# ---- helpers ---------------------------------------------------------------


def _normalize(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise APIError(400, "bad_request", "A ComfyUI base URL is required (e.g. http://localhost:8199).")
    return base


def _ws_url(http_base: str, client_id: str) -> str:
    ws_base = http_base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/ws?clientId={client_id}"


def _send(method: str, url: str, *, json_body: dict | None = None) -> httpx.Response:
    client = get_http_client()
    try:
        with client:
            return client.request(method, url, json=json_body)
    except httpx.HTTPError as exc:  # network/timeout/DNS — never expose internals
        raise APIError(
            502, "bad_gateway", f"Could not reach ComfyUI: {exc.__class__.__name__}."
        ) from exc


def _ensure_ok(res: httpx.Response) -> None:
    if res.is_success:
        return
    raise APIError(
        502,
        "upstream_error",
        f"ComfyUI returned {res.status_code}.",
        {"status": res.status_code, "body": res.text[:300]},
    )


# ---- step 1: connection ----------------------------------------------------


def check_connection(base_url: str) -> dict[str, Any]:
    """``GET /system_stats`` — confirm the server is up and return its stats."""
    res = _send("GET", f"{_normalize(base_url)}/system_stats")
    _ensure_ok(res)
    try:
        return res.json()
    except ValueError as exc:
        raise APIError(502, "upstream_error", "ComfyUI returned invalid JSON.") from exc


# ---- step 2: workflows on disk ---------------------------------------------


def _workflows_dir() -> Path:
    return get_settings().comfyui_workflows_dir


def list_workflows() -> list[str]:
    """Names of the saved workflow JSON files in ``utils/workflows/``."""
    directory = _workflows_dir()
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.glob("*.json"))


def load_workflow(name: str) -> dict[str, Any]:
    """Read a saved workflow JSON by file name (kept untouched as a template)."""
    safe = Path(name).name  # strip any path component
    path = _workflows_dir() / safe
    if not path.is_file():
        raise APIError(404, "not_found", f"Workflow '{safe}' was not found in utils/workflows/.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise APIError(400, "bad_request", f"Workflow '{safe}' could not be parsed.") from exc


# ---- step 3: patch the prompt ----------------------------------------------


def build_prompt(
    workflow: dict[str, Any],
    *,
    positive: str | None = None,
    negative: str | None = None,
    seed: int | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    width: int | None = None,
    height: int | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Deep-copy the workflow and patch only the provided fields (see node map)."""
    import copy

    wf = copy.deepcopy(workflow)

    def _set(node: str, key: str, value: Any) -> None:
        if value is None:
            return
        if node in wf and isinstance(wf[node].get("inputs"), dict):
            wf[node]["inputs"][key] = value

    _set(POSITIVE_NODE, "text", positive)
    _set(NEGATIVE_NODE, "text", negative)
    _set(SAMPLER_NODE, "seed", seed)
    _set(SAMPLER_NODE, "steps", steps)
    _set(SAMPLER_NODE, "cfg", cfg)
    _set(LATENT_NODE, "width", width)
    _set(LATENT_NODE, "height", height)
    _set(LATENT_NODE, "batch_size", batch_size)
    return wf


# ---- step 4: queue ---------------------------------------------------------


def queue_prompt(base_url: str, workflow: dict[str, Any], client_id: str) -> str:
    """``POST /prompt`` and return the ``prompt_id`` (Comfy 200s even on errors)."""
    res = _send(
        "POST",
        f"{_normalize(base_url)}/prompt",
        json_body={"prompt": workflow, "client_id": client_id},
    )
    _ensure_ok(res)
    try:
        payload = res.json()
    except ValueError as exc:
        raise APIError(502, "upstream_error", "ComfyUI returned invalid JSON.") from exc
    if isinstance(payload, dict) and payload.get("error"):
        err = payload["error"]
        message = err.get("message") if isinstance(err, dict) else str(err)
        raise APIError(400, "bad_request", f"ComfyUI rejected the workflow: {message}", {"error": err})
    prompt_id = payload.get("prompt_id") if isinstance(payload, dict) else None
    if not prompt_id:
        raise APIError(502, "upstream_error", "ComfyUI did not return a prompt_id.")
    return str(prompt_id)


# ---- step 5: wait ----------------------------------------------------------


def wait_for_completion(
    base_url: str, prompt_id: str, client_id: str, *, deadline: float = _DEFAULT_DEADLINE
) -> None:
    """Block on the WebSocket until execution finishes for ``prompt_id``.

    Done = an ``executing`` message with ``node == null`` for our ``prompt_id``.
    Binary preview frames are skipped; an ``execution_error`` raises.
    """
    url = _ws_url(_normalize(base_url), client_id)
    try:
        ws = open_ws(url)
    except Exception as exc:  # connection refused / handshake failure
        raise APIError(502, "bad_gateway", f"Could not open the ComfyUI WebSocket: {exc.__class__.__name__}.") from exc

    started = time.monotonic()
    try:
        while True:
            if time.monotonic() - started > deadline:
                raise APIError(504, "timeout", "Timed out waiting for ComfyUI to finish.")
            try:
                message = ws.recv()
            except Exception:  # recv timeout — loop and re-check the deadline
                continue
            if isinstance(message, (bytes, bytearray)):
                continue  # live preview frame — ignore
            try:
                payload = json.loads(message)
            except ValueError:
                continue
            mtype = payload.get("type")
            data = payload.get("data") or {}
            if mtype == "execution_error" and data.get("prompt_id") == prompt_id:
                raise APIError(
                    502, "upstream_error", "ComfyUI reported an execution error.", {"error": data}
                )
            if mtype == "executing" and data.get("node") is None and data.get("prompt_id") == prompt_id:
                return
    finally:
        try:
            ws.close()
        except Exception:
            pass


# ---- step 6: output info ---------------------------------------------------


def get_output_info(base_url: str, prompt_id: str, *, save_node: str = SAVE_NODE) -> list[dict[str, str]]:
    """``GET /history/{id}`` → the saved images' ``filename/subfolder/type``."""
    res = _send("GET", f"{_normalize(base_url)}/history/{prompt_id}")
    _ensure_ok(res)
    try:
        history = res.json()
    except ValueError as exc:
        raise APIError(502, "upstream_error", "ComfyUI returned invalid JSON.") from exc
    entry = history.get(prompt_id) if isinstance(history, dict) else None
    if not entry:
        raise APIError(502, "upstream_error", "ComfyUI history has no record for this prompt.")
    status = entry.get("status") or {}
    if status.get("status_str") == "error":
        raise APIError(502, "upstream_error", "ComfyUI reported the job failed.", {"status": status})
    outputs = entry.get("outputs") or {}
    node_output = outputs.get(save_node) or next(
        (v for v in outputs.values() if isinstance(v, dict) and v.get("images")), {}
    )
    images = node_output.get("images") or []
    result = [
        {
            "filename": img.get("filename", ""),
            "subfolder": img.get("subfolder", ""),
            "type": img.get("type", "output"),
        }
        for img in images
        if isinstance(img, dict) and img.get("filename")
    ]
    if not result:
        raise APIError(502, "upstream_error", "ComfyUI produced no image output.")
    return result


# ---- step 7: download ------------------------------------------------------


def download_image(base_url: str, filename: str, subfolder: str = "", type: str = "output") -> bytes:
    """``GET /view`` — return the raw image bytes."""
    query = httpx.QueryParams({"filename": filename, "subfolder": subfolder, "type": type})
    res = _send("GET", f"{_normalize(base_url)}/view?{query}")
    _ensure_ok(res)
    return res.content


# ---- orchestrator ----------------------------------------------------------


def generate(
    base_url: str,
    workflow_name: str,
    *,
    positive: str | None = None,
    negative: str | None = None,
    seed: int | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    width: int | None = None,
    height: int | None = None,
    batch_size: int | None = None,
) -> tuple[bytes, dict[str, str]]:
    """Run the full pipeline and return ``(image_bytes, output_info)`` of the first image."""
    base = _normalize(base_url)
    client_id = str(uuid.uuid4())
    check_connection(base)
    workflow = load_workflow(workflow_name)
    patched = build_prompt(
        workflow,
        positive=positive,
        negative=negative,
        seed=seed,
        steps=steps,
        cfg=cfg,
        width=width,
        height=height,
        batch_size=batch_size,
    )
    prompt_id = queue_prompt(base, patched, client_id)
    wait_for_completion(base, prompt_id, client_id)
    info = get_output_info(base, prompt_id)[0]
    image = download_image(base, info["filename"], info["subfolder"], info["type"])
    return image, info
