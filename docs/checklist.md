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

### Storyline UI tweaks + draft-502 fix (done; `feat/storyline-ui-tweaks-draft-fix`; plan: `docs/plans/storyline-ui-tweaks-and-draft-fix.md`)
Three targeted fixes. **(1) Draft 502** — `POST /api/storylines/draft` returned `502 "empty response"` because the configured model (`gemma-4-26B`, a **reasoning model**) spent the whole `max_tokens=512` budget on `reasoning_content`, returning empty `content` (`finish_reason: length`). Fixes in `agents/storyline_agent.py` (`_gen_params` floors per-call `max_tokens` to **≥8192** for draft + primer, without touching the operator's saved Options value) and `services/llm.py` (`_send` accepts a per-call timeout; `chat_complete` now uses a **300s** read window vs. 20s for list/test so slow local/reasoning models can finish; an empty reply with `finish_reason: length` raises an actionable "raise Max tokens" error). 2 new agent tests; 82 backend tests green (ruff + mypy clean). **Validated live** against the running backend + LLM — drafts now return 200. **(2) Smooth scroll** — selecting a scenario glides the active Setting into view (`SettingColumn.tsx`: `scrollIntoView` `behavior:'smooth'`, falling back to instant under `prefers-reduced-motion`). **(3) 16:9 scene art** — the hero carousel's art panel went from a fixed 200px portrait placeholder to a true `aspect-[16/9] h-full` (~437px) frame shown at `lg+`, with overlay/dots offset `lg:right-[449px]`. 65 frontend tests + typecheck + lint + build green.
- **Deferred — live in-browser a11y/responsive pass (320/375/768/1024):** the working dir's dev server (port 3346, hardcoded `-p 3346` in `npm run dev`) was already running with a browser attached via the user's `python app.py`; a second Next/Turbopack dev server in the same dir would clash on `.next`. Verified via the green suite + build + computed geometry instead (same shared-dir constraint as prior entries). Run the in-browser pass once the dir is free: confirm the smooth scroll glides (and is instant under reduced-motion), and the 16:9 art frame renders without overflow at each width.



### ComfyUI image generation (done; `feat/comfyui-image-generation`; plan: `docs/plans/comfyui-image-generation.md`)
A server-side **ComfyUI** client + an Options surface to configure it. **Backend:** `services/comfyui.py` implements the full 7-step pipeline (status → load workflow → build_prompt patch → queue → WebSocket wait → history → download → `generate` orchestrator) with injectable `get_http_client`/`open_ws` factories (offline-tested); `comfyui_base_url` config + `COMFYUI_BASE_URL` env; `comfy` namespace in `settings_store` (baseUrl/workflow/params); routes `PATCH /options/comfy`, `GET /options/comfy/workflows`, `POST /options/comfy/status`, and `comfy` added to `GET /options`. New dep: `websocket-client`. **Frontend:** `ImageModelsTab` (base URL + Check status, workflow dropdown via `GET /options/comfy/workflows`, default params + negative prompt, Save) added as a dedicated **Image Generation** tab in `OptionsView`; `api.ts` comfy types/calls; `useOptionsSettings.saveComfy`. **Validation:** 80 backend tests (ruff + mypy clean) + 65 frontend tests (typecheck + lint + build clean). **Live end-to-end proven** against the running ComfyUI 0.25.0 — `generate(...)` rendered a real 1.7 MB PNG from `ZiT-Workflow.json` in ~19s (4-step watercolor).
- **Decision:** the Options tab's "test" is a **status check only** (no GPU spend in the UI); the full `generate` pipeline lives in the service for the story engine. HTTP reuses `httpx` (the guide's `requests` was intentionally not added — `httpx` already covers it).
- **Deferred — live in-browser a11y/responsive pass (320/375/768/1024):** verified structurally via the suite (native focusable controls, `aria-live` status, `role="alert"` errors, labelled section, global `:focus-visible`, existing AA tokens), consistent with the standing Options-tab constraint. Run the in-browser pass once the working dir + backend are free.
- **Deferred — image generation in the story engine:** wiring `generate(...)` into scene rendering (character portraits / scene art) waits on the streaming story engine; a `POST /options/comfy/generate` endpoint can be added when a UI consumer needs it.


