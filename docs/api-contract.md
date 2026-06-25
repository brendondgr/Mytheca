# Velora — API & Event Contract

The contract between the Next.js frontend and the FastAPI backend. Request/response schemas are owned by the backend (Pydantic, `web/backend/app/schemas/`); shared types and the event schema live in `web/shared/contracts/`. This document and those files must stay in sync.

**Status:** the Storyline / Character / Setting / Scenario CRUD groups, the stat endpoints, and the **Options** (global settings + LLM endpoint proxy) group are **implemented** (`web/backend/app/routes/`, served under `/api`). Auth, Play, Stream, and Admin remain **planned**. Wire payloads are camelCase (`castIds`, `settingId`, `displayName`) to match `web/frontend/lib/types.ts`.

## Conventions

- Base path: `/api`.
- JSON request/response; auth via the backend-owned session/token (mechanism TBD — see `docs/architecture.md`).
- Standard error shape:

```json
{ "error": { "code": "string", "message": "string", "details": {} } }
```

- Validation errors return 422 with field-level details. Auth failures return 401; permission failures 403.

## Endpoint Groups (planned)

| Group | Endpoints | Notes |
| --- | --- | --- |
| Auth | `POST /auth/sign-up`, `POST /auth/sign-in`, `POST /auth/sign-out`, `GET /me`, `PATCH /me` | Backend owns session/token. |
| Storylines | `GET /storylines`, `POST /storylines`, `GET /storylines/{id}`, `PATCH /storylines/{id}`, `DELETE /storylines/{id}` | The world container; owns the baseline stat schema. Read/write shape: `id`, `title`, `genre`, `tagline` (one-line switcher descriptor), `premise` (nullable multi-paragraph human-facing world description), `worldPrimer` (nullable agent-facing runtime context — generated at creation, editable; see Authoring below), `symbol` (seal shape glyph shown left of the name, default `◆`), `symbolColor` (seal hex color, default `#C8862A`). |
| Stat definitions | `GET /storylines/{id}/stats`, `POST /storylines/{id}/stats`, `PATCH /storylines/{id}/stats/{key}`, `DELETE /storylines/{id}/stats/{key}` | The world's universal stat schema, shared by every character. Freely add/edit/remove: `PATCH` edits name/description/range/bands (range narrowing re-clamps character values); `DELETE` prunes the stat's values from every character. Each definition carries labeled `bands` ("tickers"). |
| Characters | `GET /storylines/{id}/characters`, `POST /storylines/{id}/characters`, `GET /characters/{id}`, `PATCH /characters/{id}`, `DELETE /characters/{id}` | Belong to a storyline; each holds a stat block. Read/write shape: `id`, `name`, `role`, `color`, `mono` (derived), `traits`, `speech`, `goal`, `secret`, plus base-identity prose `appearance`, `background`, `personality` (all nullable), and `portrait` (nullable relative `/media/...` URL of the generated WebP avatar). |
| Settings | `GET /storylines/{id}/settings`, `POST /storylines/{id}/settings`, `GET /settings/{id}`, `PATCH /settings/{id}`, `DELETE /settings/{id}` | Places within a storyline. Read/write shape: `id`, `name`, `type`, `desc` (short base description), plus §4.1 Setting-node metadata `atmosphere` (sensory character), `features` (notable fixtures/points of interest), `currentState` (initial here-and-now), and `image` (nullable relative `/media/scenes/...` URL of the generated WebP establishing shot) — all nullable; and `timeline` (append-only event log, **empty at authoring**, play-accrued; defaults `[]`). |
| Scenarios | `GET /storylines/{id}/scenarios`, `POST /storylines/{id}/scenarios`, `GET /scenarios/{id}`, `PATCH /scenarios/{id}`, `DELETE /scenarios/{id}` | The live situations; may add/override stats. |
| Authoring | `POST /storylines/draft`, `POST /storylines/primer` | **Implemented.** The agent process of building a storyline: draft metadata from a one-sentence seed, and generate the agent-facing World Primer (see Authoring Shapes below). Run over the configured LLM; no retrieval. |
| Character authoring | `POST /characters/draft`, `POST /characters/portrait-prompts`, `POST /characters/portrait`, `POST /characters/starting-stats` | **Implemented.** The agentic Character Creator (prep phase): draft a character's base identity from a seed (optionally grounded in the world + dropped docs), write watercolor portrait prompts, render the portrait via ComfyUI (saved as WebP, served at `/media`), and propose starting stats keyed to the storyline's stat schema. Produces §1 *node properties* only — no graph. See Character Authoring Shapes below. |
| Setting authoring | `POST /settings/draft`, `POST /settings/scene-art-prompts`, `POST /settings/scene-art` | **Implemented.** The agentic Setting Creator (prep phase): draft a setting's base description + current state from a seed (optionally grounded in the world + dropped docs), write watercolor establishing-shot prompts, and render the scene art via ComfyUI (saved as WebP under `/media/scenes`). Produces §4.1 Setting-*node properties* only — never the play-accrued event timeline or graph edges. See Setting Authoring Shapes below. |
| Media | `GET /media/portraits/{file}.webp`, `GET /media/scenes/{file}.webp` | **Implemented.** Read-only static mount (not under `/api`) serving generated character portraits and setting scene art from `MEDIA_DIR`. |
| Options | `GET /options`, `PATCH /options/llm`, `PATCH /options/library`, `POST /options/llm/models`, `POST /options/llm/test`, `PATCH /options/comfy`, `GET /options/comfy/workflows`, `POST /options/comfy/status` | **Implemented.** Global settings (LLM endpoint + library defaults + ComfyUI image generation). Prefix is `/options` (the Setting entity owns `/settings`). |
| Play | `POST /play/{scenarioId}/turn` | Submit a user turn; triggers the orchestrator. |
| Stream | `GET /stream/{sessionId}` (SSE) or WS `/ws/{sessionId}` | NDJSON event stream (see below). |
| Admin (future) | `GET /admin/*` | High-permission only. |

