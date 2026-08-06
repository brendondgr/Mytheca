# Plan — Wire the Story Player to Real Backend Data

## 1. Introduction

The scene overhaul made the story player *look* right, but it still resolves its scenario from in-memory seed (`resolveScenario(pickScenario(...), SEED_*)`). The user wants to open a real, database-backed scene and see it **fully populated** — the actual cast cards with their **portrait images**, real names and role titles, the setting's **scene art**, and the storyline's real **stat schema**. The backend already serves all of this (`GET /storylines/{id}/{characters,settings,scenarios,stats}`, media at `/media`), and the Library already consumes it client-side; the player just needs the same wiring.

Approach: a client hook (`useSceneData`) fetches the storyline's characters/settings/scenarios/stat-defs (+ name), resolves the requested scenario into a `ResolvedScenario` with its cast + setting, and the player renders it. Media paths (`/media/...`) resolve through the existing `mediaUrl()` helper at the render sites (the established pattern). A seed fallback keeps legacy/offline links working. This is the documented "wire the Story player to the backend" follow-up — still **no** streaming/agent turn loop (messages stay locally scripted).

## 2. Gaps & Unanswered Questions

- **CORS (known):** the backend allows only the real dev origin `:3346`. Client-side fetch therefore works in the real app (`python app.py` serves the frontend on 3346) and for verification we run the frontend on 3346. No backend change.
- **Single-scenario endpoint:** there is no `GET /scenarios/{id}`; the hook lists the storyline's scenarios and selects by id (cheap, mirrors the Library). Assumption, no blocker.
- **Null-safe scripted scene:** real characters may have null `secret`/`goal`; `genericScene` must guard them (the seed never did). Assumption.
- **Messages stay fake:** per the user, the transcript remains locally scripted (`useScenePlay`/`genericScene`) — only the *data populating the surfaces* (cast, portraits, setting, stats, titles) becomes real. The streaming engine is the next, separate phase.
- **Fallback:** on a network error → an error state with Retry + back-to-Library; if the storyline/scenario isn't in the backend, fall back to seed resolution so `/embergate/embergate` still demos offline.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend data wiring (hook + route + page)

- **Locations:** `web/frontend/features/story-player/useSceneData.ts` (new), `web/frontend/features/story-player/StoryPlayerRoute.tsx` (new, client), `web/frontend/app/[storylineId]/[scenarioId]/page.tsx` (thin server component), `web/frontend/features/story-player/scene-data.ts` (null-safe `genericScene`).
- **Work:** `useSceneData(storylineId, scenarioId)` `Promise.all`s `listScenarios`/`listCharacters`/`listSettings`/`listStatDefinitions`/`getStoryline`, resolves the scenario (`resolveScenario`), and returns `{ status, scenario, statDefs, storylineName, error, reload }`; seed fallback when not found; network error → error status. `StoryPlayerRoute` renders a loading state, an error card (Retry + ‹ Library), or `StoryPlayerView`. `page.tsx` renders `<StoryPlayerRoute …/>` and keeps a seed-based `generateMetadata` title. Guard `c.secret`/`c.goal` in `genericScene`.
- **Action:** `npm run typecheck` + Vitest (new hook test with a mocked api; existing player tests still green via seed fallback). Commit: `[Player Backend Data] (1/2) Complete: Story player loads the real scenario/cast/setting/stats from the backend (seed fallback).`

### Phase 2 — Media URLs, storyline name, verify, docs, merge

- **Locations:** `SceneLoader.tsx`, `SceneIntro.tsx`, `CastRail.tsx`, `TranscriptBeat.tsx` (`CharacterMessage`), `StoryPlayerView.tsx` (pass `storylineName`); docs (`component-map`, `routes`, `documentation`, `checklist`).
- **Work:** wrap portrait/scene-art in `mediaUrl()` at each render site (guarded for null/seed); thread `storylineName` to the loader kicker ("Entering {storyline}"). Live-verify against the running backend (Terra Vaelun `/60c77310/4e5b` — 9 cast portraits + scene image + stat schema). Update docs.
- **Action:** full gate — `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`; **live in-browser** pass on the real backend (frontend on 3346 for CORS). Commit: `[Player Backend Data] (2/2) Complete: Real portraits/scene-art in the scene + storyline-named loader; docs + verification.` Merge to `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Scene data hook | Fetch + resolve the scenario from the backend | `web/frontend/features/story-player/useSceneData.ts` |
| Route wrapper | Loading/error/ready client wrapper | `web/frontend/features/story-player/StoryPlayerRoute.tsx` |
| Page | Thin server component | `web/frontend/app/[storylineId]/[scenarioId]/page.tsx` |
| Null-safe scene | Guard real null fields in `genericScene` | `web/frontend/features/story-player/scene-data.ts` |
| Media in UI | `mediaUrl()` at portrait/scene-art sites | `components/feature/{SceneLoader,SceneIntro,CastRail,TranscriptBeat}.tsx` |
| Tests | Hook + route component tests | co-located `*.test.tsx` |
