# Plan — Scene Loading Screen + Chat Interface Overhaul

## 1. Introduction

The story player (`/{storylineId}/{scenarioId}` → `features/story-player/StoryPlayerView`) is the surface a reader lands on after pressing **Enter Scene** in the Library. Two things lag behind the rest of the app: (1) the "entering the scene" **loading screen** (`SceneLoader`) is a generic ❖ spinner that hard-codes *"Entering Embergate"* and carries none of the scenario's context, and (2) the **chat interface** (header, transcript, composer, cast rail, director rail) reads thinner than the Library it came from — it shows monogram-only cast, ad-hoc scripted stat chips, and surfaces none of the setting/atmosphere/genre/tone context that the main page now presents richly.

This plan overhauls both, **frontend-only**, with **pseudo-seeded** data: the real Embergate seed characters, setting, scenario title/genre/tone/goal/opening, and a real per-storyline **stat schema**, with fake (scripted) messages — so we can see the populated chat experience before any agent/streaming processing is wired in. The approach: enrich `lib/seed-data.ts` with the fuller character/setting fields and a stat schema, rebuild `SceneLoader` into a cinematic establishing "curtain" that folds in the begin-scene preview, then restructure the player's header / transcript / rails to match the Library's visual quality and the locked design system (`docs/design-system.md`). No backend, route, contract, or API change.

## 2. Gaps & Unanswered Questions

- **Data source (resolved):** keep the player on **seed data** (pseudo-seeding), not the live backend — confirmed by the user. The scene shows *real* seed character/setting/scenario info with *fake* messages.
- **Loading screen (resolved):** a **rich establishing screen** — scene-art backdrop, setting, cast portraits, genre/tone, goal — that dissolves into the live scene (confirmed).
- **Stats (resolved):** surface the storyline's **real stat schema** (definitions + labeled bands) *and* keep the live "scene state" section (confirmed). Requires a small `SEED_STAT_DEFS` addition so it works without the backend.
- **Images (assumption):** the seed carries no portrait/scene-art image files, so portraits/scene-art fall back to the existing monogram / setting-plate / gradient treatments (identical to how the Library degrades). We will not fabricate media files; the layout is built so art "drops in" cleanly if a `portrait`/`image` is ever present. No blocker.
- **Profile depth (assumption):** enrich seed characters with `appearance`/`background`/`personality` and settings with `atmosphere`/`features`/`currentState` so the in-scene `CharacterProfileModal` and setting context read as fully as the main page. These are additive, nullable fields already on the types.
- **Orchestration (assumption):** the phases are visually interdependent (one coherent design language across loader/header/transcript/rails), so this is implemented directly rather than as a fan-out workflow. Isolated search/implementation may be delegated to sub-agents, but the styling is kept in one hand for consistency.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Pseudo-seed enrichment (data layer)

- **Locations:** `web/frontend/lib/seed-data.ts`, `web/frontend/lib/types.ts` (no shape change expected — fields already exist).
- **Work:** add `appearance` / `background` / `personality` prose to each of the 6 `SEED_CHARACTERS`; add `atmosphere` / `features` / `currentState` to the 5 `SEED_SETTINGS`; add a new exported `SEED_STAT_DEFS: StatDefinition[]` for the Embergate world (e.g. **Health**, **Suspicion**, **Trust**, **Patience** — public, with `min`/`max`/`default` + 2–3 labeled `bands` each, mirroring `web/backend/app/content/stats/*.md`). Keep it lint-clean and under the file-size guidance.
- **Rationale:** every later phase reads this data; landing it first lets the loader and rails surface "real populated data" immediately and keeps the diff reviewable.
- **Action:** Run `npm run typecheck` + the existing Vitest suite (must stay green — no consumer changed yet). Commit: `[Scene Overhaul] (1/5) Complete: Enriched Embergate seed (character/setting prose + stat schema) for the player.`

### Phase 2 — Rich establishing loading screen

- **Locations:** `web/frontend/components/feature/SceneLoader.tsx` (rebuild), `web/frontend/features/story-player/StoryPlayerView.tsx` (pass the resolved scenario through), `web/frontend/components/feature/SceneLoader.test.tsx` (new).
- **Work:** turn `SceneLoader` from a `{title, visible}` spinner into a scenario-aware **establishing curtain**: a full-screen panel with the scenario `image` as a backdrop behind `CARD_SCRIM` (setting-plate/gradient fallback when no image), a storyline/genre eyebrow, the **scenario title**, the **setting** name + description, a **cast portrait row** (`Monogram` with `src` → portrait, monogram fallback), the **scene goal** + **tone**, and a "conjuring the scene…" progress line. Reduced-motion-safe (`motion-reduce`), `role="status"` + `aria-label`, dissolves into the scene. This folds the `BeginSceneModal` preview content into the loader. Update `StoryPlayerView` to pass `scenario` (+ derived props) to `SceneLoader`.
- **Rationale:** the loader is the bridge from the main page into the chat; making it carry the full scenario context is the headline deliverable and sets the visual language reused below.
- **Action:** Run `npm run typecheck` + Vitest (incl. the new `SceneLoader.test.tsx`); a11y/responsive reasoning at 320/375/768/1024 (keyboard N/A — non-interactive; contrast over the scrim; reduced-motion). Commit: `[Scene Overhaul] (2/5) Complete: Rebuilt the scene loader into a scenario-aware establishing screen.`

