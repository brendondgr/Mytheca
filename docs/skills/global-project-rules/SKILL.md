---
name: global-project-rules
description: Read this skill first, before any other work in the Velora repository. It defines required reading, the tech stack, environment/runtime rules, documentation maintenance duties, validation gates, and the definition of done for every AI agent and engineer.
---

# Velora — Global Project Rules

This is the universal skill every agent (Claude Code, OpenAI Codex, Cursor, or any other tool) must read before making changes in this repository. `docs/` is the single source of truth. Agent-specific folders (`.claude/`, `.agents/`, `.cursor/`) contain only pointers back to this file and the canonical skills under `docs/skills/`.

## What Velora Is

Velora is an AI-driven interactive narrative engine. Users create and play through scenes with AI characters; a multi-agent backend (Narrator, Character, Rules, Memory agents) drives the story, and narrative output is streamed to the UI as events. Core domain entities: **users, characters, scenes, events, and memories**.

## Required Reading Before Any Change

1. `docs/skills/global-project-rules/SKILL.md` (this file)
2. `docs/documentation.md` — project purpose, stack, status
3. `docs/structure.md` — repository layout and ownership
4. `docs/workflow.md` — commands, environment, validation, git rules
5. `docs/checklist.md` — active work and open follow-ups
6. The canonical skill(s) under `docs/skills/` relevant to the task

For any web/UI/API work, also read:
- `docs/architecture.md`, `docs/routes.md`, `docs/data-flow.md`, `docs/api-contract.md`
- `docs/design-system.md` and `docs/skills/ui-frontend/ui/design-quality.md`
- `docs/skills/accessibility-mobile/SKILL.md` and `docs/skills/ada-compliance/SKILL.md`

## Tech Stack (authoritative)

- **Frontend:** Next.js (App Router) + React + TypeScript + Tailwind CSS + Framer Motion. Lives in `web/frontend/`.
- **Backend:** FastAPI (Python). Lives in `web/backend/`. Launched via the root `app.py`.
- **Multi-agent brain:** Agent Orchestrator, Event Engine, Rules Engine, Memory System, KG Builder. Narrator + Character + Rules + Memory agents.
- **Data layer:** PostgreSQL (core state: users, characters, scenes, events), Redis (live/cache state). Vector DB (semantic memory) and Neo4j graph DB (advanced knowledge graph) are planned for later phases — design with seams for them, do not implement until scheduled.
- **AI layer:** LLMs via OpenAI or local models, behind a provider-agnostic interface.
- **Streaming layer:** SSE / WebSockets carrying an NDJSON event stream to the UI renderer (chat UI, narrator cards, side panels, graph visualizations).

Do not add libraries speculatively. Every dependency must have a defined job and be recorded in `docs/architecture.md` (purpose) and `docs/workflow.md` (commands).

## Environment & Runtime Rules

- **Python:** use `uv` as the only package/environment manager. Python 3.13 (`.python-version`). Install: `uv sync`. Run a script/test: `uv run ...`. Add deps: `uv add ...`. Never use pip/poetry/conda directly.
- **Node/Frontend:** managed under `web/frontend/` with its own `package.json`. Use the package manager declared there (npm unless changed).
- **Backend entrypoint:** the root `app.py` imports and runs the FastAPI app from `web/backend`.
- **Secrets:** never commit real secrets. Copy `.env.example` to `.env` (gitignored). Document any new variable in `.env.example` and `docs/deployment.md`.

## File & Code Guidelines

- Max file length 800 lines; aim under 500. Favor modularity — split oversized files into focused modules.
- Python sub-packages need `__init__.py`.
- Small helpers go directly in `utils/`; larger ones get their own sub-folder. Shared internal packages go in `libs/`.
- Frontend ownership: primitives in `web/frontend/components/ui/`, chrome in `components/layout/`, domain UI in `components/feature/` or `features/`, hooks in `hooks/`, helpers in `lib/`.
- Shared frontend↔backend types/OpenAPI/contracts live in `web/shared/contracts/`.

## Documentation Maintenance (required)

Update docs in the same change that alters behavior:
- New/changed top-level dir → update `docs/structure.md`.
- New route/page → update `docs/routes.md` and `docs/component-map.md`.
- New/changed API endpoint or contract → update `docs/api-contract.md` and `docs/data-flow.md`.
- New dependency, command, or env var → update `docs/workflow.md` (+ `docs/architecture.md` / `docs/deployment.md`).
- Visual/design-token decisions → update `docs/design-system.md`.
- Stack/architecture decisions or status changes → update `docs/documentation.md`.
- Plans and handoffs live in `docs/plans/` using the `planner` skill format.

## Validation Gate (definition of "done")

Before marking work complete, run the applicable checks (see `docs/workflow.md` for exact commands):
- **Backend:** `pytest` (in `tests/backend/`) passes.
- **Frontend:** component/route tests pass.
- **Web/UI changes additionally require:** an accessibility + responsive pass per `docs/skills/accessibility-mobile/SKILL.md` and `docs/skills/ada-compliance/SKILL.md` (keyboard, focus, contrast, 320/375/768/1024 viewports). Document any intentionally deferred a11y item in `docs/checklist.md`.
- Recommended (not required) hygiene: `ruff` + `mypy` (backend), `tsc` + ESLint (frontend).

If a check is skipped, say so explicitly and record why in `docs/checklist.md`.

## Git Workflow

- Branch off `main`; do not commit directly to `main` for feature work unless the user asks.
- **Commit per phase**: each completed plan phase ends with a local commit. No automatic push or PR unless the user requests it.
- Commit messages: `Velora — <area>: <what changed>`; for plan phases use `[Plan Name] (n/total) Complete: <summary>`.

## Cleanup & Sources of Truth

Never maintain two competing copies of an instruction. Canonical content lives under `docs/`; agent folders only point to it. Remove dead placeholders and empty generated folders as the project matures.

## Completion Standard

A task is not done until the Validation Gate above passes (or deferrals are documented), the relevant `docs/` files are updated, and remaining gaps are listed in `docs/checklist.md`.
