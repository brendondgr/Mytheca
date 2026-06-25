# Velora — Deployment

Deployment is not yet configured; this records the intended approach and required configuration. Update as infrastructure is chosen.

## Runtime Components

- **Backend:** FastAPI (ASGI) served by Uvicorn, started from root `app.py`.
- **Frontend:** Next.js app in `web/frontend/`.
- **Data:** PostgreSQL + Redis. A Vector DB (semantic memory) may be added in a later phase.

## Local Development

| Component | Command (run from) |
| --- | --- |
| Everything (dev) | `python app.py` (repo root) — backend (preflight + Uvicorn) **and** frontend together; waits for backend health, Ctrl+C stops both |
| Backend only | `python app.py backend` (repo root) — runs preflight, then Uvicorn |
| Frontend only | `python app.py frontend` (repo root) or `npm run dev` (`web/frontend/`) |
| Postgres + Redis | Automatic — `app.py` checks Docker, pulls the images, and starts them. Manual fallback: `docker compose -f web/backend/docker-compose.yml up -d` |

### Docker bring-up (owned by `app.py`)

Container handling lives in **one place**: `app.py`'s `ensure_docker_services()`, which runs before the backend on both `python app.py` and `python app.py backend`. It:

1. verifies Docker is installed (CLI on PATH) **and** the daemon is responding (`docker info`),
2. downloads the Postgres + Redis images **only when missing** (`docker compose pull`, with visible first-run progress; image refs come from the compose file via `compose config --images`, so the tags aren't duplicated), and
3. starts the containers and blocks on their healthchecks (`docker compose up -d --wait`).

A pull/up failure aborts startup. Missing Docker or a stopped daemon prints actionable guidance and continues (the preflight DB check is the real gate, so external/embedded DBs still work). On `python app.py` the bring-up runs in the **parent** process — visible first-run download, and the spawned backend (passed `VELORA_SKIP_DOCKER=1`) doesn't repeat it or race the health-wait. Skip containers with a `sqlite://` `DATABASE_URL` or `VELORA_SKIP_DOCKER=1`.

### Backend startup preflight

After the containers are up, `python app.py backend` runs `app/core/bootstrap.run_preflight()` before serving. It:

1. waits for the database and pings Redis,
2. ensures the schema (`Base.metadata.create_all`),
3. **reconciles additive columns** — `create_all` makes missing *tables* but never ALTERs existing ones, so a persistent dev DB drifts behind the models on every new column. The preflight self-heals the safe case (new **nullable** columns) with an idempotent `ADD COLUMN`; non-nullable additions on a populated table are *reported* for a real migration, not attempted (full migrations via Alembic remain the standing follow-up), and
4. seeds the Embergate world if the database is empty.

It prints a pass/fail report; a failed **required** check (the database) aborts startup with remediation. Redis and the migrate reconciliation are advisory. The schema/seed run here, **not** in the FastAPI lifespan (which only does a connection check), so Uvicorn `--reload` stays fast.

Postgres is published on host port **3347** (a dedicated port so Velora coexists with any Postgres already on 5432); Redis on **3348**. The frontend dev server runs on **3346** and the backend API on **3345**. Tests run on in-memory SQLite and need neither Docker nor Postgres.

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
| `COMFYUI_BASE_URL` | Base URL of the local ComfyUI server for image generation (default `http://localhost:8199`); workflows live in `utils/workflows/` |
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
