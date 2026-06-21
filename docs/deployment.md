# Velora — Deployment

Deployment is not yet configured; this records the intended approach and required configuration. Update as infrastructure is chosen.

## Runtime Components

- **Backend:** FastAPI (ASGI) served by Uvicorn, started from root `app.py`.
- **Frontend:** Next.js app in `web/frontend/`.
- **Data:** PostgreSQL + Redis. A Vector DB (semantic memory) may be added in a later phase.

## Local Development

| Component | Command (run from) |
| --- | --- |
| Backend | `uv run uvicorn app:app --reload` (repo root) |
| Frontend | `npm run dev` (`web/frontend/`) |
| Postgres + Redis | local install or containers (compose file TBD) |

## Build

- Backend: `uv sync` to install; no compile step.
- Frontend: `npm run build` in `web/frontend/`.

## Environment Variables

Copy `.env.example` → `.env` (gitignored). Document every new variable here and in `.env.example`. Initial set:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `LLM_PROVIDER` | `openai` or `local` |
| `OPENAI_API_KEY` | OpenAI key (if provider = openai) |
| `LOCAL_LLM_BASE_URL` | Base URL for a local model server (if provider = local) |
| `APP_ENV` | `development` / `production` |
| `SECRET_KEY` | Session/token signing |
| `FRONTEND_ORIGIN` | Allowed CORS origin for the frontend |
| `VECTOR_DB_URL` | (later) semantic memory store |

## Deployment Target

TBD. Options to evaluate: containerized full-stack (Docker Compose / a single host), or split hosting (frontend on a Next.js host, backend + datastores on a server/container platform). Record the decision here once made; if Docker is adopted, add `infra/` per the repository-structure reference.

## Pre-Deploy Checklist

- All env vars set in the target environment (no secrets in git).
- `uv run pytest` and frontend tests green.
- Accessibility + responsive pass for changed UI.
- `npm run build` succeeds.
- CORS origin and database/Redis URLs correct for the environment.
