# Frontend Polish — Motion, Loading, and Responsiveness

**Status:** planned 2026-08-12 · branch `claude/frontend-polish-ui-2275c7`
**Contract:** `docs/frontend-polish-spec.md` (§ references throughout point at that file)

## 1. Introduction

Mytheca's visual language is finished and locked (`docs/design-system.md`, derived from
`docs/CharacterFrontpage/`). What is *not* finished is the layer underneath it: the app was
assembled screen-by-screen, so every screen invented its own timing, its own idea of what
"loading" looks like, and its own breakpoints. The result reads as a scaffold wearing a good
skin — durations range from 0.12s to 2.6s with no system behind them, **no surface in the app
has a skeleton**, most async paths render nothing at all while pending, images pop in without
reserving space, hover states stick on touch devices, and the story transcript force-scrolls to
the bottom while you are reading earlier beats.

This plan implements the polish spec as a **structural pass**, not a re-skin. The token values,
themes, typography, and component silhouettes in `docs/design-system.md` do not change. What
changes is the machinery: a global motion token system every component references, a loading
state ladder with a 300 ms delay gate and real skeletons, per-container responsiveness, a
disciplined streaming-text surface, and the interaction states (`hover`/`focus-visible`/
`active`/`disabled`) that make a surface feel like it acknowledges the user.

Seven phases, each independently shippable, each ending in a local commit. Phases 1–3 build
the foundation (tokens · primitives · async infrastructure); phases 4–6 apply it to the real
surfaces; phase 7 verifies against the spec's §14 acceptance checklist and reconciles the docs.

---

## 2. Gaps & Unanswered Questions

### Assumptions taken (simple gaps)

1. **"Full overhaul" means structure, not re-skin.** The user wrote that the app "does have a
   decent stylistic look" but "wasn't actually assembled with the end user in mind." That
   matches the spec's scope exactly. **No theme token, font, or color changes** — those are
   locked and gated by `utils/scripts/check_contrast.py`. If a visual redesign is also wanted,
   that is a separate, conflicting request against the locked design system and needs a human
   decision first.
2. **Tokens live in `styles/themes.css`, surfaced through `@theme inline`.** The spec's
   Appendix suggests `@layer tokens`; Mytheca already has an established variable-in-themes.css
   → Tailwind-utility pipeline, and introducing a second mechanism would create the "two
   competing copies" the project rules forbid. Same values, existing plumbing.
3. **Framer Motion stays.** Spec §12 leans toward dropping animation libraries; the Mytheca
   stack is locked to Framer Motion 12 and GSAP is banned. Framer keeps the jobs it is good at
   (`AnimatePresence` exits, layout animations); everything the platform can do — hovers,
   fades, skeleton shimmer, reveals — moves to CSS referencing the new tokens.
4. **The spec's blanket reduced-motion reset is *not* adopted verbatim.** `styles/themes.css`
   already carries a stronger, repo-wide rule (`.mytheca-themed *` → `animation: none
   !important`) and the codebase's documented idiom is to put the resting state in the base
   style so stripping the animation degrades gracefully (`.mytheca-glow`,
   `.mytheca-field-active`, `.mytheca-wash`). Adding the spec's `*` reset on top would be a
   duplicate. Deviation recorded in `docs/design-system.md`.
5. **The signature motion moment is the `SceneLoader` curtain** dissolving into the scene —
   it already exists, it is the one place the product earns a flourish (the scene is being
   conjured), and it is the only full-screen motion in the app. Everything else gets quiet and
   fast. Per spec §11's restraint rule, one is the budget.

### Deviations flagged (stated, not silently dropped)

6. **Scroll-driven reveals (§6) apply to almost nothing here.** Mytheca has no long scrolling
   page: `/` (Library), the story player, and the creator are all `h-dvh` self-contained
   shells whose *columns* scroll, not the root. `animation-timeline: view()` therefore needs
   `view()` inside a named scroller, and a scroll progress bar on `scroll(root)` has no root
   scroll to measure. **Applied narrowly** to the Library's independently-scrolling card
   columns and the documents table; the scroll progress bar and parallax are **skipped as
   inapplicable**, not forgotten.
