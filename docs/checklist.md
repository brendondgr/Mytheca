# Velora — Checklist

## Initialization (Definition of Done)

### Intake
- [x] Project goal, runtime, deliverables, target users, supported tools, validation workflow known.
- [x] Web architecture decisions captured (`docs/architecture.md`, `docs/routes.md`, `docs/data-flow.md`, `docs/api-contract.md`, `docs/design-system.md`).
- [x] Product/domain model captured from `docs/briefings/storyline-chat-briefing.md` (Storyline / Character / Setting / Scenario + Story Event + Stat system; five event types) and reflected across docs.
- [x] Visual design system locked to the `docs/CharacterFrontpage/` reference (Cinzel / EB Garamond / IBM Plex Mono; Parchment / Ember / Slate themes) in `docs/design-system.md`.

### Canonical docs
- [x] `docs/` exists with documentation, structure, workflow, checklist, architecture, routes, component-map, data-flow, deployment, design-system, api-contract.
- [x] `docs/plans/` exists.
- [x] `docs/skills/` exists with `global-project-rules` + all selected skills.
- [x] `docs/skills/global-project-rules/SKILL.md` names the required reading.
- [x] Supporting skill files preserved (`structures/`, `ui/`, `SETUP.md`, `planner.md`).

### Agent pointers
- [x] Claude Code (`.claude/skills/`), OpenAI Codex (`.agents/skills/`), Cursor (`.cursor/rules/`) pointer files created.
- [x] Each pointer references `docs/skills/global-project-rules/SKILL.md` + its canonical skill.
- [x] No agent folder holds the only copy of instructions.

### Project structure
- [x] Required top-level directories exist (`web/frontend`, `web/backend`, `web/shared`, `utils` (with `utils/tests` + `utils/scripts`), `libs`, `docs`).
- [x] Web code is under `web/`; root `app.py` is the backend entrypoint.
- [x] `pyproject.toml`, `.python-version`, `.env.example` exist.
- [x] `README.md` points to canonical docs.

### Cleanup
- [x] Selected starter skill dirs migrated into `docs/skills/` and removed.
- [x] Unselected starter material removed.
- [x] Initialization helpers (`initialize.md`, `read-yaml.py`) removed after migration.
- [x] No duplicate competing sources of truth.

### Verification
- [x] Final tree inspected after cleanup.
- [x] Canonical docs and representative pointer files checked.
- [x] Pointer targets verified to exist.
- [x] Validation commands run — frontend now runs `tsc` / `eslint` / `next build` / `vitest` (all green at scaffold). Backend `pytest` still N/A until backend code exists.

## Follow-up Work (next steps)

### Storyline creation modal — write-first pop-up (`feat/storyline-create-modal`; plan: `docs/plans/storyline-create-modal.md`)
Replaces the one-shot "Untitled Storyline" create with a write-first modal (done end-to-end). **Phase 1:** added a nullable `premise` (long `Text`) column to `Storyline` (model/schema/CRUD/seed) — 41 backend tests, ruff + mypy clean. **Phase 2:** the switcher's "New Storyline" now opens `StorylineModal` (title / genre / tagline + multi-paragraph **premise**); `useLibraryState.openCreateStoryline` + `submitStoryline` persist via `POST /storylines` then activate the world. Verified end-to-end via preview (create "Tidefall" → persisted with premise via API; modal a11y: `role=dialog`/`aria-modal`/labelled, focus-trapped, Esc closes). **Phase 3:** added the forward-looking **seams** — a drag-and-drop **context-files** drop zone + an agentic **"Draft with Velora"** panel, both visible but non-functional ("Coming soon"), in a two-column desktop rail that collapses to the mobile By-hand/Agentically toggle. 34 frontend tests green; a11y/responsive pass at 320/375/768/1024 (no overflow; desktop two-column 887px, mobile toggle swaps form ↔ seams).
- **Dev-DB gotcha:** the backend's idempotent `create_all` creates missing *tables* but does not ALTER existing ones, so the persistent Postgres dev DB needed a manual `ALTER TABLE storylines ADD COLUMN IF NOT EXISTS premise TEXT`. Reinforces the standing **Alembic** follow-up before the next schema change.
- **Deferred:** wire the seams (context-file ingest + agentic draft-into-fields); add storyline **edit/rename** (modal is create-only); mobile still can't reach "New Storyline" (switcher hidden `< md`).

