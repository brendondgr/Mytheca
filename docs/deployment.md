# Velora — Deployment

Deployment is not yet configured; this records the intended approach and required configuration. Update as infrastructure is chosen.

## Runtime Components

- **Backend:** FastAPI (ASGI) served by Uvicorn, started from root `app.py`.
- **Frontend:** Next.js app in `web/frontend/`.
- **Data:** PostgreSQL + Redis. A Vector DB (semantic memory) may be added in a later phase.

## Local Development

| Component | Command (run from) |
| --- | --- |
| Backend | `python app.py backend` (repo root) — runs preflight, then Uvicorn |
| Frontend | `python app.py` or `npm run dev` (`web/frontend/`) |
| Postgres + Redis | `docker compose -f web/backend/docker-compose.yml up -d` (or let preflight start them) |

### Backend startup preflight

`python app.py backend` runs `app/core/bootstrap.run_preflight()` before serving. It:

1. brings up Postgres + Redis via `web/backend/docker-compose.yml` (only if Docker is installed — otherwise it assumes externally managed services),
2. waits for the database and pings Redis,
3. ensures the schema (`Base.metadata.create_all`), and
4. seeds the Embergate world if the database is empty.

It prints a pass/fail report; a failed **required** check (the database) aborts startup with remediation. Redis is advisory. The schema/seed run here, **not** in the FastAPI lifespan (which only does a connection check), so Uvicorn `--reload` stays fast.

Postgres is published on host port **5544** (a dedicated port so Velora coexists with any Postgres already on 5432); Redis on 6379. Tests run on in-memory SQLite and need neither Docker nor Postgres.

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
| `NEXT_PUBLIC_API_URL` | Frontend → backend base URL (client-readable; see `web/frontend/.env.local.example`) |
| `VECTOR_DB_URL` | (later) semantic memory store |

## Deployment Target

TBD. Options to evaluate: containerized full-stack (Docker Compose / a single host), or split hosting (frontend on a Next.js host, backend + datastores on a server/container platform). Record the decision here once made; if Docker is adopted, add `infra/` per the repository-structure reference.

## Pre-Deploy Checklist

- All env vars set in the target environment (no secrets in git).
- `uv run pytest` and frontend tests green.
- Accessibility + responsive pass for changed UI.
- `npm run build` succeeds.
- CORS origin and database/Redis URLs correct for the environment.