7. **Cross-document view transitions (§7) are skipped.** Next.js App Router navigations are
   client-side, so `@view-transition { navigation: auto }` never fires. Next 16's
   `experimental.viewTransition` is opt-in and unproven here; adding it is a stack change
   requiring a record in `docs/architecture.md`. Deferred to `docs/checklist.md` rather than
   speculatively enabled.
8. **`@starting-style` for modals (§7) is adopted**, replacing the `embPop`/`embDim` keyframes
   — this is what finally gives modals an animated *exit*, which they have never had.

### Needs human input (complex gap)

9. **Mobile rails.** `docs/checklist.md` lists "rails are hidden below `lg`; mobile drawers are
   unbuilt" as a known limitation, and "the context rail is very cramped below `lg`". Making
   the app genuinely usable on a phone means building those drawers — a *new feature*, not
   polish, and a meaningful surface-design decision (drawer vs. bottom sheet vs. tab switcher).
   **Human intervention is needed to answer this question.** This plan makes every existing
   surface correct at 320–2560 px and does not invent the drawers; the item stays open in
   `docs/checklist.md`.

---

## 3. Step-by-Step Instructions

### Phase 1 — The motion & responsive token layer

Nothing else in the plan can be consistent until there is one place that defines timing.

- **Locations:**
  - `docs/frontend-polish-spec.md` — new; the contract, checked into the repo so it is
    referenceable (the spec's own "How to use it" asks for this). Pointer row added to
    `CLAUDE.md`'s docs table and to `docs/skills/ui-frontend/SKILL.md`.
  - `web/frontend/styles/themes.css` — new `:root` token block: `--dur-instant|fast|base|slow|
    ambient`, `--ease-out|in|soft|spring`, `--lift-sm|md|lg`, `--gutter`, and the fluid type
    steps `--step-0|1|2|3`. Then **rewrite the five existing transition rules**
    (`.mytheca-page`, `.mytheca-card`, `.mytheca-row`, `.mytheca-themed button`) and the three
    keyframe-driven classes (`.mytheca-glow`, `.mytheca-field-active`, `.mytheca-wash`) to
    reference the tokens instead of their literal `0.14s` / `0.6s` / `2.2s` / `2.6s` values.
  - `web/frontend/app/globals.css` — extend `@theme inline` so Tailwind resolves the tokens:
    `--animate-duration-*`/`--ease-*` mappings giving `duration-fast`, `duration-base`,
    `duration-slow`, `ease-out-soft`, plus `--spacing-gutter` and the `--text-step-*` scale.
    Add the base-layer rules the spec's Appendix requires that Mytheca lacks: `text-wrap:
    pretty` on body, `text-wrap: balance` on headings, `overflow-wrap: break-word`,
    `scroll-margin-block-start` on anchor targets, `[aria-busy="true"] { cursor: progress }`,
    and `:where(img,video,svg){max-width:100%;display:block}`.
  - `web/frontend/styles/motion.css` — new, imported by `globals.css`: the shared motion
    utilities that are pure CSS — `.stagger` (capped at 8 items per §2), `.content-enter`,
    `.skeleton` + `skeleton-sweep`, `.tok` (streamed-token fade), `.hover-lift` gated behind
    `@media (hover: hover) and (pointer: fine)`, and `.press` (`:active` scale 0.985 at
    `--dur-instant`).
- **Rationale:** Every later phase references these names. Doing the token rewrite first means
  phases 2–6 delete hardcoded values as they touch files rather than adding new ones.
- **Validation & commit:** `npm run typecheck` + `npm run lint` + `npm test` (no behavior
  change expected — the suite is the regression net for the transition rewrites), and
  `uv run python utils/scripts/check_contrast.py` to prove no color token moved. Commit:
  `[Frontend Polish] (1/7) Complete: Added the motion/responsive token system and rewrote every hardcoded duration in the stylesheets.`

---

### Phase 2 — Primitives: the four interaction states, on everything

Spec §1.3 / §5 / §13. Today `IconButton`, `CloseButton`, and `ToggleChip` have no `:active`
and no `:disabled` treatment at all, no `hover:` in the app is gated for touch, and several
controls are well under the 44 px touch target.

- **Locations:** `web/frontend/components/ui/` —
  - `Button.tsx` — move hover behind `@media (hover: hover)` via the `.hover-lift` class;
    add the **`loading` variant** (§13): spinner replaces the label with the button's width
    pinned, `aria-busy`, `disabled`. Durations from tokens.
  - `IconButton.tsx` — add `:active` press, `disabled:` (opacity + `cursor-not-allowed` + no
    hover transform), gate hover, and give the 24 px default a **44 px hit area** via a
    centered `::before` overlay so the visual size is unchanged (`min-h`/`min-w` would break
    the dense card/rail layouts).
  - `CloseButton.tsx` — same treatment; the current `hover:scale-110` with no `:active` and no
    box is the worst offender.
  - `ToggleChip.tsx`, `Chip.tsx`, `Tag.tsx` — press state + disabled; `user-select: none` on
    labels (§5).
  - `TextField.tsx`, `TextArea.tsx` — focus ring, and the error-text slot that animates in
    **without shifting the field below it** (reserved line box, §13).
  - `MultiSelect.tsx`, `SceneControlSelect.tsx` — origin-aware `transform-origin` popover
    transitions (`--dur-base` in / `--dur-fast` out, §13).
  - `Modal.tsx` — replace `animate-[embPop_.2s_ease]`/`embDim` with `@starting-style` +
    `transition-behavior: allow-discrete`, giving modals a real **exit** animation for the
    first time; swap `max-h-[90vh]` → `max-h-[90dvh]`; give the `externalClose` button an
    `:active` state.
  - `Toast.tsx` — auto-dismiss with a **visible progress indicator**, pause on hover, and
    position transitions when the stack shifts (§13).
  - Co-located tests updated/added for each: `Button.test.tsx` (loading variant keeps width,
    sets `aria-busy`), `IconButton.test.tsx` (new — disabled has no hover transform, hit area
    ≥ 44 px), `CloseButton.test.tsx` (new), `Toast.test.tsx` (pause on hover).
- **Rationale:** Primitives are used by all 48 feature components; fixing them once fixes the
  press/disabled/touch-target gap across the app instead of 48 times.
- **Validation & commit:** `npm test`, `npm run typecheck`, `npm run lint`; keyboard pass over
  each primitive in the test suite (Tab reaches, Enter/Space activates, `:focus-visible`
  present, Escape closes the modal, focus restored). Commit:
  `[Frontend Polish] (2/7) Complete: Gave every UI primitive hover/focus/active/disabled states, 44px touch targets, and animated modal exits.`

---

### Phase 3 — Async state ladder infrastructure

Spec §3. The app has **zero skeletons** and no delay gate; the only "gate" is a 2200 ms fixed
sleep before revealing the scene, which is the opposite of the pattern.

- **Locations:**
  - `web/frontend/hooks/use-delayed-flag.ts` — new. The 300 ms gate from §3, plus a companion
    `useAsyncState` returning the discriminated `idle | loading | success | error | empty`
    union so every call site is forced to name all five.
  - `web/frontend/components/ui/Skeleton.tsx` — new. `<Skeleton.Line>` (with the §3 rule that
    the last line of a block runs 55–70 % width), `<Skeleton.Block>`, `<Skeleton.Card>`;
    `aria-hidden` on the bars, `aria-busy` on the container, and the **10–15 s timeout** that
    swaps in the error state so a shimmer can never hide a dead request.
  - `web/frontend/components/ui/AsyncPanel.tsx` — new. The shared shell that renders the five
    states with Mytheca's voice: the error state names what failed and carries a **Retry**
    control; the empty state carries its **primary action inline** (never a blank panel); both
    enter with the same `.content-enter` animation as success, per §3.
  - `web/frontend/components/ui/SmartImage.tsx` — new. Reserves space via a required
    `aspect` prop, fades in on `load`, and **checks `img.complete` on mount** so cached images
    do not stay invisible (the exact bug §3 calls out); `loading="lazy"` + `decoding="async"`
    by default with an `eager` opt-out for the LCP image.
  - Co-located tests: `Skeleton.test.tsx` (times out into an error, bars are `aria-hidden`),
    `AsyncPanel.test.tsx` (all five states; retry fires), `SmartImage.test.tsx` (cached-image
    path sets `data-loaded` without a `load` event), `use-delayed-flag.test.ts` (nothing
    renders before 300 ms).
- **Rationale:** Building the ladder once as primitives means phase 4 is mechanical
  application rather than 20 bespoke loading treatments — which is how the current
  inconsistency arose.
- **Validation & commit:** `npm test` (new suites), `npm run typecheck`, `npm run lint`.
  Commit: `[Frontend Polish] (3/7) Complete: Added the async state ladder — 300ms delay gate, timing-out skeletons, AsyncPanel, and SmartImage.`

---

### Phase 4 — Apply the ladder to every async surface

- **Locations (each gets idle/loading/success/error/empty + the delay gate):**
  - `web/frontend/features/library/LibraryView.tsx` + `LibraryColumns.tsx` — replace "Loading
    your library…" with column skeletons that **mirror the real card shapes** (scenario rows,
    2:3 character tiles, setting rows); empty columns get their create action inline.
  - `web/frontend/features/documents/DocumentsView.tsx` + `components/feature/DocumentsTable.tsx`
    — skeleton rows (§13 Tables), empty state with the upload action inline, error with retry.
  - `web/frontend/components/feature/GraphView.tsx` — the text-only "Reading the story graph…"
    becomes a canvas-shaped skeleton; keep the existing offline/empty/retry states.
  - `web/frontend/components/feature/PortraitModal.tsx`, `SceneArtModal.tsx`,
    `PromptOverridesModal.tsx` — errors currently require closing and reopening the modal;
    add inline **Retry**.
  - `web/frontend/components/feature/EntityModal.tsx`, `CharacterModal.tsx`, `SettingModal.tsx`
    — save/delete currently change only the button label; switch to the `Button` `loading`
    variant and mark the panel `aria-busy`.
  - `web/frontend/features/story-player/useScenePlay.ts` — the fixed **2200 ms** reveal sleep
    becomes a real readiness signal gated by `useDelayedFlag`, so a fast load reveals
    immediately instead of always waiting (§3: the fastest loading state is the one that never
    appears; §11: a spinner for a 150 ms request feels *slower* than nothing).
  - **All image call sites → `SmartImage`:** `CharacterCard`, `SettingCard`, `ScenarioCard`,
    `ScenarioCarousel`, `CharacterDossier`, `CharacterProfileModal`, `SceneImageBeat`,
    `SceneArtModal`, `PortraitModal`, `BuildWorldModal`, `SceneLoader`. `SettingCard` and
    `ScenarioCard` currently paint art into `absolute inset-0` with no reserved ratio.
  - Co-located tests updated for each touched component; new
    `LibraryColumns.skeleton.test.tsx`-style cases asserting the skeleton's card count matches
    the real render (§3.1 — a skeleton showing 3 cards when 7 arrive breaks trust).
- **Rationale:** This is where the user-visible "it feels unfinished" complaint actually lives.
- **Validation & commit:** `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`
  (worktree note: `next build` needs a real `node_modules`, not a symlink). Manual pass with
  the network throttled so each ladder rung is observed. Commit:
  `[Frontend Polish] (4/7) Complete: Every async surface now renders idle/loading/success/error/empty with skeletons, retries, and space-reserved images.`

---

### Phase 5 — Streaming text discipline (the story player)

Spec §4. This is the product's signature surface and the one with the worst offender in the
app: `StoryPlayerView.tsx:63-66` sets `scrollTop = scrollHeight` unconditionally on every new
beat — spec §11 calls auto-scrolling a user who is reading above "actively hostile."

- **Locations:**
  - `web/frontend/features/story-player/use-sticky-bottom.ts` — new hook: sticks to the bottom
    **only while the user is already there** (64 px tolerance, per §4.5), releases the moment
    they scroll up, and exposes the state that drives a **"Jump to latest" pill**.
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — adopt the hook; add the pill;
    set `overflow-anchor: none` on the viewport; give the streaming assistant beat a
    `min-height` of a few lines so the composer does not jump when the first token lands (§4.8).
  - `web/frontend/components/feature/JumpToLatest.tsx` — new; the pill, keyboard-reachable.
  - `web/frontend/components/feature/TranscriptBeat.tsx` — wrap newly-arrived text in the
    `.tok` blur-to-sharp fade; add the 2 px block **caret** at the tail during streaming
    (removed on completion, blink disabled under reduced motion, §4.4).
  - **Live-region fix:** the transcript container is `aria-live="polite"` with
    `aria-relevant="additions"` around *streaming deltas*, so a screen reader is told about
    text that is still growing. Move the announcement to **completion** per §9 — announce the
    finished beat, not every delta.
  - `web/frontend/features/story-player/useScenePlay.ts` — buffer incoming NDJSON deltas and
    flush on a ~30–50 ms tick instead of a `setState` per frame (§4.2), and distinguish the
    four states `submitted → thinking → streaming → complete` visually (the Cast rail's
    Thinking/Speaking labels already carry two of them).
  - Tests: `use-sticky-bottom.test.ts` (new — does not scroll when the user is 200 px up; does
    when within 64 px), `StoryPlayerView.test.tsx` (pill appears/disappears; announcement fires
    once per completed beat, not per delta).
- **Rationale:** Reading is the whole product. A transcript that yanks itself away mid-sentence
  is the single most damaging interaction defect in the app.
- **Validation & commit:** `npm test`, `npm run typecheck`; a live streaming pass against a
  running backend, scrolling up mid-turn to confirm the transcript holds and the pill appears;
  screen-reader announcement check. Commit:
  `[Frontend Polish] (5/7) Complete: Sticky-bottom autoscroll with a Jump-to-latest escape hatch, buffered token flushing, and announce-on-completion.`

---

### Phase 6 — Responsiveness: container-first, fluid, 320 px clean

Spec §8. There are currently **zero container queries**, **zero `clamp()`**, and four `vh`
uses that break with mobile browser chrome.

- **Locations:**
  - `web/frontend/components/feature/` cards — `CharacterCard`, `SettingCard`, `ScenarioCard`,
    `CharacterDossier` become **container-query driven** (`container-type: inline-size` on the
    wrapper) so a card put in a rail reshapes on its own width, not the viewport's. This is the
    structural fix behind "a card that changes shape based on the viewport is broken the moment
    you put it in a sidebar."
  - `styles/themes.css` — the `--step-*` fluid scale from phase 1 is applied to the headings
    and the `--gutter` rhythm; the six `--fs-*` preset variables stay as-is (they are the
    user's *explicit* size preference and must keep winning).
  - **`vh` → `dvh`:** `components/ui/Modal.tsx:120`, `components/feature/SceneImageModal.tsx:46`,
    `components/feature/DirectorRail.tsx:256`.
  - `components/feature/TurnInspectorPanel.tsx:166` — `w-[340px]` with no breakpoint, always
    rendered; make it responsive so it cannot overflow a 320 px viewport.
  - Horizontal scrollers get the §13 **edge-fade affordance**: `components/feature/LibraryTabs.tsx:43`,
    `ScenarioCarousel.tsx:315`, `features/options/OptionsView.tsx:99`.
  - `ScenarioCarousel.tsx:401` and `DirectorRail.tsx:36,149` /
    `ContextBudgetMeter.tsx:58` animate `grid-template-columns`, `width`, and
    `grid-template-rows` — non-compositor properties (§1.5). Convert the meters to `scaleX` on
    a transform-origin-left fill; the grid animations stay (they are genuine layout reveals,
    run once, not on scroll) but move to `--dur-base`/`--ease-out` and are documented as the
    deliberate exception.
  - Narrow reveal-on-scroll (§6, deviation 6 above): `.reveal` on the Library column cards and
    documents rows, behind `@supports (animation-timeline: view())` and
    `prefers-reduced-motion: no-preference`, with the **base style as the revealed state**.
  - Tests: co-located cases for the container-query card variants; a
    `responsive.test.tsx`-style assertion that no component ships a fixed width ≥ 320 px
    without a breakpoint.
- **Rationale:** Container queries are the "structure is wrong" fix — they are why the same
  card can live in the Library grid, the hero carousel, and a rail without three sets of
  viewport overrides.
- **Validation & commit:** `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`;
  responsive pass at **320 / 375 / 768 / 1024 / 1440 / 2560** confirming no horizontal overflow
  and no root-scroll growth (`documentElement.scrollHeight > clientHeight` is the repo's known
  `sr-only` symptom — re-check it here). Commit:
  `[Frontend Polish] (6/7) Complete: Container-query cards, fluid type/spacing, dvh fixes, scroll affordances, and a clean 320px floor.`

---

### Phase 7 — Acceptance checklist, docs, and merge

- **Locations:**
  - Run the spec's **§14 Acceptance Checklist** and report every line pass/fail **with the file
    and line where it is satisfied** — the spec forbids claiming an unverified pass. Failures
    are recorded in `docs/checklist.md`, not quietly dropped.
  - `docs/design-system.md` — the motion token table, the loading-state ladder, the skeleton
    and `SmartImage` contracts, the container-query rule, the sticky-bottom behavior, the
    single signature motion moment, and the four recorded deviations (§6 narrow, §7 skipped,
    reduced-motion reset, Framer retained).
  - `docs/component-map.md` — the new primitives (`Skeleton`, `AsyncPanel`, `SmartImage`,
    `JumpToLatest`) and hooks (`use-delayed-flag`, `use-sticky-bottom`).
  - `docs/checklist.md` — close the long-deferred "live in-browser accessibility + responsive
    pass" item if it is genuinely done here; open the mobile-rails item (gap 9) explicitly.
  - `CLAUDE.md` + `docs/skills/ui-frontend/SKILL.md` — point at `docs/frontend-polish-spec.md`
    as the standing contract for new UI.
  - **Merge:** `claude/frontend-polish-ui-2275c7` → `main`, fixing any conflicts.
- **Validation & commit:** full gate — `uv run pytest` (unchanged backend, run as the
  regression net), `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`,
  `uv run python utils/scripts/check_contrast.py`; keyboard + 320/375/768/1024 pass across all
  three themes. Commit: `[Frontend Polish] (7/7) Complete: Verified against the §14 acceptance checklist and reconciled the design-system, component-map, and checklist docs.`

---

## 4. Deliverables

| Deliverable | Description | Location |
| --- | --- | --- |
| Polish contract | The spec, checked in and referenced | `docs/frontend-polish-spec.md` |
| Motion tokens | Durations, easings, lifts, fluid steps | `web/frontend/styles/themes.css` |
| Motion utilities | Stagger, content-enter, skeleton, token fade, gated hover/press | `web/frontend/styles/motion.css` |
| Tailwind mapping | Tokens → utilities; spec base layer | `web/frontend/app/globals.css` |
| Primitive states | hover/focus/active/disabled, 44 px targets, modal exits, loading button | `web/frontend/components/ui/*.tsx` |
| Delay gate | 300 ms indicator gate + five-state union | `web/frontend/hooks/use-delayed-flag.ts` |
| Skeletons | Layout-tracing placeholders that time out | `web/frontend/components/ui/Skeleton.tsx` |
| Async shell | idle/loading/success/error/empty with retry | `web/frontend/components/ui/AsyncPanel.tsx` |
| Images | Space-reserved, fade-in, cache-safe | `web/frontend/components/ui/SmartImage.tsx` |
| Sticky bottom | Autoscroll that respects the reader | `web/frontend/features/story-player/use-sticky-bottom.ts` |
| Jump pill | Escape hatch back to the live edge | `web/frontend/components/feature/JumpToLatest.tsx` |
| Container cards | Cards that respond to their container | `web/frontend/components/feature/{Character,Setting,Scenario}Card.tsx` |
| Frontend tests | Co-located, per component/hook | beside each file (`Foo.tsx` → `Foo.test.tsx`) |
| Docs | Tokens, ladder, deviations, new components | `docs/design-system.md`, `docs/component-map.md`, `docs/checklist.md` |

## 5. Out of scope

- Theme/color/typography changes (locked; contrast-gated).
- Mobile rail drawers (gap 9 — needs a human design decision).
- Next.js view transitions (deviation 7 — stack change).
- Backend work of any kind. `uv run pytest` runs as a regression net only.
