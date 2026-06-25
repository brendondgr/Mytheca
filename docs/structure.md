# Velora — Repository Structure

`docs/` is the source of truth. All runtime web code lives under `web/`. The root `app.py` launches the FastAPI backend. Keep this file updated whenever the tree changes.

```text
velora/
├── app.py                  # Root launcher — `python app.py` → backend + frontend together; `python app.py frontend|backend` → one side
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
│   ├── frontend/           # Live Next.js 16 app (App Router, Turbopack) + React 19 + TS + Tailwind v4 + Framer Motion
│   │   ├── app/            # Routes, layouts, route handlers (+ co-located *.test.tsx)
│   │   ├── components/{ui,layout,feature}/
│   │   ├── features/       # Feature modules (story player, editors)
│   │   ├── hooks/          # Shared hooks (event-stream consumer, etc.)
│   │   ├── lib/            # Frontend helpers, API client
│   │   ├── styles/         # Global styles / Tailwind target
│   │   ├── public/         # Static assets
│   │   ├── test/           # Vitest setup (jsdom, jest-dom)
│   │   └── *config*        # package.json, next.config.ts, tsconfig.json, vitest.config.ts, eslint/postcss configs
│   ├── backend/            # FastAPI "brain"
│   │   └── app/
│   │       ├── routes/     # API + SSE/WebSocket endpoints
│   │       ├── services/   # Orchestrator/Director, event engine, state manager, validator
│   │       ├── agents/     # LLM agents — storyline_agent (creation-time draft + World Primer); Narrator + Character agents later
│   │       ├── content/    # Authored YAML config + Markdown stat guidance (per-stat files)
│   │       ├── memory/     # Memory seam (Postgres/Redis now; vector DB later)
│   │       ├── events/     # Event / NDJSON stream definitions (5 event types)
│   │       ├── models/     # PostgreSQL models (storylines, characters, settings, scenarios, events, stats, app_settings)
│   │       ├── schemas/    # Pydantic request/response + event schemas (stat clamping)
│   │       └── core/       # Config, db/redis clients, LLM provider interface, YAML/Markdown loaders
│   └── shared/
│       └── contracts/      # Shared FE↔BE types / OpenAPI / event schemas
├── utils/                  # Small standalone helpers
│   ├── tests/              # pytest + frontend tests, grouped by area
│   │   ├── backend/{api,agents,data}/
│   │   └── frontend/
│   └── scripts/            # Dev/build/ops scripts
├── libs/                   # Internal shared packages
└── docs/                   # (see above)
```

## Top-Level Path Purpose

| Path | Why it exists |
| --- | --- |
| `app.py` | Single root launcher: `python app.py` starts **both** the backend (preflight + uvicorn, `web/backend`) and the frontend dev server (`npm run dev` in `web/frontend`), waiting for backend health before the frontend and stopping both on Ctrl+C; `python app.py frontend` / `python app.py backend` run a single side. **Owns Docker** — `ensure_docker_services()` verifies Docker + daemon, pulls the Postgres/Redis images when missing, and starts the containers before the backend (you never run `docker compose` yourself). |
| `docs/` | All durable documentation and canonical skills — the source of truth. |
| `web/frontend/` | The Next.js UI: story player, narrator cards, character bubbles, stats/branch side panels. |
| `web/backend/` | The FastAPI brain: routes, multi-agent logic, the stat system, events, validation, persistence. |
| `web/shared/contracts/` | Types/contracts shared by both layers (events, API shapes). |
| `utils/` | Small standalone Python helpers; also holds `utils/tests/` and `utils/scripts/`. |
| `utils/tests/` | pytest + frontend tests, grouped by area. |
| `utils/scripts/` | Dev/build/ops scripts. |
| `utils/workflows/` | Saved ComfyUI workflow JSON (e.g. `ZiT-Workflow.json`) loaded by `services/comfyui.py` for image generation. |
| `media/` | Generated media (character portraits as WebP), written by `services/portraits.py` and served read-only at `/media`. Path is `MEDIA_DIR` (default `<repo>/media`); gitignored. |
| `libs/` | Internal shared packages that grow beyond a single helper. |

Agent-tool pointer folders (`.claude/`, `.agents/`, `.cursor/`) contain only pointers to `docs/skills/` and are intentionally not the source of truth.