### Storyline World Primer + agentic creation (done; `feat/storyline-world-primer`; plan: `docs/plans/storyline-world-primer.md`)
The **agent process of building a storyline** + the frontend to match it — the World Primer slice of `Documents/Plans/1.storyline-context-model.md`. **RAG is intentionally out of scope.**
- **Phase 1 — data layer:** `world_primer` (Text, nullable) on `Storyline` — agent-facing runtime context, distinct from the human-facing `premise`. Model column + Base/Update/Read schema fields + create-CRUD wiring + a sample primer on the Embergate seed + roundtrip/default-null tests. Docs: `api-contract` storyline shape gains `worldPrimer`.
- **Phase 2 — authoring agent:** `services/llm.chat_complete` (generic completion primitive); `agents/storyline_agent.py` with `draft_storyline` (seed → title/genre/tagline/premise via tolerant JSON extraction) and `generate_world_primer` (seed+premise → agent-facing primer); resolves endpoint/model/key from `settings_store`; clear `400` when the LLM is unconfigured. Routes `POST /storylines/draft` + `POST /storylines/primer`. 9 agent/endpoint tests via `httpx.MockTransport` (no network). Docs: `api-contract` Authoring endpoints + shapes, `data-flow` authoring flow.
- **Phase 3 — frontend:** `worldPrimer` on the `Storyline` type/`Draft`/`STORYLINE_DRAFT`; `lib/api` `draftStoryline`/`generateWorldPrimer`; `useLibraryState` `draftStoryline()`/`generatePrimer()` (independent spinners + error handling); `StorylineModal` live seed box + enabled "Draft with Velora", editable **World Primer** field + "Generate primer" action. Full draft→primer→persist flow tested through the real hook (api mocked).
- **Phase 4 — context-file grounding (non-persistent):** `lib/readDocs.ts` (read `.txt`/`.md` client-side, concat under per-file headers, cap at 8k chars); `StorylineModal` drop zone now reads dropped/selected files into `draft._docFiles` (removable chips) and passes them as `docsOverview` to draft/primer. **Files are never uploaded, persisted, or indexed.** Helper unit tests + a modal test asserting a dropped file's text reaches the generation call.
- **Validation:** 61 backend tests (ruff + mypy clean) + 61 frontend tests (typecheck + lint + build clean).
- **Dev-DB gotcha (now auto-handled for nullable columns):** idempotent `create_all` adds tables but not columns, so a persistent dev DB used to need a manual `ALTER` per new column. The preflight now **reconciles additive nullable columns automatically** (`bootstrap._reconcile_additive_columns` → `ADD COLUMN` for any nullable model column missing from an existing table), so `world_primer` self-healed on the live `backend-db-1` on first run (`migrate (optional): added columns: storylines.world_primer`). **Non-nullable** additions on a populated table are still *reported* (not auto-added) and need a manual `ALTER`/migration — the standing **Alembic** follow-up remains.
- **Deferred — live in-browser a11y/responsive pass (320/375/768/1024):** a concurrent agent session held the working dir with a *stale* shared backend + dev-DB (no `world_primer` column or authoring routes) that couldn't be restarted without disrupting it. a11y was verified structurally instead (global `:focus-visible` covers the new controls; modal scrolls internally via `max-h-[90vh] overflow-auto`; `role="alert"` errors with a `md:hidden` mobile echo to avoid double-announce; native focusable controls; existing AA tokens). Run the in-browser pass once the dir is free (apply the ALTER, restart the backend on this branch, then exercise draft/primer/file-drop at each width).
- **Deferred — the RAG system (next plan):** document **persistence, structure-aware chunking, dense (`fastembed`/`nomic`) + BM25 hybrid + RRF, automatic/agentic retrieval at runtime, `start` vs. `dynamic` inclusion tiers, contextual-retrieval prefixes, reranking, derived lore graph / `query_kg`**. Also deferred: **runtime injection** of the World Primer into conversations (waits on the story-player↔backend wiring — the player is still on in-memory seed).


