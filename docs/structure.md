# Mytheca — Repository Structure

`docs/` is the source of truth. All runtime code lives under `web/`. The root `app.py` launches both sides. Update this file whenever the tree changes.

```text
mytheca/
├── app.py                  # Root launcher — backend + frontend; owns the Docker data stores
├── CLAUDE.md               # Claude Code entry point — routing tables into docs/ and web/
├── README.md
├── pyproject.toml          # uv-managed Python project (backend + tooling)
├── uv.lock                 # Fully pinned Python deps
├── .python-version         # 3.13
├── .env.example            # Every environment variable, documented
├── Makefile                # Research-record targets only — does NOT replace app.py
├── CONTRIBUTING.md         # Validation gate + how to run an experiment
├── line_counter.py         # Standalone LOC-counting utility (not part of the app)
├── images/                 # Brand kit — Basic.svg, Basic-Light.svg, DarkText.svg, LightText.svg
├── media/                  # Generated WebP output (portraits/, scenes/, moments/) — gitignored, served at /media
├── libs/                   # Internal shared packages — currently empty (.gitkeep)
├── docs/                   # Source of truth
│   ├── documentation.md    # Purpose, domain model, stack, status
│   ├── structure.md        # This file
│   ├── workflow.md         # Commands, environment, validation, git
│   ├── checklist.md        # Active work + genuinely-open follow-ups
│   ├── architecture.md     # Boundaries, data layer, decisions
│   ├── routes.md           # Frontend route map
│   ├── component-map.md    # Component ownership
│   ├── data-flow.md        # Data origins + the turn/streaming path
│   ├── deployment.md       # Build, run, env, deploy targets
│   ├── design-system.md    # Themes, tokens, UI states
│   ├── api-contract.md     # API + NDJSON event contract
│   ├── rag.md              # Hybrid RAG pipeline
│   ├── story-graph-neo4j.md    # Neo4j Story Graph
│   ├── comfyui-image-generation.md  # Image generation
│   ├── skills/             # Canonical skills, read by every agent tool
│   ├── plans/              # Active implementation & handoff plans (planner skill)
│   │   └── archive/        # Shipped-feature plans — historical provenance, not routing
│   ├── briefings/          # Original product briefing
│   ├── research/           # THE research record — see AGENT_INSTRUCTIONS.md
│   │   ├── experiments/    # The unit of record: one dir per experiment, fixed contract
│   │   ├── templates/      # Copied wholesale by `make new-experiment`
│   │   ├── figures/        # Publication-ready ONLY, promoted from experiments
│   │   ├── tables/ datasets/ paper/
│   │   └── mytheca-research-audit.md   # External audit (3 Aug 2026); ledger provenance
│   └── CharacterFrontpage/ # Locked-in visual reference mockups (HTML)
├── web/
│   ├── frontend/           # Next.js 16 app (App Router, Turbopack) + React 19 + TS + Tailwind v4
│   │   ├── app/            # 8 routes (see docs/routes.md) + root layout + fonts/ (self-hosted woff2 + OFL)
│   │   ├── components/{ui,layout,feature}/   # 24 / 6 / 74 components
│   │   ├── features/       # Route-level modules: story-player, library, options, documents
│   │   ├── hooks/          # 12: use-event-stream, use-focus-trap (shared by Modal + Drawer), use-media-query, use-coach-marks, use-model-health, use-scene-shortcuts, …
│   │   ├── lib/            # API client, types, events, theme, helpers (18 files)
│   │   ├── styles/         # themes.css — the only stylesheet besides app/globals.css
│   │   ├── public/         # Static assets
│   │   ├── test/           # Vitest setup (jsdom, jest-dom)
│   │   └── *config*        # package.json, next.config.ts, tsconfig.json, vitest.config.ts, eslint/postcss
│   ├── backend/            # FastAPI brain
│   │   ├── docker-compose.yml   # Postgres · Redis · Neo4j · Qdrant (started by app.py)
│   │   ├── docker/neo4j/   # Custom Neo4j 5.26 image (APOC)
│   │   ├── alembic.ini     # DB URL injected at runtime from app.core.config — no secret
│   │   ├── alembic/        # env.py + versions/ (20 migrations)
│   │   └── app/
│   │       ├── main.py     # App factory; every router mounted under /api; /media static mount
│   │       ├── routes/     # characters · context_documents · graph · options · play · rag
│   │       │               #   scenarios · settings · stats · storylines
│   │       ├── services/   # Turn loop, CRUD, graph, RAG glue, media, LLM transport (46 modules)
│   │       │   └── llm_providers/  # The provider seam: base contract + 4 adapters
│   │       │                       # (gemini splits its reply/frame reading into gemini_parse.py)
│   │       ├── agents/     # LLM agents — authoring + turn loop + prompt_registry + storyline_edit/
│   │       ├── content/    # graph_registry.py (type catalogue) + stats/*.md guidance
│   │       ├── rag/        # schema · serializer · tokens · entries · embedder · store · indexer
│   │       │               #   · retriever · const
│   │       ├── memory/     # buffer.py (Redis recent-turn buffer) · interior.py
│   │       ├── events/     # envelope.py (9 story events) · stream.py (NDJSON + trace/error frames)
│   │       ├── models/     # 13 SQLAlchemy tables
│   │       ├── schemas/    # Pydantic request/response + event schemas
│   │       └── core/       # config · db · redis · neo4j · qdrant · bootstrap · seed · errors · ids
│   └── shared/
│       └── contracts/      # Intended FE↔BE contract home — currently EMPTY (.gitkeep)
├── utils/
│   ├── tests/
│   │   ├── backend/{api,agents,services,rag,data}/  # pytest, grouped by area + conftest.py
│   │   ├── frontend/       # EMPTY (__init__.py only) — frontend tests are co-located
│   │   └── tools/          # Research-record tooling tests (validator, scaffolder, capture)
│   ├── scripts/            # check_contrast.py (WCAG-AA token gate)
│   │   └── research/       # new_experiment · validate_research · gen_index · record · run_scene · run_moment · run_live_turn_visibility
│   └── workflows/          # ZiT-Workflow.json — the ComfyUI workflow loaded by services/comfyui.py
├── .claude/                # Claude Code — skill pointers + launch.json + worktrees/
├── .agents/                # OpenAI Codex — skill pointers
└── .cursor/                # Cursor — rule pointers (.mdc)
```

