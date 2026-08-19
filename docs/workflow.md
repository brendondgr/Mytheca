# Mytheca — Workflow

Commands, environment, validation gate, git rules.

## Environment

- **Python 3.13** (`.python-version`), managed by **`uv` only** — never pip/poetry/conda.
- **Node** for `web/frontend/`, managed by **npm**.
- **Ports:** backend API **3345** · frontend dev **3346** · Postgres **3347** · Redis **3348** · Neo4j Bolt **3349** / Browser **3350** · Qdrant REST **3351** / gRPC **3352**. Non-default ports so Mytheca coexists with anything already running.

### The launcher

`python app.py` starts **both** sides: it brings up Docker, runs backend preflight, waits for health, then starts `next dev`. Ctrl+C stops both.

| Command | Effect |
| --- | --- |
| `uv run python app.py` | Backend + frontend (default; also `all`, `both`) |
| `uv run python app.py backend` | Backend only (also `be`, `api`) |
| `uv run python app.py frontend` | Frontend only (also `fe`, `dev`, `web`, `ui`) |
| `uv run python app.py stop` | Kill running frontend/backend and exit (also `kill`, `down`); leaves containers up |

Every launch **forcibly frees its ports first** — anything still bound to 3345/3346 is terminated (SIGTERM, then SIGKILL), so a fresh start never dies on `EADDRINUSE`.

### Docker (owned by `app.py`)

You never run `docker compose` yourself. `ensure_docker_services()` verifies Docker + a live daemon, pulls the Postgres/Redis/Qdrant images when missing (`--ignore-buildable` skips the custom Neo4j service), builds the Neo4j image from `web/backend/docker/neo4j/Dockerfile`, and starts all four containers with `up -d --build --wait`.

Skip containers entirely with `MYTHECA_SKIP_DOCKER=1` or a `sqlite://` `DATABASE_URL`. Missing Docker prints guidance and continues — the preflight DB check is the real gate, so an external DB still works.

### Optional substrates

All three degrade to a no-op; CRUD and `pytest` run with none of them.

- **Neo4j (Story Graph)** — set `NEO4J_URI` (default `bolt://localhost:3349`) to enable; **blank disables**. Credentials default to `neo4j` / `mytheca-graph`. See `story-graph-neo4j.md`.
- **Qdrant (Hybrid RAG)** — `QDRANT_URL` (default `http://localhost:3351`); **blank disables**. Embeddings via fastembed `BAAI/bge-large-en-v1.5` (1024-dim, ONNX/CPU); set `EMBED_PROVIDER=hash` for the offline/test path (the test suite forces it). See `rag.md`.
- **ComfyUI (images)** — `COMFYUI_BASE_URL` (default `http://localhost:8199`); workflow JSON in `utils/workflows/`. See `comfyui-image-generation.md`.

### Runtime knobs worth knowing

- **`authoringConcurrency`** (Options › Language Models, seeded from `BUILD_MAX_CONCURRENCY`, default 3) bounds concurrent authoring drafts and RAG re-indexing. Set **1** for a single-slot llama.cpp, higher for a batching vLLM. Image generation is always sequential (single-GPU ComfyUI).
- **Reasoning budget** — the backend probes the configured LLM endpoint (`GET /version` → vLLM, `GET /props` → llama.cpp, then `GET /models` for a relay naming its upstream) and injects a per-call thinking-token budget. Never user-facing. `LLM_BACKEND_POLL_SECONDS` (30) re-probes; `LLM_BACKEND_CACHE_TTL_SECONDS` (60) caches. An endpoint matching no probe still gets **both** engine keys, so an unrecognized server (Ollama included) is capped rather than left to think without limit. `LLM_GEN_TIMEOUT_SECONDS` (300) bounds a generation's read window.
- **`TURN_BUFFER_SIZE`** (default 100) is the Redis recent-turn buffer. It must be ≥ the largest per-scene `context_beats` (max 100), or the scene asks for more history than the buffer retains.

### Migrations (Alembic)

Alembic (`web/backend/alembic/`, config `web/backend/alembic.ini`) is the versioned path for **non-additive** schema changes — dropped/renamed columns, type changes, new NOT NULL columns, indexes, constraints. 12 migrations exist today.

It **coexists** with `create_all` + an additive reconciler rather than replacing them: `create_all` builds missing tables, the reconciler self-heals new *nullable* columns, and the SQLite test path skips Alembic. On Postgres, preflight **stamps** an existing `create_all` schema to `head` on first run, then **upgrades to head** thereafter — best-effort, never blocking startup. The DB URL comes from `app.core.config`, so `alembic.ini` holds no secret.

After changing a model, run the "New migration" command below, review the generated script, and commit it.

### Secrets

Copy `.env.example` → `.env` (gitignored). Document every new variable in **both** `.env.example` and `deployment.md`.

## Commands

### Backend (Python / uv)

