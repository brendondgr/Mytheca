# Velora — Repository Structure

`docs/` is the source of truth. All runtime web code lives under `web/`. The root `app.py` launches the FastAPI backend. Keep this file updated whenever the tree changes.

```text
velora/
├── app.py                  # Root entrypoint — imports & runs web/backend FastAPI app
├── pyproject.toml          # uv-managed Python project (backend + tooling)
├── .python-version         # 3.13
├── .env.example            # Documented environment variables
├── .gitignore
├── README.md
├── docs/                   # Source of truth
│   ├── skills/             # Canonical skills (read by every agent tool)
│   ├── plans/              # Implementation & handoff plans (planner skill)
│   ├── documentation.md    # Project purpose, stack, decisions, status
│   ├── structure.md        # This file
│   ├── workflow.md         # Commands, environment, validation, git
│   ├── checklist.md        # Active work + open follow-ups
│   ├── architecture.md     # Modes, auth, boundary, decisions
│   ├── routes.md           # Route map
│   ├── component-map.md    # Component ownership
│   ├── data-flow.md        # Data origins + the streaming/event path
│   ├── deployment.md       # Build, run, env, deploy targets
│   ├── design-system.md    # Visual motif, tokens, UI states
│   └── api-contract.md     # API + NDJSON event contract
├── web/
│   ├── frontend/           # Next.js (App Router) + React + TS + Tailwind + Framer Motion
│   │   ├── app/            # Routes, layouts, route handlers
│   │   ├── components/{ui,layout,feature}/
│   │   ├── features/       # Feature modules (story player, editors)
│   │   ├── hooks/          # Shared hooks (event-stream consumer, etc.)
│   │   ├── lib/            # Frontend helpers, API client
│   │   ├── styles/         # Global styles / Tailwind target
│   │   └── public/         # Static assets
│   ├── backend/            # FastAPI "brain"
│   │   └── app/
│   │       ├── routes/     # API + SSE/WebSocket endpoints
│   │       ├── services/   # Orchestrator, event engine, rules engine
│   │       ├── agents/     # Narrator, Character, Rules, Memory agents
│   │       ├── memory/     # Memory system (Postgres/Redis; vector/Neo4j later)
│   │       ├── events/     # Event / NDJSON stream definitions
│   │       ├── models/     # PostgreSQL models (users, characters, scenes, events)
│   │       ├── schemas/    # Pydantic request/response schemas
│   │       └── core/       # Config, db/redis clients, LLM provider interface
│   └── shared/
│       └── contracts/      # Shared FE↔BE types / OpenAPI / event schemas
├── tests/
│   ├── backend/{api,agents,data}/
│   └── frontend/
├── utils/                  # Small standalone helpers
├── libs/                   # Internal shared packages
└── scripts/                # Dev/build/ops scripts
```

## Top-Level Path Purpose

| Path | Why it exists |
| --- | --- |
| `app.py` | Single root entrypoint that runs the FastAPI backend (`web/backend`). |
| `docs/` | All durable documentation and canonical skills — the source of truth. |
| `web/frontend/` | The Next.js UI: story player, narrator cards, side panels, graph views. |
| `web/backend/` | The FastAPI brain: routes, multi-agent logic, rules, events, persistence. |
| `web/shared/contracts/` | Types/contracts shared by both layers (events, API shapes). |
| `tests/` | pytest + frontend tests, grouped by area. |
| `utils/` | Small standalone Python helpers. |
| `libs/` | Internal shared packages that grow beyond a single helper. |
| `scripts/` | Dev/build/ops scripts. |

Agent-tool pointer folders (`.claude/`, `.agents/`, `.cursor/`) contain only pointers to `docs/skills/` and are intentionally not the source of truth.
