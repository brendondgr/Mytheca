# Mytheca — Deployment

No production deployment is configured. This records how the app runs locally and every variable a target environment needs.

## Runtime Components

- **Backend** — FastAPI (ASGI) under Uvicorn, started from the root `app.py`.
- **Frontend** — Next.js 16 in `web/frontend/`.
- **Data** — PostgreSQL · Redis · **Neo4j 5.26** (custom APOC image, `web/backend/docker/neo4j/Dockerfile`) · **Qdrant** (stock `qdrant/qdrant`). All four are declared in `web/backend/docker-compose.yml` and started by `app.py`.

## Local Development

| Component | Command (from repo root) |
| --- | --- |
| Everything | `uv run python app.py` — backend + frontend, waits for health, Ctrl+C stops both |
| Backend only | `uv run python app.py backend` |
| Frontend only | `uv run python app.py frontend` (or `npm run dev` in `web/frontend/`) |
| Stop both | `uv run python app.py stop` (leaves containers running) |
| Containers | Automatic. Manual fallback: `docker compose -f web/backend/docker-compose.yml up -d --build` |

### Docker bring-up

`app.py`'s `ensure_docker_services()` runs before the backend on both `python app.py` and `python app.py backend`. It:

1. verifies the Docker CLI is on PATH **and** the daemon responds (`docker info`);
2. pulls images only when missing (`docker compose pull --ignore-buildable` — `--ignore-buildable` skips the custom Neo4j service, which is built rather than pulled; image refs come from `compose config --images`, so tags aren't duplicated);
3. builds the Neo4j image and starts all four containers, blocking on healthchecks (`up -d --build --wait`).

A pull/up failure aborts startup. Missing Docker or a stopped daemon prints guidance and continues — the preflight DB check is the real gate, so external DBs still work. On `python app.py` the bring-up runs in the **parent** process, and the spawned backend receives `MYTHECA_SKIP_DOCKER=1` so it doesn't repeat the work or race the health-wait.

### Backend preflight

`app/core/bootstrap.run_preflight()` runs before serving. It:

1. waits for the database, pings Redis, pings Qdrant (advisory — ensures the `mytheca_lore` collection);
2. ensures the schema (`Base.metadata.create_all`);
3. **reconciles additive columns** — `create_all` never ALTERs existing tables, so a persistent dev DB drifts behind the models. Preflight self-heals new **nullable** columns with an idempotent `ADD COLUMN`; non-nullable additions on a populated table are reported, not attempted;
4. **applies Alembic migrations** (non-SQLite only) — stamps `head` on a DB with no `alembic_version` table, otherwise upgrades to head. Best-effort: logged and reported, never blocking;
5. seeds the Embergate world if the database is empty.

A failed **required** check (the database) aborts with remediation. Redis, the reconciler, and Alembic are advisory. Schema and seed run here rather than in the FastAPI lifespan, so `uvicorn --reload` stays fast.

### Ports

Backend API **3345** · frontend **3346** · Postgres **3347** · Redis **3348** · Neo4j Bolt **3349** / Browser **3350** · Qdrant REST **3351** / gRPC **3352**. Tests run on in-memory SQLite and `QdrantClient(":memory:")` — no Docker, Postgres, Neo4j, or Qdrant server needed.

## Build

- Backend: `uv sync`; no compile step.
- Frontend: `npm run build` in `web/frontend/`.

## Environment Variables

Copy `.env.example` → `.env` (gitignored). This table is the complete set read by `web/backend/app/core/config.py`, plus the two vars read elsewhere. Document every new variable here **and** in `.env.example`.

### Runtime

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `development` / `production` |
| `SECRET_KEY` | `change-me` | Session/token signing — replace in any real environment |
| `FRONTEND_ORIGIN` | `http://localhost:3346` | Allowed CORS origin |
| `NEXT_PUBLIC_API_URL` | — | Frontend → backend base URL (read by Next.js, not by `Settings`) |
| `MYTHECA_SKIP_DOCKER` | unset | `1` skips the container bring-up (read directly by `app.py`) |

### Data stores

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://mytheca:mytheca@localhost:3347/mytheca` | Postgres DSN; a `sqlite://` URL also skips Docker |
| `REDIS_URL` | `redis://localhost:3348/0` | Redis DSN; blank disables the turn buffer |
| `NEO4J_URI` | `bolt://localhost:3349` | Story Graph Bolt URL; **blank disables the graph** |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `mytheca-graph` | Neo4j password (matches compose `NEO4J_AUTH`) |
| `QDRANT_URL` | `http://localhost:3351` | Qdrant REST URL; **blank disables the vector store** |
| `QDRANT_COLLECTION` | `mytheca_lore` | Qdrant collection name |

### Turn loop

| Variable | Default | Purpose |
| --- | --- | --- |
| `TURN_BUFFER_SIZE` | `160` | Redis recent-turn retention ceiling. Must exceed the largest per-scene `context_beats` (max 100) by at least `TURN_TRANSCRIPT_ANCHOR_BLOCK`, or the anchored window has no headroom |
| `TURN_TRANSCRIPT_ANCHOR_BLOCK` | `20` | How far the transcript window's **start** jumps when it moves. Holds the prompt-cache prefix still for `block` beats at a time; `1` restores the per-beat slide |
| `TURN_MAX_CONCURRENCY` | `4` | Bounds the off-hot-path worker pool (speech stays sequential) |
| `TURN_REFLECTION_ENABLED` | `true` | Toggles the read-time reflection interlude |
| `TURN_TTFT_SLO_MS` | `1200` | Informational time-to-first-token target for logging |
| `TURN_ASYNC_FINALIZE` | `false` | Runs reflection off the request thread; never used on SQLite |
| `TURN_MAX_BEATS` | `24` | Runaway backstop for the ReAct loop — the effective ceiling is `max(TURN_MAX_BEATS, 2·cast + 6)`, not a feature cap |
| `TURN_PLANNER_LOOKAHEAD` | `3` | How many beats the planner decides per call. `1` restores the original once-per-beat ReAct loop; higher trades planner calls for prediction, and the engine re-plans whenever a plan goes stale |
| `BUILD_MAX_CONCURRENCY` | `3` | Seeds the user-facing `authoringConcurrency` setting |

### AI + media

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `openai` | `openai` or `local` |
| `OPENAI_API_KEY` | `""` | OpenAI key when provider = openai |
| `LOCAL_LLM_BASE_URL` | `http://localhost:11434` | Local OpenAI-compatible endpoint. vLLM (`GET /version`), llama.cpp (`GET /props`), and relays naming their upstream in `GET /models` are auto-detected; anything else is capped with both engine budget keys rather than left uncapped |
| `LLM_BACKEND_POLL_SECONDS` | `30` | How often the engine probe re-runs |
| `LLM_BACKEND_CACHE_TTL_SECONDS` | `60` | Engine-detection cache lifetime |
| `LLM_GEN_TIMEOUT_SECONDS` | `300` | Read window for a generation call. On a streaming generation it bounds the gap *between* chunks, not the whole call |
| `LLM_DECISION_TIMEOUT_SECONDS` | `25` | Read window for the prose-free structural calls (intent, beat planner, direction packer, triage). Each falls back to a heuristic on timeout, so a stall degrades a turn instead of hanging it |
| `COMFYUI_BASE_URL` | `http://localhost:8199` | Local ComfyUI server; workflows in `utils/workflows/` |
| `MEDIA_DIR` | `<repo>/media` | Where generated WebP output is written; served at `/media` |

### Embeddings

| Variable | Default | Purpose |
| --- | --- | --- |
| `EMBED_PROVIDER` | `fastembed` | `fastembed` (real ONNX) or `hash` (offline/test, no download) |
| `EMBED_MODEL` | `BAAI/bge-large-en-v1.5` | Dense model; ~1.3 GB on first use |
| `EMBED_DIM` | `1024` | Vector dimension |
| `EMBED_DEVICE` | `cpu` | `cpu` / `cuda` / `rocm`; unavailable accelerators fall back to CPU |
| `EMBED_CACHE_DIR` | `""` | ONNX cache dir (defaults to fastembed's own) |

## Deployment Target

TBD. Options to evaluate: containerized full-stack (Docker Compose on one host) or split hosting (frontend on a Next.js host, backend + datastores on a container platform). Record the decision here once made.

## Pre-Deploy Checklist

- All env vars set in the target environment; no secrets in git; `SECRET_KEY` rotated off `change-me`.
- `uv run pytest` and frontend tests green.
- Accessibility + responsive pass for changed UI.
- `npm run build` succeeds.
- CORS origin and datastore URLs correct for the environment.
- **Add a LICENSE file** — the repository has none, so the code is all-rights-reserved by default.
