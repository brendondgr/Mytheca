# ComfyUI Image Generation

Velora generates images by driving a local **ComfyUI** server. ComfyUI is *not*
OpenAI-compatible — it has its own HTTP API for queuing prompts and reading
results, plus a **WebSocket** that streams execution progress. The server-side
client lives in [`web/backend/app/services/comfyui.py`](../web/backend/app/services/comfyui.py)
and the configuration UI is the **Image Generation** tab of the Options menu
(`/options`).

## Setup

1. Run a ComfyUI server (default expected at `http://localhost:8199`).
2. Put your workflow JSON in `utils/workflows/` (the bundled one is
   `ZiT-Workflow.json`). Export it from ComfyUI via **Save (API Format)** so the
   JSON is the node-graph dict the `/prompt` endpoint expects.
3. Set `COMFYUI_BASE_URL` in `.env` if your server isn't on `localhost:8199`.

The Python dependencies are `websocket-client` (the WebSocket progress stream)
and `pillow` (PNG→WebP conversion for portraits) — both in `pyproject.toml`; HTTP
uses the existing `httpx`.

## Character portraits (WebP)

The agentic Character Creator renders character avatars through this same
pipeline. [`web/backend/app/services/portraits.py`](../web/backend/app/services/portraits.py)
resolves the configured Comfy server + workflow + default params, calls
`comfyui.generate(...)` with the agent-written positive/negative prompts at a
portrait-orientation frame, converts the PNG result to **WebP** with Pillow, and
writes it under `MEDIA_DIR` (default `<repo>/media/portraits/`, gitignored). The
file is served read-only at `/media/portraits/<uuid>.webp` (a `StaticFiles` mount
on the app root, *not* under `/api`), and that relative URL is stored on the
character's `portrait` column. The ComfyUI client and bundled workflow are left
untouched — conversion happens at the edge. Endpoint: `POST /api/characters/portrait`.

## The pipeline (7 steps)

`services/comfyui.py` implements the full flow; `generate(...)` chains it:

1. **`check_connection(base_url)`** — `GET /system_stats`. Fails loudly with a
   readable error before anything is queued.
2. **`load_workflow(name)`** — reads a saved workflow JSON off disk (kept
   untouched as a template; deep-copied before patching).
3. **`build_prompt(workflow, …)`** — `copy.deepcopy` then surgically patches only
   the nodes you pass. Any field omitted keeps the value authored in the JSON.
4. **`queue_prompt(base_url, workflow, client_id)`** — `POST /prompt` with the
   patched workflow + a UUID `client_id`. ComfyUI returns HTTP 200 even for a bad
   workflow, so the JSON body is checked for an `error` and surfaced as a `400`.
5. **`wait_for_completion(base_url, prompt_id, client_id)`** — opens the
   WebSocket at `ws://…/ws?clientId=<uuid>` and blocks until an `executing`
   message reports `node: null` for the `prompt_id`. Binary preview frames are
   skipped; an `execution_error` raises. A deadline guards against hangs.
6. **`get_output_info(base_url, prompt_id)`** — `GET /history/{id}`; pulls
   `filename/subfolder/type` from the `SaveImage` node (and checks job status).
7. **`download_image(base_url, filename, …)`** — `GET /view…` returns the raw
   image `bytes` (write to disk or pipe straight into the app).

All errors map to the contract envelope (`{ error: { code, message, details } }`).
The HTTP client (`get_http_client`) and WebSocket (`open_ws`) are built by
injectable factories so the whole pipeline is tested offline
([`utils/tests/backend/api/test_comfyui.py`](../utils/tests/backend/api/test_comfyui.py)).

### Node map (bundled `ZiT-Workflow.json`)

| Node | Class | Patched by `build_prompt` |
| --- | --- | --- |
| `67` | CLIPTextEncode | `positive` → `inputs.text` |
| `71` | CLIPTextEncode | `negative` → `inputs.text` |
| `70` | KSampler | `seed`, `steps`, `cfg` |
| `68` | EmptySD3LatentImage | `width`, `height`, `batch_size` |
| `77` | SaveImage | output is read from here |

If you use a different workflow, update the node-id constants at the top of
`services/comfyui.py` (`POSITIVE_NODE`, `NEGATIVE_NODE`, `SAMPLER_NODE`,
`LATENT_NODE`, `SAVE_NODE`) to match its graph.

## Using it from code

```python
from app.services import comfyui

image_bytes, info = comfyui.generate(
    "http://localhost:8199",
    "ZiT-Workflow.json",
    positive="a serene mountain lake at dawn, watercolor",
    seed=12345,
)
```

## Options menu (Image Generation tab)

The tab configures and verifies the connection; it does **not** spend GPU time:

- **ComfyUI base URL** + a **Check status** button → `POST /options/comfy/status`
  (`GET /system_stats`), showing the Comfy version and device.
- **Workflow** dropdown → `GET /options/comfy/workflows` lists the `*.json` in
  `utils/workflows/`.
- **Default generation parameters** (steps, cfg, width, height, batch size,
  negative prompt) + **Save** → `PATCH /options/comfy`.

Config persists in the global `app_settings` row (`comfy` namespace), alongside
the LLM and library namespaces. Endpoints are documented in
[`docs/api-contract.md`](api-contract.md) (Options group).
