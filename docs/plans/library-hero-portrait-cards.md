# Library Hero — Portrait Cards & Contrast Refresh

## 1. Introduction

The Library front page (`web/frontend/features/library/LibraryView.tsx` → `components/feature/ScenarioCarousel.tsx`) renders a "recent scenario" hero with a left scenario panel and a right strip of character cards. The reference target (image 1) makes this hero read much cleaner with far more contrast than the current build (image 2): each cast member becomes a **full-bleed portrait card** (portrait fills the card, a dark bottom scrim carries the colored Cinzel name + role + a `Statistics` footer, and a small wax-seal badge sits in the corner), and the left scenario panel lets its **scene art show through boldly** behind a graduated scrim instead of a flat near-black wash. The three bottom columns (Scenarios · Characters · Settings) already match the target and are out of scope.

This is a **frontend-only, visual** change concentrated in one component (`ScenarioCarousel.tsx`) plus a new co-located test and doc updates. It touches no backend, no data shape, and no API. Because the work is one tightly-coupled component with sequential validation (redesign cards → restyle panel → test the whole surface → merge), it is implemented as a linear, commit-per-phase plan rather than a fan-out workflow (the phases depend on each other, so parallel agents would add coordination cost without parallelism benefit).

## 2. Gaps & Unanswered Questions

