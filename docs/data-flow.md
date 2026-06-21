# Velora — Data Flow

How data originates and moves through Velora. The streaming/event path is first-class.

## Sources

| Source | Examples | Where it lives |
| --- | --- | --- |
| PostgreSQL (core state) | users, characters, scenes, events, memories | `web/backend/app/models/` |
| Redis (live/cache) | active session state, stream pub/sub, cached reads | `web/backend/app/core/` (client), used by `services/`, `memory/` |
| LLM providers | model completions for agents | `web/backend/app/core/` (provider interface) → `app/agents/` |
| Client-only state | UI state, draft input, panel toggles | `web/frontend/` (React state) |
| Derived/cached | computed scene state, summaries | `app/services/`, cached in Redis |
| Vector DB (planned) | semantic memory retrieval | `app/memory/` (seam) |
| Neo4j (planned) | knowledge-graph relationships | `app/memory/` / `app/services/` (seam) |

## Read Path (e.g. open a scene)

1. Frontend route loads → calls `GET /scenes/{id}` (and related) via the `lib/` API client.
2. FastAPI route → service → Postgres model → Pydantic schema → JSON response.
3. Frontend renders; server-state caching via TanStack Query if/when adopted.

## Write Path (e.g. submit a turn)

1. User submits a turn in the Story Player → `POST /play/{sceneId}/turn`.
2. Backend validates (Pydantic), persists the user event (Postgres), updates live state (Redis).
3. The **Agent Orchestrator** runs the relevant agents (Rules → Character/Narrator → Memory), consulting the LLM provider and memory system.
4. Each produced beat is persisted (Postgres) and emitted to the **Event Engine**.

## Streaming Path (live story output)

1. The client opens `GET /stream/{sessionId}` (SSE or WebSocket).
2. The Event Engine publishes typed events as **NDJSON** (one JSON object per line) — character turn, narrator beat, scene/state change, memory recall, heartbeat, error.
3. Redis pub/sub fans events from the orchestrator to the active stream connection(s).
4. `useEventStream` parses each line and appends to the transcript; the UI renders chat turns, narrator cards, and side-panel updates incrementally.
5. Connection states (connecting, open, stalled, reconnecting, closed) are surfaced in the UI.

The event schema is shared via `web/shared/contracts/` and documented in `docs/api-contract.md`. Keep all three in sync.

## State Ownership

- Authoritative state: backend (Postgres) — validated server-side.
- Live/ephemeral state: Redis.
- UI/interaction state: frontend only.
- Never trust client-sent state as authoritative; always re-validate on the backend.
