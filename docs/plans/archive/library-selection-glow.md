# Plan: Animated Selection Glow (Library Characters + Setting)

## 1. Introduction

On the Story Library main screen (`web/frontend/features/library/LibraryView.tsx`), a scenario is always "featured" (selected). Below the hero carousel, two library sections list **every** character and **every** setting the user has authored (`CharacterColumn` / `SettingColumn` in `LibraryColumns.tsx`). Today, the subset that belongs to the featured scenario is marked with a static highlight: `CharacterCard` gets a fixed generic-accent box-shadow ring when `highlighted`, and `SettingCard` gets a fixed `border-accent` + hardcoded shadow when `active`. Both already show a "◆ In this scene" label.

This plan upgrades that static highlight into an **animated, pulsing glow** that surrounds the card container, so the selected cast + setting visually stand out and draw the eye — while keeping the glow color tied to **each entity's own existing outline color** (a character's own `color` field for `CharacterCard`; the theme accent for `SettingCard`, since settings have no per-entity color and the accent is already their outline color today). The approach: add one reusable CSS keyframe + utility class driven by a `--glow-color` custom property in `web/frontend/styles/themes.css` (mirroring the existing `embFade`/`embPop`/etc. keyframes already in that file), then apply it conditionally in `CharacterCard.tsx` and `SettingCard.tsx`. This is frontend-only — no backend, schema, or API change (the `castIds`/`settingId` plumbing driving `highlighted`/`active` already exists).

## 2. Gaps & Unanswered Questions

