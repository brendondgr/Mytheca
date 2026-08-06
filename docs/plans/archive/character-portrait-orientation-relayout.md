# Plan — Portrait-Orientation Images + Profile/Card Relayout

## 1. Introduction

Three connected changes to the character surfaces, following the bolder profile
work already merged:

1. **Profile modal relayout** (`CharacterProfileModal`): widen the container and
   restructure the hero into two columns — a tall portrait on the **left**, and a
   **right** column holding name, role, trait pills, **Appearance**, and
   **Background**. The remaining four sections (**Personality, Voice, Goal,
   Secret**) move below into a **2×2 grid**.
2. **Portrait generation goes vertical**: character portraits are generated at
   **832×1216 (2:3 portrait)** instead of square 1024×1024. Scene art (scenarios +
   settings) is unchanged (landscape 1024×576). The frontend never passes
   dimensions, so the backend default constant is the single lever; the portrait
   display surfaces switch from `aspect-square` to the 2:3 ratio.
3. **Storyline character cards go taller** (`CharacterCard`, the Library
   "Characters" column): the card becomes portrait-dominant — a tall image area
   (2:3) with the character-color outline filling the card's vertical space so the
   picture is easy to see — name/role below or overlaid.

Backend touch is one constant + one test (`web/backend/app/services/portraits.py`,
`utils/tests/backend/services/test_portraits.py`). Everything else is frontend
(Next.js + React + Tailwind tokens). Theme-agnostic across Parchment / Ember /
Slate; AA contrast; keyboard-operable; verified at 320 / 375 / 768 / 1024.

Decisions confirmed with user: **2:3 (832×1216)** portrait ratio; profile right
column carries **Appearance + Background**, 2×2 below carries Personality / Voice
/ Goal / Secret.

## 2. Gaps & Unanswered Questions

- **Existing portraits** were rendered square; they'll be object-cover-cropped to
  2:3 in the new frames until regenerated. Acceptable (cover crop is centered);
  no migration/backfill of old images.
- **Container width:** the two-column hero + 2×2 grid needs more room — target
  ~`md:w-[860px] lg:w-[900px]`, still inside `max-w-[92vw]`; `max-h-[90vh]` +
  `overflow-auto` (already on `Modal`) handles tall content.
- **Card name/role placement:** name/role sit in a footer band **below** the
  image (not overlaid) to guarantee AA contrast without a scrim; the
  "◆ In this scene" highlight + edit pencil are preserved.
- **832×1216 divisibility:** both divisible by 8 (832/8=104, 1216/8=152) — valid
  latent grid. `ComfyParams` global width/height are not used by the portrait path
  (it passes the module constant), so no Options change is required.

## 3. Hierarchical Step-by-Step Instructions

### Step 1 (Phase 1): Portrait generation → 832×1216

- **Locations:** `web/backend/app/services/portraits.py` (`_PORTRAIT_W`,
  `_PORTRAIT_H`, module docstring + the inline comment),
  `utils/tests/backend/services/test_portraits.py` (the `== 1024` assertion).
- **Work:** set `_PORTRAIT_W = 832`, `_PORTRAIT_H = 1216`; update the docstring
  ("square 1024×1024" → "portrait 832×1216 (2:3)") and the comment; update the
  test to assert `width == 832 and height == 1216`.
- **Rationale:** the default constant is the only control on the portrait path
  (frontend sends no dimensions); changing it makes every new render vertical.
- **Action:** `uv run pytest utils/tests/backend/services/test_portraits.py` green.
  Commit: `[Portrait Orientation & Relayout] (1/4) Complete: Character portraits now generate at 832×1216 (2:3 portrait).`

### Step 2 (Phase 2): Profile modal two-column relayout

