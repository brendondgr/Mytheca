# Velora — Workflow

## Environment

- **Python:** 3.13 (`.python-version`). Manager: **`uv` only** (never pip/poetry/conda).
- **Node:** for `web/frontend/` (Next.js). Package manager: npm (unless changed in `web/frontend/package.json`).
- **Backend entrypoint:** root `app.py` runs the FastAPI app from `web/backend`.
- **Secrets:** copy `.env.example` → `.env` (gitignored). Document every new variable in `.env.example` and `docs/deployment.md`.

## Commands

> The frontend (`web/frontend/`) is scaffolded and these commands run today. Backend commands still depend on app code added in a later phase.

### Backend (Python / uv)

| Action | Command |
| --- | --- |
| Install deps | `uv sync` |
| Add a dependency | `uv add <pkg>` |
| Run the API (dev) | `uv run uvicorn app:app --reload` (or `uv run python app.py`) |
| Tests | `uv run pytest` |
| Lint (recommended) | `uv run ruff check .` |
| Format (recommended) | `uv run ruff format .` |
| Type check (recommended) | `uv run mypy web/backend` |

### Frontend (Next.js)

Installed stack: **Next.js 16** (App Router, Turbopack) · React 19 · TypeScript · **Tailwind CSS v4** (CSS-first `@theme`; Velora tokens surfaced as CSS variables) · **Framer Motion** · **Vitest + React Testing Library** (tests co-located beside components, e.g. `app/page.test.tsx`). The three brand fonts (Cinzel / EB Garamond / IBM Plex Mono) load via `next/font` in `app/layout.tsx`.

Run from `web/frontend/`:

| Action | Command |
| --- | --- |
| Install deps | `npm install` |
| Dev server | `npm run dev` |
| Build | `npm run build` |
| Tests | `npm test` (Vitest, run once) / `npm run test:watch` |
| Lint | `npm run lint` |
| Type check | `npm run typecheck` (`tsc --noEmit`) |

## Validation Gate (before "done")

Required:
- Backend: `uv run pytest` passes for affected areas.
- Frontend: component/route tests pass.
- **Web/UI changes also require** an accessibility + responsive pass per `docs/skills/accessibility-mobile/SKILL.md` and `docs/skills/ada-compliance/SKILL.md`: keyboard operability, visible focus, contrast (AA), live-region announcements for streamed content, and layout checks at 320 / 375 / 768 / 1024 px.

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