### Phase 3 — Chat interface structure (header · transcript · composer)

- **Locations:** `web/frontend/components/layout/SceneHeader.tsx`, `web/frontend/components/feature/TranscriptBeat.tsx` (`CharacterMessage`), `web/frontend/features/story-player/StoryPlayerView.tsx`, plus their `*.test.tsx`.
- **Work:** (a) `SceneHeader` — carry scenario **genre · tone** alongside the setting line; keep the back-link/theme/status. (b) Transcript — add a compact **scene-intro band** at the top of the transcript (setting + goal + cast at the table) so the chat itself "contains the main-page info", and upgrade `CharacterMessage` to render the character **portrait** via `Monogram src` (monogram fallback) so dialogue avatars match the Library. (c) Keep the ≤720px reading measure, narrator/character/player typographic distinction, and Framer beat entrances per the design system. (d) Composer polish only if needed.
- **Rationale:** this is the "fix the chat's general structure" core — the central reading column is the primary surface and must read like the rest of the app.
- **Action:** Run `npm run typecheck` + Vitest (update `StoryPlayerView.test.tsx` / `TranscriptBeat` tests for the new structure); a11y/responsive pass (live region intact, focus, contrast, 320/375/768/1024). Commit: `[Scene Overhaul] (3/5) Complete: Restructured the scene header + transcript (scene-intro band, portrait avatars).`

### Phase 4 — Rails: real cast + stat schema + scene context

- **Locations:** `web/frontend/components/feature/CastRail.tsx`, `web/frontend/components/feature/DirectorRail.tsx`, `web/frontend/features/story-player/{StoryPlayerView,useScenePlay,scene-data}.ts(x)`, `web/frontend/app/[storylineId]/[scenarioId]/page.tsx`, plus tests.
- **Work:** (a) `CastRail` — portraits (`Monogram src`) + role, keep speaking marker + turn order. (b) `DirectorRail` — add a **Scene** context section (setting name/type/description/atmosphere, genre · tone), surface the **storyline stat schema** (`SEED_STAT_DEFS`, public defs with default values + a band hint) as a "Character stats" block, and keep the live **Scene state** chips + **Tension** meter + **Relationships**. (c) Thread `statDefs` from the page → `StoryPlayerView` → `DirectorRail` (resolve `SEED_STAT_DEFS` in `page.tsx`); keep scripted scene-state chips driven by `useScenePlay`.
- **Rationale:** the rails are where the "all the context from the main page" requirement and the real-stat-schema decision land; doing it after the center column keeps the shared tokens consistent.
- **Action:** Run `npm run typecheck` + Vitest (rail tests: portraits present, stat-schema names/defaults shown, scene-state still updates on choice); a11y/responsive pass (rails hidden < lg as today; contrast; labelled progressbar). Commit: `[Scene Overhaul] (4/5) Complete: Enriched cast + director rails with portraits, the stat schema, and scene context.`

### Phase 5 — Docs, validation sweep, merge

- **Locations:** `docs/component-map.md`, `docs/design-system.md`, `docs/routes.md` (story-player row note), `docs/documentation.md` (status), `docs/checklist.md` (new entry).
- **Work:** update the docs for the new loader + player structure and the pseudo-seed/stat-schema decisions; record any deferred a11y/responsive item; run the full validation gate; merge the worktree branch to `main`, fixing any conflicts.
- **Rationale:** the Mytheca definition of done requires docs in the same change and a clean validation gate; the task also requires merging the worktree to main.
- **Action:** Run the full gate — `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` (frontend-only → backend `pytest` N/A, note it); a11y/responsive reasoning at 320/375/768/1024 across all three themes. Commit: `[Scene Overhaul] (5/5) Complete: Docs + validation; merged the scene loader + chat overhaul.` Then merge to `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Enriched seed | Character prose, setting metadata, stat schema | `web/frontend/lib/seed-data.ts` |
| Establishing loader | Scenario-aware loading "curtain" + test | `web/frontend/components/feature/SceneLoader.tsx` (+ `.test.tsx`) |
| Scene header | Genre · tone + setting context | `web/frontend/components/layout/SceneHeader.tsx` |
| Chat structure | Scene-intro band + portrait dialogue avatars | `web/frontend/components/feature/TranscriptBeat.tsx`, `features/story-player/StoryPlayerView.tsx` |
| Cast rail | Portrait cast + turn order | `web/frontend/components/feature/CastRail.tsx` |
| Director rail | Scene context + real stat schema + scene state | `web/frontend/components/feature/DirectorRail.tsx` |
| Page wiring | Resolve + thread stat schema | `web/frontend/app/[storylineId]/[scenarioId]/page.tsx` |
| Tests | Loader/header/transcript/rail component tests | co-located `*.test.tsx` under `web/frontend/...` |
| Docs | Component map, design system, routes, status, checklist | `docs/*.md` |