- **Simple gap — glow color source for settings:** `Setting` has no `color` field (confirmed in `lib/types.ts`). Assumption: use `var(--accent)`, which is already the color of the setting's current active border/label, so the glow matches its existing outline exactly. Proceeding on this assumption.
- **Simple gap — hero carousel `CastCard` scope:** the hero `ScenarioCarousel`'s `CastCard` only ever renders the *featured scenario's own cast* (every card shown there is already "in the scene" — there's no mixed selected/unselected set to distinguish). The user's request describes sections showing "the different characters and settings" where only *some* are selected, which matches the library columns, not the hero. Assumption: hero `CastCard` is out of scope for this pass; only `CharacterColumn`/`CharacterCard` and `SettingColumn`/`SettingCard` change. Flagging this assumption in the phase 4 docs update; easy to extend later if the user wants the hero included too.
- **Simple gap — motion preference:** the project's accessibility skill requires respecting `prefers-reduced-motion`. Assumption: reduced motion gets a static (non-animated) glow at the keyframe's mid-intensity, not "no glow at all" — so the visual "this one is selected" signal survives, only the pulsing motion is dropped.
- No complex gaps requiring human intervention.

## 3. Hierarchical Step-by-Step Instructions

### Phase 0: Branch / worktree setup

- **Locations:** repo root.
- **Rationale:** Isolate this UI change per Mytheca git workflow (branch off `main`, commit per phase, merge back at the end). A worktree also gives an isolated `.next` for a live dev-server check later (per prior sessions' `node_modules` symlink / build gotcha in project memory).
- **Action:** Create `git worktree add ../mytheca-library-selection-glow -b feat/library-selection-glow` (or a plain feature branch if a worktree isn't warranted — this is a small, low-risk frontend change, but a worktree keeps `main`'s dev server undisturbed if it's running). No validation gate for this phase (no code yet); no commit.

### Phase 1: Reusable animated glow primitive

- **Locations:** `web/frontend/styles/themes.css`.
- **Rationale:** All existing pulsing/entrance motion in the project lives as named `@keyframes` in this file, applied via Tailwind's arbitrary `animate-[name_duration_easing]` syntax. A single keyframe parameterized by a CSS custom property (`--glow-color`) lets both `CharacterCard` (per-character hex) and `SettingCard` (theme accent) reuse one animation definition instead of duplicating box-shadow math.
- **Details:**
  - Add `@keyframes mythecaGlowPulse` animating `box-shadow` between a tight/dim ring and a wider/brighter ring, both expressed in terms of `var(--glow-color)` (e.g. two-layer box-shadow: an inner solid ring + an outer soft blur, matching the existing ring math already used in `CharacterCard`/`SettingCard` today).
  - Add a `.mytheca-glow` utility class that sets `animation: mythecaGlowPulse 2.2s ease-in-out infinite;` and, nested under `@media (prefers-reduced-motion: reduce)`, overrides it to a static box-shadow (no `animation`) at the keyframe's brighter frame — consistent with how `docs/skills/accessibility-mobile/SKILL.md` requires reduced-motion handling for continuous/looping motion.
  - Do not touch the existing `.mytheca-card` transition rule — it already animates `box-shadow` changes on hover/mount, and `.mytheca-glow`'s `animation` shorthand takes precedence for the ring itself.
- **Action:** Run frontend validation for this phase — `npm run typecheck` (no TS touched, should still be a no-op pass) and `npm test` (should be unaffected, confirms nothing else broke by editing global CSS). Once green, commit: `Library Selection Glow (1/4) Complete: Added reusable mythecaGlowPulse keyframe + .mytheca-glow utility with reduced-motion fallback.`

### Phase 2: Apply the glow to in-scene `CharacterCard`s

- **Locations:** `web/frontend/components/feature/CharacterCard.tsx`, `web/frontend/components/feature/CharacterCard.test.tsx`.
- **Rationale:** `highlighted` already identifies cast members of the featured scenario (wired from `CharacterColumn` → `LibraryColumns.tsx` → `lib.featured.castIds`). Swap the current static `boxShadow: highlighted ? "0 0 0 2px var(--accent), 0 6px 16px rgba(142,43,28,.20)" : undefined` for the new animated glow, keyed to the character's own `c.color` (not the generic accent) — this is the part of the request that explicitly asks for "the same color as their outline," and `c.color` is already the card's own border color.
- **Details:**
  - When `highlighted`, add `"mytheca-glow"` to the card's `className` and set the `--glow-color` CSS custom property inline to `c.color` (TypeScript: a `style` object typed to allow the custom property, e.g. `style={{ border: ..., ["--glow-color" as string]: c.color } as React.CSSProperties}`, matching how the codebase already inlines dynamic per-character colors elsewhere).
  - When not `highlighted`, omit both the class and the custom property (keep the plain `2px solid ${c.color}` border, unglowed) — same behavior as before minus the old static ring.
  - Keep the existing "◆ In this scene" label untouched.
- **Test updates:** extend the existing `"shows the cast badge only when highlighted"` case (or add a sibling case) in `CharacterCard.test.tsx` to assert the container carries the `mytheca-glow` class (or the `--glow-color` inline style) when `highlighted` and does not when it isn't — querying by a stable selector (e.g. the card root via `container.querySelector`, since there's no dedicated `data-testid` today; add one only if the class-based assertion proves brittle).
- **Action:** Run `npm test` (Vitest — full suite, confirm `CharacterCard.test.tsx` green + no regressions elsewhere) and `npm run typecheck`. Once green, commit: `Library Selection Glow (2/4) Complete: CharacterCard highlighted state now uses an animated glow keyed to the character's own color.`

### Phase 3: Apply the glow to the active `SettingCard`

- **Locations:** `web/frontend/components/feature/SettingCard.tsx`, `web/frontend/components/feature/SettingCard.test.tsx`.
- **Rationale:** `active` already identifies the featured scenario's setting (wired from `SettingColumn` → `LibraryColumns.tsx` → `lib.featured.settingId`). Swap the current static `border-2 border-accent` + hardcoded `shadow-[0_6px_18px_rgba(142,43,28,.18)]` combination for the same `.mytheca-glow` treatment used on `CharacterCard`, keyed to `var(--accent)` (the setting's existing outline color) for parity across both sections.
- **Details:**
  - When `active`, add `"mytheca-glow"` to the card's `className` (alongside the existing `active`-branch classes) and set `--glow-color: var(--accent)` inline — since the accent already varies per theme (Parchment/Ember/Slate), no hardcoded hex is introduced.
  - Keep the `border-2 border-accent` border itself (the glow surrounds/reinforces the existing outline, it doesn't replace it) and the existing `-translate-y-[2px]` lift and `aria-current`/label logic untouched.
  - Remove the now-redundant hardcoded static shadow (`shadow-[0_6px_18px_rgba(142,43,28,.18)]`) since `.mytheca-glow` supplies the ring; keep the plain hover shadow (`hover:shadow-[...]`) used by inactive cards as-is.
- **Test updates:** extend `"marks the active setting with a label + aria-current"` (or add a sibling case) in `SettingCard.test.tsx` to assert `mytheca-glow` is present when `active` and absent otherwise, without breaking the existing `aria-current`/label assertions.
- **Action:** Run `npm test` and `npm run typecheck`. Once green, commit: `Library Selection Glow (3/4) Complete: SettingCard active state now uses the same animated glow, keyed to the theme accent.`

### Phase 4: Validation gate, docs, live check, merge

- **Locations:** `docs/design-system.md`, `docs/component-map.md`, `docs/checklist.md`; the running dev server for a live check.
- **Rationale:** Mytheca's documentation-maintenance rule requires visual/design-token decisions to land in `design-system.md` in the same change, and `component-map.md` to reflect any changed component behavior; the checklist gets a status entry per the project's plan-tracking convention. A live check confirms the animation actually pulses (CSS animations can't be verified by Vitest/jsdom) and that reduced-motion + contrast still hold.
- **Details:**
  - `docs/design-system.md`: add a short note (near the existing "Cast highlight" / active-setting description) documenting the `.mytheca-glow` utility, that it's keyed per-entity via `--glow-color`, and the reduced-motion fallback.
  - `docs/component-map.md`: update the `CharacterCard`/`SettingCard` rows to mention the animated glow replacing the old static ring/shadow.
  - `docs/checklist.md`: add a "Library selection glow" entry under Follow-up Work summarizing the change, validation, and the phase-1 hero-`CastCard`-out-of-scope assumption (so it's visible if the user later wants parity there).
  - Run the full validation gate: `npm test`, `npm run typecheck`, `npm run lint`, `npm run build` (`next build`), all from `web/frontend`. Backend is untouched → `pytest` N/A, state that explicitly in the checklist entry.
  - Live check: start (or reuse) a dev server — if `main`'s own dev server is occupying its ports, use the worktree's own `.next` on a free port per the project's known "second dev server in a worktree" pattern. Open the Story Library, confirm: the highlighted cast cards and the active setting card show a visibly pulsing glow in their respective colors; toggling the OS/browser reduced-motion preference (or the emulated equivalent) freezes the glow to a static ring instead of removing it; check at 320/375/768/1024 widths that the glow doesn't clip or cause layout shift; confirm keyboard focus rings are still visible and distinguishable from the glow (contrast/focus-visibility per the accessibility skill).
  - **Action:** Once the full gate is green and the live check is done (or explicitly deferred with a reason, matching this project's established deferral pattern for a standing shared-dir constraint), commit: `Library Selection Glow (4/4) Complete: Docs updated, full validation gate green, live glow behavior verified.`
  - **Merge:** from the worktree, merge `feat/library-selection-glow` into `main` (fast-forward or a merge commit per whatever `git merge` naturally does — no rebase needed for a 4-commit linear feature branch), resolving any conflicts against anything else that landed on `main` in the meantime. Do not push.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Glow keyframe + utility | `mythecaGlowPulse` keyframes + `.mytheca-glow` class, reduced-motion fallback | `web/frontend/styles/themes.css` |
| Character glow | `CharacterCard` highlighted state → animated glow keyed to `c.color` | `web/frontend/components/feature/CharacterCard.tsx` |
| Setting glow | `SettingCard` active state → animated glow keyed to `var(--accent)` | `web/frontend/components/feature/SettingCard.tsx` |
| Character glow tests | Assert glow class present/absent by `highlighted` | `web/frontend/components/feature/CharacterCard.test.tsx` |
| Setting glow tests | Assert glow class present/absent by `active`, `aria-current`/label unchanged | `web/frontend/components/feature/SettingCard.test.tsx` |
| Docs | Design-system + component-map + checklist entries | `docs/design-system.md`, `docs/component-map.md`, `docs/checklist.md` |