## The turn loop, and which module owns what

`services/turn_engine.py` is the **orchestrator only** — it defines exactly
`validate_turn_inputs` and `run_turn`, and everything a turn actually does lives in a
sibling. Four plans in this program independently proposed a split with four different
module names; this is the one that shipped, and a new one must not be invented beside it.

| Module | Owns |
| --- | --- |
| `turn_engine.py` | `validate_turn_inputs` + `run_turn`. Orchestration and nothing else. |
| `freetext_turn.py` | **The other engine.** `sceneMode: "freetext"`: look up → checklist → write → grade → continue, producing ONE `scene_prose` event per turn. Shares `turn_setup` and `turn_finalize` with `turn_engine`; replaces everything between. |
| `freetext_context.py` | The free-text prompt: one cached prefix (contract, style, world, place, **the whole cast**) shared byte-for-byte by every call of a turn, with live stat values and the per-call instruction in the small tail. |
| `freetext_effects.py` | Consequences from a passage with no speaker: each block names its subject, resolved against the roster and never guessed. |
| `turn_setup.py` | `prepare_turn` — everything before the first beat. |
| `beat_runner.py` | Producing one decided beat: `narrator_interstitial`, `relationship_note`, `beat_or_skip`, `generate_speaker`, `silent_backstop`. |
| `beat_stream.py` | Emission → delta-streamed events, and the per-beat stops. |
| `turn_effects.py` | The consequences: `apply_declared_presence`, `apply_presence_change`, `apply_relationship_change`, `apply_stat_change`. |
| `turn_emit.py` | `Emitter`, `LiveSegment`, `Tracer`. |
| `direction_runtime.py` | What the direction still owes mid-turn (`attempted` → `confirm`). |
| `direction_check.py` | Whether the prose actually reached it — lexical, no LLM call. |
| `context_budget.py` | The model's context window and the block-quantised transcript depth. |
| `history_compaction.py` | What falls out of the window becomes a rolling summary; invalidated on rewind. |
| `turn_finalize.py` | Suggestions → graph write → reflection → recency. |
| `session_state.py` | The one owner of history mutation — truncate, copy, replay, rebuild. |
| `beat_rerun.py` | Re-roll a beat or a turn, keeping takes. |

Every module under `web/backend/app/` stays **under 800 lines**, enforced by
`utils/tests/backend/data/test_file_length_budget.py`.

## Two things that trip people up

1. **Frontend tests are co-located**, next to what they test (`Foo.tsx` → `Foo.test.tsx`) — 138 files, 1375 cases, across `app/`, `components/`, `features/`, `hooks/`, `lib/`. `utils/tests/frontend/` holds only an `__init__.py` and should be ignored.
2. **`web/shared/contracts/` is empty.** The live FE↔BE event and entity types are hand-written in `web/frontend/lib/events.ts` and `lib/types.ts`, kept in sync with `web/backend/app/events/envelope.py` by hand.

## Top-Level Path Purpose

| Path | Why it exists |
| --- | --- |
| `app.py` | Single launcher. `python app.py` runs backend + frontend; `… backend` / `… frontend` run one side; `… stop` (aliases `kill`, `down`) ends both. Frees ports 3345/3346 (SIGTERM→SIGKILL) before starting, and owns Docker via `ensure_docker_services()` — verify daemon → pull missing images → build the custom Neo4j image → `up -d --build --wait`. |
| `CLAUDE.md` | Auto-loaded routing index for Claude Code. Not a source of truth — keep it in sync with this file. |
| `docs/` | All durable documentation and the canonical skills. |
| `web/frontend/` | The Next.js UI: library, storyline creator, story player, options. |
| `web/backend/` | The FastAPI brain: routes, agents, services, events, persistence. |
| `utils/` | Standalone helpers: `tests/`, `scripts/`, `workflows/`. Research tooling lives in `scripts/research/`, its tests in `tests/tools/`. |
| `libs/` | Reserved for internal shared packages; empty today. |
| `media/` | Generated WebP portraits and scene art. Path is `MEDIA_DIR` (default `<repo>/media`); gitignored, served read-only at `/media`. |
| `images/` | Brand SVGs used by the README and the app header. |

Agent-tool folders (`.claude/`, `.agents/`, `.cursor/`) contain only pointers to `docs/skills/` and are deliberately not a source of truth.

**No LICENSE file exists.** Absent one, the code is all-rights-reserved by default — add one before any public release.
