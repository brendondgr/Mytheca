# Velora — Workflow

## Environment

- **Python:** 3.13 (`.python-version`). Manager: **`uv` only** (never pip/poetry/conda).
- **Node:** for `web/frontend/` (Next.js). Package manager: npm (unless changed in `web/frontend/package.json`).
- **Root launcher:** `python app.py` starts **both** the backend (preflight + uvicorn on 3345) and the frontend dev server (3346) together — it waits for the backend to report healthy before launching the frontend, and Ctrl+C stops both. `python app.py frontend` and `python app.py backend` run just one side. Every launch **forcibly frees its ports first** — any process still bound to 3345/3346 (typically a leftover `next dev` / uvicorn from a previous run) is terminated (SIGTERM, then SIGKILL) so a fresh start never dies on `EADDRINUSE`. `python app.py stop` (aliases: `kill`, `down`) does only that — ends any running frontend/backend processes and exits, leaving the Docker data containers up.
- **Docker is handled by `app.py`** (one place — you never run `docker compose` yourself). Every backend launch first verifies Docker is installed + its daemon is running, downloads the Postgres + Redis images (only when missing — visible progress on first run), **builds the custom Neo4j image** (`web/backend/docker/neo4j/Dockerfile`), and starts the containers in `web/backend/docker-compose.yml` (`up -d --build --wait`). Missing Docker / a stopped daemon prints actionable guidance; a `sqlite://` `DATABASE_URL` or `VELORA_SKIP_DOCKER=1` skips containers entirely (external/embedded DB).
- **Story Graph (Neo4j):** the substrate is **best-effort** — set `NEO4J_URI` (default `bolt://localhost:3349`, Browser on 3350) to enable it; leave it **blank to disable** the graph entirely (CRUD + `pytest` run with no Neo4j). `NEO4J_USER`/`NEO4J_PASSWORD` default to `neo4j`/`velora-graph`. See `docs/story-graph-neo4j.md`.
- **Hybrid RAG (Qdrant + embeddings):** the vector store is **best-effort** — the Qdrant container (owned by `app.py`, REST port **3351** / gRPC **3352**) starts alongside Postgres/Redis/Neo4j; leave `QDRANT_URL` **blank to disable** (CRUD + `pytest` run with no Qdrant). Embeddings use **fastembed** (`BAAI/bge-large-en-v1.5`, 1024-dim, ONNX/CPU by default; deps: `fastembed` + `qdrant-client`). Set `EMBED_PROVIDER=hash` for the offline/test path — a deterministic `HashEmbedder` (no model download; the test suite forces it). See `docs/rag.md` for the full pipeline.
- **Authoring parallelism:** the world build drafts characters/settings concurrently and a RAG re-index embeds entities concurrently, bounded by the user-facing **`authoringConcurrency`** setting (Options › Language Models; default seeded from `BUILD_MAX_CONCURRENCY`, default **3**). Set it to **1** for a single-slot llama.cpp, higher for a batching vLLM. Image generation always renders sequentially (single-GPU ComfyUI) regardless.
- **Reasoning budget (vLLM / llama.cpp):** the backend auto-detects the local inference engine of the configured LLM endpoint and sends a backend-controlled thinking-token budget per authoring operation (Triage = Low, world build + drafts = Medium; never user-facing). `LLM_BACKEND_POLL_SECONDS` (default 30) is how often a background task re-probes so it adapts to engine swaps; `LLM_BACKEND_CACHE_TTL_SECONDS` (default 60) is the detection cache lifetime. No effect on OpenAI / unknown endpoints. See `docs/api-contract.md` (Reasoning budget) + `docs/data-flow.md`.
- **Migrations (Alembic):** Alembic (`web/backend/alembic/`, config `web/backend/alembic.ini`) is the versioned-migration path for **non-additive** schema changes (dropped/renamed columns, type changes, new NOT NULL columns, indexes/constraints). It **coexists** with `create_all` + the additive reconciler rather than replacing them: `create_all` still builds missing tables and the reconciler still self-heals new nullable columns (and the SQLite test path uses `create_all` directly — Alembic is skipped there). On a real (Postgres) DB, preflight **stamps** an existing `create_all`-built schema to `head` on first run (adopting it without re-creating) and **upgrades to head** thereafter; the step is best-effort (logged + reported, never blocks startup). The DB URL is supplied at runtime from `app.core.config` — `alembic.ini` holds no secret. After changing a model, run the "New migration" command, review the script, commit it.
- **Secrets:** copy `.env.example` → `.env` (gitignored). Document every new variable in `.env.example` and `docs/deployment.md`.

