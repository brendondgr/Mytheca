# Velora — API & Event Contract

The contract between the Next.js frontend and the FastAPI backend. Request/response schemas are owned by the backend (Pydantic, `web/backend/app/schemas/`); shared types and the event schema live in `web/shared/contracts/`. This document and those files must stay in sync.

**Status:** the Storyline / Character / Setting / Scenario CRUD groups, the stat endpoints, the **Options** (global settings + LLM endpoint proxy) group, the **Story Graph** (Type Registry + scenario subgraph read), and the **Hybrid RAG** (status, reindex stream, query) are **implemented** (`web/backend/app/routes/`, served under `/api`). Auth, Play, Stream, and Admin remain **planned**. Wire payloads are camelCase (`castIds`, `settingId`, `displayName`) to match `web/frontend/lib/types.ts`.

**Identifiers:** the two **URL-facing** ids are short, bare hex (no prefix) so they read cleanly in `/{storylineId}/{scenarioId}` — **Storyline = 8-hex** (`1a2b3c4d`), **Scenario = 4-hex** (`9f8e`), both collision-checked at create time (`services/crud.py`). All other entities keep prefixed ids (`c_…`, `s_…`, `stat_…`, `ev_…`). Ids are string primary keys, so hand-authored seed slugs (`embergate`, `maerin`) and any client-supplied id still pass through unchanged.

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
| Storylines | `GET /storylines`, `POST /storylines`, `GET /storylines/{id}`, `PATCH /storylines/{id}`, `DELETE /storylines/{id}` | The world container; owns the baseline stat schema. Read/write shape: `id`, `title`, `genre`, `tagline` (one-line switcher descriptor), `premise` (nullable multi-paragraph human-facing world description), `worldPrimer` (nullable agent-facing runtime context — generated at creation, editable; see Authoring below), `symbol` (seal shape glyph shown left of the name, default `◆`), `symbolColor` (seal hex color, default `#C8862A`). The list (`GET /storylines`) and single-get (`GET /storylines/{id}`) responses also include **`scenarioCount`**, **`characterCount`**, and **`settingCount`** (integers, default `0`) — computed via SQL COUNT subqueries so the header switcher always shows accurate totals for every world without loading full child arrays. Create/update responses return `0` for all three (newly created worlds have no children; clients re-fetch the list on next load). |
| Stat definitions | `GET /storylines/{id}/stats`, `POST /storylines/{id}/stats`, `PATCH /storylines/{id}/stats/{key}`, `DELETE /storylines/{id}/stats/{key}` | The world's universal stat schema, shared by every character. Freely add/edit/remove: `PATCH` edits name/description/range/bands (range narrowing re-clamps character values); `DELETE` prunes the stat's values from every character. Each definition carries labeled `bands` ("tickers"). |
| Characters | `GET /storylines/{id}/characters`, `POST /storylines/{id}/characters`, `GET /characters/{id}`, `PATCH /characters/{id}`, `DELETE /characters/{id}` | Belong to a storyline; each holds a stat block. Read/write shape: `id`, `name`, `role`, `color`, `mono` (derived), `traits`, `speech`, `goal`, `secret`, plus base-identity prose `appearance`, `background`, `personality` (all nullable), `portrait` (nullable relative `/media/...` URL of the generated WebP avatar), and `portraitPositive` / `portraitNegative` (nullable ComfyUI prompt strings that produced the portrait — persisted so the author can tweak-and-re-render on re-edit). |
| Settings | `GET /storylines/{id}/settings`, `POST /storylines/{id}/settings`, `GET /settings/{id}`, `PATCH /settings/{id}`, `DELETE /settings/{id}` | Places within a storyline. Read/write shape: `id`, `name`, `type`, `desc` (short base description), plus §4.1 Setting-node metadata `atmosphere` (sensory character), `features` (notable fixtures/points of interest), `currentState` (initial here-and-now), and `image` (nullable relative `/media/scenes/...` URL of the generated WebP establishing shot) — all nullable; `sceneArtPositive` / `sceneArtNegative` (nullable ComfyUI prompt strings that produced the image — persisted for re-edit); and `timeline` (append-only event log, **empty at authoring**, play-accrued; defaults `[]`). |
| Scenarios | `GET /storylines/{id}/scenarios`, `POST /storylines/{id}/scenarios`, `GET /scenarios/{id}`, `PATCH /scenarios/{id}`, `DELETE /scenarios/{id}` | The live situations; may add/override stats. Read/write shape includes `image` (nullable relative `/media/scenes/...` URL of the generated WebP scene art), `sceneArtPositive`, and `sceneArtNegative` (nullable prompt strings). |
| Context documents | `GET /storylines/{id}/context-docs`, `POST /storylines/{id}/context-docs`, `POST /storylines/{id}/context-docs/bulk`, `PATCH /context-docs/{docId}`, `DELETE /context-docs/{docId}` | **Implemented.** The persisted **triaged RAG corpus** for a world (written by the New Storyline page's Triage → commit). Each doc carries a `category` (`character`/`setting`/`other`) and inclusion tiers `includeDraft` / `includeRag`. Docs are **storyline-level** (Triage default) or **entity-scoped** — a doc with `entityType` + `entityId` reappears in that editor on re-edit and is removed (with its embedding) when the entity is deleted. `GET /storylines/{id}/context-docs` accepts `?entityType=&entityId=` to filter by scope. Docs with `includeRag` are embedded on save (hybrid RAG). See Context Document Shape below. |
| Hybrid RAG | `GET /storylines/{id}/rag/status`, `POST /storylines/{id}/rag/reindex/stream`, `POST /storylines/{id}/rag/query` | **Implemented.** Vector-store status, NDJSON reindex progress stream, and debug retrieval query for a world's corpus. Best-effort (`available: false` when Qdrant is down/disabled). See RAG Shapes below. |
| Story Graph | `GET /scenarios/{id}/graph` | **Implemented.** Loads the scenario's Story-Graph subgraph (cast + setting nodes + the edges among them), read live from Neo4j (§7.2). Returns `{ available, scenarioId, nodes[], edges[] }`; `available` is `false` with empty lists when the graph is disabled/unreachable (best-effort). See Story Graph Shapes below. |
| Graph types | `GET /storylines/{id}/graph/types`, `POST /storylines/{id}/graph/types`, `PATCH /graph/types/{typeId}`, `DELETE /graph/types/{typeId}` | **Implemented.** The Type Registry (§1.4): list the node/edge types visible to a storyline (global built-ins + its own user types), and register/patch/delete user-defined types. Built-in types are immutable (409). Edge types require a `valence`; user types default `status: experimental`. |
| Authoring | `POST /storylines/draft`, `POST /storylines/primer`, `POST /storylines/triage`, `POST /storylines/build` | **Implemented.** The agent process of building a storyline: draft metadata from a one-sentence seed, generate the agent-facing World Primer, **triage** dropped reference docs into Characters / Settings / Other with Draft/RAG inclusion, and **build** an entire reviewable world (metadata + primer + stat schema + cast + settings) in one orchestrated call (see Authoring Shapes below). Run over the configured LLM; no retrieval. |
| Authoring (live) | `POST /storylines/build/stream`, `POST /storylines/triage/stream` | **Implemented.** NDJSON (`application/x-ndjson`) streaming variants of build + triage so the New Storyline page renders the world / triage **as they are built** — the build emits `meta`/`primer`/`plan`/`character`/`setting`/`done`; triage classifies **per file**, emitting `status`+`item` per doc then `done`. Pre-flight failures (no context / unconfigured LLM) return a normal `400` before the stream opens; mid-stream failures arrive as a terminal `error` event. See Live Authoring Stream below. |
| Character authoring | `POST /characters/draft`, `POST /characters/portrait-prompts`, `POST /characters/portrait`, `POST /characters/starting-stats` | **Implemented.** The agentic Character Creator (prep phase): draft a character's base identity from a seed (optionally grounded in the world + dropped docs), write watercolor portrait prompts, render the portrait via ComfyUI (saved as WebP, served at `/media`), and propose starting stats keyed to the storyline's stat schema. Produces §1 *node properties* only — no graph. See Character Authoring Shapes below. |
| Setting authoring | `POST /settings/draft`, `POST /settings/scene-art-prompts`, `POST /settings/scene-art` | **Implemented.** The agentic Setting Creator (prep phase): draft a setting's base description + current state from a seed (optionally grounded in the world + dropped docs), write watercolor establishing-shot prompts, and render the scene art via ComfyUI (saved as WebP under `/media/scenes`). Produces §4.1 Setting-*node properties* only — never the play-accrued event timeline or graph edges. See Setting Authoring Shapes below. |
| Scenario authoring | `POST /scenarios/draft`, `POST /scenarios/scene-art-prompts`, `POST /scenarios/scene-art` | **Implemented.** The agentic Scenario Creator: draft a scenario (title/genre/tone/goal/opening) from a seed, plus a **valid cast + setting chosen from the active world's real roster**. The model returns names from a numbered roster; the agent resolves names→ids server-side, **dropping** unknown cast and falling back to `""` for an unmatched setting — so the draft never invents or dangles a reference. Scene-art prompts and image generation follow the same watercolor pipeline as Setting authoring. Declared above `/scenarios/{id}`. See Scenario Authoring Shapes below. |
| Media | `GET /media/portraits/{file}.webp`, `GET /media/scenes/{file}.webp` | **Implemented.** Read-only static mount (not under `/api`) serving generated character portraits and setting scene art from `MEDIA_DIR`. |
| Options | `GET /options`, `PATCH /options/llm`, `PATCH /options/library`, `POST /options/llm/models`, `POST /options/llm/test`, `GET /options/llm/backend`, `PATCH /options/comfy`, `GET /options/comfy/workflows`, `POST /options/comfy/status`, `GET /options/media/orphans`, `POST /options/media/cleanup` | **Implemented.** Global settings (LLM endpoint + library defaults + ComfyUI image generation), read-only inference-engine detection (`/llm/backend`), and orphaned-media maintenance (`/media/orphans`, `/media/cleanup`). Prefix is `/options` (the Setting entity owns `/settings`). |
| Play | `POST /play/{scenarioId}/turn` | **Implemented.** Submit a player turn; the response body **is** the NDJSON event stream (`application/x-ndjson`, one event per line) — the turn engine runs the per-character POV loop and streams the resulting story events directly (reusing the build/triage streaming pattern), so there is no separate stream connection for the single-player case. Body: `{ text, directedAt?, sessionId?, mode? }` (omit `sessionId` to start a session; `mode` ∈ `pov` (default) \| `narrator`). The reasoned **Director** picks who reacts + order (a directed addressee / solo cast is the no-LLM fast path); **Narrator Mode** inserts a narration interstitial before each speaker, **POV Mode** omits it (one engine — D1). Pre-flight failures (unknown scenario → 404, empty text → 400, bad session → 404/400) return a normal error envelope before the 200 stream opens; a mid-stream failure is the terminal `{ "type": "error", "message": "…" }` frame. See Turn Stream below. |
| Stream (seam) | `GET /stream/{sessionId}` (SSE) or WS `/ws/{sessionId}` | **Deferred seam.** A separate fan-out connection (Redis pub/sub, reconnect/replay-from-`seq`, multi-watcher) for cases the single-response stream above doesn't cover. Not built. |
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

## Context Document Shape

A persisted, triaged reference document on a storyline (the RAG-corpus seam):

```json
{
  "id": "cd_…",
  "storylineId": "embergate",
  "name": "maerin.md",
  "content": "Maerin Voss is a harbor smuggler …",
  "category": "character",
  "includeDraft": false,
  "includeRag": true,
  "source": "upload",
  "charCount": 812,
  "entityType": "character",
  "entityId": "c_abc123"
}
```

`category` ∈ `character | setting | other` — a doc about **one** character/setting
lands in that bucket; one holding **multiple** characters or settings, or a general
world doc, lands in `other` (set by Triage). `includeDraft` marks world-setting docs
that ground generation; `includeRag` (default `true`) marks the retrieval corpus.
`entityType` + `entityId` (both nullable) scope a doc to a specific
character/setting/scenario: a scoped doc reappears in that editor on re-edit and is
deleted (with its Qdrant point) when the entity is deleted. A doc without these
fields is storyline-level (the Triage/bulk default). `GET /storylines/{id}/context-docs`
accepts `?entityType=character&entityId=c_abc123` to filter by scope.
`POST …/context-docs/bulk` takes `{ docs: [ContextDocumentCreate…] }` and persists
the whole corpus in one call (the New Storyline commit). Docs with `includeRag: true`
are embedded on save and pruned on delete (hybrid RAG).

## Story Graph Shapes

The scenario subgraph (`GET /scenarios/{id}/graph`) — cast + setting and the edges among them, read live from Neo4j:

```json
{
  "available": true,
  "scenarioId": "sc_…",
  "nodes": [
    { "id": "maerin", "type": "Character", "label": "Maerin Voss", "storyline": "embergate", "metadata": { "appearance": "…" } },
    { "id": "saltworn", "type": "Setting", "label": "The Saltworn Tavern", "storyline": "embergate", "metadata": { "atmosphere": "…", "kind": "Social Hub" } }
  ],
  "edges": [
    { "source": "maerin", "target": "saltworn", "type": "present_at", "metadata": { "weight": 1.0, "visibility": "public", "status": "active" } }
  ]
}
```

A Type Registry entry (`GET/POST /storylines/{id}/graph/types`):

```json
{
  "id": "gt_…",
  "storylineId": null,
  "kind": "edge",
  "typeName": "loves",
  "fieldSchema": [{ "name": "potency", "kind": "numeric", "min": 0, "max": 1 }],
  "description": "A character's love toward another.",
  "valence": "positive",
  "decay": { "half_life_turns": 40, "floor": 0.05 },
  "status": "built_in"
}
```

`kind` ∈ `node | edge`; `valence` ∈ `positive | negative | neutral` (edges only; required on create); `status` ∈ `built_in | experimental | trusted`. Built-in types have `storylineId: null` and are immutable; user types are storyline-scoped and start `experimental` (only `built_in`/`trusted` reach the hot path — §10). See `docs/story-graph-neo4j.md`.

## RAG Shapes

Three storyline-scoped endpoints for the hybrid RAG layer. All return `available: false`
(with no error) when Qdrant is disabled or unreachable — best-effort, like the Story Graph.

**`GET /api/storylines/{id}/rag/status`** — reachability + indexed count:

```json
{ "available": true, "indexed": 42 }
```

**`POST /api/storylines/{id}/rag/reindex/stream`** — re-embeds the world's corpus
streaming NDJSON (`application/x-ndjson`). Emits one `embedding` event per entry,
then a terminal `done` event:

```json
{ "stage": "embedding", "index": 1, "total": 42, "name": "Maerin Voss", "type": "character" }
{ "stage": "done", "indexed": 41, "skipped": 1, "total": 42, "available": true }
```

`skipped` counts entries whose content hash is unchanged (idempotent — no re-embed
for unchanged entries). `available: false` in the `done` event when Qdrant is
unreachable.

**`POST /api/storylines/{id}/rag/query`** — debug retrieval for a query string:

Request body:
```json
{ "query": "who controls the harbor?", "k": 5, "prefilter": {} }
```

Response:
```json
{
  "available": true,
  "results": [
    { "entryId": "character:c_abc123", "name": "Maerin Voss", "type": "character",
      "score": 0.87, "body": "Maerin Voss is a harbor smuggler …" }
  ]
}
```

`k` (default 5) is the number of top entries after RRF fusion. `prefilter` is an
optional payload filter passed to Qdrant (e.g. `{ "type": "character" }`). This
endpoint is for debugging retrieval — the authoring agents call `rag_block` directly.

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
- `GET /options/llm/backend` — read-only diagnostics for the auto-detected local
  inference engine of the configured endpoint → `{ "backend": "vllm" | "llamacpp" |
  "unknown", "budgets": { "low": 256, "medium": 512, "high": 1024, "very_high": 2048,
  "max": 4096 } }` (budget keys are the effort enum values, not camelized). The
  engine is probed (`GET /version` → vLLM, `GET /props` →
  llama.cpp), cached, and refreshed by a background poller. `unknown` (OpenAI /
  unreachable) means no thinking budget is sent. See **Reasoning budget** below.
  Surfaced read-only in the Options **About** tab (`getLlmBackend` in `lib/api.ts`):
  the detected engine plus the budget ladder, degrading to "unavailable" on error.

**Orphaned-media cleanup** (maintenance — generated WebPs that no DB row references,
left by cancelled drafts or deleted entities):

- `GET /options/media/orphans?min_age_hours=24` — dry-run scan (deletes nothing).
  Cross-references the `*.webp` files under `MEDIA_DIR/portraits` + `MEDIA_DIR/scenes`
  against every `Character.portrait` / `Setting.image` basename. Response →
  `{ "portraits": {...}, "scenes": {...}, "orphanCount", "eligibleCount", "totalBytes",
  "eligibleBytes", "minAgeHours" }` where each per-dir object is
  `{ "orphanCount", "eligibleCount", "totalBytes", "eligibleBytes" }`. An orphan is a
  WebP whose basename is unreferenced; it is *eligible* only when its mtime is older
  than `minAgeHours` — the **grace period** that protects files from an in-flight draft
  (generated but not yet saved).
- `POST /options/media/cleanup?min_age_hours=24` — deletes only **eligible** orphans
  (unreferenced AND grace-expired); recent orphans are skipped. Response →
  `{ "deletedCount", "freedBytes", "skippedRecentCount" }`. Safe by construction: never
  touches referenced files, non-`.webp` files, or anything outside the two media subdirs.
  Surfaced in the Options **About** tab's Maintenance section (scan → confirm → delete).

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

## Reasoning budget (backend-controlled thinking cap)

Local reasoning models spend most of their wall-clock on hidden *thinking* tokens.
Velora caps that **per authoring operation** so quick work finishes fast. The effort
is set on the **backend** at each call-site and is **never exposed to the user** for
Storyline / Character / Setting creation — there is no request field or settings
toggle for it.

- **Efforts → thinking-token budget:** `low` 256 · `medium` 512 · `high` 1024 ·
  `very_high` 2048 · `max` 4096 (`web/backend/app/schemas/reasoning.py`).
- **Per call-site:** **Triage = Low**; **Build the whole world** + the standalone
  storyline/character/setting drafts = **Medium** (`DEFAULT_AUTHORING_EFFORT`).
- **Transport:** `services/llm.chat_complete(..., reasoning=)` detects the engine and
  adds the matching key — **vLLM** `thinking_token_budget`, **llama.cpp**
  `thinking_budget_tokens`. An OpenAI / unknown endpoint gets no key (unchanged
  behaviour). Requires reasoning enabled server-side (vLLM `--reasoning-parser`;
  llama.cpp `--jinja --reasoning on` with no CLI `--reasoning-budget`).

## Authoring Shapes (storyline creation agent)

The agent process that builds a storyline at creation time, run over the
configured LLM (the `/options` endpoint above). **No retrieval / RAG:** when
present, `docsOverview` is inline text read from dropped reference files in the
browser and used for that single generation only — it is never persisted or
indexed. Inline grounding is capped at **32000 characters** server-side
(`_common.DOCS_CAP`; the frontend mirrors it via `readDocs.DOCS_CHAR_CAP` and the
on-page context-budget meter).

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
- `POST /storylines/triage` — `{ docs: [{ name, text }], storylineId? }`. Classifies
  each dropped reference document in one call → `{ "items": [{ name, category, includeDraft,
  includeRag, rationale }] }`. `category` ∈ `character | setting | other` (a doc about
  ONE character/setting → that bucket; multiple/mixed/general → `other`); `includeDraft`
  marks world-setting docs that ground drafting, `includeRag` (default on) marks the
  retrieval corpus. Empty `docs` → `{ "items": [] }` (no LLM call); a doc the model omits
  falls back to `other`/RAG-on; unconfigured LLM → `400`; non-JSON reply → `502`. The
  classified docs are persisted on commit via the **Context documents** bulk endpoint.
- `POST /storylines/build` — `{ seed?, docsOverview?, storylineId?, maxCharacters?,
  maxSettings?, characterDocs?: [{ name, text }], settingDocs?: [{ name, text }],
  otherDocs?: [{ name, text }] }`
  (at least one of `seed` / `docsOverview` / any attached doc is required). Orchestrates
  several LLM calls (storyline draft → World Primer → one **blueprint** call for the
  stat schema → **one extraction call per attached doc** that lists the distinct
  characters/settings it contains → one draft per extracted character → one draft per
  extracted setting) and returns a reviewable `ProposedWorld`:

  ```json
  {
    "storyline": { "title": "…", "genre": "…", "tagline": "…", "premise": "…", "worldPrimer": "…" },
    "stats": [ { "key": "health", "displayName": "Health", "min": 0, "max": 100, "default": 100, "bands": […] } ],
    "characters": [ { "name": "…", "role": "…", "traits": "…", "appearance": "…", …, "startingStats": [ { "key": "health", "value": 100 } ] } ],
    "settings": [ { "name": "…", "type": "…", "desc": "…", "atmosphere": "…", "features": "…", "currentState": "…" } ]
  }
  ```

  **The cast/settings come ONLY from the attached docs, but each doc is *mined*** —
  every attached doc (`characterDocs` + `settingDocs` + `otherDocs`) is scanned for the
  **distinct characters and settings it contains**, and one card is drafted per subject
  found. A single file describing several characters yields several character cards; a
  mixed/`other` doc yields both kinds; a pure-lore doc yields none (it still grounds the
  world). Subjects are de-duped across docs by folded name. The build never **invents** a
  character/setting the author didn't attach: with no docs, `characters`/`settings` are
  `[]`. The storyline metadata, World Primer, and the universal **stat schema** are
  always produced. Nothing is persisted by this call — the page reviews the proposal and
  commits it via the normal CRUD endpoints (rendering portraits/scene-art then, only if
  ComfyUI is reachable). The cast/settings are **uncapped** (every distinct subject the
  author attached becomes a card); only the invented **stats** are bounded (≤8). Proposed stats are
  sanitized to valid ranges so they persist straight through `POST /storylines/{id}/stats`;
  starting stats default to the schema defaults. No context at all → `400`; unconfigured
  LLM → `400`; a non-JSON sub-reply → `502`.

### Live Authoring Stream (NDJSON)

Streaming variants of build + triage. The response is `application/x-ndjson` — **one
JSON object per line** — so the New Storyline page renders the world / triage *as they
are built*. **Pre-flight** errors (no context, unconfigured LLM) are validated before
the `200` stream opens and returned as the usual error envelope; once the stream is open
the status can't change, so a mid-run failure is emitted as a terminal `error` event.
The non-streaming `/build` + `/triage` routes above are unchanged (collectors over the
same generators).

- `POST /storylines/build/stream` — same body as `/build`. Emits, in order:
  - `{ "type": "status", "stage": "metadata|primer|blueprint|extract|characters|settings", "message": "…" }` — progress markers.
  - `{ "type": "meta", "title", "genre", "tagline", "premise" }` — storyline metadata drafted.
  - `{ "type": "primer", "worldPrimer": "…" }` — the World Primer.
  - `{ "type": "plan", "stats": […], "characters": ["name", …], "settings": ["name", …] }` — the stat schema + the skeleton labels for the cast/settings to be built (the **extracted subject names**, after every attached doc is mined; empty when no subjects are found).
  - `{ "type": "character", "index", "total", "character": { … } }` — one full character per extracted subject (fills its skeleton).
  - `{ "type": "setting", "index", "total", "setting": { … } }` — one full setting per extracted subject.
  - `{ "type": "done", "world": ProposedWorld }` — terminal success (the assembled proposal).
  - `{ "type": "error", "message": "…" }` — terminal in-band failure.
- `POST /storylines/triage/stream` — same body as `/triage`, but classifies **one
  document per LLM call** (genuinely live). Emits, per file:
  `{ "type": "status", "name", "index", "total" }` then `{ "type": "item", "item": TriageItem }`,
  and a terminal `{ "type": "done" }`. A per-doc failure falls back to `other`/RAG-on
  (it does not abort the run). Empty/blank docs stream straight to `done` with no LLM call
  (and need no configured LLM).

## Character Authoring Shapes (agentic Character Creator)

The agent process that fleshes out a **character's base identity** at creation
time (§1 node properties of `Documents/Plans/3.character-graph-structure-prep.md`
— never graph structure). Run over the configured LLM. Same **no retrieval**
rule: `docsOverview` is inline dropped-file text used for one generation only.

- `POST /characters/draft` — `{ seed, docsOverview?, storylineId? }`. Drafts a
  full character → `{ name, role, traits, speech, goal, secret, appearance,
  background, personality, color }`. **`seed` and `docsOverview` are each
  optional individually but at least one must be non-empty** — with no seed the
  draft is grounded purely on the Draft-tagged reference docs. When `storylineId`
  is given, the draft is also grounded in that world's primer/genre (best-effort).
  Empty `seed` **and** empty `docsOverview` → `400 bad_request`; unconfigured LLM
  → `400 bad_request`; a reply that is not valid JSON → `502 upstream_error`.
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
  so it works during creation before a row exists). The `positive` / `negative`
  prompts that produced it are carried into the same payload's `portraitPositive` /
  `portraitNegative` fields, so they persist and re-hydrate the editor on re-edit
  (mirrors the Setting `sceneArt*` and Scenario `sceneArt*` fields). Empty
  `positive` / unconfigured ComfyUI URL → `400 bad_request`; a Comfy failure →
  `502`. **Opt-in — it spends GPU time on the local Comfy server.**
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
  chosen from the canonical setting-type list. **`seed` and `docsOverview` are
  each optional individually but at least one must be non-empty** — with no seed
  the draft is grounded purely on the Draft-tagged reference docs. When
  `storylineId` is given, the draft is also grounded in that world's primer/genre
  (best-effort). Empty `seed` **and** empty `docsOverview` → `400 bad_request`;
  unconfigured LLM → `400 bad_request`; a reply that is not valid JSON →
  `502 upstream_error`.
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