- **Corner badge glyph (simple gap → assumption):** image 1 shows pictographic role icons (paw/leaf/star/shield) in each card's top-right. We have **no role→icon data** and inventing one violates the "no fake data" rule. **Assumption:** render the character's **monogram initial** in a small color-ringed circle (reuses `Monogram`, data-backed, on-brand with the wax-seal motif) as the corner badge. Recorded as a deviation in `design-system.md`.
- **Per-card "selected" highlight (simple gap → assumption):** image 1 shows one card (Finnian) with a brighter gold frame. The carousel has **no selected-character concept** (a slide shows a whole scenario's cast). **Assumption:** use a **hover/focus** ring rather than a persistent selected state.
- **Statistics content (simple gap → assumption):** per-character stat *values* are not yet wired to the resolved `Character` (the current code already shows an empty state). **Assumption:** keep the **"No statistics available."** empty state in the new footer; no data wiring in this plan.
- **Card separation (simple gap → assumption):** keep the existing flush `border-r` dividers between cards but give each card an internal rounded portrait frame, so the strip reads as framed cards (image 1) without changing the hero's outer geometry.
- **Live visual verification (constraint):** the shared working dir's dev server (3346) is the user's `python app.py`. **Assumption:** work in a dedicated **git worktree** (its own `.next`) and attempt `preview_start` on a free port for real screenshots; if a second Turbopack still clashes, fall back to the documented structural-verification pattern (green Vitest + `tsc` + ESLint + `next build` + reasoned a11y/contrast review).

## 3. Hierarchical Step-by-Step Instructions

### Phase 0: Worktree setup
- **Locations:** `.claude/worktrees/library-hero-portrait-cards/` (new worktree on branch `feat/library-hero-portrait-cards` off `main`).
- **Rationale:** Isolate from the user's running dev server / concurrent sessions (memory: *concurrent-sessions branch gotcha*). Frontend deps must be present to build; a symlinked `node_modules` breaks `next build` (memory: *worktree frontend build gotcha*) — **hardlink-copy** with `cp -al` instead.
- **Actions:** `git worktree add` the branch; `cp -al web/frontend/node_modules <wt>/web/frontend/node_modules`; confirm `npm test`/`tsc` resolve in the worktree. No commit (setup only).

### Phase 1: Portrait character cards
- **Locations:** `components/feature/ScenarioCarousel.tsx` (the `s.cast.map(...)` card block, ~lines 191–266); reuse `components/ui/Monogram.tsx`, `Eyebrow`, `lib/api.mediaUrl`.
- **Work:**
  - Replace the centered avatar-over-text card with a **relative, full-height portrait card**: portrait `<img object-cover absolute inset-0>` when `c.portrait` exists; otherwise a **tinted fallback** (character color at low alpha over `--field-bg`) with a large centered `Monogram` initial.
  - Add a **bottom-anchored dark gradient scrim** (transparent top → strong dark bottom) so overlaid text meets AA.
  - Over the scrim, bottom-anchored: **name** (Cinzel, `c.color`, large), **role** (mono, light parchment), a hairline divider, then the **`Statistics`** gold eyebrow + **"No statistics available."** italic.
  - **Corner badge** top-right: small color-ringed `Monogram` initial (per §2 assumption).
  - Keep the whole card an accessible control when `onProfile` is set (`<button>` overlay, `aria-label="View {name}"`); preserve hover lift/scale and a visible `:focus-visible` ring.
  - Preserve flush `border-r` dividers and the existing card width (`w-[250px] sm:w-[282px]`).
- **Rationale:** This is the dominant visual gap; portraits supply the contrast and "real artifact" imagery the design system mandates.
- **Action:** Add a co-located `components/feature/ScenarioCarousel.test.tsx` (per repo convention — tests co-locate beside components, overriding the planner template's `utils/tests/frontend` path) covering: portrait `<img>` when `portrait` set; monogram fallback when absent; name + role shown; statistics empty state; `onProfile`/`onBegin`/`onPrev`/`onNext` fire; empty-state branch. Run `npm test` + `npm run typecheck` + `npm run lint`. Once green, commit: `[Library Hero Portrait Cards] (1/3) Complete: Full-bleed portrait cards with scrim, name/role/stats footer, corner badge.`

### Phase 2: Scenario panel contrast + hero polish
- **Locations:** `components/feature/ScenarioCarousel.tsx` (left scenario panel, ~lines 96–183; the overlay at line 116–119).
- **Work:**
  - Replace the flat `rgba(20,14,6,0.68)` overlay with a **graduated scrim** (e.g. stronger at the bottom-left under the title/Begin button, lighter at top-right) so the scene art reads while keeping title/location/description/button at AA.
  - Minor hero-frame polish for cohesion (consistent border/divider tokens, ensure the empty-state panel still uses the same frame). No change to hero height/geometry or the overlay label/chevrons/counter.
- **Rationale:** The target derives its richness from visible scene art; the current near-opaque wash flattens it.
- **Action:** Re-run `npm test` + `typecheck` + `lint`; verify title/desc/tag/button contrast against the lightened art (AA: 4.5:1 body, 3:1 large). Once green, commit: `[Library Hero Portrait Cards] (2/3) Complete: Graduated scene-art scrim + hero framing polish.`

### Phase 3: Validation, docs, and merge
- **Locations:** `docs/design-system.md` (Library Layout — carousel card description + badge deviation), `docs/component-map.md` (`ScenarioCarousel` entry), `docs/checklist.md` (this entry, incl. any deferred a11y note).
- **Work:** Update docs to describe the portrait-card hero. Run the **full frontend gate** from the worktree: `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`. Attempt a live `preview_start` (worktree `.next`, free port) for screenshots at 1024/768/375/320; if it clashes, record the structural a11y/contrast verification per the standing pattern. **Backend untouched → pytest N/A** (state so explicitly).
- **Action:** Commit: `[Library Hero Portrait Cards] (3/3) Complete: Docs + full frontend validation.` Then **merge `feat/library-hero-portrait-cards` → `main`** (fixing any conflict), remove the worktree, and confirm `main` builds clean.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Portrait carousel cards | Full-bleed portrait cards with scrim, colored name, role, Statistics footer, corner badge, monogram fallback | `web/frontend/components/feature/ScenarioCarousel.tsx` |
| Scenario panel contrast | Graduated scene-art scrim + hero framing polish | `web/frontend/components/feature/ScenarioCarousel.tsx` |
| Carousel tests | Co-located component tests (portrait/fallback/name/role/stats/callbacks/empty-state) | `web/frontend/components/feature/ScenarioCarousel.test.tsx` |
| Docs | Library hero card description + badge deviation; component-map; checklist | `docs/design-system.md`, `docs/component-map.md`, `docs/checklist.md` |