## Stat Definition Shape

A stat definition (on a storyline, optionally overridden by a scenario):

```json
{
  "key": "health",
  "displayName": "Health",
  "description": "Physical condition and vitality.",
  "min": 0,
  "max": 100,
  "default": 100,
  "guidance": "stats/health.md",
  "visibility": "public",
  "appliesTo": ["character"],
  "bands": [
    { "min": 0, "max": 20, "label": "Nearly dead" },
    { "min": 81, "max": 100, "label": "Very healthy" }
  ]
}
```

Stats are **freely editable** — name, description, range (`min`/`max`/`default`), and bands all change via `PATCH` (only `key` is immutable). When a range narrows, the service **re-clamps** every character's value for that stat in the same transaction so no stored value sits out of bounds. `DELETE /storylines/{id}/stats/{key}` removes the definition **and prunes that stat's values from every character** (the value link is by key, not a FK). The validator clamps every stat change to `[min, max]`. `bands` ("tickers") are an ordered list of `{ min, max, label }` describing what value ranges *mean* (for future state-extraction); they need not tile the range or be contiguous, but each requires `min ≤ max` and a non-empty label. `visibility` ∈ `public | private_to_user | private_to_character | hidden`. A character holds values only: `{ "health": 80, "strength": 14 }`.

## Options / Settings Shape

Global settings for the `/options` page. There is no auth yet, so this is a
single global document (one DB row per namespace in `app_settings`). The LLM API
key is **write-only**: it is stored server-side and never returned in clear.

`GET /options` →

```json
{
  "llm": {
    "baseUrl": "http://localhost:7070/v1",
    "model": "llama-3.1-8b",
    "provider": "openai-compatible",
    "params": { "temperature": 0.7, "maxTokens": 512, "topP": 1.0, "frequencyPenalty": 0.0, "presencePenalty": 0.0 },
    "hasApiKey": true,
    "apiKeyHint": "…AB12"
  },
  "library": { "defaultStorylineId": "embergate", "openLastStoryline": true },
  "comfy": {
    "baseUrl": "http://localhost:8199",
    "workflow": "ZiT-Workflow.json",
    "params": { "steps": 4, "cfg": 1.0, "width": 1024, "height": 1024, "batchSize": 1, "negativePrompt": "" }
  }
}
```

- `PATCH /options/llm` — body may include `baseUrl`, `model`, `provider`, `params`,
  and `apiKey`. **`apiKey` semantics:** omitted = keep the stored key; `""` =
  clear it; any other value = replace it. The base URL is normalized (trailing
  slash trimmed). Returns the masked `LlmConfigRead`.
- `PATCH /options/library` — body may include `defaultStorylineId`,
  `openLastStoryline`. Returns `LibraryDefaultsRead`.
- `POST /options/llm/models` — `{ baseUrl?, apiKey? }` (fall back to stored).
  Proxies `GET {baseUrl}/models` server-side (dodges browser CORS, keeps the key
  off the client) → `{ "models": ["id", …] }`. Upstream non-2xx →
  `502 upstream_error`; network/timeout → `502 bad_gateway`; missing URL →
  `400 bad_request`.
- `POST /options/llm/test` — `{ baseUrl?, apiKey?, model, params? }`. Proxies a
  tiny `POST {baseUrl}/chat/completions` → `{ ok, model, latencyMs, sample }`.