## Scenario Authoring Shapes (agentic Scenario Creator)

The agent process that assembles a **scenario** at creation time — the present-
moment "truth object" — from a one-line scene seed. Run over the configured LLM.
Same **no retrieval** rule: `docsOverview` is accepted for parity but the scenario
modal does not wire dropped files yet (first cut grounds on **seed + world
roster** only).

- `POST /scenarios/draft` — `{ seed, docsOverview?, storylineId? }`. Drafts a
  scenario → `{ title, genre, tone, goal, opening, castIds, settingId }`.
  - **Roster grounding, name→id resolution.** When `storylineId` is given, the
    agent builds a **numbered roster** of that world's real characters and settings
    (`crud.list_characters` / `list_settings`, capped at 40 each, ordered by
    position) and instructs the model to return character/place **names drawn only
    from the roster**. Names are resolved back to ids server-side via a
    case/whitespace-folded match: **unknown cast names are dropped**, an **unmatched
    setting falls back to `""`** (the soft-reference contract), and cast ids are
    de-duplicated in order. So `castIds`/`settingId` are **always** real members of
    the active world — never invented or dangling.
  - World grounding (primer/genre) is folded in the same way as the character and
    setting drafts (shared `agents/_common.world_context`).
  - Empty `seed` → `400 bad_request`; unconfigured LLM → `400 bad_request`; a reply
    that is not valid JSON → `502 upstream_error`.
  - Persists nothing — the draft fills the create form; the author reviews, then the
    normal `POST /storylines/{id}/scenarios` saves it.

