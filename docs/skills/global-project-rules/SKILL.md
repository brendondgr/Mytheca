---
name: global-project-rules
description: Read this skill first, before any other work in the Mytheca repository. It defines required reading, the tech stack, environment and runtime rules, documentation duties, the validation gate, and the definition of done for every AI agent and engineer.
---

# Mytheca — Global Project Rules

The universal skill every agent (Claude Code, OpenAI Codex, Cursor, or anything else) must read before making changes. **`docs/` is the single source of truth.** Agent folders (`.claude/`, `.agents/`, `.cursor/`) contain only pointers back to this file and the canonical skills under `docs/skills/`.

## What Mytheca Is

An AI-driven, multi-character roleplay chat engine. You author a world and its cast, then play through scenes where several AI characters talk to you and to each other while a Narrator sets the scene. The player can also speak *as* a cast member (POV mode).

The backend emits small, typed, validated story events; the frontend maps each type to a component. The model decides what happens, never how it looks.

**Core domain objects: Storyline · Character · Setting · Scenario**, plus the Story Event abstraction and the Stat system. There is **no user model and no authentication** — do not write code that assumes either.

## Required Reading Before Any Change

1. This file
2. `docs/documentation.md` — purpose, domain model, stack, status
3. `docs/structure.md` — repository layout and ownership
4. `docs/workflow.md` — commands, environment, validation, git
5. `docs/checklist.md` — genuinely-open work
6. The canonical skill(s) under `docs/skills/` relevant to the task

For any web/UI/API work, also read `docs/architecture.md`, `docs/routes.md`, `docs/data-flow.md`, `docs/api-contract.md`, `docs/design-system.md`, and the `accessibility-mobile` + `ada-compliance` skills.

## Tech Stack (authoritative)

- **Frontend** — Next.js 16 (App Router, Turbopack) · React 19 · TypeScript · Tailwind CSS v4 · Framer Motion 12 · `react-force-graph-2d`. Lives in `web/frontend/`. **Framer Motion is the animation library — GSAP is not installed and must not be introduced.**
- **Backend** — FastAPI, Python 3.13, `uv`, SQLAlchemy 2.0, Alembic. Lives in `web/backend/`, launched from the root `app.py`.
- **Agents** — the real set in `web/backend/app/agents/`: turn loop (`planner_agent`, `character_turn_agent`, `narrator_agent`, `intent_agent`, `director_agent`, `reflection_agent`, `relationship_agent`) and authoring (`storyline_agent`, `storyline_edit/`, `character_agent`, `setting_agent`, `scenario_agent`, `triage_agent`), plus `prompt_registry.py` and `_common.py`. There is no "Orchestrator", "Rules Engine" or "KG Builder" — do not reference components that don't exist. Memory is real but is not a single component: volatile per-turn state lives in `app/memory/` (Redis buffer + interior state) and durable episodic memory in `services/memory_store.py` (`character_memories`, canonical in Postgres).
- **Data** — PostgreSQL (15 tables, core state) · Redis (recent-turn buffer, interior state) · **Neo4j 5.26** (the Story Graph, implemented) · **Qdrant + fastembed** (hybrid RAG, implemented). The last three are **best-effort**: each degrades to a no-op, and CRUD plus the full test suite run with none of them.
- **AI** — a **provider seam** (`services/llm_providers/`) over one transport (`services/llm.py`). Four adapters: `openai-compatible` (OpenAI, vLLM, llama.cpp, LM Studio, DeepSeek, a relay), `anthropic`, `gemini`, `ollama`. Application code never branches on provider name — an adapter owns the URL, auth, body shape, reply parsing, usage accounting and model listing, and nothing else does. The active provider is a process global primed at startup.
- **Streaming** — NDJSON, streamed directly in the turn POST response. There is no separate `GET /stream` endpoint.

Do not add libraries speculatively. Every dependency needs a defined job and a record in `docs/architecture.md` and `docs/workflow.md`.

## Environment & Runtime Rules

- **Python** — `uv` only (`uv sync`, `uv add`, `uv run`). Never pip/poetry/conda. Python 3.13.
- **Node** — npm, under `web/frontend/`.
- **Launcher** — `python app.py` runs both sides; `… backend` / `… frontend` run one; `… stop` ends both. It owns Docker; never run `docker compose` yourself.
- **Secrets** — never commit real secrets. Copy `.env.example` → `.env`. Document every new variable in `.env.example` **and** `docs/deployment.md`.

