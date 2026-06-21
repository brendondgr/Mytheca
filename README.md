# Velora

Velora is an AI-driven interactive narrative engine. Users create characters and scenes and play through stories driven by a multi-agent AI backend (Narrator, Character, Rules, and Memory agents). Story output streams to the UI in real time as discrete events.

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
- **Data:** PostgreSQL (core) · Redis (live/cache) · Vector DB + Neo4j (planned)
- **AI:** LLMs via OpenAI or local, multi-agent · **Streaming:** SSE/WebSocket NDJSON event stream

## Layout

```
app.py            # root entrypoint → runs the FastAPI backend
web/frontend/     # Next.js app
web/backend/      # FastAPI app (routes, agents, services, memory, events, models)
web/shared/       # shared FE↔BE contracts
docs/             # documentation + canonical skills
utils/            # helpers + utils/tests (pytest + frontend) + utils/scripts
```

## Getting Started

> Application code is scaffolded in the next phase (see [docs/checklist.md](docs/checklist.md)). Intended commands:

Backend (from repo root):

```bash
uv sync
uv run uvicorn app:app --reload
uv run pytest
```

Frontend (from `web/frontend/`):

```bash
npm install
npm run dev
```

Copy `.env.example` to `.env` and fill in values before running.
