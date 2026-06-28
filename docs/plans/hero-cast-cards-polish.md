# Hero Cast Cards — gaps, color glow, solid statistics, cast carousel

## 1. Introduction

The recent-scenario **hero** (`web/frontend/components/feature/ScenarioCarousel.tsx`) renders, beside the
left scene-art panel, a horizontally-scrolling strip of **full-bleed portrait cards** — one per cast
member. Four issues with that cast strip were reported:

1. The character cards are flush against each other (separated only by a `border-r` hairline), so they
   read as one continuous band rather than discrete cards.
2. The cards have no per-character identity in their framing — the reference target gives each card an
   **outer glow keyed to the character's accent color**.
3. The **Statistics** block at the bottom of each card is laid over the portrait scrim (semi-transparent),
   so the artwork bleeds through and the text fights the image.
4. When a scenario has many cast members the strip just scrolls horizontally with a thin scrollbar; the
   user wants an explicit **carousel with left/right arrows** that appear only when the cast overflows the
   visible width.

This is a **frontend-only, single-component** change (plus its co-located test and the two docs that
describe the hero). No backend, data-shape, API, or route change. The cast strip stays inside the existing
outer scenario carousel; only the inner cast presentation changes. Because all four fixes live in the same
component and the carousel logic builds on the new card framing, the phases are **sequential** (not
independent), so they are implemented in one focused branch with a commit per phase rather than fanned out
across parallel agents.

## 2. Gaps & Unanswered Questions

- **Glow color source (simple gap → assume):** each resolved `Character` already carries `color` (hex
  accent, surfaced as `c.color`). The outer glow + card border will be derived from it via a soft
  `box-shadow` and a low-alpha colored border. No new data needed.
- **"Colored background" for Statistics (simple gap → assume):** the request says the Statistics area must
  not be see-through and should have a colored background. Interpreted as: the whole bottom footer
  (name / role / Statistics) sits on a **solid dark panel tinted with the character's accent** (via
  `color-mix`), and the Statistics sub-block gets its own slightly-distinct inset panel + top hairline so it
  reads as a labeled section — matching the reference image.
- **Arrow visibility heuristic (simple gap → assume):** arrows appear only when the cast strip actually
  overflows its visible width (`scrollWidth > clientWidth`), and each arrow hides at its respective end
  (left hidden at scroll start, right hidden at scroll end). Overflow is measured from the DOM (layout
  effect + `ResizeObserver` when available + window-resize + scroll listeners); in jsdom (no layout) the
  arrows stay hidden, so existing tests are unaffected. The arrows page the strip by ~85% of the visible
  width via `scrollBy({ behavior: "smooth" })`, preserving native keyboard/trackpad scroll.
- **Per-card width / height (simple gap → assume):** keep the current `~250–282px` card width; card height
  becomes `container height − vertical track padding` so the gap shows on the top and bottom edges too.
- **No new dependency, env var, route, or contract.** Nothing for `docs/routes.md`, `docs/api-contract.md`,
  `docs/data-flow.md`, or `docs/structure.md`.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1: Gaps on all edges + per-character color glow

- **Locations:** `web/frontend/components/feature/ScenarioCarousel.tsx` — the cast-strip container
  (`overflow-x-auto` row) and each cast card (`div.group...border-r`).
- **Work:**
  - Convert the cast row from a flush `flex` with `border-r` dividers into a **gapped track**: add
    `gap-[14px]` + uniform padding (`p-[14px]`) so every card has space on all four edges (the track
    padding handles top/bottom + the leading/trailing edges; `gap` handles between-card spacing). Drop the
    per-card `border-r` and the trailing spacer.
  - Make each card a **discrete rounded tile**: `rounded-[8px]` + `overflow-hidden` so the full-bleed
    portrait clips to the rounded corners.
  - Add a per-character **outer glow + colored hairline border** via inline `style` keyed to `c.color`
    (soft multi-layer `box-shadow`: a tight accent ring + a wider low-alpha accent glow + a neutral drop
    shadow for depth). Keep the hover lift behavior.
- **Rationale:** Separating the cards is the foundation the solid footer (Phase 2) and the carousel paging
  (Phase 3) sit on; the glow gives each card its character identity per the reference.
- **Action:** Run validation for this phase — `npm run typecheck`, `npm run lint`, `npm test`
  (`ScenarioCarousel.test.tsx` + suite), `npm run build`. Web/UI a11y + responsive reasoning pass
  (contrast unchanged; layout still horizontally scrollable, no new interactive elements yet). Once green,
  commit: `[Hero Cast Cards Polish] (1/4) Complete: Gapped, rounded cast cards with per-character color glow.`

### Phase 2: Solid colored Statistics / footer panel

- **Locations:** `web/frontend/components/feature/ScenarioCarousel.tsx` — the card footer
  (`relative z-[1] mt-auto ...` block holding name / role / divider / Statistics) and its bottom scrim.
- **Work:**
  - Give the footer a **solid background** tinted with the character accent
    (`color-mix(in srgb, c.color N%, <fixed dark>)`) so the portrait no longer shows through behind the
    name / role / Statistics. Add a thin accent top hairline so the footer reads as a deliberate plate.
  - Wrap the **Statistics** eyebrow + empty-state line in their own **inset panel** (slightly distinct
    background + top hairline + small radius/padding) so the "Statistics" block has the requested
    non-transparent colored background and reads as a labeled section.
  - Re-tune the portrait scrim above the footer to a gentle top→bottom fade that blends the image into the
    now-opaque footer (the heavy near-opaque bottom band is no longer needed since the footer is solid).
  - Re-verify the name's `color-mix(... , #F6ECDA)` lightening still clears AA over the new **solid** footer
    background (it sits on an opaque dark tint now, which is easier than over bright art).
