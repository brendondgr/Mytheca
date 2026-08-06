# Plan — Cast-Card Reorg: Profile, Grid, Transparent Hero Cards + Stats Carousel

## 1. Introduction

A round of UI refinements across the character surfaces, all frontend (Next.js +
React + Tailwind tokens), plus one new read-only data fetch (storyline stat
definitions) into the library state. Built in a worktree, commit-per-phase,
merged to `main`. Theme-agnostic across Parchment / Ember / Slate; AA contrast;
keyboard-operable; checked at 320 / 375 / 768 / 1024.

Four user asks:

1. **Character pop-up** (`CharacterProfileModal`): right of the portrait shows
   **only Background**; **Appearance** moves into the 2×2 (replacing **Secret**,
   which is removed from the view); remove the `❖` **seal medallion** under the
   portrait.
2. **Characters column** (`CharacterColumn`): cards are too big — **3 per row**
   instead of 2.
3. **Hero "Recent Scenario" cast cards** (`ScenarioCarousel` → `CastCard`):
   - **Transparency** — match the Library column card style (full-bleed portrait
     + transparent `PORTRAIT_SCRIM` footer) instead of the current solid
     accent-tinted footer + solid baked-in Statistics panel.
   - A **`❯` arrow inside each card** that, when clicked, opens a **Statistics
     panel inline to the right of that card**, pushing the following cards over
     (one open at a time; arrow flips to `❮` to close).
   - A working **carousel** so cast members are never cut off (the strip must
     scroll/page to reveal every character).

Decisions confirmed with the user: inline stats panel beside the card (pushes
siblings); panel content = the storyline's **stat names + default values**
(public-visibility, applicable to the character), falling back to "No statistics
available" when none.

## 2. Gaps & Unanswered Questions

- **Stat values are not per-character yet.** Show the storyline's `StatDefinition`
  list (displayName + `default`) filtered to `visibility === "public"` and
  (`appliesTo` empty ⇒ all, else includes the character id). This is a real
  preview; per-character values are a later task.
- **Stat defs aren't in `useLibraryState`** (only `useStorylineCreator` fetches
  them). Add a best-effort load of `api.listStatDefinitions(activeStorylineId)`
  into the library state, exposed as `lib.statDefs`, refreshed when the active
  storyline changes. Failure → empty list (cards show the fallback).
- **Carousel cut-off:** main already has an arrow-paged `overflow-x-auto` strip
  (recent "Hero Cast Cards Polish"). Verify it actually scrolls in-browser; if the
  cut-off persists, the fix is sizing (narrower cards so ≥2 fit) + ensuring the
  arrows/scroll are reachable. Do not regress the existing paging logic/tests.
- **Concurrent area:** the hero cast work was just merged by another session;
  this rebuilds the `CastCard` visual + adds the stats toggle. Keep `CastStrip`'s
  measure/page logic and its tests working.

## 3. Hierarchical Step-by-Step Instructions

### Step 1 (Phase 1): Profile pop-up reorg + Characters grid 3-per-row

- **Locations:** `web/frontend/components/feature/CharacterProfileModal.tsx`,
  `web/frontend/components/feature/CharacterColumn.tsx`.
- **Work:** profile — right column keeps only **Background**; the 2×2 becomes
  **Appearance · Personality · Voice · Goal**; **Secret** removed from render
  (field stays on the type); delete the seal-medallion span; drop the now-unused
  `tone`/danger branch from `ProfileSection`. Column — grid
  `grid-cols-1 sm:grid-cols-2` → `grid-cols-2 sm:grid-cols-3` (3 per row),
  verify card legibility at the column width.
- **Action:** `npm run typecheck`; update `CharacterProfileModal.test.tsx`
  (no Secret; Appearance present) — run it. Commit: `[Cast Cards Reorg] (1/4) Complete: Profile pop-up shows Background beside the portrait with Appearance in the 2×2 (Secret + medallion removed); Characters column is 3-up.`

### Step 2 (Phase 2): Load storyline stat definitions into library state

- **Locations:** `web/frontend/features/library/useLibraryState.ts` (+ its types),
  `web/frontend/features/library/LibraryView.tsx` (pass `statDefs` down),
  `web/frontend/components/feature/ScenarioCarousel.tsx` (accept `statDefs`).
- **Work:** add `statDefs: StatDefinition[]` state; fetch with
  `api.listStatDefinitions(activeStorylineId)` (best-effort, guarded) whenever the
  active storyline changes; expose on the hook's return. Thread `statDefs` into
  `ScenarioCarousel` → `CastStrip` (no visual change yet).