### Options menu — settings store + LLM proxy + `/options` page (complete; plan: `docs/plans/options-menu.md`)
Backend Phase 1 of the Options menu (`[Options Menu] (1/3)`): a global `app_settings` key/value model (one row per namespace — `llm`, `library`; no auth yet so config is global) + camelCase schemas in `schemas/settings.py`; `services/settings_store.py` (get-or-create defaults seeded from process `Settings`, **write-only API key** stored server-side and never returned in clear — reads expose only `hasApiKey` + a masked `…AB12` hint); `services/llm.py` (server-side httpx proxy for `GET /models` + a tiny `POST /chat/completions` test, dodging browser CORS to local model servers; upstream non-2xx → `502 upstream_error`, network/timeout → `502 bad_gateway`). Routes live under the **`/options`** prefix (`routes/options.py`) — *not* `/settings`, since the Setting entity already owns that. 9 new backend tests (httpx `MockTransport`, no network); 49 backend total green; ruff + mypy clean. Docs updated: `api-contract.md` (Options group + shapes), `structure.md` (`app_settings`), `data-flow.md` (Settings Flow).
**Phase 2 (`[Options Menu] (2/3)`):** header **Options ▾** dropdown (`OptionsMenu` — Settings Menu link → `/options` + a label-free Appearance theme selector; theme moved out of `AppHeader`) and the **`/options`** route (`features/options/OptionsView` — centered 66%-width panel, vertical ARIA tablist with ↑/↓/Home/End, keyed-remount lazy-init tabs). Tabs: `AppearanceTab` (theme swatches), `LibraryDefaultsTab` (default storyline + startup, via `PATCH /options/library`), `AboutTab` (read-only diagnostics + `GET /health`, no secrets), and a Phase-2 `LanguageModelsTab` (base URL / API key / model / params → `PATCH /options/llm`). `useOptionsSettings` loads `GET /options`. `lib/api.ts` extended (+`getSettings`/`updateLlmConfig`/`updateLibraryDefaults`/`fetchLlmModels`/`testLlmConnection`/`getHealth`). 11 new frontend tests; 44 frontend total green; typecheck + lint + build clean.
**Phase 3 (`[Options Menu] (3/3)`):** the Language Models tab now **discovers models** (`POST /options/llm/models` — "Fetch models" button + on-blur of the base URL → a `<select>`, falling back to a text input when none are reported) and runs a **connection test** (`POST /options/llm/test` → OK + latency + sample, or a structured error). 47 frontend tests green; typecheck + lint + build clean.
- **Deferred:** live preview a11y/responsive pass was constrained by a concurrent session sharing the working dir, so this was built and validated in an **isolated git worktree** (`/home/bdgr/Agents/Velora-options` on `feat/options-menu`); structure/keyboard verified via the suite + an earlier preview snapshot — a final in-browser pass at 320/375/768/1024 should run once the working dir is free. Encryption-at-rest for the key + per-owner scoping deferred to the auth phase.

### Storyline seal — customizable symbol + color (`feat/storyline-seal-symbol`)
Each storyline gets a **seal** — a simple shape glyph (`symbol`) plus a hex `symbolColor` — shown left of its name. **Backend:** new `symbol` / `symbol_color` columns on `Storyline` (defaults `◆` / `#C8862A`), camelCase schema fields (Base/Update/Read), create-CRUD wiring, Embergate seed; 1 new API test (default + custom roundtrip + PATCH); 51 backend tests green, ruff + mypy clean. **Frontend:** `symbol?`/`symbolColor?` on the `Storyline` type, a tiny `lib/seals.ts` (8 shapes + gold-first color palette + defaults), a **seal picker** (preview chip + symbol grid + color swatches, mirroring `CharacterForm`'s accent picker) in `StorylineModal`, dynamic seal render in `StorylineMenu` (active button + each dropdown row, default-◆ fallback), and draft/submit wiring in `useLibraryState`/`editor.ts`. 54 frontend tests green; typecheck + lint + build clean.
- **Dev-DB gotcha (applied):** the persistent Postgres dev DB needed `ALTER TABLE storylines ADD COLUMN IF NOT EXISTS symbol TEXT DEFAULT '◆'; ADD COLUMN IF NOT EXISTS symbol_color TEXT DEFAULT '#C8862A';` — idempotent `create_all` adds missing tables but does **not** ALTER existing ones. This was run against `backend-db-1` (existing rows backfilled to the gold ◆ default). Reinforces the standing **Alembic** follow-up.
- **Live preview verified:** created a "Starfall" world with a teal ★ seal end-to-end — the picker live-preview updated, the switcher rendered the seal (button + dropdown rows), and the API persisted `symbol`/`symbolColor` (verified at desktop + tablet; the picker is `flex-wrap` so it can't overflow narrower widths). Test storyline cleaned up afterward.

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
