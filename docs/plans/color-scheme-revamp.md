# Color Scheme Revamp — layered contrast, decisive interactions, consistent menus

## 1. Introduction

The current three themes (Parchment / Ember / Slate) read as a single flat wash: the page,
header, rails, and cards sit within a few points of lightness of each other, `--hair-strong`
is literally identical to `--hair` in Ember and Slate, and most interactive elements signal
hover with near-invisible changes (`hover:brightness-[1.08]` on the primary button). The user
ask: **significantly more advanced color schemes** — clear visual division between sections
(some areas noticeably darker than others), clearer/more dynamic buttons and hover states,
consistent dropdown menus, a deeper/richer Parchment (currently "too pale and washed out"),
darker chrome zones in Ember (not uniformly brown) and Slate. The **chat interface is fine
as-is** — the story player keeps its structure and inherits only the token-level tonal shift.

The approach exploits the existing token architecture (`web/frontend/styles/themes.css` →
`@theme inline` in `app/globals.css`): re-tune the three palettes into an explicit
**three-tier lightness system** — chrome (header/rails, darkest tier per theme), page ground
(middle), cards/fields (lightest tier so content pops) — and add a small set of new
**interaction tokens** (`--accent-hover`, `--menu-bg`, `--menu-bd`, `--hover-bg`,
`--surface`) that primitives and menus consume. Then sweep the interactive primitives,
dropdowns, and page-level section boundaries to consume them. All work is token-driven, so
the story player changes tone without changing structure.

## 2. Gaps & Unanswered Questions

- **"Brainstorm ideas" scope (assumption):** the session runs autonomously, so instead of an
  interactive brainstorm the plan commits to one clear direction — the three-tier layering
  system above — and documents the reasoning in `docs/design-system.md`. Alternative
  directions (e.g. flipping the light-theme header to dark leather) were rejected because
  header/rail children use `--ink`-family text tokens; an inverted band would need a parallel
  text-token set and breaks the "no structural change" constraint.
- **Chat exemption vs. shared tokens (assumption):** the story player consumes the same
  tokens, so it will pick up the darker rails/header and stronger hovers. This is treated as
  aligned with the ask ("Ember … should be darker in certain areas") — the chat's structure,
  bubbles, and composer remain untouched.
- **Exact hex values:** the values in Phase 1 are the design intent; the WCAG-AA contrast
  script added in the same phase is the arbiter — any pair that fails AA is adjusted before
  the phase commits.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Token architecture + re-tuned palettes (the foundation)

- **Locations:** `web/frontend/styles/themes.css`, `web/frontend/app/globals.css`,
  `utils/scripts/check_contrast.py` (new), `docs/design-system.md`.
- **Rationale:** every later phase consumes these tokens; palettes must land first so the
  primitive/menu/section sweeps are pure class edits.
