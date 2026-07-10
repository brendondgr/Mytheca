# Velora — Repository Structure

`docs/` is the source of truth. All runtime web code lives under `web/`. The root `app.py` launches the FastAPI backend. Keep this file updated whenever the tree changes.

```text
velora/
├── CLAUDE.md                # Claude Code entry point — routing tables to docs/ and web/ files, avoids blind search
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
│   ├── api-contract.md     # API + NDJSON event contract
│   └── rag.md              # Hybrid RAG: pipeline, components, embedding, Qdrant, utilization
├── web/
│   ├── frontend/           # Live Next.js 16 app (App Router, Turbopack) + React 19 + TS + Tailwind v4 + Framer Motion
│   │   ├── app/            # Routes, layouts, route handlers (+ co-located *.test.tsx)
│   │   ├── components/{ui,layout,feature}/
│   │   ├── features/       # Feature modules (story player, library, options, documents)
│   │   ├── hooks/          # Shared hooks (event-stream consumer, etc.)
│   │   ├── lib/            # Frontend helpers, API client
│   │   ├── styles/         # Global styles / Tailwind target
│   │   ├── public/         # Static assets
│   │   ├── test/           # Vitest setup (jsdom, jest-dom)
│   │   └── *config*        # package.json, next.config.ts, tsconfig.json, vitest.config.ts, eslint/postcss configs
│   ├── backend/            # FastAPI "brain"
│   │   ├── docker/neo4j/   # Custom Neo4j 5.26 image (APOC) — the Story Graph substrate, built by app.py
│   │   ├── docker-compose.yml  # Postgres + Redis + Neo4j + Qdrant containers (started by app.py)
│   │   ├── alembic.ini     # Alembic config (no secret — DB URL injected at runtime from app.core.config)
│   │   ├── alembic/        # Migrations: env.py (→ Base.metadata + settings) + versions/ (baseline = current schema). Non-additive migration path; coexists with create_all/reconciler (preflight stamps/upgrades on Postgres, skips SQLite)
│   │   └── app/
│   │       ├── routes/     # API + NDJSON streaming endpoints — incl. play.py (POST /play/{id}/turn streams the turn); (+ graph: Story-Graph Type Registry + scenario subgraph)
│   │       ├── services/   # Turn loop: turn_engine (POV loop + delta streaming; persists the diagnostic trace), assembler (Band-1 context), retrieval_gate, emission (thin-tag parse), validator (stat clamp + presence), presence (scene-presence fold from the event log), events_store (seq/persist + session list/history/close), session_export (JSON/Markdown record), turn_writer (cold-path consequences); event engine; stat_guidance; stat_render (current-band + {Character} substitution into the character prompt); storyline_apply.py (agentic-edit diff guard + transactional validated writes + content-hash stale reconcile); media_cleanup; Story Graph: type_registry, graph_writer, graph_reader
│   │       ├── agents/     # LLM agents — authoring (storyline/character/setting/scenario, triage, shared _common); storyline_edit/ (scope.py — dynamic response schema + diff guard, core.py — shared converse engine, editor.py — existing-storyline agent, creation.py — blank/partial-draft agent) is the conversational, scope-aware agent that replaced build/extract; turn loop: character_turn_agent (think→speak), director_agent (who's-up + branches), narrator_agent (interstitials), planner_agent (ReAct beat planner); prompt_registry.py (single source of truth for the four writing agents' system prompts — PromptSpec + PROMPT_REGISTRY [7 keys] + resolve_prompts four-layer fold)
│   │       ├── content/    # Authored content — the built-in Story-Graph type catalogue (graph_registry.py) + per-stat Markdown guidance (stats/*.md, loaded by services/stat_guidance.py); YAML config later
│   │       ├── rag/        # Entry-based hybrid RAG: schema.py (LoreEntry) · serializer.py (prefix-fusion) · tokens.py (512-token guard) · entries.py (entity→entry adapters) · embedder.py (fastembed bge-large + HashEmbedder fallback) · store.py (Qdrant) · indexer.py (embed-on-save/delete hooks + reindex progress) · retriever.py (dense+BM25+RRF+pre-filter) · const.py
│   │       ├── memory/     # Live turn state (Redis, best-effort): buffer.py (recent-turn buffer); interior state + prefetch are later-phase seams
│   │       ├── events/     # Story-event envelope (6 types incl. internal_thought) + stream.py (build_event/to_ndjson_line/chunk_text)
│   │       ├── models/     # PostgreSQL models (storylines, characters, settings, scenarios, play_sessions, events, turn_traces, stats, app_settings, graph_type_definitions, context_documents, context_document_links)
│   │       ├── schemas/    # Pydantic request/response + event schemas (stat clamping, rag.py); storyline_edit.py (FieldScope/ScopeState, FieldChange, StatChange, StoryPlan, agent stream frames)
│   │       └── core/       # Config, db/redis/neo4j/qdrant.py clients, LLM provider interface, YAML/Markdown loaders
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
| `CLAUDE.md` | Auto-loaded by Claude Code at session start. Not a source of truth (`docs/` is) — a condensed routing index into it: which skill for which task, and concrete file paths per backend/frontend layer, so agents route directly instead of grepping. Keep in sync with this file and `docs/skills/global-project-rules/SKILL.md` when top-level layout changes. |
| `app.py` | Single root launcher: `python app.py` starts **both** the backend (preflight + uvicorn, `web/backend`) and the frontend dev server (`npm run dev` in `web/frontend`), waiting for backend health before the frontend and stopping both on Ctrl+C; `python app.py frontend` / `python app.py backend` run a single side; `python app.py stop` forcibly ends any running frontend/backend processes and exits. **Forcibly frees its ports** — every launch terminates whatever still holds 3345/3346 (a leftover `next dev` / uvicorn) via SIGTERM→SIGKILL before starting, so a fresh run never hits `EADDRINUSE` (`_free_port`/`_pids_on_port`/`_kill_pid`). **Owns Docker** — `ensure_docker_services()` verifies Docker + daemon, pulls the Postgres/Redis images when missing, **builds the custom Neo4j image** (`docker/neo4j/Dockerfile`), and starts all four containers (Postgres · Redis · Neo4j · **Qdrant**) before the backend (`up -d --build --wait`; you never run `docker compose` yourself). |
| `docs/` | All durable documentation and canonical skills — the source of truth. |
| `web/frontend/` | The Next.js UI: story player, narrator cards, character bubbles, stats/branch side panels. |
| `web/backend/` | The FastAPI brain: routes, multi-agent logic, the stat system, events, validation, persistence. |
| `web/shared/contracts/` | Types/contracts shared by both layers (events, API shapes). |
| `utils/` | Small standalone Python helpers; also holds `utils/tests/` and `utils/scripts/`. |
| `utils/tests/` | pytest + frontend tests, grouped by area. |
| `utils/scripts/` | Dev/build/ops scripts. |
| `utils/workflows/` | Saved ComfyUI workflow JSON (e.g. `ZiT-Workflow.json`) loaded by `services/comfyui.py` for image generation. |
| `media/` | Generated media (character portraits under `portraits/`, setting scene art under `scenes/`, all WebP), written by `services/portraits.py` / `services/scene_art.py` (shared WebP helpers in `services/media.py`) and served read-only at `/media`. Path is `MEDIA_DIR` (default `<repo>/media`); gitignored. |
| `libs/` | Internal shared packages that grow beyond a single helper. |

Agent-tool pointer folders (`.claude/`, `.agents/`, `.cursor/`) contain only pointers to `docs/skills/` and are intentionally not the source of truth.