- **Action:** `npm run typecheck`; existing library/carousel tests green. Commit:
  `[Cast Cards Reorg] (2/4) Complete: Library state loads the active storyline's stat definitions and threads them to the carousel.`

### Step 3 (Phase 3): Transparent hero cast cards + inline stats panel + carousel

- **Locations:** `web/frontend/components/feature/ScenarioCarousel.tsx`
  (`CastStrip`, `CastCard`, new inline `CastStatsPanel`),
  `web/frontend/lib/cardArt.ts` (reuse `PORTRAIT_SCRIM`/`OVER_ART`).
- **Work:**
  - **CastCard transparency:** rebuild to mirror the Library `CharacterCard` —
    full-bleed portrait (monogram fallback), transparent `PORTRAIT_SCRIM`, name
    (`OVER_ART.title`) + role (`OVER_ART.eyebrow`) over the scrim, 2px
    character-color border. Remove the solid footer plate + the baked-in
    Statistics block + the corner monogram badge.
  - **Arrow + inline panel:** add a `❯`/`❮` toggle button in the card (e.g.
    bottom-right, above the whole-card profile button). Lift `openStatsId` state
    into `CastStrip`; when a card is open, render a `CastStatsPanel` (fixed-width,
    `flex-none`) **immediately after that card** in the flex row so following
    cards shift right; only one open at a time. Panel lists the character's public
    stat names + defaults from `statDefs` (fallback "No statistics available").
    The toggle is a sibling of the profile button (stops propagation; no nested
    interactives). Opening scrolls the panel into view.
  - **Carousel:** keep `CastStrip`'s overflow/measure/page logic; verify in-browser
    that all cast cards are reachable (scroll + arrows) including when a stats
    panel is open; adjust card width if needed so it never permanently clips.
- **Action:** `npm run typecheck`; in-browser verify (transparency, arrow toggle
  pushes siblings, carousel scrolls, all themes, 375/1024). Commit:
  `[Cast Cards Reorg] (3/4) Complete: Transparent hero cast cards with a per-card stats arrow that opens an inline pushing panel; carousel reveals all cast.`

### Step 4 (Phase 4): Tests, a11y/responsive pass, docs

- **Locations:** `ScenarioCarousel.test.tsx`, `CharacterProfileModal.test.tsx`
  (done in P1 — confirm), `docs/component-map.md`, `docs/design-system.md`,
  `docs/checklist.md`.
- **Work:** extend carousel tests — stats arrow toggles a panel, panel shows stat
  names/defaults (or fallback), one-open-at-a-time, transparent footer (no solid
  Statistics block always present); keep paging tests green. Full a11y +
  responsive pass. Update docs (carousel cast card treatment + stats panel +
  3-up column + profile reorg).
- **Action:** `npm test` (Vitest) green; `npm run typecheck` clean; a11y/responsive
  pass. Commit: `[Cast Cards Reorg] (4/4) Complete: Tests, a11y/responsive pass, and docs for the cast-card reorg.`

### Step 5 (Phase 5): Merge worktree → main

- **Work:** merge `feat/cast-cards-reorg` into `main` (resolve conflicts, keep
  unrelated in-progress changes); re-run `npm test` + `npm run typecheck` on main.
- **Action:** clean merge + green → on `main` locally. No push/PR unless asked.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Profile reorg | Background beside portrait; Appearance in 2×2; Secret + medallion removed | `web/frontend/components/feature/CharacterProfileModal.tsx` |
| 3-up Characters grid | 3 cards per row | `web/frontend/components/feature/CharacterColumn.tsx` |
| Stat defs in state | Load + expose active storyline stat definitions | `web/frontend/features/library/useLibraryState.ts` |
| Transparent cast cards + stats panel | Column-card style + per-card arrow → inline pushing stats panel | `web/frontend/components/feature/ScenarioCarousel.tsx` |
| Tests | Carousel stats/arrow + profile coverage | `web/frontend/components/feature/ScenarioCarousel.test.tsx`, `CharacterProfileModal.test.tsx` |
| Docs | component-map / design-system / checklist | `docs/` |
| This plan | Phase-by-phase plan | `docs/plans/archive/cast-cards-reorg.md` |

## 5. Validation Gate

- Frontend: `npm run typecheck` clean; `npm test` (Vitest) green.
- Web/UI: a11y + responsive pass — keyboard (arrow toggle + carousel paging
  reachable), visible focus, AA contrast, 320/375/768/1024, all three themes;
  reduced-motion respected.
- No backend change (stat-defs endpoint already exists) → `pytest` N/A.
- Commit per phase; merge worktree → main; no push/PR unless requested.
