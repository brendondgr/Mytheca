# Velora — API & Event Contract

The contract between the Next.js frontend and the FastAPI backend. Request/response schemas are owned by the backend (Pydantic, `web/backend/app/schemas/`); shared types and the event schema live in `web/shared/contracts/`. This document and those files must stay in sync. Endpoints below are **planned** (not yet implemented).

## Conventions

- Base path: `/api` (final prefix TBD during scaffolding).
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
| Characters | `GET /characters`, `POST /characters`, `GET /characters/{id}`, `PATCH /characters/{id}`, `DELETE /characters/{id}` | Owned by the user. |
| Scenes | `GET /scenes`, `POST /scenes`, `GET /scenes/{id}`, `PATCH /scenes/{id}`, `DELETE /scenes/{id}` | Owned by the user. |
| Play | `POST /play/{sceneId}/turn` | Submit a user turn; triggers the orchestrator. |
| Stream | `GET /stream/{sessionId}` (SSE) or WS `/ws/{sessionId}` | NDJSON event stream (see below). |
| Graph | `GET /graph/{sceneId}` | Relationship/KG data (Neo4j later). |
| Admin (future) | `GET /admin/*` | High-permission only. |

## NDJSON Event Stream

The stream emits one JSON object per line. Every event shares a base envelope:

```json
{ "type": "string", "id": "string", "seq": 0, "sessionId": "string", "ts": "ISO-8601", "data": {} }
```

Planned `type` values:

| `type` | Meaning | `data` highlights |
| --- | --- | --- |
| `turn.character` | A character agent speaks/acts | `characterId`, `text` (may stream in chunks), `done` |
| `turn.user` | Echo of the user's submitted turn | `text` |
| `beat.narrator` | Structured narrator beat | `kind` (scene-change/outcome/recall), `title`, `body` |
| `state.scene` | Scene/world state update | partial scene state |
| `memory.recall` | Memory surfaced this turn | `memoryId`, `summary` |
| `error` | Recoverable/terminal error | `code`, `message`, `fatal` |
| `heartbeat` | Keep-alive | — |

Rules:
- `seq` is monotonic per session so the client can detect gaps and reorder.
- Chunked text turns set `done: false` until the final chunk sets `done: true`.
- The client must handle reconnect (resume from last `seq` where possible) and stalled streams.

## Shared Contracts Location

TypeScript types for events and API payloads live in `web/shared/contracts/`. When an endpoint or event changes, update: the Pydantic schema, the shared contract type, and this document.