| Action | Command |
| --- | --- |
| Install deps | `uv sync` |
| Add a dependency | `uv add <pkg>` |
| Run the API | `uv run python app.py backend` |
| Tests | `uv run pytest` — in-memory SQLite, no Docker needed (826 cases) |
| New migration | `uv run alembic -c web/backend/alembic.ini revision --autogenerate -m "<msg>"` |
| Apply migrations | `uv run alembic -c web/backend/alembic.ini upgrade head` |
| Lint (recommended) | `uv run ruff check .` |
| Format (recommended) | `uv run ruff format .` |
| Type check (recommended) | `uv run mypy web/backend` |

**Dependency groups.** `dev` (pytest, ruff, mypy) and `research` (`pyyaml` — the
experiment manifest format; `matplotlib` — figure generators must emit `.svg` **and**
`.pdf`). Neither is in the runtime `dependencies` list; the backend is unaffected.
Install with `uv sync --group research` when working on `docs/research/`.

### Research record (`make`)

A root `Makefile` carries the research-record targets. It does **not** replace
`app.py`, which still owns Docker and both dev servers.

| Action | Command |
| --- | --- |
| Scaffold an experiment | `make new-experiment SLUG=<slug>` |
| Enforce the contract | `make validate-research` |
| Regenerate `INDEX.md` | `make research-index` |
| Regenerate figures | `make figures` |
| Tooling tests only | `make test` |

Contract: `research/AGENT_INSTRUCTIONS.md`. There is deliberately **no CI and no
pre-commit hook** — see `research/DECISIONS.md` D-005 and `checklist.md`.

### Frontend (Next.js)

Installed: **Next.js 16.2.9** (App Router, Turbopack) · React 19.2.4 · TypeScript 5 · **Tailwind CSS v4** (CSS-first `@theme`) · **Framer Motion 12** · **`react-force-graph-2d`** (lazy-loaded via `next/dynamic({ ssr:false })` for the story-player Graph view) · **Vitest 4 + React Testing Library** (tests co-located beside components). Fonts (Cinzel / EB Garamond / IBM Plex Mono) load via `next/font` in `app/layout.tsx`.

Run from `web/frontend/`:

| Action | Command |
| --- | --- |
| Install deps | `npm install` |
| Dev server | `npm run dev` |
| Build | `npm run build` |
| Tests | `npm test` (Vitest, run once) / `npm run test:watch` |
| Lint | `npm run lint` |
| Type check | `npm run typecheck` |

Theme-contrast gate, run from the repo root:

```bash
uv run python utils/scripts/check_contrast.py
```

It parses `web/frontend/styles/themes.css` and asserts the WCAG-AA token pairs across all three themes.

Stylesheet gate, also from the repo root:

```bash
node utils/scripts/check_frontend_css.mjs
```

It compiles `app/globals.css` (and therefore `themes.css` + `motion.css`) through the real
Tailwind v4 pipeline, then asserts that no custom property is defined in terms of itself and
that every `var(--dur-*/--ease-*/--lift-*)` motion token referenced actually exists.

**Use it whenever `npm run build` is unavailable.** `next build` is the normal gate, but
`next/font/google` fetches Cinzel / EB Garamond / IBM Plex Mono at build time and hard-fails
with no network — so in a sandbox or an offline worktree the build cannot validate CSS at all.
This script needs no network.

## Validation Gate (definition of "done")

Required:

- `uv run pytest` passes.
- Frontend tests pass (`npm test` in `web/frontend/`).
- **UI changes also require** an accessibility + responsive pass per `skills/accessibility-mobile/SKILL.md` and `skills/ada-compliance/SKILL.md`: keyboard operability, visible focus, AA contrast, live-region announcements for streamed content, and layout at 320 / 375 / 768 / 1024 px.
- **Theme-token changes also require** `check_contrast.py` to pass.
- **Stylesheet changes also require** `check_frontend_css.mjs` to pass (or a green
  `npm run build`, where the network allows one).
- **Any experiment, benchmark, baseline, ablation or evaluation run also requires**
  `make validate-research` to pass, with the run recorded under
  `research/experiments/`. Failed runs are recorded, not deleted.

Recommended hygiene: ruff + mypy (backend), ESLint + tsc (frontend).

If a check is skipped, say so and record why in `checklist.md`.

## Documentation Maintenance

Update docs in the same change that alters behavior:

| Change | Update |
| --- | --- |
| Top-level layout | `structure.md` |
| Frontend route | `routes.md` + `component-map.md` |
| API endpoint or event | `api-contract.md` + `data-flow.md` |
| Dependency, command, env var | `workflow.md` + `deployment.md` |
| Visual token / theme | `design-system.md` |
| Architecture decision or status | `documentation.md` + `architecture.md` |
| Anything deferred | `checklist.md` |
| An experiment or evaluation run | `research/experiments/<EXP-ID>/` + `research/CLAIMS.md` |

## Git Workflow

- Branch off `main`; don't commit feature work directly to `main` unless asked.
- **Commit per phase** — each completed plan phase ends with a local commit. No push or PR unless requested.
- Messages: `Mytheca — <area>: <what changed>`, or `[Plan Name] (n/total) Complete: <summary>` for plan phases.

## Supported Agent Tools

Claude Code (`.claude/skills/`), OpenAI Codex (`.agents/skills/`), Cursor (`.cursor/rules/`). All three hold **pointers only** — canonical instructions live in `docs/skills/`. Never duplicate instructions into agent folders.