## File & Code Guidelines

- Max file length 800 lines; aim under 500. Split oversized files into focused modules.
- Python sub-packages need `__init__.py`.
- Helpers go in `utils/` (`utils/scripts/` for standalone tools). There is no `libs/`.
- Frontend ownership: primitives in `components/ui/`, chrome in `components/layout/`, domain UI in `components/feature/`, route-level modules in `features/`, hooks in `hooks/`, helpers in `lib/`.
- **Backend tests** live in `utils/tests/backend/{api,agents,services,rag,data}/` as `test_<behavior>.py`.
- **Frontend tests are co-located** beside what they test (`Foo.tsx` → `Foo.test.tsx`). `utils/tests/frontend/` is empty and must stay that way.
- `web/shared/contracts/` is **empty**. The FE↔BE event contract is hand-mirrored in `web/frontend/lib/events.ts` and `lib/types.ts` against `web/backend/app/events/envelope.py`. Changing the envelope means updating the mirror in the same change.

## Documentation Maintenance (required)

Update docs in the same change that alters behavior:

| Change | Update |
| --- | --- |
| Top-level directory | `docs/structure.md` |
| Route or page | `docs/routes.md` + `docs/component-map.md` |
| API endpoint or event contract | `docs/api-contract.md` + `docs/data-flow.md` |
| Dependency, command, env var | `docs/workflow.md` + `docs/deployment.md` (+ `architecture.md`) |
| Visual token or theme | `docs/design-system.md` |
| Architecture decision or status | `docs/documentation.md` + `docs/architecture.md` |
| Deferred or blocked work | `docs/checklist.md` |
| **An experiment, benchmark, ablation or evaluation run** | `docs/research/experiments/<EXP-ID>/` + `docs/research/CLAIMS.md` — contract: `docs/research/AGENT_INSTRUCTIONS.md` |

Plans and handoffs go in `docs/plans/` using the `planner` skill format.

**Write documentation that will still be true next month.** Describe what the code does, not what a phase intended. If you remove or supersede something, delete the sentence that described it — do not leave it beside its replacement. The docs were rebuilt on 2026-08-04 precisely because per-phase prose accumulated without ever being reconciled.

## Validation Gate (definition of done)

- **Backend:** `uv run pytest` passes (2325 cases today).
- **Frontend:** `npm test` passes in `web/frontend/`.
- **UI changes also require** an accessibility + responsive pass per the `accessibility-mobile` and `ada-compliance` skills: keyboard operability, visible focus, AA contrast, live-region announcements for streamed content, and layout at 320 / 375 / 768 / 1024 px.
- **Theme-token changes also require** `uv run python utils/scripts/check_contrast.py`.
- **Experiment/evaluation runs also require** `make validate-research`. Never report
  a metric without writing it to the experiment's `manifest.yaml` and `RESULTS.md`;
  failed runs are recorded, not deleted.

Recommended hygiene: ruff + mypy (backend), ESLint + tsc (frontend).

If a check is skipped, say so explicitly and record why in `docs/checklist.md`.

## Git Workflow

- Branch off `main`; don't commit feature work directly to `main` unless asked.
- **Commit per phase.** No push or PR unless the user requests it.
- Messages: `Mytheca — <area>: <what changed>`, or `[Plan Name] (n/total) Complete: <summary>`.
- Delete worktrees and branches when their work merges. **Zero worktrees are outstanding** as of 2026-08-31 (`git worktree list` shows only the main checkout); the "eleven stale worktrees" this line used to warn about are gone. Keep it that way. Stale *branches* are a separate and much longer list — `git branch` shows ~60 — and are not covered by this rule.

## Cleanup & Sources of Truth

Never maintain two competing copies of an instruction. Canonical content lives under `docs/`; agent folders only point to it. Remove dead placeholders as the project matures.

## Completion Standard

A task is not done until the validation gate passes (or deferrals are documented), the relevant `docs/` files are updated in the same change, and remaining gaps are listed in `docs/checklist.md`.
