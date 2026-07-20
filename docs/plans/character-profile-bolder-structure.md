# Plan — Bolder, More Structured Character Profile Card

## 1. Introduction

The read-only character profile modal (`CharacterProfileModal`) is the surface a
player sees when they open a character from the cast rail, the library, or a
monogram. Today it is a flat two-column grid of mono-label + prose pairs inside a
plain dialog. The user wants it **bolder and more defined/structured** — closer
to the attached reference: a framed hero portrait with a seal medallion, a large
Cinzel display name, a role title set off by a rule, trait "pills", and each
content section (Background, Appearance, Personality, Voice, Goal) living in its
own bordered box with a circular icon badge, with the Secret called out in a
distinct danger-tinted box beside the Edit action.

This is a **frontend-only, single-component redesign** built with the locked
Mytheca stack (Next.js + React + TypeScript + Tailwind tokens). It must stay
theme-agnostic across Parchment / Ember / Slate, keep WCAG AA contrast, stay
keyboard-operable, and read well at 320 / 375 / 768 / 1024 px. No backend, route,
contract, or data-model change is involved. Because the steps build on one
another (markup → sub-components → polish → validation) they are **sequential**,
so this is implemented directly rather than via a parallel agent workflow; the
work is still committed per phase.

**Scope (confirmed with user):** redesign `CharacterProfileModal` only. The
compact `CharacterCard` and `CastRail` rows are intentionally left unchanged.
**Trait pills (confirmed):** uniform bordered pills each led by the brand `◆`
glyph — robust for free-text traits — not a per-keyword icon map.

## 2. Gaps & Unanswered Questions

- **Per-trait icons (reference shows lightning/eye/shield/star):** traits are a
  single free-text string (`c.traits`, e.g. `"Energetic · Observant · …"`).
  Resolved: split on the `·`/`,` separators and render each token as a `◆`-led
  pill. No per-keyword icon mapping.
- **Compass medallion in the reference:** approximated with the Mytheca seal
  glyph (`❖`) in a small circular badge overlapping the portrait frame's bottom
  edge — on-brand and avoids shipping new art assets. Decorative (`aria-hidden`).
- **Drop-cap / oversized name:** the reference renders the name in large
  small-caps. Use Cinzel at a larger size with `.16em` letter-spacing rather than
  a true drop cap, to stay within the existing type system.
- **Section icons:** use single coherent glyphs already in the brand vocabulary
  (`❖`/`◆`) inside circular badges rather than introducing a new icon font.
- **Modal width:** the richer layout needs more room than the current
  `sm:w-[560px]`; widen to roughly `sm:w-[640px]` and verify it still fits
  `max-w-[92vw]` on small screens (Modal already caps width/height).

## 3. Hierarchical Step-by-Step Instructions

### Step 1 (Phase 1): Restructure the profile modal — hero + section boxes

- **Locations:** `web/frontend/components/feature/CharacterProfileModal.tsx`.
- **Work:**
  - Replace the flat header + grid with a structured layout:
    - **Hero block:** larger framed portrait (decorative double border using
      `--card-bd` + an inner hairline, `box-shadow` per the elevation tokens) with
      a small circular `❖` seal medallion overlapping the bottom edge; the
      `Monogram` (portrait or initials fallback) sits inside the frame at a larger
      size. Beside it: large Cinzel name, a role title with a trailing hairline
      rule, and a **trait-pill row** (split `c.traits` on `·`/`,`, render each as
      a `◆`-led bordered pill; render nothing if `traits` is empty).
    - **Section boxes:** introduce a local `ProfileSection` sub-component (replaces
      `ProfileCell`) rendering a bordered box (`border-cardbd`, `bg-card2`, manuscript
      radius, subtle shadow) with a circular icon badge + Cinzel/eyebrow section
      header and the prose below. Keep the empty-skip behavior (`return null` when
      the value is falsy).
    - **Layout:** Background full-width first; Appearance | Personality and
      Voice | Goal in a responsive 2-col grid that collapses to 1 col below `sm`.
    - **Secret + Edit footer:** Secret in a distinct danger-tinted box
      (`text-danger`/accent border + faint tint) spanning full width, with the
      `Edit Character` button right-aligned (kept gated on `onEdit`).
  - Widen the dialog (`className="sm:w-[640px]"`) and keep `CloseButton`.
- **Rationale:** This is the core visual change and the one the screenshot
  illustrates; everything else is polish on top of this structure.
- **Action:** Run `npm run typecheck` and `npm test -- CharacterProfileModal`
  (tests updated in Phase 3 — at this point confirm typecheck + existing tests
  that still apply). Commit: `[Character Profile Bolder Structure] (1/3) Complete: Restructured profile modal into framed hero + bordered section boxes.`

