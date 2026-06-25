# Velora — Data Flow

How data originates and moves through Velora. The streaming/event path is first-class.

> **Current implementation.** The **Library** is now backend-backed: it reads from and writes to the FastAPI CRUD API via `web/frontend/lib/api.ts` (hand-rolled fetch, await-then-apply), so storylines/characters/settings/scenarios **persist** in Postgres. The backend is seeded with the Embergate world (`web/backend/app/core/seed.py`) so the app looks the same. The **Story player** still runs on in-memory seed data (`web/frontend/features/story-player/scene-data.ts`) — the streaming path below is the planned design. (TanStack Query is still deferred; the hand-rolled client suffices for this CRUD surface.)

## Sources

| Source | Examples | Where it lives |
| --- | --- | --- |
| PostgreSQL (core state) | users, storylines, characters, settings, scenarios, events, stat definitions, stat values | `web/backend/app/models/` |
| Redis (live/cache) | active scenario state, stream pub/sub, cached reads | `web/backend/app/core/` (client), used by `services/` |
| YAML config | hand-authored storylines, characters, settings, stat definitions | loaded by `app/core/` → `services/` (State manager) |
| Markdown guidance | one file per stat (what raises/lowers it, bands, behavior) | `app/core/` loader → injected into agent context |
| LLM providers | model completions for agents | `web/backend/app/core/` (provider interface) → `app/agents/` |
| Client-only state | UI state, draft input, panel toggles, theme | `web/frontend/` (React state) |
| Derived/cached | computed scenario state, summaries | `app/services/`, cached in Redis |
| Vector DB (deferred) | semantic memory retrieval | `app/memory/` (seam) |

## Read Path (e.g. open a scenario)

1. Frontend route loads → calls `GET /scenarios/{id}` (and related storyline/characters/settings) via the `lib/` API client.
2. FastAPI route → service → Postgres model → Pydantic schema → JSON response.
3. Frontend renders; server-state caching via TanStack Query if/when adopted.

## Write Path (e.g. submit a turn)

1. User submits a turn in the Story Player → `POST /play/{scenarioId}/turn`.
2. Backend validates (Pydantic), persists the user event (Postgres), updates live scenario state (Redis).
3. The **Orchestrator/Director** runs the relevant agents (Character/Narrator) against the canonical scenario state, the current stat values, and the injected stat guidance files, consulting the LLM provider.
4. Each proposed event (and any implied stat change) is **validated and clamped**, persisted (Postgres), and emitted to the **Event Engine**.

## Streaming Path (live story output)

1. The client opens `GET /stream/{sessionId}` (SSE or WebSocket).
2. The Event Engine publishes typed events as **NDJSON** (one JSON object per line) — `narration`, `character_dialogue`, `character_action`, `state_update`, `branch_choices`.
3. Redis pub/sub fans events from the orchestrator to the active stream connection(s).
4. `useEventStream` parses each line and routes by `type`: visible messages render as deltas arrive (then finalize on `message_end`); `state_update` (incl. stat changes) updates the side panels without adding a chat message; `branch_choices` updates the branch panel.
5. Connection states (connecting, open, stalled, reconnecting, closed) are surfaced in the UI.

## Stat Change Flow

```
Director/character agent proposes a change (stat key, delta or value, reason)
  → emitted as a state_update event
  → Validator confirms the stat exists and clamps the result to [min, max]
  → event streamed to the UI
  → Stats panel updates; narrator may reference the new state next turn
```

The change carries a **reason**, giving a free audit trail ("Health −25: struck by the falling beam") useful for debugging the model and for showing the player *why* a number moved. Current stat values plus their guidance files feed back into agent context each turn, so a near-dead character fights weakly and a high-strength character can plausibly force a door.

The event schema is shared via `web/shared/contracts/` and documented in `docs/api-contract.md`. Keep all three in sync.

## Settings Flow (Options menu)

```
Options page (/options) → lib/api.ts → GET/PATCH /api/options
  → settings_store reads/writes the app_settings rows (one per namespace)
  → LLM tab: POST /api/options/llm/{models,test}
      → backend httpx proxy → {baseUrl}/models · {baseUrl}/chat/completions
      → result returned to the UI (CORS-free; API key stays server-side)
  → Image Generation tab: GET /api/options/comfy/workflows · POST /api/options/comfy/status
      → comfyui client → {baseUrl}/system_stats (status); the full generate
        pipeline (POST /prompt → WebSocket wait → /history → /view) is server-side
```

The LLM API key is **write-only**: stored in the `app_settings` row, never
returned to the browser (reads expose `hasApiKey` + a masked hint). Model listing
and the connection test run on the backend so they work against `localhost:*`
servers that don't send CORS headers, and so the key never reaches the client.
When the multi-agent brain lands it reads the same stored config.

## Storyline Authoring Flow (creation-time agent)

```
Create modal (StorylineModal) → lib/api.ts
  → POST /api/storylines/draft   {seed, docsOverview?}  → {title, genre, tagline, premise}
  → POST /api/storylines/primer  {premise, seed?, docsOverview?} → {worldPrimer}
      → routes/storylines → agents/storyline_agent
          → settings_store resolves the configured endpoint/model/key
          → services/llm.chat_complete → {baseUrl}/chat/completions
  → drafted fields + primer fill the form; author edits, then the normal
    POST/PATCH /api/storylines persists premise + worldPrimer
```

This is a **one-time, creation-time** generation, not a per-turn cost. There is
**no retrieval / RAG**: `docsOverview`, when present, is text read from dropped
reference files *in the browser* and passed inline for that one call only — the
files are never uploaded, persisted, or indexed (the corpus/RAG layer is a later
plan). The agent reuses the same stored LLM config as the Options menu.

## State Ownership

- Authoritative state: backend (Postgres) — validated server-side, stats clamped.
- Live/ephemeral state: Redis (active scenario).
- UI/interaction state: frontend only (panel toggles, theme, draft input).
- Never trust client-sent state as authoritative; always re-validate on the backend.
