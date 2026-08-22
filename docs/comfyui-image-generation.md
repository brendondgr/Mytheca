# ComfyUI Image Generation

Mytheca generates images by driving a local **ComfyUI** server. ComfyUI is *not*
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
portrait-orientation frame in the requested **art style** (see below), converts the PNG
result to **WebP** with Pillow, and
writes it under `MEDIA_DIR` (default `<repo>/media/portraits/`, gitignored). The
file is served read-only at `/media/portraits/<uuid>.webp` (a `StaticFiles` mount
on the app root, *not* under `/api`), and that relative URL is stored on the
character's `portrait` column. The ComfyUI client and bundled workflow are left
untouched — conversion happens at the edge. Endpoint: `POST /api/characters/portrait`.

## Scene art (WebP)

[`web/backend/app/services/scene_art.py`](../web/backend/app/services/scene_art.py)
is the setting/scenario counterpart to `portraits.py`: it drives the same
`comfyui.generate(...)` pipeline, but renders a **landscape 1024×576 (16:9)**
establishing shot (vs. the portrait's 832×1216) with a **fresh random seed on
every call** (so re-rendering always re-executes rather than serving a cached
result). The PNG is converted to WebP and written under `MEDIA_DIR`
(`<repo>/media/scenes/`, gitignored), served at `/media/scenes/<uuid>.webp`. It
backs **four** endpoints — prompt-drafting + generation for both settings and
scenarios:

- `POST /settings/scene-art-prompts` / `POST /settings/scene-art`
- `POST /scenarios/scene-art-prompts` / `POST /scenarios/scene-art`

## In-play scene images (WebP)

[`web/backend/app/services/scene_moment.py`](../web/backend/app/services/scene_moment.py)
is the **player-facing** counterpart to the two authoring pipelines above: the story
player's **Create image** control paints the moment the scene is in. It is two-stage —
[`agents/moment_agent.py`](../web/backend/app/agents/moment_agent.py) writes the prompt
from the recent beats, the in-frame cast and the place, then `comfyui.generate(...)`
renders it at a **landscape 1216x832** frame (pinned in the service, *not* taken from the
Options defaults, which are tuned for portraits) with a fresh random seed. The WebP lands
in `MEDIA_DIR/moments/` and is served at `/media/moments/<uuid>.webp`.

Two things make this pipeline different from the authoring ones:

- **No names in the prompt.** An image model cannot resolve "Maerin Voss" into a face, so
  the system prompt demands every figure be described by appearance and by what they are
  doing, and `moment_agent.strip_names` deterministically rewrites any name that survives
  into that character's own **visual tag** — the opening phrases of the `portrait_positive`
  that produced their avatar, so a moment and a portrait depict the same person.
- **The result is a story event.** The rendered image is persisted as a `scene_image`
  event on the play session (not a column), so it keeps its place in the transcript, the
  session history, and the export. Endpoint: `POST /api/play/{scenarioId}/moment/stream`
  (NDJSON: two `moment_stage` frames, then the event).

## Orphaned-media cleanup

Generated portrait/scene-art/moment WebPs are written to disk immediately, but
cancelled drafts and deleted entities can leave files behind with no DB row
referencing them.
[`web/backend/app/services/media_cleanup.py`](../web/backend/app/services/media_cleanup.py)
(`scan_orphans` / `delete_orphans`) cross-references the on-disk `*.webp` files
under `portraits_dir`/`scenes_dir`/`moments_dir` against every `Character.portrait`,
`Setting.image`, and `Scenario.image` value in the DB **plus the `url` of every persisted
`scene_image` event** (an in-play moment is referenced by an event row, not a column), and
deletes only the
unreferenced files older than a grace period (`min_age_hours`, default **24**)
so in-flight drafts (generated but not yet saved) are never touched. Backed by
`GET /options/media/orphans` (dry-run scan) and `POST /options/media/cleanup`
(delete), surfaced in the Options → **About** tab's **Maintenance** section
(scan → review counts/bytes → confirm delete).

## Art styles

Every generated image wears one of three **art styles**, authored in
[`web/backend/app/content/art_styles.py`](../web/backend/app/content/art_styles.py):

| id | look | LoRA out of the box |
| --- | --- | --- |
| `painted` | watercolor/oil washes — the house look, and the **default** | `zit_watercolor.safetensors` @ 0.8 |
| `anime` | cel-shaded anime illustration | none (node `72` bypassed) |
| `photoreal` | photograph | none |

A style carries three things: the phrase describing the model in a prompt-writing agent's
system prompt (`model_hint`), a tag string per surface (`portrait_tags` / `scene_tags` /
`moment_tags`), and the style-dependent slice of the negative prompt. `painted`'s tags are
the strings the four agents carried as literals before styles existed, moved verbatim — so a
default render is unchanged by the catalog.

It reaches an image through **both** halves of the pipeline:

- The prompt-writing agent (`character_agent` · `setting_agent` · `scenario_agent` ·
  `moment_agent`) interpolates the hint and tags into its system prompt, so the model writes
  *toward* the look. `agents/_style.py` resolves `None` to the operator's stored default —
  not the catalog default — so an agent called without a style still follows Options.
- The render service (`portraits` · `scene_art` · `scene_moment`) runs the finished prompts
  through `art_styles.apply_style`, which **drops** any phrase belonging to another style and
  then **appends** whichever of this style's tags are missing. The drop is what makes a
  switch actually switch: a prompt stored while painted still ends in `watercolor portrait,
  soft washes`, and — worse — `painted` and `anime` both push `photorealistic` away, which
  would flatly contradict a `photoreal` render. Phrases every style shares (`3d render`,
  `wide view`) survive untouched. This is also the only place the look can land on a
  **hand-written** prompt, which no agent ever sees.

### Choosing one

- **Globally** — `PATCH /options/comfy {"artStyle": "anime"}`, set in Options → Image
  Generation. This is what an omitted style resolves to.
- **Per render** — an `artStyle` field on `POST /characters/portrait-prompts`,
  `/characters/portrait`, `/settings/scene-art-prompts`, `/settings/scene-art`,
  `/scenarios/scene-art-prompts`, `/scenarios/scene-art`, and
  `/play/{scenarioId}/moment/stream`. The frontend offers it as
  `components/feature/ArtStylePicker.tsx` on all four image surfaces.
- **Per world build** — `artStyle` on `POST /storylines/{id}/populate/stream`, chosen in
  `BuildWorldModal` on the **New Storyline** page. Chosen **once for the whole run** rather
  than per entity: a build paints a whole cast and every place in one go, so a world half
  painted and half photoreal is the failure mode worth designing against. Reaches both
  `_render_portrait` and `_render_scene_art` inside `services/world_populate.py`.

An unknown or retired style id **falls back to the default rather than raising** — an image
request must never fail because a stale client named a style that no longer exists.

### LoRAs are operator-owned

Each style's LoRA file, strength and on/off flag live in the `comfy` settings row
(`styleLoras`, keyed by style id) and are edited in Options.
`settings_store.resolve_art_style` folds those over the catalog defaults and is the single
answer to "what look, and with which LoRA?".

`anime` and `photoreal` ship LoRA-less because no anime LoRA is installed and the base
checkpoint (`zit_intorealism_zitV60`) is already realism-leaning — **not** because the code
cannot give them one. Dropping an anime LoRA into ComfyUI's `models/loras/` and pointing
`anime` at it in Options is the whole change. A style with a LoRA enabled but no file
selected stays bypassed: there is nothing to load.

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
| `72` | LoraLoaderModelOnly | `lora_name`, `strength_model` — **or bypassed entirely** |
| `77` | SaveImage | output is read from here |

If you use a different workflow, update the node-id constants at the top of
`services/comfyui.py` (`POSITIVE_NODE`, `NEGATIVE_NODE`, `SAMPLER_NODE`,
`LATENT_NODE`, `LORA_NODE`, `SAVE_NODE`) to match its graph.

The LoRA node is the only one that can be taken *out* of the graph rather than merely
retuned. `build_prompt(..., lora_enabled=False)` calls `_bypass_node`, which repoints every
input reading `["72", 0]` at whatever node `72` itself consumes on its `model` input. It
reads the wiring rather than hard-coding the checkpoint node, so a workflow whose loader
sits somewhere else still bypasses correctly; the node is left in the graph, orphaned and
therefore never executed, so the template on disk stays read-only. A workflow with no LoRA
node is a no-op, not an error.

## Using it from code

```python
from app.services import comfyui

image_bytes, info = comfyui.generate(
    "http://localhost:8199",
    "ZiT-Workflow.json",
    positive="a serene mountain lake at dawn, watercolor",
    seed=12345,
    lora_name="zit_watercolor.safetensors",
    lora_strength=0.8,
    lora_enabled=True,   # False bypasses the LoRA node; omit to keep the workflow as authored
)
```

`GET /options/comfy/loras` proxies ComfyUI's `/object_info/LoraLoaderModelOnly` to list the
LoRA files the server offers. Best-effort: an unreachable or unrecognised server yields
`[]` rather than an error, so the Options field degrades to free text.

## Options menu (Image Generation tab)

The tab configures and verifies the connection; it does **not** spend GPU time:

- **ComfyUI base URL** + a **Check status** button → `POST /options/comfy/status`
  (`GET /system_stats`), showing the Comfy version and device.
- **Workflow** dropdown → `GET /options/comfy/workflows` lists the `*.json` in
  `utils/workflows/`.
- **Default generation parameters** (steps, cfg, width, height, batch size,
  negative prompt) + **Save** → `PATCH /options/comfy`.
- **Art style** — the default look for every generated image (see below).
- **Style LoRAs** — per style: an on/off checkbox, the LoRA file (a dropdown once
  **List LoRAs** has run, free text otherwise), and its strength.

Config persists in the global `app_settings` row (`comfy` namespace), alongside
the LLM and library namespaces. Endpoints are documented in
[`docs/api-contract.md`](api-contract.md) (Options group).

## The player can write the image prompt

The in-play scene image (`services/scene_moment.py`) normally has its prompt written by
`agents/moment_agent.py` from the scene as it stands. The enlarged view's prompt is now
**editable**, and `POST /play/{scenarioId}/moment/stream` accepts `prompt` / `negative`: when
`prompt` is present the agent call is **skipped entirely** — the player has already said what
they want painted, and asking a model to re-derive it would both cost a call and override them.
A blank value falls back to the agent.

The player's text is still passed through `moment_agent.strip_names`. That guarantee — an image
prompt describes people by **appearance**, never by name — is the subject of `EXP-2026-08-002`,
and a hand-written prompt is precisely the hole through which it would quietly leak back. A
test asserts that "Mei stands at the window" reaches ComfyUI without "Mei" in it.

Painting again is **additive**: it produces a new `scene_image` beat. Removing or replacing an
existing picture is a separate, destructive path and is not built (see `docs/checklist.md`).