- **Work:**
  1. **New tokens per theme** in `themes.css`: `--accent-hover` (darker accent in Parchment,
     brighter in Ember/Slate), `--menu-bg` + `--menu-bd` (elevated popover surface, distinct
     from cards), `--hover-bg` (solid row-hover tint, visibly darker/lighter than the surface
     it sits on), `--surface` (alias of the raised surface for generic use).
  2. **Re-tune the three palettes** into three lightness tiers:
     - *Parchment:* deepen the ground (`--page-bg` ≈ `#DCCCA8`), keep cards light
       (`#F4ECDA`+) so they lift, darken chrome gradients (header/rail ≈ `#DECDA6→#D2BF93`),
       strengthen borders (`--card-bd` ≈ `#C2AC7E`, `--hair-strong` ≈ `#A98F5D`,
       `--field-bd` ≈ `#B49A67`), enrich text (`--ink-soft`, `--mute`, `--mute2` darker).
     - *Ember:* near-black ground (`--page-bg` ≈ `#0D0A06`) and darker chrome
       (header ≈ `#171108→#100C06`, rails ≈ `#140F09→#0F0B06`) so the warm-brown cards become
       the bright tier; make `--hair-strong` finally distinct (≈ `#5A4827`); recess inputs
       (`--field-bg` ≈ `#171209`); slightly brighten `--accent` and the mute tiers for AA on
       the darker grounds.
     - *Slate:* same treatment cool-toned — ground ≈ `#0A0E13`, chrome header ≈
       `#11161D→#0C1015`, rails ≈ `#0F141B→#0B0F14`, `--hair-strong` ≈ `#41505E`, recessed
       fields, brightened mutes.
  3. **Map new tokens in `globals.css`** `@theme inline`: `--color-accent-hover`,
     `--color-menu`, `--color-menu-bd`, `--color-hover`, `--color-surface` (this also makes
     AboutTab's currently-dead `bg-surface` / `hover:bg-hover` classes real).
  4. **`utils/scripts/check_contrast.py`** — parses the `.theme-*` blocks out of
     `themes.css`, computes WCAG ratios for the load-bearing pairs (ink/ink-soft/mute/mute2 ×
     page/card/card2/field/menu; accent + gold vs page/card; accent-ink `#F6ECDA` vs accent
     and accent-hover), asserts AA (≥4.5 text, ≥3 large/UI), exits non-zero on failure.
     Adjust hexes until green.
  5. **`docs/design-system.md`:** rewrite the token table with the new values + new tokens;
     document the three-tier layering rule and the interaction-token contract.
- **Action:** Run `uv run python utils/scripts/check_contrast.py` + frontend
  `npm test` / `npm run typecheck` (no component churn expected). Once green, commit:
  `Color Scheme Revamp (1/5) Complete: three-tier palettes + interaction tokens + contrast gate.`

### Phase 2 — Interactive primitives: decisive hover/active states

- **Locations:** `web/frontend/components/ui/` — `Button.tsx`, `IconButton.tsx`, `Chip.tsx`,
  `ToggleChip.tsx`, `CloseButton.tsx`, `Tag.tsx` (audit), plus co-located tests;
  `components/layout/ThemeSwitcher.tsx` if it owns its own hover styles.
- **Rationale:** these primitives are used everywhere; fixing them once propagates the
  "buttons should be obvious" ask across the app.
- **Work:** primary Button → solid `hover:bg-accent-hover` (replace `brightness-[1.08]`) +
  1px lift + soft shadow; ghost Button → `hover:bg-hover hover:text-ink hover:border-accent`
  (current `hover:bg-card` is invisible on card surfaces); IconButton `field` variant gains a
  background change, `card` variant keeps the accent fill-swap; Chip/ToggleChip/CloseButton
  get the same treatment via `--hover-bg`/`--accent-hover`; add `active:` (pressed) states
  that cancel the lift. Update any class-asserting tests.
- **Action:** `cd web/frontend && npx vitest run components/ui` + typecheck. Once green,
  commit: `Color Scheme Revamp (2/5) Complete: decisive hover/active states on interactive primitives.`

### Phase 3 — Dropdown/menu consistency

- **Locations:** `web/frontend/styles/themes.css` (`.velora-menu` helper),
  `components/feature/` — `StorylineMenu.tsx`, `CreateMenu.tsx`, `OptionsMenu.tsx`,
  `ExportMenu.tsx`, `PovSelect.tsx`, `SceneConfigMenu.tsx`; `components/ui/MultiSelect.tsx`;
  `features/options/tabs/AboutTab.tsx` (now-real `bg-surface`/`hover:bg-hover`).
- **Rationale:** menus are "hit-or-miss" because each popover hand-rolls its surface, border,
  shadow, and row hover; a shared surface class + a consistent row idiom
  (`hover:bg-hover` + accent text) makes every dropdown read the same.
- **Work:** define `.velora-menu` (menu-bg surface, `--menu-bd` border, elevated shadow) and
  apply to every popover panel; normalize row hovers to `hover:bg-hover` (+
  `hover:text-accent`/`hover:text-danger` where semantically colored); normalize trigger
  hovers to the Phase-2 idiom. No behavioral/ARIA changes. Update class-asserting tests.
- **Action:** `npx vitest run components` + typecheck. Once green, commit:
  `Color Scheme Revamp (3/5) Complete: shared .velora-menu surface + consistent dropdown rows.`

### Phase 4 — Section division on pages (non-chat)

- **Locations:** `components/layout/AppHeader.tsx`, `features/options/OptionsView.tsx`,
  `features/library/LibraryView.tsx` / `LibraryColumns.tsx`,
  `features/library/StorylineCreatorView.tsx`, `features/documents/DocumentsView.tsx`.
- **Rationale:** with the darker chrome tier in place, page-level boundaries need to actually
  use it: headers cast a separating shadow; sidebars/rails sit on the rail surface instead of
  blending into the page; column dividers use the now-truly-stronger `--hair-strong`.
- **Work:** AppHeader/Options header gain a subtle bottom shadow; the Options nav rail, the
  StorylineCreator's two sidebars, and the Documents-page chrome sit on `velora-rail`
  (or `--surface`) so the center content zone reads as the light tier; Library column
  dividers upgrade to `border-hair-strong`; sticky ColumnHeader keeps an opaque `bg-page`.
  The story player (`StoryPlayerView`, `SceneHeader`, `Composer`, rails) is **not edited** —
  it inherits the token shift only.
- **Action:** `npx vitest run features components/layout` + typecheck + lint. Once green,
  commit: `Color Scheme Revamp (4/5) Complete: darker chrome zones + hard section boundaries on library/options/creator pages.`

### Phase 5 — Validation gate, docs, merge, cleanup

- **Locations:** `docs/design-system.md` (final deltas), `docs/checklist.md` (new entry),
  `docs/workflow.md` (contrast-script command), worktree merge.
- **Rationale:** the project's definition of done.
- **Work:** full `cd web/frontend && npm test` + `npm run typecheck` + `npm run lint` +
  `next build`; `uv run pytest` (expected untouched-green — no backend changes);
  `uv run python utils/scripts/check_contrast.py`; a11y/responsive pass — contrast via the
  script across all three themes, keyboard focus unchanged (`:focus-visible` outline is
  untouched), attempt a live `preview_start` pass and document the standing worktree/CORS
  deferral if blocked; write the checklist entry; merge the branch into `main`
  (`--no-ff`), resolve anything, and remove the worktree.
- **Action:** Full validation as above. Once green, commit:
  `Color Scheme Revamp (5/5) Complete: validation gate + docs; merged to main.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Re-tuned palettes | Three-tier (chrome/page/card) token sets for Parchment/Ember/Slate + interaction tokens | `web/frontend/styles/themes.css` |
| Token mapping | `--color-accent-hover/menu/menu-bd/hover/surface` Tailwind utilities | `web/frontend/app/globals.css` |
| Contrast gate | WCAG-AA checker over the theme tokens, CI-runnable | `utils/scripts/check_contrast.py` |
| Primitive polish | Decisive hover/active states | `web/frontend/components/ui/*.tsx` |
| Menu surface | `.velora-menu` + normalized rows across all seven dropdowns | `styles/themes.css`, `components/feature/*Menu*.tsx`, `PovSelect.tsx`, `components/ui/MultiSelect.tsx` |
| Section chrome | Rail-surfaced sidebars, header shadows, strong dividers | `components/layout/AppHeader.tsx`, `features/{options,library,documents}/…` |
| Updated tests | Class-assertion updates where hovers/surfaces changed | co-located `*.test.tsx` |
| Docs | Token table + layering rule; checklist entry; script command | `docs/design-system.md`, `docs/checklist.md`, `docs/workflow.md` |
