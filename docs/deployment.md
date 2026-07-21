# Mytheca — Deployment

Deployment is not yet configured; this records the intended approach and required configuration. Update as infrastructure is chosen.

## Runtime Components

- **Backend:** FastAPI (ASGI) served by Uvicorn, started from root `app.py`.
- **Frontend:** Next.js app in `web/frontend/`.
- **Data:** PostgreSQL + Redis + **Neo4j** (the Story Graph substrate — a custom `neo4j:5.26-community` image with APOC, `web/backend/docker/neo4j/Dockerfile`) + **Qdrant** (the hybrid RAG vector store — standard `qdrant/qdrant` image, REST 3351 / gRPC 3352, volume `mytheca_qdrantdata`; best-effort, see `docs/rag.md`).

## Local Development

| Component | Command (run from) |
| --- | --- |
| Everything (dev) | `python app.py` (repo root) — backend (preflight + Uvicorn) **and** frontend together; waits for backend health, Ctrl+C stops both |
| Backend only | `python app.py backend` (repo root) — runs preflight, then Uvicorn |
| Frontend only | `python app.py frontend` (repo root) or `npm run dev` (`web/frontend/`) |
| Postgres + Redis + Neo4j + Qdrant | Automatic — `app.py` checks Docker, pulls/builds the images, and starts them. Manual fallback: `docker compose -f web/backend/docker-compose.yml up -d --build` |

### Docker bring-up (owned by `app.py`)

Container handling lives in **one place**: `app.py`'s `ensure_docker_services()`, which runs before the backend on both `python app.py` and `python app.py backend`. It:

1. verifies Docker is installed (CLI on PATH) **and** the daemon is responding (`docker info`),
2. downloads the Postgres + Redis images **only when missing** (`docker compose pull --ignore-buildable`, with visible first-run progress; `--ignore-buildable` skips the custom Neo4j service, which is built rather than pulled; image refs come from the compose file via `compose config --images`, so the tags aren't duplicated), and
3. **builds** the custom Neo4j image and starts the containers, blocking on their healthchecks (`docker compose up -d --build --wait`).

A pull/up failure aborts startup. Missing Docker or a stopped daemon prints actionable guidance and continues (the preflight DB check is the real gate, so external/embedded DBs still work). On `python app.py` the bring-up runs in the **parent** process — visible first-run download, and the spawned backend (passed `MYTHECA_SKIP_DOCKER=1`) doesn't repeat it or race the health-wait. Skip containers with a `sqlite://` `DATABASE_URL` or `MYTHECA_SKIP_DOCKER=1`.

### Backend startup preflight

After the containers are up, `python app.py backend` runs `app/core/bootstrap.run_preflight()` before serving. It:

1. waits for the database, pings Redis, and pings **Qdrant** (advisory — ensures the `mytheca_lore` collection),
2. ensures the schema (`Base.metadata.create_all`),
3. **reconciles additive columns** — `create_all` makes missing *tables* but never ALTERs existing ones, so a persistent dev DB drifts behind the models on every new column. The preflight self-heals the safe case (new **nullable** columns) with an idempotent `ADD COLUMN`; non-nullable additions on a populated table are *reported*, not attempted,
4. **applies Alembic migrations** (non-SQLite only) — the versioned path for non-additive schema changes. On a DB with no `alembic_version` table it **stamps** `head` (adopts the existing `create_all` schema without re-running the baseline); otherwise it **upgrades to head**. Best-effort: failures are logged + reported but never block startup. Skipped entirely under SQLite (the test/embedded path). See `docs/workflow.md` (Migrations) for the author-side commands, and
5. seeds the Embergate world if the database is empty.

It prints a pass/fail report; a failed **required** check (the database) aborts startup with remediation. Redis, the additive reconciliation, and the Alembic step are advisory. The schema/seed run here, **not** in the FastAPI lifespan (which only does a connection check), so Uvicorn `--reload` stays fast.

Postgres is published on host port **3347** (a dedicated port so Mytheca coexists with any Postgres already on 5432); Redis on **3348**; Neo4j Bolt on **3349** and the Neo4j Browser on **3350** (coexisting with any Neo4j on 7687/7474); **Qdrant REST on 3351 and gRPC on 3352**. The frontend dev server runs on **3346** and the backend API on **3345**. Tests run on in-memory SQLite and `QdrantClient(":memory:")` — no Docker, Postgres, Neo4j, or Qdrant server needed.

## Build

- Backend: `uv sync` to install; no compile step.
- Frontend: `npm run build` in `web/frontend/`.

## Environment Variables

Copy `.env.example` → `.env` (gitignored). Document every new variable here and in `.env.example`. Initial set:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `NEO4J_URI` | Story Graph (Neo4j) Bolt URL (default `bolt://localhost:3349`); **blank to disable the graph** (CRUD + tests run with no Neo4j) |
| `NEO4J_USER` | Neo4j username (default `neo4j`) |
| `NEO4J_PASSWORD` | Neo4j password (default `mytheca-graph`; matches `docker-compose` `NEO4J_AUTH`) |
| `LLM_PROVIDER` | `openai` or `local` |
| `OPENAI_API_KEY` | OpenAI key (if provider = openai) |
| `LOCAL_LLM_BASE_URL` | Base URL for a local model server (if provider = local) |
| `LLM_BACKEND_POLL_SECONDS` | How often the backend re-probes the LLM endpoint to detect the inference engine (vLLM / llama.cpp) for the reasoning budget (default `30`) |
| `LLM_BACKEND_CACHE_TTL_SECONDS` | How long an engine detection is cached before a re-probe (default `60`) |
| `COMFYUI_BASE_URL` | Base URL of the local ComfyUI server for image generation (default `http://localhost:8199`); workflows live in `utils/workflows/` |
| `APP_ENV` | `development` / `production` |
| `SECRET_KEY` | Session/token signing |
| `FRONTEND_ORIGIN` | Allowed CORS origin for the frontend |
| `NEXT_PUBLIC_API_URL` | Frontend → backend base URL (client-readable; see `web/frontend/.env.local.example`) |
| `EMBED_PROVIDER` | Embedding backend: `fastembed` (real, default) or `hash` (offline/test fallback — no model download) |
| `EMBED_MODEL` | Dense embedding model (default `BAAI/bge-large-en-v1.5`); downloads ~1.3 GB on first use, cached under `EMBED_CACHE_DIR` |
| `EMBED_DIM` | Vector dimension (default `1024`) |
| `EMBED_DEVICE` | Execution device: `cpu` (default) / `cuda` / `rocm` |
| `EMBED_CACHE_DIR` | ONNX model cache directory (defaults to fastembed's platform cache) |
| `QDRANT_URL` | Qdrant REST URL (default `http://localhost:3351`); **blank to disable** the vector store (CRUD + tests run without Qdrant) |
| `QDRANT_COLLECTION` | Qdrant collection name (default `mytheca_lore`) |

## Deployment Target

TBD. Options to evaluate: containerized full-stack (Docker Compose / a single host), or split hosting (frontend on a Next.js host, backend + datastores on a server/container platform). Record the decision here once made; if Docker is adopted, add `infra/` per the repository-structure reference.

## Pre-Deploy Checklist

- All env vars set in the target environment (no secrets in git).
- `uv run pytest` and frontend tests green.
- Accessibility + responsive pass for changed UI.
- `npm run build` succeeds.
- CORS origin and database/Redis URLs correct for the environment.
