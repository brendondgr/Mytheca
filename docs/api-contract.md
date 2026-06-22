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
| Storylines | `GET /storylines`, `POST /storylines`, `GET /storylines/{id}`, `PATCH /storylines/{id}`, `DELETE /storylines/{id}` | The world container; owns the baseline stat schema. Read/write shape: `id`, `title`, `genre`, `tagline` (one-line switcher descriptor), `premise` (nullable multi-paragraph world description). |
| Stat definitions | `GET /storylines/{id}/stats`, `POST /storylines/{id}/stats`, `PATCH /storylines/{id}/stats/{key}` | Baseline stat schema (range locked at creation). |
| Characters | `GET /storylines/{id}/characters`, `POST /storylines/{id}/characters`, `GET /characters/{id}`, `PATCH /characters/{id}`, `DELETE /characters/{id}` | Belong to a storyline; each holds a stat block. |
| Settings | `GET /storylines/{id}/settings`, `POST /storylines/{id}/settings`, `GET /settings/{id}`, `PATCH /settings/{id}`, `DELETE /settings/{id}` | Places within a storyline. |
| Scenarios | `GET /storylines/{id}/scenarios`, `POST /storylines/{id}/scenarios`, `GET /scenarios/{id}`, `PATCH /scenarios/{id}`, `DELETE /scenarios/{id}` | The live situations; may add/override stats. |
| Options | `GET /options`, `PATCH /options/llm`, `PATCH /options/library`, `POST /options/llm/models`, `POST /options/llm/test` | **Implemented.** Global settings (LLM endpoint + library defaults). Prefix is `/options` (the Setting entity owns `/settings`). |
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
  "appliesTo": ["character"]
}
```

`min`/`max`/`default` are **locked at creation**. The validator clamps every stat change to `[min, max]`. `visibility` ∈ `public | private_to_user | private_to_character | hidden`. A character holds values only: `{ "health": 80, "strength": 14 }`.

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
  "library": { "defaultStorylineId": "embergate", "openLastStoryline": true }
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
