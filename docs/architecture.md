# Velora — Architecture

## Application Mode

API + separate frontend (streaming-first). The Next.js frontend is the UI renderer; the FastAPI backend is the "brain" that runs the multi-agent system and streams events to the UI.

## Rendering Model

- App shell and interactive surfaces: Next.js App Router (client + SSR as appropriate).
- Live story content: pushed from the backend over SSE/WebSocket as an NDJSON event stream and rendered incrementally.
- Static/marketing surfaces (landing, docs): static/SSG where it fits.

## Frontend Stack

Next.js (App Router), React, TypeScript, Tailwind CSS, Framer Motion. Optional, adopted only when a real need appears: TanStack Query (server-state caching), TanStack Table (dense tables), React Hook Form + Zod (complex editors), Radix UI / shadcn-style copy-owned primitives (`web/frontend/components/ui/`).

## Backend Stack

FastAPI (Python 3.13, `uv`). Components:

- **Agent Orchestrator** (`app/services/`) — coordinates the agents per turn.
- **Event Engine** (`app/events/`, `app/services/`) — produces the NDJSON event stream.
- **Rules Engine** (`app/services/`) — enforces scene/world constraints.
- **Memory System** (`app/memory/`) — Postgres + Redis now; Vector DB + Neo4j seams for later.
- **Agents** (`app/agents/`) — Narrator, Character, Rules, Memory.
- **Core** (`app/core/`) — config, Postgres/Redis clients, provider-agnostic LLM interface.

## User Roles & Auth

| Role | Access |
| --- | --- |
| Public | Landing/marketing, sign-up, sign-in. |
| Authenticated user | Own characters, scenes, play sessions, memories. |
| Admin (future) | Moderation, global content management. |

Auth/session is **backend-owned** (token/session). The frontend stores credentials and guards protected routes; the backend is the source of truth and validates every request. The exact mechanism (e.g. JWT vs. session cookie, provider) is to be finalized before auth is built — tracked in `docs/checklist.md`.

## Frontend/Backend Boundary

- Frontend owns frontend routing and UX-level validation (Zod); backend owns API + streaming routes and authoritative validation (Pydantic, `app/schemas/`).
- Shared request/response and event types live in `web/shared/contracts/` and mirror `docs/api-contract.md`.
- Backend owns errors, retries, caching (Redis), and the streaming lifecycle; the frontend owns optimistic UI and reconnect behavior.

## Data Layer

- **PostgreSQL** — core state: users, characters, scenes, events, memories.
- **Redis** — live session state, pub/sub for streaming, and caching.
- **Vector DB** (planned) — semantic memory retrieval.
- **Neo4j** (planned, optional) — advanced knowledge graph relationships.

Build the Memory System behind an interface so vector/graph backends can be added without rewrites.

## AI Layer

LLMs via OpenAI or local models behind a provider-agnostic interface in `app/core/`. The multi-agent system composes Narrator + Character + Rules + Memory agents per turn.

## Streaming Layer

SSE or WebSockets carry an NDJSON event stream. Each event is a typed object (see `docs/api-contract.md`) — e.g. character turn, narrator beat, scene/state change, memory recall, error/heartbeat. The UI renders chat turns, narrator cards, side panels, and graph visualizations from these events.

## Key Decisions Log

- "Everything under `web/`" layout with root `app.py` backend entrypoint.
- `uv`-only Python tooling, Python 3.13.
- Vector DB + Neo4j deferred; design seams only.
- Provider-agnostic LLM interface from day one.