## Commands

> The frontend (`web/frontend/`) is scaffolded and these commands run today. Backend commands still depend on app code added in a later phase.

### Backend (Python / uv)

| Action | Command |
| --- | --- |
| Install deps | `uv sync` |
| Add a dependency | `uv add <pkg>` |
| Start Postgres + Redis + Neo4j + Qdrant | Automatic — `python app.py` (or `… backend`) checks Docker, pulls/builds the images, and starts them. Manual fallback: `docker compose -f web/backend/docker-compose.yml up -d --build` |
| Run the API (dev) | `uv run python app.py backend` — ensures Docker + containers, runs preflight (check DB+Redis, create schema, reconcile, **Alembic stamp/upgrade**, seed), then Uvicorn |
| New migration | `uv run alembic -c web/backend/alembic.ini revision --autogenerate -m "<msg>"` — diffs the models against the configured DB and writes a versioned script under `web/backend/alembic/versions/` (review it before committing) |
| Apply migrations | `uv run alembic -c web/backend/alembic.ini upgrade head` — preflight also does this automatically on a non-SQLite DB; the DB URL comes from `app.core.config` (no secret in `alembic.ini`) |
| Tests | `uv run pytest` (in-memory SQLite — no Postgres/Docker needed; Alembic is skipped under SQLite) |
| Lint (recommended) | `uv run ruff check .` |
| Format (recommended) | `uv run ruff format .` |
| Type check (recommended) | `uv run mypy web/backend` |

### Frontend (Next.js)

Installed stack: **Next.js 16** (App Router, Turbopack) · React 19 · TypeScript · **Tailwind CSS v4** (CSS-first `@theme`; Velora tokens surfaced as CSS variables) · **Framer Motion** · **Vitest + React Testing Library** (tests co-located beside components, e.g. `app/page.test.tsx`). The three brand fonts (Cinzel / EB Garamond / IBM Plex Mono) load via `next/font` in `app/layout.tsx`.

Run from `web/frontend/` (or from the repo root with `python app.py frontend`):

| Action | Command |
| --- | --- |
| Install deps | `npm install` |
| Dev server | `npm run dev` |
| Build | `npm run build` |
| Tests | `npm test` (Vitest, run once) / `npm run test:watch` |
| Lint | `npm run lint` |
| Type check | `npm run typecheck` (`tsc --noEmit`) |
| Theme contrast gate | `uv run python utils/scripts/check_contrast.py` (from the repo root) — parses `styles/themes.css` and asserts the WCAG-AA token pairs for all three themes |

## Validation Gate (before "done")

Required:
- Backend: `uv run pytest` passes for affected areas.
- Frontend: component/route tests pass.
- **Web/UI changes also require** an accessibility + responsive pass per `docs/skills/accessibility-mobile/SKILL.md` and `docs/skills/ada-compliance/SKILL.md`: keyboard operability, visible focus, contrast (AA), live-region announcements for streamed content, and layout checks at 320 / 375 / 768 / 1024 px.
- **Theme-token changes also require** `uv run python utils/scripts/check_contrast.py` to pass (the WCAG-AA pair gate over `styles/themes.css`).

Recommended hygiene: ruff + mypy (backend), ESLint + tsc (frontend).

If a check is skipped, say so and record why in `docs/checklist.md`.

## Documentation Maintenance

Update docs in the same change that alters behavior (see `docs/skills/global-project-rules/SKILL.md` for the full map). At minimum: structure changes → `structure.md`; routes → `routes.md` + `component-map.md`; API/contract → `api-contract.md` + `data-flow.md`; deps/commands/env → this file + `architecture.md`/`deployment.md`; visual tokens → `design-system.md`; status/decisions → `documentation.md`.

## Git Workflow

- Branch off `main` for feature work; don't commit features directly to `main` unless asked.
- **Commit per phase:** each completed plan phase ends with a local commit. No automatic push or PR unless the user requests it.
- Messages: `Velora — <area>: <what changed>`, or for plan phases `[Plan Name] (n/total) Complete: <summary>`.

## Supported Agent Tools

Claude Code (`.claude/skills/`), OpenAI Codex (`.agents/skills/`), Cursor (`.cursor/rules/`). All pointer files reference `docs/skills/global-project-rules/SKILL.md` plus the relevant canonical skill. Do not duplicate instructions into agent folders.

## Handoff

Leave `docs/checklist.md` current, ensure docs reflect the change, and record any deferred work before ending a session.
