# Velora — Route Map

Planned routes for the Next.js frontend. Routes are not yet implemented; this is the agreed map. Update it whenever a route is added or changed. For each route: path, purpose, auth, data, ownership, backend endpoints, and required UI states.

> Auth legend: **Public** (no session), **User** (authenticated), **Admin** (future high-permission).

## Frontend Routes

| Path | Purpose | Auth | Data dependencies | Primary ownership | Backend endpoints | States to design |
| --- | --- | --- | --- | --- | --- | --- |
| `/` | **The Library** (storyline home): a header **storyline switcher** (active world + "New Storyline"), recent-scenario carousel, and three **open columns** — Scenarios · Characters · Settings — side-by-side on desktop (collapsing to a 3-tab section switcher on mobile). Selecting a scenario features it, lights up its cast, and brings its setting forward. **Backend-backed CRUD** (persists). (A separate marketing landing is deferred — `/` currently serves the Library.) | Public* | Postgres via `lib/api.ts` | `app/page.tsx` → `features/library/LibraryView` → `features/library/useLibraryState` (+ `LibraryColumns`) | `GET /storylines` (+ per-storyline characters/settings/scenarios), `POST`/`PATCH`/`DELETE` for each | loading, error (banner + Retry), empty (no-scenario storyline), mobile |
| `/sign-in`, `/sign-up` | Auth | Public | — | `app/(auth)/...` | `POST /auth/*` | loading, error, success |
| `/library` | The Library: user's storylines (and recent scenarios) | User | Postgres (storylines, scenarios) | `app/(app)/library` | `GET /storylines`, `GET /scenarios` | loading, empty, error, permission, mobile |
| `/storylines/[id]` | Storyline home — tabs for Characters · Settings · Scenarios · Storyline branches; owns the stat schema | User | Postgres | `features/storylines` | `GET /storylines/{id}` (+ characters/settings/scenarios/stats) | loading, empty, error, partial-data, permission, mobile |
| `/storylines/[id]/characters/[charId]` | Character editor (personality, goals, secrets, **stat block**) | User | Postgres | `features/characters` + `components/feature` | `GET/PATCH /characters/{id}` | loading, error, partial-data, success, permission |
| `/storylines/[id]/settings/[settingId]` | Setting editor (place, atmosphere, state) | User | Postgres | `features/settings` | `GET/PATCH /settings/{id}` | loading, error, success, permission |
| `/storylines/[id]/scenarios/[scenarioId]/edit` | Scenario setup (cast, setting, goals, scenario-specific stats) | User | Postgres | `features/scenarios` | `GET/PATCH /scenarios/{id}` | loading, error, success, permission |
| `/play/[scenarioId]` | **Story player** — three-zone live scene (implemented now with client seed data: scripted Embergate transcript, local send/roll/choose; streaming/auth later) | User* | Seed now (Postgres + Redis + event stream later) | `app/play/[scenarioId]/page.tsx` → `features/story-player/StoryPlayerView` + `components/feature` (transcript beats, rails) | (later) `POST /play/{scenarioId}/turn`, `GET /stream/{sessionId}` | loading (scene loader), success, reduced-motion (mobile drawers + streaming/reconnect later) |
| `/options` | **Options menu** (full-screen settings). A centered panel (66% width on desktop) with a **vertical tab list on the left** and the active tab's content on the right. Tabs: **Language Models** (OpenAI-compatible endpoint: base URL → fetch `/models` → pick model → edit params → connection test), **Appearance** (theme), **Library defaults** (default storyline / startup), **About/Diagnostics** (version, backend health, provider, API base — no secrets). Reached from the header **Options ▾** dropdown (Settings Menu → here; plus a quick Appearance theme selector). **Implemented** (backend-backed). | Public* | Postgres via `lib/api.ts` (`/options`) | `app/options/page.tsx` → `features/options/OptionsView` → `useOptionsSettings` (+ `tabs/*`) | `GET /options`, `PATCH /options/llm`, `PATCH /options/library`, `POST /options/llm/{models,test}` | loading, error (banner + Retry), success, mobile (tabs collapse to a horizontal scroller) |
| `/settings` | Account & preferences (incl. theme) | User | Postgres | `app/(app)/settings` | `GET/PATCH /me` | loading, error, success |
| `/admin/*` | Moderation/management (future) | Admin | Postgres | `app/(admin)` | `GET /admin/*` | permission, empty, error |

## Notes

- **Current implementation:** `/` serves the Library directly, now reading/writing the FastAPI CRUD API (`lib/api.ts`) so changes persist in Postgres; no auth yet (the reserved marketing landing + auth gating are deferred). The Storyline is the organizing object: a header dropdown switches the active storyline (each owns its own cast/settings/scenarios, hydrated lazily on switch), and the body shows three open columns. The old standalone "Storylines"/branch-authoring tab has been removed.
- The **story player** (`/play/[scenarioId]`) is the core surface: it consumes the NDJSON event stream and renders narrator cards + character bubbles + action cards + side panels (cast / turn order / scenario goal / tone / **stats** / relationships / branch choices). Its streaming and reconnect states are mandatory, not optional.
- The **storyline home** (`/storylines/[id]`) is the authoring hub — a tabbed "library" (Characters · Settings · Scenarios · Storyline) where the cast and settings compose into playable scenarios, mirroring the reference design in `docs/CharacterFrontpage/`.
- Protected routes redirect logged-out users to `/sign-in`.
- Every page needs a unique, descriptive `<title>` and a logical heading hierarchy (see `docs/skills/ada-compliance/SKILL.md`).