### Step 2 (Phase 2): Theme, motion, responsive & a11y polish

- **Locations:** `web/frontend/components/feature/CharacterProfileModal.tsx`
  (and, only if a token gap is found, `web/frontend/styles/themes.css` /
  `app/globals.css` — avoid if existing tokens suffice).
- **Work:**
  - Verify all colors come from tokens (`bg-card`, `bg-card2`, `border-cardbd`,
    `border-hair`, `text-ink`, `text-ink-soft`, `text-mute`, `text-gold`,
    `text-danger`, character `color`) so all three themes work; no hardcoded
    theme colors. Section icon badges use `--gold` accent; Secret uses
    `--accent`/`--danger`.
  - Decorative glyphs (`❖`, `◆`, section badges) are `aria-hidden`; the name keeps
    `id="profile-name"` for `aria-labelledby`; portrait alt text preserved.
  - Confirm contrast AA in Parchment/Ember/Slate; ensure trait pills and section
    headers meet 4.5:1 (body) / 3:1 (large/non-text).
  - Responsive: 2-col section grid → 1 col under `sm`; hero stacks (portrait above
    text) on the narrowest widths; check 320/375/768/1024.
  - Honor reduced motion (rely on existing Modal `embPop` + `motion-reduce`;
    add no new always-on motion).
- **Rationale:** Mytheca's validation gate requires a theme + a11y + responsive
  pass for any UI change; doing it as its own phase keeps the structural diff
  reviewable.
- **Action:** Manual a11y + responsive pass (keyboard, focus, contrast,
  320/375/768/1024 in all three themes) via the dev server/preview; `npm run
  typecheck`. Commit: `[Character Profile Bolder Structure] (2/3) Complete: Theme-agnostic, accessible, responsive polish for the redesigned profile.`

### Step 3 (Phase 3): Tests + docs

- **Locations:**
  `web/frontend/components/feature/CharacterProfileModal.test.tsx`,
  `docs/design-system.md`, `docs/checklist.md`,
  `docs/component-map.md` (only if the modal's description there needs updating).
- **Work:**
  - Update/extend the existing Vitest suite so it still asserts: prose renders,
    portrait replaces initials, traits appear (now as split pills — assert each
    trait token is present), empty fields are skipped, Edit button shows/hides and
    fires `onEdit`. Add a case for the trait-pill split (e.g. `"Patient ·
    Calculating"` → two pills) and the Secret box rendering.
  - Note the redesigned profile treatment in `docs/design-system.md` (a short
    line under the relevant section) and record any deferred a11y item in
    `docs/checklist.md`.
- **Rationale:** Tests are required by the planner gate; docs must change in the
  same change that alters the visual treatment.
- **Action:** `npm test -- CharacterProfileModal` green; `npm run typecheck`
  clean; full `npm test` for regressions. Commit: `[Character Profile Bolder Structure] (3/3) Complete: Updated tests and design-system docs for the bolder profile card.`

### Step 4 (Phase 4): Merge worktree → main

- **Locations:** repo root (git).
- **Work:** if implemented in a worktree, merge the feature branch into `main`,
  resolving any conflicts (notably the pre-existing uncommitted
  `web/frontend/components/ui/MultiSelect.tsx` change on `main` — keep it intact).
  Re-run `npm run typecheck` + `npm test` on `main` after the merge.
- **Action:** After a clean merge and green checks, the branch work is on `main`
  locally. **No push / PR** unless the user asks.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Redesigned profile modal | Framed hero portrait + seal medallion, large name, trait pills, bordered section boxes, distinct Secret box | `web/frontend/components/feature/CharacterProfileModal.tsx` |
| Updated component tests | Prose/portrait/traits-as-pills/empty-skip/Secret/Edit coverage | `web/frontend/components/feature/CharacterProfileModal.test.tsx` |
| Design-system note | Short note recording the bolder profile treatment | `docs/design-system.md` |
| Checklist update | Any deferred a11y/responsive item recorded | `docs/checklist.md` |
| This plan | Phase-by-phase implementation plan | `docs/plans/character-profile-bolder-structure.md` |

## 5. Validation Gate

- Frontend: `npm run typecheck` clean; `npm test` (Vitest) green, including the
  updated `CharacterProfileModal` suite.
- Web/UI: accessibility + responsive pass — keyboard operability, visible focus,
  AA contrast, layout at 320 / 375 / 768 / 1024 px, across Parchment / Ember /
  Slate, reduced-motion respected.
- No backend change → `pytest` not applicable (state this explicitly at handoff).
- Commit per phase; merge worktree → main; no push/PR unless requested.
