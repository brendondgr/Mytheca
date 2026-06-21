---
name: repository-structure
description: Use this skill when setting up, restructuring, documenting, or enforcing Velora's repository layout — the web/ split (Next.js frontend + FastAPI backend), root app.py entrypoint, shared contracts, utils/libs, and the docs/ source of truth.
---

# Velora Repository Structure Standard

This skill defines and enforces Velora's file layout. It is paired with `website-architecture` (which owns routes, stack, data flow, and the design-quality gate) and the `ui-frontend`, `accessibility-mobile`, and `ada-compliance` skills for the web surface.

`docs/` is the documentation source of truth. All runtime web code lives under `web/`. The repository was initialized with the **"everything under `web/`"** layout: a Next.js frontend and a FastAPI backend both under `web/`, with a thin root `app.py` that launches the backend.

## Canonical Tree

```text
velora/
├── app.py                  # Root entrypoint: imports & runs web/backend FastAPI app
├── pyproject.toml          # uv-managed Python project (backend, tooling)
├── .python-version         # 3.13
├── .env.example            # Documented environment variables
├── docs/                   # Source of truth (see global-project-rules)
│   ├── skills/             # Canonical skills used by all agent tools
│   ├── plans/              # Implementation & handoff plans (planner skill)
│   └── *.md                # documentation, structure, workflow, architecture, etc.
├── web/
│   ├── frontend/           # Next.js (App Router) + React + TS + Tailwind + Framer Motion
│   │   ├── app/            # Routes, layouts, route handlers
│   │   ├── components/
│   │   │   ├── ui/         # Reusable primitives
│   │   │   ├── layout/     # Chrome: nav, panels, shells
│   │   │   └── feature/    # Domain UI (narrator cards, scene view, etc.)
│   │   ├── features/       # Feature modules (story player, character editor, ...)
│   │   ├── hooks/          # Shared React hooks (e.g. event-stream consumer)
│   │   ├── lib/            # Frontend helpers, API client
│   │   ├── styles/         # Tailwind config target, global styles
│   │   └── public/         # Static assets
│   ├── backend/            # FastAPI app (the "brain")
│   │   └── app/
│   │       ├── routes/     # API + streaming (SSE/WebSocket) endpoints
│   │       ├── services/   # Orchestrator, event engine, rules engine
│   │       ├── agents/     # Narrator, Character, Rules, Memory agents
│   │       ├── memory/     # Memory system (Postgres/Redis now; vector/Neo4j later)
│   │       ├── events/     # Event/NDJSON stream definitions
│   │       ├── models/     # PostgreSQL models (users, characters, scenes, events)
│   │       ├── schemas/    # Pydantic request/response schemas
│   │       └── core/       # Config, db/redis clients, LLM provider interface
│   └── shared/
│       └── contracts/      # Shared types / OpenAPI / event schemas (FE↔BE)
├── utils/                  # Small standalone helpers
│   ├── tests/              # pytest, grouped by area
│   │   ├── backend/{api,agents,data}/
│   │   └── frontend/
│   └── scripts/            # Dev/build/ops scripts
└── libs/                   # Internal shared packages
```

## Ownership Rules

- Route/page UI → `web/frontend/app/` and `components/feature/` or `features/`.
- Reusable visual primitives → `web/frontend/components/ui/`.
- App chrome (nav, side panels, shells) → `web/frontend/components/layout/`.
- API + streaming endpoints → `web/backend/app/routes/`.
- Multi-agent logic → `web/backend/app/agents/`; orchestration glue → `app/services/`.
- DB models → `app/models/`; Pydantic contracts → `app/schemas/`; cross-layer contracts shared with the frontend → `web/shared/contracts/`.
- Memory/vector/graph code → `app/memory/` (keep seams for Vector DB + Neo4j without implementing them early).
- Design tokens and visual decisions → `docs/design-system.md`.

## General Rules

- Max file length 800 lines (ideal < 500). Outsource logic when files grow.
- Python sub-packages require `__init__.py`.
- `uv` is the only Python package manager (`uv add`, `uv sync`, `uv run`).
- Keep `docs/structure.md` updated whenever the tree changes — it is mandatory.

## Test Layout

Tests live under `utils/tests/` (alongside `utils/scripts/`). Keep them small and grouped by area (`utils/tests/backend/api/`, `utils/tests/backend/agents/`, `utils/tests/backend/data/`, `utils/tests/frontend/`). Prefer `utils/tests/<area>/test_<behavior>.py` over one flat folder.

## Reference Structures

Alternate layouts are documented in `structures/` for reference only — Velora uses the `web/` split above:

- [Web Interfaces](structures/web-interfaces.md)
- [LangGraph Structure](structures/langgraph.md)
- [Lab Reports](structures/lab-reports.md)