**ComfyUI image generation** (the local Comfy server — its own HTTP + WebSocket
protocol, not OpenAI-compatible):

- `PATCH /options/comfy` — body may include `baseUrl`, `workflow`, `params`
  (`steps`, `cfg`, `width`, `height`, `batchSize`, `negativePrompt`). Base URL is
  normalized. Returns `ComfyConfigRead`.
- `GET /options/comfy/workflows` — `{ "workflows": ["ZiT-Workflow.json", …] }`,
  the `*.json` files saved in `utils/workflows/`.
- `POST /options/comfy/status` — `{ baseUrl? }` (fall back to stored). Server-side
  `GET {baseUrl}/system_stats` → `{ ok, comfyuiVersion, device, pythonVersion }`.
  Network/timeout → `502 bad_gateway`; missing URL → `400 bad_request`.

The full generation pipeline (load workflow → patch prompt → `POST /prompt` →
WebSocket wait → `GET /history` → `GET /view`) lives in
`web/backend/app/services/comfyui.py` (`generate(...)`), used by the story engine;
the Options tab exposes config + the status check only.

## Authoring Shapes (storyline creation agent)

The agent process that builds a storyline at creation time, run over the
configured LLM (the `/options` endpoint above). **No retrieval / RAG:** when
present, `docsOverview` is inline text read from dropped reference files in the
browser and used for that single generation only — it is never persisted or
indexed.

- `POST /storylines/draft` — `{ seed, docsOverview? }`. Drafts metadata from a
  one-sentence seed → `{ "title", "genre", "tagline", "premise" }` (the create
  form prefill). Empty `seed` → `400 bad_request`; unconfigured LLM →
  `400 bad_request` ("Configure a model in Options first."); a reply that is not
  valid storyline JSON → `502 upstream_error`.
- `POST /storylines/primer` — `{ premise?, seed?, docsOverview? }` (at least one
  of `premise`/`seed` required). Generates the agent-facing **World Primer** →
  `{ "worldPrimer": "…prose…" }`. The result is stored on the storyline via the
  normal `worldPrimer` field on create/PATCH. Same unconfigured-LLM /
  empty-completion error mapping as above.

## Character Authoring Shapes (agentic Character Creator)

The agent process that fleshes out a **character's base identity** at creation
time (§1 node properties of `Documents/Plans/3.character-graph-structure-prep.md`
— never graph structure). Run over the configured LLM. Same **no retrieval**
rule: `docsOverview` is inline dropped-file text used for one generation only.

- `POST /characters/draft` — `{ seed, docsOverview?, storylineId? }`. Drafts a
  full character → `{ name, role, traits, speech, goal, secret, appearance,
  background, personality, color }`. When `storylineId` is given, the draft is
  grounded in that world's primer/genre (best-effort). Empty `seed` →
  `400 bad_request`; unconfigured LLM → `400 bad_request`; a reply that is not
  valid JSON → `502 upstream_error`.
- `POST /characters/portrait-prompts` — `{ name?, role?, appearance?, traits?,
  personality?, species?, notes? }` (at least one descriptive field required).
  Writes the watercolor ComfyUI prompts → `{ positive, negative }`: short
  comma-separated phrases leading with the subject's species/race so the image
  depicts that being.
- `POST /characters/portrait` — `{ positive, negative?, baseUrl?, workflow?,
  width?, height?, steps?, cfg? }`. Renders the portrait through the configured
  ComfyUI watercolor pipeline, converts the result to **WebP**, saves it under
  `MEDIA_DIR`, and returns `{ portrait: "/media/portraits/<uuid>.webp" }`. The URL
  is carried into the normal character create/PATCH `portrait` field (id-agnostic,
  so it works during creation before a row exists). Empty `positive` /
  unconfigured ComfyUI URL → `400 bad_request`; a Comfy failure → `502`. **Opt-in
  — it spends GPU time on the local Comfy server.**
- `POST /characters/starting-stats` — `{ storylineId, name?, role?, traits?,
  personality?, background? }`. Proposes starting values for the storyline's stat
  definitions → `{ proposals: [{ key, displayName, value, min, max, rationale }] }`.
  Each definition's **bands** are folded into the prompt so the model picks a value
  whose band matches the character's intended starting condition. Values are clamped
  to each definition's range, unknown keys dropped, and any skipped stat filled with
  its default. Returns `{ proposals: [] }` (no LLM call) when the world defines no
  stats. **Proposal only** — the caller applies them via `PUT /characters/{id}/stats`.

## Setting Authoring Shapes (agentic Setting Creator)

