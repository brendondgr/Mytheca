# Velora — Project Documentation

## Purpose

Velora is an AI-driven interactive narrative engine. Users create characters and scenes and play through stories that are driven by a multi-agent AI backend. A Narrator agent advances the story, Character agents speak and act, a Rules agent enforces constraints, and a Memory agent tracks what has happened. Story output is streamed to the UI in real time as discrete events (chat turns, narrator cards, state updates).

**Core domain entities:** users, characters, scenes, events, memories.

## Tech Stack

| Layer | Choice |
| --- | --- |
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS, Framer Motion |
| Backend | FastAPI (Python 3.13, `uv`), launched from root `app.py` |
| Brain | Agent Orchestrator, Event Engine, Rules Engine, Memory System, KG Builder |
| Agents | Narrator, Character, Rules, Memory |
| Core data | PostgreSQL (users, characters, scenes, events) |
| Live/cache | Redis |
| Semantic memory | Vector DB — **planned (later)** |
| Advanced KG | Neo4j graph DB — **planned (later, optional)** |
| AI | LLMs via OpenAI or local models, behind a provider-agnostic interface |
| Streaming | SSE / WebSockets carrying an NDJSON event stream |
| UI renderer | Chat UI, narrator cards, side panels, graph visualizations |

## Architecture Summary

```
Frontend (Next.js/React/TS/Tailwind/Framer Motion)
        ↓  HTTP + SSE/WebSocket (NDJSON events)
Backend "Brain" (FastAPI): Orchestrator · Event Engine · Rules Engine · Memory · KG Builder
        ↓
Data: PostgreSQL (core) · Redis (live) · [Vector DB] · [Neo4j]  ← bracketed = planned
        ↓
AI: LLMs (OpenAI / local) · multi-agent (Narrator/Character/Rules/Memory)
```

The frontend and backend both live under `web/`; a thin root `app.py` runs the FastAPI backend. See `docs/architecture.md` for the route/auth/data-flow detail and `docs/structure.md` for the layout.

## Major Decisions

- **Repo layout:** "everything under `web/`" — `web/frontend` (Next.js) + `web/backend` (FastAPI) + `web/shared/contracts`. Root `app.py` is the backend entrypoint.
- **Python tooling:** `uv` only, Python 3.13.
- **Agent tools supported:** Claude Code, OpenAI Codex, Cursor. Canonical instructions live in `docs/skills/`; agent folders only point to them.
- **Git workflow:** commit per phase (no auto push/PR unless requested).
- **Validation gate:** pytest (backend) + frontend component/route tests; web/UI changes also require an accessibility + responsive pass.
- **Deferred capabilities:** Vector DB (semantic memory) and Neo4j (advanced KG) — designed for with seams, not yet implemented.

## Selected Skills

`global-project-rules` (mandatory), `repository-structure`, `website-architecture`, `ui-frontend`, `accessibility-mobile`, `ada-compliance`, `planner`. All under `docs/skills/`.

## Current Status

Repository initialized: docs, canonical skills, agent pointers, and a structural skeleton (directories + config stubs) are in place. Application code (Next.js app, FastAPI app, DB integration, agents) is **not yet implemented** — that is the next step. Open items are tracked in `docs/checklist.md`.