- `POST /scenarios/scene-art-prompts` — `{ title?, genre?, tone?, goal?, opening?,
  settingName?, settingDesc?, notes? }`. Calls the LLM to produce a watercolor
  establishing-shot prompt pair for the scenario's setting atmosphere (no characters
  or people). Returns `{ positive, negative }` (`SceneArtPromptResponse`). At least
  one non-empty field required; unconfigured LLM → `400 bad_request`.

- `POST /scenarios/scene-art` — `{ positive, negative?, baseUrl?, workflow?, width?,
  height?, steps?, cfg? }`. Renders the scene-art image through the configured
  ComfyUI watercolor pipeline (landscape 16:9 default), converts to **WebP**, saves
  it under `MEDIA_DIR/scenes`, and returns `{ image: "/media/scenes/<uuid>.webp" }`.
  The URL is stored in the scenario's `image` field. Empty `positive` /
  unconfigured ComfyUI → `400 bad_request`; a Comfy failure → `502`. **Opt-in —
  spends GPU time on the local Comfy server.**

**`ScenarioRead` shape** — includes the three scene-art fields added alongside the
original draft fields:

```json
{
  "id": "9f8e",
  "title": "The Salt Ledger",
  "genre": "Intrigue",
  "tone": "Tension · rising",
  "goal": "Keep the ledger safe.",
  "opening": "Lamplight gutters over the wet dock.",
  "castIds": ["c_abc123"],
  "settingId": "s_def456",
  "branches": [],
  "image": "/media/scenes/abc123.webp",
  "sceneArtPositive": "misty harbor, lamplit cobblestones, watercolor",
  "sceneArtNegative": "people, text, anime, cartoon"
}
```