The agent process that fleshes out a **setting's base description + current
state** at creation time (§4.1 Setting-node properties of
`Documents/Plans/4.story-graph-structure-prep.md` — never the play-accrued event
timeline, never graph edges). Run over the configured LLM. Same **no retrieval**
rule: `docsOverview` is inline dropped-file text used for one generation only.

- `POST /settings/draft` — `{ seed, docsOverview?, storylineId? }`. Drafts a full
  setting → `{ name, type, desc, atmosphere, features, currentState }`. `type` is
  chosen from the canonical setting-type list. When `storylineId` is given, the
  draft is grounded in that world's primer/genre (best-effort). Empty `seed` →
  `400 bad_request`; unconfigured LLM → `400 bad_request`; a reply that is not
  valid JSON → `502 upstream_error`.
- `POST /settings/scene-art-prompts` — `{ name?, type?, desc?, atmosphere?,
  features?, currentState?, notes? }` (at least one descriptive field required).
  Writes the watercolor ComfyUI prompts → `{ positive, negative }`: an atmospheric
  establishing shot of the location itself, no people.
- `POST /settings/scene-art` — `{ positive, negative?, baseUrl?, workflow?, width?,
  height?, steps?, cfg? }`. Renders the establishing image through the configured
  ComfyUI watercolor pipeline (landscape 16:9 default), converts to **WebP**, saves
  it under `MEDIA_DIR/scenes`, and returns `{ image: "/media/scenes/<uuid>.webp" }`.
  The URL is carried into the normal setting create/PATCH `image` field (id-agnostic,
  so it works during creation before a row exists). Empty `positive` / unconfigured
  ComfyUI URL → `400 bad_request`; a Comfy failure → `502`. **Opt-in — it spends GPU
  time on the local Comfy server.**

## NDJSON Event Stream

> **Scaffold status:** the event envelope types (the five types below + `StatPatch`, as a discriminated union) exist in `web/backend/app/events/envelope.py`, and `events` + `play_sessions` tables exist in `web/backend/app/models/`. The streaming transport, turn engine, `seq` monotonicity, and validation/repair loop are **not built yet** — this is the data-structure scaffold only.

The stream emits one JSON object per line. Every event shares a base envelope:

```json
{ "type": "string", "id": "string", "seq": 0, "scenarioId": "string", "sessionId": "string", "ts": "ISO-8601", "visibility": "public", "data": {} }
```

`visibility` ∈ `public | private_to_user | private_to_character | hidden` — some content is shown to the player, some only affects agent reasoning.

### Event types (minimal set to start)

Start with **five** types, not thirty. Each maps to one frontend component.

| `type` | UI rendering | `data` highlights |
| --- | --- | --- |
| `narration` | Teal narrator card | `text` (may delta-stream) |
| `character_dialogue` | Character chat bubble (speaker's avatar/color) | `characterId`, `text` (may delta-stream), `done` |
| `character_action` | Action / emote card | `characterId`, `text` |
| `state_update` | Updates side panels (no chat message) | `patch` — partial scenario state; **stat changes ride here** |
| `branch_choices` | Branch-choices panel | `choices[]` (`label`, `outcome`, optional `check`) |

**Stat changes** are carried on `state_update`:

```json
{ "type": "state_update", "data": { "stat": {
  "characterId": "kira", "key": "health", "delta": -25, "value": 55,
  "reason": "Struck by the falling beam." } } }
```

The validator confirms the stat exists and clamps `value` to `[min, max]`; the Stats panel re-renders and the narrator may reference the new state next turn. When bespoke rendering is wanted (an animating bar, a floating "+5 / −10"), promote stat changes to a dedicated `stat_update` event later — the data shape is the same.

Additional types to layer in later: `internal_thought` (with visibility controls), `relationship_update`, `goal_update`, `turn_update`, and the dice-resolution set (`check_request`, `roll_result`, `consequence`).

### Streaming modes

- **Full events** (one complete object) — used for `state_update` and `branch_choices`. Easy to validate and render.
- **Delta streaming** — `message_start` → repeated `message_delta` → `message_end` — used for visible messages (`narration`, `character_dialogue`). The client renders deltas as they arrive and finalizes on `message_end`.

### Rules

- `seq` is monotonic per session so the client can detect gaps and reorder.
- Chunked/delta text sets `done: false` until the final chunk sets `done: true`.
- The client must handle reconnect (resume from last `seq` where possible) and stalled streams.
- The validator runs `parse → validate (incl. stat clamping) → repair/retry` before anything reaches the stream.

## Shared Contracts Location

TypeScript types for events and API payloads live in `web/shared/contracts/`. When an endpoint, event, or stat shape changes, update: the Pydantic schema, the shared contract type, and this document.