### Storyline data layer — Postgres persistence + Library wiring (done; `feat/storyline-data-layer`)
Backend stood up end-to-end (plan: `docs/plans/storyline-data-layer.md`): core config/db/redis clients; SQLAlchemy models + camelCase Pydantic schemas for Storyline/Character/Setting/Scenario + the stat seam; CRUD routes under `/api` with the error envelope; per-storyline stat definitions + clamped character stat values; Embergate seed; `python app.py backend` preflight (docker compose up + checks + schema + seed) with `web/backend/docker-compose.yml` (Postgres on host **5544**); chat-scaffold `events`/`play_sessions` tables + NDJSON envelope types (no streaming). Frontend `lib/api.ts` client + `NEXT_PUBLIC_API_URL`; the **Library now reads/writes the backend** (await-then-apply, loading/error/Retry) and **persists** (verified end-to-end via preview: create → reload → survives; delete → gone). 38 backend tests + 33 frontend tests green.
- **Remaining:** populate `web/shared/contracts/` (currently the FE reuses `lib/types.ts` and BE owns Pydantic); wire the **Story player** to the backend; surface stats on the **scene pages**; author stat **guidance Markdown** + loader; introduce **Alembic** before the first non-additive schema change; add a `users`/auth owner column.

### Frontend — Embergate UI (built from `docs/CharacterFrontpage/`)
- [x] Library at `/` — header (wordmark/storyline/search/theme/create), recent-scenario carousel, ARIA tabs, character/setting/scenario/branch cards, create/edit/delete editors (By-hand + faked Agentic), character profile, begin-scene → `/play/[id]`.
- [x] **Library redesign — storyline-scoped, open columns** (`redesign/storyline-library`): prominent **storyline switcher** (outlined button, large Cinzel small-caps + ◆ seal + rotating chevron; active world + counts + "New Storyline") swapping the whole working set; body is three **open columns** (Scenarios · Characters · Settings) side-by-side on desktop, collapsing to the 3-tab section switcher on `< lg`; selecting a scenario lights up its cast and brings its setting forward ("◆ In this scene" cue + `aria-current`, not color alone) **and scrolls the active setting into view**. The page is **self-contained** (`h-dvh`, no page scroll) with **per-column scrolling** + **sticky column headers** on a **solid `bg-page`** so the radial glow never shows behind scrolling cards. The old standalone "Storylines"/branch entity removed (Branch type + `Scenario.branches` retained as sub-data). State refactored to storyline-scoped in `useLibraryState`. Verified: typecheck/lint/Vitest (29) + build green; a11y/responsive pass at 320/375/768/1024 (no page or horizontal overflow; per-column scroll + mobile collapse confirmed via preview).
  - **Deferred:** the storyline switcher is hidden `< md` (mobile can't switch storylines yet) — surface it on mobile when multi-storyline ships; "New Storyline" creates an empty storyline but there's no storyline rename/editor yet.
- [x] **Creation modal — side-by-side agentic layout** (`EntityModal`): on desktop (`md+`) the By-hand form and the Agentic draft panel show at once (form left, agentic chat in a fixed right rail); the mode toggle collapses to mobile-only (`< md`), still tab-switching one column at a time. UI structure only — verified at 375/1280 via preview (desktop form 533px + agentic rail 325px side-by-side, toggle hidden; mobile single-column toggle swap). **Deferred:** the agentic draft is still faked (`generate()` 850ms stub) and does not yet stream/build live into the form fields — that's the next functional step.
- [x] Story player at `/play/[scenarioId]` — three-zone scene: cast rail + turn order, transcript beats (narrator/dialogue/action/player/check/branch_choices), composer (send/roll/choose), director rail (goal/tension/state/relationships), ❖ loader.
- [x] Three themes (Parchment/Ember/Slate) with persistence; Cinzel/EB Garamond/IBM Plex Mono via `next/font`.
- [x] A11y/responsive pass: keyboard (tabs arrow-keys, modal focus-trap, menu/Esc), `:focus-visible`, polite live region on the transcript, `sr-only` page `<h1>`, and **no horizontal overflow at 320/375/768/1024**; reduced-motion via Framer `MotionConfig` + CSS `motion-reduce`.
- [ ] **Deferred:** rails → mobile drawers (currently hidden < lg, transcript stays primary); the 3D page-flip nav transition; a formal automated WCAG contrast audit (tokens designed for AA); wiring the **Story player** to the backend (the Library is now backend-backed and persists; the Story player still uses in-memory seed).



### Scaffolding (next step after init)
- [x] Scaffold the Next.js app in `web/frontend/` (`create-next-app`: TS, Tailwind, App Router) + add Framer Motion. **Done:** Next.js 16 (Turbopack) · React 19 · Tailwind v4 (CSS-first `@theme`) · Framer Motion 12. Fonts via `next/font` (Cinzel / EB Garamond / IBM Plex Mono). Test runner: **Vitest + React Testing Library**, tests co-located as `*.test.tsx`.
- [x] Scaffold the FastAPI app in `web/backend/app/` and wire root `app.py` to it (factory + routers + CORS + error envelope + preflight).
- [x] Add backend deps (declared in `pyproject.toml`; `uv sync`). No new deps were needed for the data layer.
- [x] Set up PostgreSQL + Redis connections in `app/core/` (`config.py`, `db.py`, `redis.py`).
- [x] Create initial DB models (storylines, characters, settings, scenarios, events/play_sessions, stat definitions, stat values). **Deferred:** a `users` table (no auth yet) and **migrations** (Alembic — using idempotent `create_all` for now).
- [ ] Add YAML config + Markdown stat-guidance loaders in `app/core/` (`app/content/`).

### Core domain & event system (next after scaffolding)
- [x] Lock the four core objects (Storyline / Character / Setting / Scenario) as Pydantic models + ORM (`app/models`, `app/schemas`). **Remaining:** move the shared types into `web/shared/contracts/` (FE currently reuses `lib/types.ts`).
- [~] Five-event NDJSON schema — the envelope **types** exist as a discriminated union (`app/events/envelope.py`); the validator (parse → validate → repair/retry) and the stream are not built yet.
- [ ] Stand up the NDJSON stream in full-event mode, then add delta streaming for visible messages.
- [~] Stat system — storyline stat schema, per-character values, and validator **clamping** are done at the data layer (`/api` stat endpoints). **Remaining:** the Stats panel UI (on scene pages) and `state_update`-carried stat changes (needs the stream).
- [ ] Author guidance files for the first handful of stats and wire them into agent context.
- [ ] Extend stats to relationship/mood values (same machinery, relational target).

### Architecture decisions to finalize
- [ ] Auth mechanism (JWT vs. session cookie; provider) — currently "backend-owned, TBD".
- [ ] SSE vs. WebSocket for the event stream (or both) — define before building the story player.
- [x] API base prefix (`/api`) and CORS origins (`FRONTEND_ORIGIN`) decided and wired in `app/main.py`.
- [ ] LLM provider interface shape (OpenAI + local).
- [ ] Stat lifecycle across scenarios (reset / persist / partial carry-over) and how hidden stats render.
- [ ] Deployment target (containerized vs. split hosting).

### Deferred capabilities (design seams only for now)
- [ ] Dice-based resolution (optional later layer: `check_request` → `roll_result` → `consequence` → `state_update`).
- [ ] Vector DB for semantic memory / cross-scenario character & setting memory.

### Quality gates to enforce once code exists
- [x] pytest in `utils/tests/backend/` (38 tests across `data/` + `api/`, on in-memory SQLite; ruff + mypy clean).
- [x] Frontend test runner chosen: **Vitest + React Testing Library**, tests **co-located** beside components (`web/frontend/**/*.test.tsx`). Playwright e2e still optional/later.
- [ ] Accessibility + responsive pass per `accessibility-mobile` + `ada-compliance`.

## Retained / Removed Setup Files
- Removed: `initialize.md`, `read-yaml.py`, and the starter skill directories (`accessibility-mobile/`, `ada-compliance/`, `plan/`, `repo-structure/`, `ui-frontend/`, `website-architecture/`) — all migrated into `docs/skills/`.
- Retained: `.gitignore`, `.python-version` (runtime config).