- **Rationale:** A solid footer fixes the see-through Statistics complaint and makes the text legible
  independent of the portrait behind it.
- **Action:** Run validation for this phase — `npm run typecheck`, `npm run lint`, `npm test`,
  `npm run build`; a11y contrast check on name/role/Statistics over the solid footer (AA). Once green,
  commit: `[Hero Cast Cards Polish] (2/4) Complete: Solid accent-tinted footer with a non-transparent Statistics panel.`

### Phase 3: Cast carousel with left/right arrows

- **Locations:** `web/frontend/components/feature/ScenarioCarousel.tsx` — wrap the cast strip in a
  `relative` container; add a small local overflow-tracking hook (or inline `useRef` + `useState` +
  `useLayoutEffect`/listeners) and two overlaid arrow buttons.
- **Work:**
  - Add a `useRef` on the scroll row and track `{ overflow, atStart, atEnd }` derived from
    `scrollWidth / clientWidth / scrollLeft`. Recompute on mount (layout effect), on the row's `scroll`
    event, on window `resize`, and via `ResizeObserver` when it exists (guarded — jsdom lacks it).
  - Render a **left** arrow (hidden unless `overflow && !atStart`) and a **right** arrow (hidden unless
    `overflow && !atEnd`), absolutely positioned at the cast strip's left/right edges, vertically centered,
    styled with the existing gold chevron treatment (`HERO.chev` / `HERO.label`), `aria-label`
    `"Previous characters"` / `"Next characters"`. Clicking calls `scrollBy({ left: ±0.85*clientWidth,
    behavior: "smooth" })`.
  - Keep the native horizontal scroll (keyboard/trackpad) intact for accessibility; arrows are an
    additive affordance. Ensure arrows don't overlap the per-slide active/`inert` logic (they live inside
    the slide so non-active slides' arrows are `inert` too).
- **Rationale:** Delivers the requested explicit carousel while preserving native scroll and keeping the
  arrows out of the way when everything fits.
- **Action:** Run validation for this phase — `npm run typecheck`, `npm run lint`, `npm test` (new cast-
  carousel test: arrows appear when overflow is forced, call `scrollBy`, and stay hidden when content fits),
  `npm run build`; a11y pass (arrow buttons are labeled `<button>`s, keyboard-reachable, visible focus
  ring; native scroll still works). Once green, commit:
  `[Hero Cast Cards Polish] (3/4) Complete: Cast strip becomes an arrow-paged carousel on overflow.`

### Phase 4: Tests, docs, validation sweep, merge

- **Locations:** `web/frontend/components/feature/ScenarioCarousel.test.tsx`; `docs/component-map.md`
  (the `ScenarioCarousel` row); `docs/design-system.md` (the recent-scenario hero paragraph);
  `docs/checklist.md` (a "done" entry).
- **Work:**
  - Finalize/extend `ScenarioCarousel.test.tsx`: keep the existing 7 cases green; add cases for the gapped
    card framing, the solid Statistics panel, and the cast-carousel arrows (overflow-forced visible +
    `scrollBy` wiring + hidden-when-fits). Total target ≈ 10 cases.
  - Update `docs/component-map.md` and `docs/design-system.md` so the hero description matches the new
    gapped/glowing cards, solid Statistics panel, and arrow-paged cast carousel.
  - Add a `docs/checklist.md` "Follow-up Work" entry summarizing the change, validation results, and any
    deferred live a11y/responsive pass (per the standing shared-dir dev-server constraint).
  - Full frontend validation sweep; then **merge the branch into `main`**, resolving any conflicts (the
    working tree has an unrelated uncommitted `MultiSelect.tsx` edit — keep it out of these commits).
- **Rationale:** Locks the behavior with tests and keeps `docs/` the source of truth; the merge completes
  the worktree workflow.
- **Action:** Run the full validation for this phase — `npm run typecheck`, `npm run lint`, `npm test`
  (full suite), `npm run build`; backend untouched → `pytest` N/A (state this explicitly). a11y +
  responsive reasoning pass documented. Once green, commit:
  `[Hero Cast Cards Polish] (4/4) Complete: Tests + docs for the hero cast-card refresh; merged to main.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Gapped, glowing cast cards | Rounded discrete tiles with all-edge gaps + per-character `box-shadow` glow keyed to `c.color` | `web/frontend/components/feature/ScenarioCarousel.tsx` |
| Solid Statistics footer | Accent-tinted opaque footer + inset non-transparent Statistics panel | `web/frontend/components/feature/ScenarioCarousel.tsx` |
| Cast carousel arrows | Overflow-tracked left/right arrow paging over the cast strip (native scroll preserved) | `web/frontend/components/feature/ScenarioCarousel.tsx` |
| Component tests | Existing 7 cases + new framing / Statistics-panel / arrow cases (≈10) | `web/frontend/components/feature/ScenarioCarousel.test.tsx` |
| Docs | Hero description refreshed (component map + design system) + checklist entry | `docs/component-map.md`, `docs/design-system.md`, `docs/checklist.md` |

**Validation gate (all phases):** frontend `tsc` + ESLint + Vitest + `next build` green. Backend untouched →
`uv run pytest` N/A. Web/UI a11y + responsive reasoning pass per `accessibility-mobile` + `ada-compliance`
(labeled arrow buttons, visible focus, AA contrast over the solid footer, native scroll fallback); live
320/375/768/1024 in-browser pass deferred under the standing shared-working-dir dev-server constraint and
recorded in `docs/checklist.md`.