- **Locations:** `web/frontend/components/feature/CharacterProfileModal.tsx`.
- **Work:**
  - Widen the dialog (~`md:w-[860px] lg:w-[900px]`).
  - **Hero (2-col on `md+`, stacked below):** left = the framed portrait at the
    new 2:3 ratio (replace the fixed `size={108}` `Monogram` usage with a
    portrait-ratio frame — a `w`-driven box with `aspect-[2/3]`, character-color
    frame + inner hairline + `❖` medallion; portrait via `object-cover`, monogram
    fallback centered). Right = name, role eyebrow on a rule, trait pills, then the
    **Appearance** and **Background** `ProfileSection` boxes.
  - **Below hero:** a `grid sm:grid-cols-2` (the 2×2) with **Personality, Voice,
    Goal, Secret** (Secret keeps its danger tint; it no longer spans full width —
    it's one cell of the 2×2). Keep empty-skip behavior.
  - Edit button stays right-aligned at the bottom.
  - Responsive: hero stacks to one column below `md`; the 2×2 collapses to one
    column below `sm`.
- **Rationale:** matches the confirmed layout and gives the larger image room.
- **Action:** `npm run typecheck`; profile-modal tests updated in Phase 4 — at this
  point confirm typecheck + visually verify. Commit: `[Portrait Orientation & Relayout] (2/4) Complete: Profile modal hero split into portrait-left / identity+Appearance+Background-right with a 2×2 below.`

### Step 3 (Phase 3): Taller portrait-dominant character cards + portrait preview

- **Locations:** `web/frontend/components/feature/CharacterCard.tsx`,
  `web/frontend/components/feature/PortraitModal.tsx` (preview box),
  and a glance at `CharacterColumn.tsx` (grid still 2-up — adjust gap only if
  needed).
- **Work:**
  - **CharacterCard:** restructure to a vertical card — a top image area at
    `aspect-[2/3]` filling the card width with the **character-color outline**
    (portrait via `object-cover`; monogram-on-parchment fallback centered, large),
    then a footer band with name (Cinzel) + role eyebrow; preserve the edit pencil
    (top-right, over the image) and the "◆ In this scene" highlight (accent
    ring/border + label). Keep the whole card click → `onPreview` (no nested
    interactives — pencil is a sibling).
  - **PortraitModal preview:** swap `aspect-square w-[220px]` to the 2:3 ratio
    (e.g. `aspect-[2/3] w-[200px]`) so the preview matches what's generated.
- **Rationale:** the user wants the storyline card's picture to be large and easy
  to see; the preview must reflect the real output ratio.
- **Action:** `npm run typecheck`; visually verify the card grid + preview. Commit:
  `[Portrait Orientation & Relayout] (3/4) Complete: Portrait-dominant taller character cards + 2:3 portrait preview.`

### Step 4 (Phase 4): Tests, a11y/responsive pass, docs

- **Locations:**
  `web/frontend/components/feature/CharacterProfileModal.test.tsx` (and
  `CharacterCard` test if one exists / add light coverage),
  `utils/tests/backend/services/test_portraits.py` (done in Phase 1 — re-confirm),
  `docs/component-map.md`, `docs/design-system.md`, `docs/checklist.md`.
- **Work:**
  - Update profile-modal tests: still assert all sections render, traits split
    into pills, empty-skip, Edit; adjust any layout-coupled assertions for the new
    grouping (Appearance/Background in hero; Personality/Voice/Goal/Secret in the
    2×2). Add/adjust a `CharacterCard` test for the portrait/monogram fallback +
    name/role render if a suitable harness exists.
  - In-browser a11y + responsive pass (keyboard, focus, contrast, 320/375/768/
    1024) across all three themes; reduced-motion respected.
  - Docs: update the `CharacterProfileModal` + `CharacterCard` rows in
    `component-map.md`; note the portrait-orientation decision (832×1216, 2:3) and
    the card/profile treatment in `design-system.md`; record the work +
    portrait-ratio token in `checklist.md`.
- **Action:** `uv run pytest` (portrait service) + `npm test` (full Vitest) green;
  `npm run typecheck` clean. Commit: `[Portrait Orientation & Relayout] (4/4) Complete: Tests, a11y/responsive pass, and docs for portrait orientation + relayout.`

### Step 5 (Phase 5): Merge worktree → main

- **Locations:** repo root (git).
- **Work:** merge the feature branch into `main`, resolving conflicts (keep any
  unrelated in-progress changes intact); re-run `uv run pytest` (affected) +
  `npm test` + `npm run typecheck` on `main`.
- **Action:** clean merge + green checks → work is on `main` locally. No push / PR
  unless asked.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Portrait dimensions | Default render 832×1216 (2:3) | `web/backend/app/services/portraits.py` |
| Portrait service test | Asserts 832×1216 | `utils/tests/backend/services/test_portraits.py` |
| Profile modal relayout | Portrait-left hero + identity/Appearance/Background right; 2×2 below | `web/frontend/components/feature/CharacterProfileModal.tsx` |
| Taller character card | Portrait-dominant 2:3 card with color outline | `web/frontend/components/feature/CharacterCard.tsx` |
| Portrait preview ratio | 2:3 preview box | `web/frontend/components/feature/PortraitModal.tsx` |
| Frontend tests | Profile modal + card coverage | `web/frontend/components/feature/CharacterProfileModal.test.tsx` (+ card) |
| Docs | component-map / design-system / checklist | `docs/` |
| This plan | Phase-by-phase plan | `docs/plans/archive/character-portrait-orientation-relayout.md` |

## 5. Validation Gate

- Backend: `uv run pytest utils/tests/backend/services/test_portraits.py` (and any
  affected) green.
- Frontend: `npm run typecheck` clean; `npm test` (Vitest) green.
- Web/UI: a11y + responsive pass — keyboard, focus, AA contrast, 320/375/768/1024,
  across Parchment / Ember / Slate; reduced-motion respected.
- Commit per phase; merge worktree → main; no push/PR unless requested.
