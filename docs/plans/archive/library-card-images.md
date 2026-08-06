# Library Column Cards — full-bleed art + left→right gradient

## 1. Introduction

Follow-up to the hero portrait-card work. The carousel hero now uses full-bleed scene art behind a left-dark→right-bright "filter" gradient, and the user wants the **Scenario cards** and **Setting cards** in the Library columns to match: the scene/establishing image should fill the **whole card** (not a 96px banner over a solid body), with the same horizontal gradient scrim on top — dark on the left under the text, brightening to the right so the artwork reads. Frontend-only, two components: `web/frontend/components/feature/ScenarioCard.tsx` and `SettingCard.tsx`.

("Scroll-down menu" in the request is read as the scrollable Scenarios/Settings **columns** these cards live in — same cards. If a distinct dropdown was meant, that's a follow-up.)

## 2. Gaps & Unanswered Questions

- **No image → fallback (assumption):** cards without a generated image keep the current solid, theme-aware treatment (the striped "setting plate" for settings; solid card for scenarios). Only image-backed cards get the overlay.
- **Text over bright art / AA (assumption, documented):** like the approved carousel scrim, light text sits over the **dark left** of the gradient and the text block is **width-capped** so it stays in the dark zone; over typical mid-tone watercolor art this clears AA, with near-white art directly behind the text band as the known theoretical edge (the user explicitly wants this look). Title/labels are large (3:1).
- **Badge/pencil overlap (assumption):** in an overlay the "Recent" badge (scenario) and edit pencil both want the top-right; they'll be grouped into one absolute top-right cluster. The setting "◆ In this scene" label moves to a line under the type (dark-left), readable over art.
- **Theme (assumption):** the overlay (dark scrim + light text) is theme-independent for image cards (matching the carousel); the no-image fallback stays theme-aware.

## 3. Steps

### Phase 0: Worktree (done)
Worktree `.claude/worktrees/library-card-images` on `feat/library-card-images`; `node_modules` hardlinked.

### Phase 1: ScenarioCard full-bleed
- **Locations:** `components/feature/ScenarioCard.tsx`; extend `ScenarioCard.test.tsx`.
- **Work:** when `s.image` is set — image `absolute inset-0 object-cover`; shared `CARD_SCRIM` gradient overlay; content `relative z-[1]` with light text (title/eyebrow/goal width-capped, goal `line-clamp-3`); footer (cast monograms + `◆ setting`) full-width with a light hairline; top-right cluster = Recent badge + edit pencil. No-image → current solid layout. `min-h` on image cards so art shows.
- **Action:** `npm test` (ScenarioCard) + `typecheck` + `lint`; commit `[Library Card Images] (1/3) Complete: Scenario cards use full-bleed art + left→right gradient.`

### Phase 2: SettingCard full-bleed
- **Locations:** `components/feature/SettingCard.tsx`; new `SettingCard.test.tsx`.
- **Work:** same overlay treatment; name (light, `pr` for pencil), type eyebrow (gold), `◆ In this scene` under the type when active (light-ember over art), description width-capped + `line-clamp-2`. Active = 2px accent border (over the page bg) + the label. No-image → current plate fallback.
- **Action:** `npm test` (SettingCard) + `typecheck` + `lint`; commit `[Library Card Images] (2/3) Complete: Setting cards use full-bleed art + left→right gradient.`

### Phase 3: Validation, docs, merge
- **Work:** full gate (`test`/`typecheck`/`lint`/`build`); live-verify in the worktree (free-port dev server + throwaway route with real `/media`, computed-style/geometry/contrast via `preview_eval`). Docs: `component-map.md` (ScenarioCard/SettingCard), `design-system.md` (Library Layout cards), `checklist.md`. Backend untouched → pytest N/A.
- **Action:** commit `[Library Card Images] (3/3) Complete: Docs + validation.`; merge to `main`, remove worktree.

## 4. Deliverables

| Deliverable | Location |
| --- | --- |
| Full-bleed scenario card | `web/frontend/components/feature/ScenarioCard.tsx` |
| Full-bleed setting card | `web/frontend/components/feature/SettingCard.tsx` |
| Tests | `ScenarioCard.test.tsx` (extended), `SettingCard.test.tsx` (new) |
| Docs | `docs/component-map.md`, `docs/design-system.md`, `docs/checklist.md` |