`image`, `sceneArtPositive`, and `sceneArtNegative` default to `null`; they are
populated when the author generates scene art in the Scenario Creator.

## NDJSON Event Stream

> **Status:** the event envelope (the types below + `internal_thought` + `StatPatch`, as a discriminated union) lives in `web/backend/app/events/envelope.py`. The **turn transport is implemented** (P1): `POST /play/{scenarioId}/turn` streams a validated, `seq`-monotonic event set (DB-authoritative `seq` via a `(session_id, seq)` unique constraint; persisted to the `events` table). Per-character generation, delta streaming, the Director, gated RAG, the cold-path turn-writer, and the read-time reflection interlude land in the later turn-loop phases (`docs/plans/turn-loop-runtime.md`).

The stream emits one JSON object per line. Every event shares a base envelope:

```json
{ "type": "string", "id": "string", "seq": 0, "scenarioId": "string", "sessionId": "string", "ts": "ISO-8601", "visibility": "public", "data": {} }
```

`visibility` ∈ `public | private_to_user | private_to_character | hidden` — some content is shown to the player, some only affects agent reasoning.

### Event types

Each maps to one frontend component.

| `type` | UI rendering | `data` highlights |
| --- | --- | --- |
| `narration` | Teal narrator card | `text` (may delta-stream), `done` |
| `character_dialogue` | Character chat bubble (speaker's avatar/color) | `characterId`, `text` (may delta-stream), `done` |
| `character_action` | Action / emote card | `characterId`, `text` |
| `internal_thought` | **Not rendered** — `visibility: hidden`, conditioning only | `characterId`, `text` (persisted, withheld from the stream) |
| `state_update` | Updates side panels (no chat message) | `patch` — partial scenario state; **stat changes ride here** |
| `branch_choices` | Branch-choices panel | `choices[]` (`label`, `outcome`) |

**No dice (D11):** `branch_choices` options carry `label` + `outcome` (a narrative-direction
tag) only — there is no `check` field. A branch is a narrative fork resolved by the player's
selection + the characters' in-character response, never a stat test.

**`internal_thought`** is the hidden think→speak conditioning block (the turn-loop plan
Step 5 / §7): persisted with `visibility: hidden` and **withheld from the client stream**
(it conditions the spoken line in the same context window; it is never shown).

**Stat changes** are carried on `state_update`:

```json
{ "type": "state_update", "data": { "stat": {
  "characterId": "kira", "key": "health", "delta": -25, "value": 55,
  "reason": "Struck by the falling beam." } } }
```

The validator confirms the stat exists and clamps `value` to `[min, max]`; the Stats panel re-renders and the narrator may reference the new state next turn. When bespoke rendering is wanted (an animating bar, a floating "+5 / −10"), promote stat changes to a dedicated `stat_update` event later — the data shape is the same.

Additional types to layer in later: `relationship_update`, `goal_update`, `turn_update`.

### Streaming modes

- **Full events** (one complete object) — used for `state_update`, `branch_choices`, and `character_action`. Easy to validate and render.
- **Delta streaming** — visible prose (`narration`, `character_dialogue`) is delta-streamed by emitting the **same event** (identical `id` + `seq`) repeatedly with an *incremental* `text` chunk and `done: false`, until the final chunk sets `done: true`. The client accumulates the chunks by `id` (`"".join` of the pieces == the full line); the **persisted** row holds the full text. This reuses the `done` field already on those payloads rather than a separate `message_start`/`message_delta`/`message_end` frame set. (`character_action` has no `done` field, so it streams as one full event.)

### Turn Stream (`POST /play/{scenarioId}/turn`)

The response **is** the stream — `application/x-ndjson`, one event per line, in `seq`
order — for the same `postNdjson`/`StreamingResponse` reasons as the build/triage streams.
Request body: `{ "text": "…", "directedAt": "ch_id" | null, "sessionId": "ps_…" | null,
"mode": "pov" | "narrator" }` (omit `sessionId` to open a new play session; the streamed
events carry the resolved `sessionId`; `mode` defaults to `pov`). Multiple speakers stream
**sequentially** in the Director's order — a later speaker reacts to its predecessor (the
hidden `internal_thought` of each is withheld from the stream and from later speakers). A
speaker may propose a stat change (a thin `state_update` block): the validator confirms the
stat exists, applies the **delta/value clamped to `[min,max]`** on the hot path (keeping the
`reason`), and emits a `state_update` event — an unknown stat is dropped. When the Director
flags a fork, a `branch_choices` event offers `label` + `outcome` options (no dice — D11);
stats inform which surface, never gate them. The player's input is persisted as a
`user_turn` event at `seq` 0 of the turn (not streamed back — the client already shows it
optimistically); the bot's events follow at the next seqs. A mid-stream failure is the terminal `{ "type": "error", "message": "…" }`
frame; pre-flight failures (unknown scenario, empty text, bad session) are a normal error
envelope before the 200 opens.

### Rules

- `seq` is monotonic per session (DB-authoritative: `max(seq)+1`, guarded by a
  `(session_id, seq)` unique constraint) so the client can detect gaps and reorder.
- Chunked/delta text sets `done: false` until the final chunk sets `done: true`.
- `internal_thought` (`visibility: hidden`) is persisted but never placed on the wire.
- The validator runs `parse → validate (incl. stat clamping) → repair/retry` before anything reaches the stream.

## Shared Contracts Location

TypeScript types for events and API payloads live in `web/shared/contracts/`. When an endpoint, event, or stat shape changes, update: the Pydantic schema, the shared contract type, and this document.
