# Velora

Velora is an AI-driven, multi-character roleplay chat engine. Users build a **storyline** (the world) with its **characters**, **settings**, and **scenarios** (live situations), then play through scenes driven by a multi-agent backend (Orchestrator/Director, Narrator, and Character agents) with a State manager and a Validator. The AI emits small, validated **story events** that stream to the UI in real time, and a near-term **stat system** (bounded, guidance-driven numeric values) gives the world continuity and consequence.

## Documentation (source of truth)

All durable documentation lives in [`docs/`](docs/). Start here:

- [docs/documentation.md](docs/documentation.md) — purpose, stack, decisions, status
- [docs/structure.md](docs/structure.md) — repository layout
- [docs/workflow.md](docs/workflow.md) — commands, environment, validation, git
- [docs/architecture.md](docs/architecture.md) — modes, auth, boundary, data layer
- [docs/checklist.md](docs/checklist.md) — current status and next steps

Agents must read [docs/skills/global-project-rules/SKILL.md](docs/skills/global-project-rules/SKILL.md) first. Canonical skills live under [docs/skills/](docs/skills/); the `.claude/`, `.agents/`, and `.cursor/` folders contain only pointers to them.

## Stack

- **Frontend:** Next.js (App Router) · React · TypeScript · Tailwind CSS · Framer Motion — in `web/frontend/`
- **Backend:** FastAPI (Python 3.13, `uv`) — in `web/backend/`, launched from root `app.py`
- **Data:** PostgreSQL (core) · Redis (live scenario/cache) · Vector DB (deferred) — plus YAML config + Markdown stat guidance
- **AI:** LLMs via OpenAI or local, multi-agent · **Streaming:** SSE/WebSocket NDJSON event stream (5 event types)

## Layout

```
app.py            # root launcher → `python app.py` runs the frontend; `python app.py backend` runs the API
web/frontend/     # Next.js app
web/backend/      # FastAPI app (routes, agents, services, content, events, models)
web/shared/       # shared FE↔BE contracts
docs/             # documentation + canonical skills
utils/            # helpers + utils/tests (pytest + frontend) + utils/scripts
```

## Getting Started

The frontend (Library + Story player) is built. Run everything from the repo root through `app.py`:

```bash
python app.py             # frontend dev server (npm run dev) → http://localhost:3346  [default]
python app.py backend     # FastAPI API via uvicorn → http://127.0.0.1:3345  (after `uv sync`)
```

`python app.py` installs the frontend deps on first run. Equivalent direct commands:

```bash
cd web/frontend && npm install && npm run dev   # frontend
uv sync && uv run python app.py backend          # backend
uv run pytest                                    # backend tests
```

Copy `.env.example` to `.env` and fill in values before running.
