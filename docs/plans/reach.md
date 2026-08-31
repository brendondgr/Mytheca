# Reach — mobile, keyboard, and assistive-technology parity for the story player

> **Superseded in part, 2026-08-31.** This plan shipped `SceneRailBar`, a `lg:hidden` row of
> Cast / Scene / Knows triggers above the composer. That component is **deleted**: the rails it
> opened are unchanged and now open from rows in `SceneMenu` instead, because a third horizontal
> band of chrome on the narrowest screen in the app was itself the problem. See
> `docs/plans/mobile-shell-and-provider-streaming.md`. Everything else here still describes the
> code. Kept as the record of why the rails reach a phone at all.

## 1. Introduction

Mytheca is a roleplay chat engine, and roleplay happens on a phone. Today it does not. Below
the `lg` breakpoint the story player throws away both rails — `CastRail.tsx:235` and
`DirectorRail.tsx:340` are both `hidden … lg:block`, and `CharacterDossier.tsx:36` is the same
shell — so a phone player loses presence controls, per-character stats, the turn order, the
live scene pulse, the scene-state chips, and the direction checklist outright. At the 320px
floor the scene header's Turn Inspector button is clipped 7px past an `overflow: hidden`
ancestor and is *genuinely unreachable*; the storyline switcher is `hidden md:block`, so a
phone is locked to whatever world it deep-linked into. On the authoring side the stacked
context rail leaves the document list ~34px of scroll. Underneath all of it sits a latent
repo-wide defect — Tailwind's `sr-only` is `position: absolute`, so with no positioned
ancestor it is laid out against the *initial containing block*, escapes every `overflow:
hidden` ancestor, and grows the **root** scroller (`TriagePanel` produced 6212px of blank page
before it was patched locally on 2026-08-11; the rest of the tree has never been swept).

This plan closes the "Known UI limitations" block in `docs/checklist.md` and the one outright
**FAIL** in `docs/plans/frontend-polish-acceptance.md`. The approach is deliberately
structural rather than cosmetic. First a real `Drawer` primitive is built beside `Modal`,
sharing one extracted focus-trap hook, so a bottom sheet is a solved problem instead of three
bespoke ones. Then each rail is split into a *content* component and a *shell*, so the drawer
and the `lg` aside render **the same** component — that is the only design that guarantees the
mobile surface carries identical functionality, and it is what makes the other four plans'
additions (a growing direction checklist, a play-through tray, a planner toggle) land on
mobile for free rather than needing a second implementation. The scene header gets a real
overflow menu with an ordered, extensible item list so the controls the other plans add have
somewhere to go. The `sr-only` bug is fixed once, at the utility definition, and pinned by the
existing offline CSS gate. Finally the fonts are self-hosted — which permanently unblocks
`next build` offline and is itself an LCP improvement — so that Core Web Vitals can be
measured at all, with any number produced recorded under `docs/research/experiments/` per
`docs/research/AGENT_INSTRUCTIONS.md`.

Nothing here touches the backend. There is no schema change, no envelope change, no new
endpoint, and therefore no `web/frontend/lib/events.ts` mirror work. `uv run pytest` should be
unaffected by every phase and is run anyway as a regression check.

---

## 2. Gaps & Unanswered Questions

### Decisions taken by the owner — 2026-08-21 (supersede the gaps below)

These three were asked and answered before implementation began. Where the text further down
states a different default, **this block wins** and that text is superseded.

**D-1 — Stat values become session-scoped, with a per-stat `carry_over` flag.**
(Answers Control H-1 and Depth §2.2 together — they were the same decision asked from two sides.)
`StatDefinition` gains a `carry_over` boolean. Stat *values* move to a session scope: a new
`session_character_stats` row set keyed `(session_id, character_id, key)`. Resolution order when
the engine reads a stat is: the open session's value → else, if `carry_over` is true, the
character-global value → else the authored baseline. Consequences that the phases below must
absorb:
  * **Rewind** no longer needs `StatPatch.fromValue` as its un-apply mechanism. It deletes the
    session's stat rows and **replays the surviving `state_update` events** from the authored
    baseline — deterministic, needs no per-event provenance, and works for legacy rows written
    before this program. Keep `fromValue` only if it earns its place for the Inspector's display;
    it is no longer load-bearing.
  * **Branch** copies the source session's stat rows to the fork at the fork point, so the two
    play-throughs diverge instead of sharing.
  * **Two play-throughs of one scenario no longer disagree** — they are simply separate, which was
    the defect H-1 named.
  * `GET /characters/{id}/stats` keeps returning the character-global values (the authored/carried
    baseline). Play surfaces read the session-scoped values. Say which is which at every call site.
  * This is additive-but-not-trivial: it is a new table plus a change to every stat read and write
    (`services/stats.py`, `services/stat_render.py`, `beat_runner`'s stat application, the cast
    rail, the dossier, and `useScenePlay`'s baseline load). Give it **its own phase** rather than
    smuggling it into the rewind phase.

**D-2 — Context compaction ships OFF by default.**
`TURN_CONTEXT_COMPACTION` defaults to disabled. Long scenes keep today's behaviour (older history
falls out of the window) until the interleaved two-arm experiment reports. The flag flip is a
one-line change and is explicitly *not* to be made on the strength of a read-through. This
supersedes any "ship on" reading of the compaction phases.

**D-3 — The `sr-only` defect is fixed by redefining the utility once.**
`@utility sr-only { position: fixed }` — one change, covering all existing call sites and every
future one. The per-file sweep is **not** done. The change must be pinned by a regression test and
must pass the offline CSS gate (`node utils/scripts/check_frontend_css.mjs`).

---

### Assumed (simple gaps — the most logical assumption, stated and proceeded with)

1. **All four of the other plans exist; three were read at authoring time, the fourth was not.**
   `docs/plans/control-over-the-record.md`, `steering-the-scene.md` and
   `making-it-legible.md` were read at authoring time and their surface area is absorbed
   **concretely** below, not by assumption. `docs/plans/depth-for-players.md` was written in
   parallel and **now exists** — the reconciliation pass recorded its real surface area, which is
   listed below in place of the original guess. Reach lands last, so every one of these components
   already exists when Reach is implemented — re-read all **four** files before Phase 3 and
   confirm the lists below against what actually shipped.

   *From **control-over-the-record** (11 phases):* `SceneHeader` gains a `tray?: ReactNode`
   prop holding `PlaythroughTray` (its Phase 2), and that same phase **deletes the hardcoded
   "Narrator active" dot** to buy back the 7px — see Gap #3. It also adds a per-beat control
   cluster `BeatControls` (Re-roll · Edit · Rewind here · Branch here · Delete) rendered
   inside `TranscriptBeat`, plus `BeatEditor`, `BeatTakePager`, `RewindNotice`,
   `TranscriptFootBar` and a `GhostwriteButton` in the composer's controls row. **This is the
   largest new touch surface in the app** and it is the single biggest risk item for Phase 11:
   a per-beat cluster that reveals on hover is invisible and unreachable on touch, and five
   controls on every beat is five controls in the tab order of a long transcript. Phase 11
   audits it explicitly.

   *From **steering-the-scene** (11 phases):* a `DirectionRow` always present in the composer,
   a `SceneVerbBar` (`role="toolbar"` with roving tabindex) inside it, a richer
   `DirectionChecklist` (three states, carried-over badge, per-item dismiss), a grouped
   `MentionMenu` with a cast namespace, a `CastRequestBeat` with accept/decline, and **a third
   section in `CastRail`** — "Elsewhere in the world". The checklist and the third cast
   section reach mobile for free because Phase 2 makes the drawer render the same content
   component the `lg` rail does; Phase 2's split must simply move whatever sections exist at
   the time, not the three that exist today.

   *From **making-it-legible** (12 phases):* `SceneHeader` gains a **real four-state model
   health indicator** (`hooks/use-model-health.ts`) in place of the deleted fake dot, plus
   `onToggleMemory`/`memoryOpen` for a memory panel, a `ShortcutSheet` behind `?`, and
   `use-scene-shortcuts.ts` binding `/`, `ArrowUp`, `Escape` and `?`. Its own handoff table
   states: *"Rails as mobile drawers, the 320px header | the mobile plan | Phase 8/9 surfaces
   must not assume `lg`"* — it explicitly hands both to this plan. Two consequences: the
   memory panel is a candidate **third drawer tab** (Phase 3 notes it), and `/` and `?` are
   **single-character shortcuts**, which WCAG 2.2 requires be disableable, remappable, or
   limited to a focused context (Phase 11 checks this).

   *From **depth-for-players** (12 phases, read during reconciliation):* it **creates
   `web/frontend/components/feature/SceneMenu.tsx` and deletes `ExportMenu.tsx`** in its Phase 9
   — so Phase 4 below **extends** that file rather than creating it (the phase says so). It also
   adds four more rows plus per-row **pin** toggles to `SceneConfigMenu` (presets, Turn planning,
   Register, Ties), a play-time "How this world writes" prompt-overrides modal opened from the
   header, a `looseness` range control in `VoiceSamplesEditor`, a "Start this scene fresh"
   checkbox in `BeginSceneModal`, and read-only additions to `CharacterDossier` — all of which
   reach mobile through Phase 3's drawer and Phase 4's item list without redesign. It does **not**
   touch `GraphView.tsx` or `GraphInspectorPanel.tsx`; the graph scope call it adds is
   backend-side (`graph_reader.offscene_ties`). The `SceneConfigMenu` popover is 264 px wide
   inside a composer that must not overflow at 320 px, and it now carries roughly twice the rows
   it does today — Phase 11 must measure it, and its pin toggles are in the 24×24 / 44×44 sweep.

2. **Graph mode below `lg` is OUT of scope, with one exception.** `docs/checklist.md` records
   that graph mode is canvas-only below `lg`, that the `sr-only` node/edge table is the data
   alternative, and that node clicks are wired for Character only. A force-directed canvas is
   genuinely two-dimensional content, which WCAG 2.2 exempts from the 320px reflow
   requirement, and the `sr-only` table is a conforming alternative. Making
   `GraphInspectorPanel` a drawer and widening node-click coverage belongs to whichever plan
   owns the graph — **no plan in this program does** (depth-for-players' graph work is entirely
   backend-side), so it stays open in `docs/checklist.md` and Phase 12 must restate it honestly
   rather than assigning it. **The exception:** Phase 7's `sr-only` fix
   *must* cover `GraphView.tsx:187`, which renders a full node+edge table inside `sr-only` —
   the single largest instance of the defect in the tree — and Phase 11 must confirm that
   table still reads correctly afterwards.

3. **The "Narrator active" dot is somebody else's delete, and the 7px it frees does not
   survive.** `SceneHeader.tsx:114–117` renders a hardcoded green dot reflecting nothing;
   **control-over-the-record Phase 2 deletes it** and its Action line claims the Inspector
   clip is thereby fixed, while **making-it-legible Phase 7 puts a real four-state model
   health indicator back in the same slot**. Net: the width is reclaimed and then spent, and
   the clip returns. Reach therefore does **not** re-delete anything — Phase 4 assumes the
   fake dot is already gone and treats the real indicator as a control to place. Its
   placement: the indicator stays **inline at every width** (a status you must open a menu to
   see is not a status), collapsed below `sm` to a state-specific **glyph** — not a
   state-specific colour, since WCAG forbids colour-alone — carrying the full four-state text
   as its accessible name, with `role="status"` intact and the text label `hidden sm:inline`.
   The overflow menu, not a width saving, is the durable fix for the 320px clip: it is the
   only mechanism that still works after the *next* control is added.

4. **The scene header's `ThemeSwitcher` moves into the overflow menu below `sm` rather than
   being deleted.** `AppHeader.tsx`'s own comment records that theme switching already lives
   in the Options dropdown and the Options page Appearance tab, so the header copy is a
   convenience duplicate. It is kept (players change theme mid-scene for reading comfort) but
   demoted.

5. **Bottom sheet, not side drawer.** Both rails become bottom sheets below `lg`. The composer
   owns the bottom of the story player and is the thing a player's thumb is already near; a
   sheet rising from the same edge is the shortest travel and does not fight the sticky-bottom
   transcript hook (`use-sticky-bottom.ts`), which a side drawer overlaying the scroller
   would.

6. **The two load-flaky tests are half-fixed already.** `features/library/CharacterModal.test.tsx:82`
   already carries `}, 15000)` on "drafts a full character from a seed into the form".
   `features/library/SettingModal.test.tsx` does **not**. Phase 8 is therefore smaller than
   `docs/checklist.md` implies and its scope is: `SettingModal.test.tsx`, plus a sweep for any
   other test that awaits the ~150ms-per-field `use-field-reveal` choreography.

7. **`prefers-reduced-motion` needs an explicit rule for portalled content.** The brief notes
   that `.mytheca-themed *` in `styles/themes.css:420` already strips `animation` and
   `transition` under reduce. That is true for in-tree content, but `Drawer` portals to
   `document.body`, *outside* the `.mytheca-themed` wrapper — which is exactly why
   `Modal.tsx`'s CSS in `motion.css` carries its own explicit
   `@media (prefers-reduced-motion: reduce)` block. The Drawer gets the same treatment, and
   its base style is the resting (open) state so the degraded path is "it is simply there".

### Needing a decision (complex gaps)

8. **How is the Core Web Vitals number actually captured?** Phase 9 removes the *build*
   blocker permanently by self-hosting the three Google fonts, so a production bundle will
   exist. What does not exist is a headless browser with CPU throttling in this environment.
   Two options: (a) add `puppeteer` or `playwright` + `lighthouse` as devDependencies and
   write `utils/scripts/research/run_core_web_vitals.mjs` as a repeatable, checked-in harness
   — the research contract's §7 preference, but ~300MB of browser binaries in a repo that
   currently has 5 runtime dependencies; or (b) ship a `web-vitals` probe behind
   `NEXT_PUBLIC_VITALS=1` and record a **manual** Chrome DevTools procedure (4× CPU throttle,
   3 loads per route), which produces a real number from a real browser but is not
   reproducible by a command. **Human intervention is needed to answer this question.** Phase
   10 is written to work either way and, per the contract, records the experiment folder with
   `status: failed` and an honest `ISSUES.md` if neither run happens — never deleted, never
   reported in chat alone.

9. **Should the `sr-only` fix redefine the utility, or be a per-site sweep?** The plan chooses
   redefinition (`@utility sr-only` with `position: fixed` in `app/globals.css`) because it is
   one line that fixes 23 call sites and every future one, and because `position: fixed`
   cannot grow any scroller: its containing block is the viewport, or — inside a transformed
   ancestor such as a Framer `motion.div` — that ancestor, which is itself in flow and
   clipped. The residual risk is that some assistive technology treats a `fixed` 1×1 element
   differently from an `absolute` one; document order and the accessibility tree are unchanged
   by positioning, so this is judged safe, but it is a repo-wide CSS change to a utility
   almost every screen-reader affordance depends on. **If the owner would rather not touch the
   `sr-only` definition, Phase 7 falls back to auditing all 23 sites for a positioned scroll
   ancestor.** Human intervention is needed to confirm the preference; the plan proceeds with
   redefinition and the fallback is written into Phase 7.

10. **The 24×24 minimum (WCAG 2.5.8) is not met by the older per-row chips.**
    `TriagePanel.tsx`'s `DocRow` Draft/RAG/Extract chips are `py-[2px]` and the file's own
    comment says they "predate that and are tracked separately". The coarse-pointer 44px floor
    in `motion.css` covers touch, but 2.5.8 applies to **pointer inputs generally**, including
    a mouse. Growing them changes the density the design system explicitly specifies
    (`docs/design-system.md`: rails are "small and quiet"). Phase 11 measures and reports;
    whether to grow them, add spacing exceptions, or claim the 2.5.8 "spacing" exception is a
    design call. Human intervention is needed to answer this question.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — A `Drawer` primitive, and one shared focus trap

- **Locations:**
  - New `web/frontend/hooks/use-focus-trap.ts` — extract the trap/Escape/scroll-lock/restore
    effect currently inlined in `components/ui/Modal.tsx` (the `FOCUSABLE` selector constant,
    the `onKeyDown` Tab-cycling handler, the `document.body.style.overflow` lock, and the
    `previouslyFocused?.focus?.()` restore). Signature takes `{ open, containerRef, onClose }`
    and keeps the existing `onCloseRef` indirection, which exists so the effect does not
    re-run on every render and steal focus from a controlled input.
  - `web/frontend/components/ui/Modal.tsx` — refactored to call the hook. **No behavior
    change**; `Modal.test.tsx` must pass untouched, which is the proof the extraction is
    faithful.
  - New `web/frontend/components/ui/Drawer.tsx` — a bottom sheet. Props:
    `open`, `onClose`, `title` (rendered as a real heading, see Phase 11), `children`,
    `heightClass` (default `max-h-[80dvh]`), `z` (default 55, below `Modal`'s 60 so a modal
    opened from inside a drawer stacks correctly), and `labelledBy`. Portals to
    `document.body` via `createPortal`, mirrors `Modal`'s `useHydrated` +
    `useExitTransition(open, EXIT_MS)` pattern exactly, sets `role="dialog"`
    `aria-modal="true"`, renders a drag-handle affordance (`aria-hidden`) and a `CloseButton`,
    and dismisses on backdrop click and Escape.
  - `web/frontend/styles/motion.css` — new `.drawer-panel` / `.drawer-backdrop` rules directly
    beneath the existing `---------- Dialogs ----------` block, following that block's idiom:
    the **base style is the resting, fully-open state**, `@starting-style` supplies the
    entrance (translateY from `var(--lift-lg)` + opacity), `[data-closing="true"]` supplies
    the exit at `--dur-fast` with `--ease-in`, and an explicit
    `@media (prefers-reduced-motion: reduce)` block sets `transition: none` on both. The
    explicit media query is **required, not redundant**: the repo-wide rule in
    `themes.css:420` is scoped to `.mytheca-themed *`, and a portalled drawer is not a
    descendant of that wrapper — the same reason `.modal-panel` carries its own rule.
    Durations come from `--dur-slow` in / `--dur-fast` out; no literals (the CSS gate fails on
    an undefined motion token).
  - New `web/frontend/components/ui/Drawer.test.tsx` — traps Tab and Shift+Tab inside the
    panel; Escape calls `onClose`; the backdrop click calls `onClose` while a click inside
    does not; `document.body.style.overflow` is locked while open and restored on close; focus
    returns to the trigger; nothing renders before hydration.
  - New `web/frontend/hooks/use-focus-trap.test.ts`.
- **Rationale:** Both drawers, and any drawer the other four plans want, need identical
  trapping, locking and reduced-motion behavior. Writing it once as a primitive beside `Modal`
  is the repository's stated ownership rule (`components/ui/` holds primitives), and
  extracting the trap first means `Modal` and `Drawer` cannot drift. Doing the extraction
  *before* any consumer exists keeps this phase's diff provably behavior-neutral.
- *Action: Run the validation for this phase — `uv run pytest` (no backend area is affected;
  this is a regression check), `npm test` in `web/frontend/` with particular attention to
  `components/ui/Modal.test.tsx`, `npm run typecheck`, `npm run lint`, and
  `node utils/scripts/check_frontend_css.mjs` for the new motion rules; plus an accessibility
  + responsive pass on the new primitive (keyboard trap in both directions, visible focus, AA
  contrast, 320/375/768/1024). Once green, commit locally:
  `[Reach] (1/12) Complete: Added a Drawer primitive and extracted Modal's focus trap into a shared hook.`
  Do not push or open a PR.*

---

### Phase 2 — Split each rail into content + shell (no behavior change)

- **Locations:**
  - `web/frontend/components/feature/CastRail.tsx` — extract everything inside the
    `<aside className="mytheca-rail hidden … lg:block">` into an exported
    `CastRailContent({ …same props })`. `CastRail` becomes the `lg`-only `<aside>` shell that
    renders it, and gains the `aria-label="Cast"` it currently lacks (`CharacterDossier` has
    one; these two do not — a landmark with no name). **Move whatever sections exist at
    implementation time, not the three that exist today:** steering-the-scene Phase 9 adds a
    third section, "Elsewhere in the world", holding the storyline's absent cast and any
    pending join request. The extraction is mechanical and must not editorialise the contents.
  - `web/frontend/components/feature/DirectorRail.tsx` — same split into
    `DirectorRailContent`. The already-exported `TensionMeter`, `StateChips`, `StatSchema`,
    `Relationships`, `liveValueFor` stay exported unchanged (`CastRail.tsx` and
    `CharacterDossier.tsx` import from here). Add `aria-label="Scene"` to the `<aside>`.
    `ScenePulse` gains a `live?: boolean` prop (default `true`) that switches
    `aria-live="polite"` to `"off"`; the `role="log"` and label stay in both cases.
  - `web/frontend/components/feature/DirectionChecklist.tsx` — same `live?: boolean` prop on
    its `sr-only aria-live` paragraph (`DirectionChecklist.tsx:43`).
  - `web/frontend/components/feature/CharacterDossier.tsx` — extract
    `CharacterDossierContent`; `CharacterDossier` keeps the `lg` `<aside>` shell.
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — unchanged in this phase; it
    still renders the three shells.
  - Tests: `components/feature/CastRail.test.tsx`, `DirectorRail.test.tsx`,
    `CharacterDossier.test.tsx`, `DirectionChecklist.test.tsx` — existing cases must pass
    **unmodified** except where they query the `<aside>` by role and now need the new
    accessible name. Add one case per file rendering the `…Content` component standalone, and
    one asserting `live={false}` drops `aria-live` while keeping `role="log"`.
- **Rationale:** This is the phase that makes "the same functionality, not a reduced version"
  structurally true rather than a promise. If the drawer rendered its own markup, every future
  rail addition would have to be built twice and the mobile copy would rot — which is
  precisely how the current `lg`-only rails came to hide five distinct capabilities. It also
  keeps every file under the 500-line target as Phase 3 adds consumers. The `live` prop is
  needed *before* the drawer exists: a scene-pulse log that is unmounted while the drawer is
  closed and then announces twelve backlog entries the instant it opens is worse than silence,
  and `TurnStatusStrip` + `TranscriptAnnouncer` already carry the live signal in the reading
  column at every width.
- *Action: Run the validation for this phase — `uv run pytest`, `npm test` in `web/frontend/`,
  `npm run typecheck`, `npm run lint`; plus an accessibility + responsive pass (the two rails
  now have accessible landmark names — confirm with the accessibility tree, keyboard, visible
  focus, AA contrast, 320/375/768/1024, where the rails are still `lg`-only). Once green,
  commit locally:
  `[Reach] (2/12) Complete: Split the cast, director and dossier rails into reusable content components behind their lg-only shells.`
  Do not push or open a PR.*

---

### Phase 3 — Both rails as bottom sheets below `lg`

- **Locations:**
  - New `web/frontend/components/feature/SceneRailBar.tsx` — a thin `lg:hidden` row rendered
    directly above `Composer` inside the centre column of
    `features/story-player/StoryPlayerView.tsx`. Two buttons:
    **"Cast"** with the present-cast count, and **"Scene"** carrying a small badge when
    `direction.outstanding` is non-empty (so the direction checklist advertises itself instead
    of hiding). Both are `aria-haspopup="dialog"` with `aria-expanded`. Placed above the
    composer, not in the header: it is one thumb-reachable tap, and it leaves the header free
    for the overflow menu Phase 4 builds.
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — add local state
    `railDrawer: "cast" | "scene" | null`. Render `<SceneRailBar>` + two `<Drawer>`s, both
    `lg:hidden` (guarded in JS by the same `useMediaQuery` hook Phase 4 introduces, or simply
    always mounted and hidden by a `lg:hidden` wrapper class on the trigger — the drawer
    itself only exists while `railDrawer !== null`, so no duplicate landmark is ever in the
    tree). The Cast drawer renders `<CastRailContent …>` with the exact same props the
    `<CastRail>` shell receives. The Scene drawer renders `<CharacterDossierContent …>` when
    `scene.profileId` is set, else `<DirectorRailContent … live={false}>` — mirroring the
    desktop rule where the dossier takes over the Director rail.
  - Opening a profile below `lg` (from `CastRailContent`, `SceneIntro`, or a
    `TranscriptBeat` monogram) must set `railDrawer = "scene"` as well as `profileId`, so a
    tap on a character on a phone actually shows the dossier instead of silently doing
    nothing. Route this through one callback in `StoryPlayerView` rather than changing
    `useScenePlay.openProfile`, keeping the hook's surface stable for the other plans.
  - **If making-it-legible's memory panel has shipped by now** (its `SceneHeader`
    `onToggleMemory`/`memoryOpen` props and the panel behind them), add it as a third
    `SceneRailBar` trigger and a third drawer rather than leaving it header-only — a panel
    reachable only from a header menu is exactly the pattern this plan exists to end. If it
    has not shipped, `SceneRailBar` takes an `extraTriggers?: RailTrigger[]` array so adding
    it later is one entry.
  - New `web/frontend/components/feature/SceneRailBar.test.tsx`.
  - New `web/frontend/features/story-player/StoryPlayerView.drawers.test.tsx` — a co-located
    route-module test: opening the Cast drawer exposes the presence `<select>` for a cast
    member, the per-character stat values, and the turn order (i.e. every capability the
    checklist lists as lost below `lg`); opening the Scene drawer exposes the scene pulse,
    the scene-state chips and the direction checklist; tapping a character from inside the
    Cast drawer switches to the dossier; Escape closes; focus returns to the trigger.
  - `web/frontend/docs`-side: update `docs/component-map.md` (three new components,
    `CastRail`/`DirectorRail`/`CharacterDossier` ownership note) and `docs/design-system.md`
    — line 113 already *claims* "on mobile, where the rails collapse to drawers", which has
    been false since it was written; this phase makes it true and the sentence must be
    rewritten to describe the actual mechanism (bottom sheets, the `SceneRailBar` triggers,
    the dossier-replaces-scene rule). `docs/routes.md`'s story-player row gains the mobile
    states.
- **Rationale:** This is the headline gap. It lands after the split so the drawer is ~30 lines
  of composition rather than a second implementation, and after the primitive so the trap,
  scroll lock and reduced-motion path are already proven. The route-module test asserting each
  *capability* — not each element — is what stops a future refactor quietly reducing the
  mobile surface again.
- *Action: Run the validation for this phase — `uv run pytest`, `npm test` in `web/frontend/`,
  `npm run typecheck`, `npm run lint`; plus a full accessibility + responsive pass on the
  story player (drawer opens by keyboard and by touch, focus trapped and restored, Escape
  closes, body scroll locked, visible focus on both triggers, AA contrast on the badge, no
  horizontal overflow and `documentElement.scrollHeight == clientHeight` at
  320/375/768/1024, and the sheet does not cover the composer's active input). Once green,
  commit locally:
  `[Reach] (3/12) Complete: The cast and scene rails are reachable below lg as bottom sheets carrying identical functionality.`
  Do not push or open a PR.*

---

### Phase 4 — Collapse the scene header below `sm` into a real overflow menu

- **First task of this phase:** re-read the sibling plans and confirm the live prop list on
  `SceneHeader`. As written, Reach expects to find: `tray` (control-over-the-record Phase 2 —
  `PlaythroughTray`), a model-health indicator from `hooks/use-model-health.ts`
  (making-it-legible Phase 7), `onToggleMemory`/`memoryOpen` (making-it-legible), the
  `ViewModeSwitch`, `ThemeSwitcher`, and a `ShortcutSheet` entry point — plus the **existing
  `SceneMenu`** built by depth-for-players Phase 9, which by then already holds *Writing…*, the
  Inspector toggle and the two export actions (`ExportMenu.tsx` is **deleted** by that phase, so
  do not expect to find it). That is still **seven** control clusters where there are five today —
  the header does not fit them at 640px, let alone 320px, which is why the item model rather than
  the width saving is the fix.
- **The nesting rule.** `PlaythroughTray` is itself a popover, and a
  popover inside a popover is not operable by keyboard or screen reader in any sane way. Below
  `sm`, `SceneMenu` handles a `render`-less item that owns a panel by **drilling down one
  level in place**: selecting it replaces the menu's rows with that control's panel plus a
  "‹ Back" row, keeping one focus context and one Escape target. Never nest.
- **Locations:**
  - New `web/frontend/hooks/use-media-query.ts` — a `useSyncExternalStore` over
    `window.matchMedia`, mirroring the idiom already used by `hooks/use-theme.tsx`. Returns
    `false` during SSR and wherever `matchMedia` is absent (jsdom does not implement it), so
    the server-rendered form is the **narrow** one. That is the safe default in both
    directions: the overflow menu is fully functional at every width, so a viewer who never
    hydrates still has every control, whereas an inline cluster that never collapses is the
    bug being fixed.
  - New `web/frontend/hooks/use-media-query.test.ts`.
  - `web/frontend/components/feature/SceneMenu.tsx` — **created by
    `docs/plans/depth-for-players.md` Phase 9**, which lands immediately before this plan, deletes
    `ExportMenu.tsx`, and builds it to the interface below. **Extend that file; do not create a
    second one.** If Depth for Players has not landed, create it here to exactly this shape and
    say so in the commit body. What this phase adds: the `useMediaQuery` narrow/wide split, the
    drill-down-in-place rule for panel-owning items, and the remaining header controls (tray,
    theme, memory toggle, shortcut sheet). It is a `⋯`-triggered `role="menu"`
    popover following the popover idiom `ExportMenu.tsx` established before it was deleted (outside-click + Escape close,
    `aria-haspopup="menu"`, `aria-expanded`, `aria-controls`, `.mytheca-menu` surface), taking
    an **ordered `items` array** of
    `{ key, label, hint?, icon?, onSelect, disabled?, pressed?, render? }` plus an
    `extraSlot?: React.ReactNode` at the foot. `render` lets a non-button control (the
    `ThemeSwitcher` group) sit in the menu as a labeled row rather than being flattened into
    a menu item.
  - `web/frontend/components/layout/SceneHeader.tsx` — becomes a client component
    (`"use client"`). It calls `useMediaQuery("(min-width: 640px)")` (the Tailwind `sm`
    breakpoint) and renders the control cluster **exactly once** in one of two forms: at `sm`
    and up, the current inline row; below `sm`, **two things stay inline** — the
    `ViewModeSwitch` (the scene's primary mode toggle, already compact) and the model-health
    indicator in its glyph form (Gaps #3) — and everything else moves into `SceneMenu`:
    the play-through tray, Export, Theme, the Inspector toggle, the memory toggle, and the
    shortcut sheet. Rendering once, not twice with one copy `aria-hidden`, is deliberate: a
    duplicated control cluster produces duplicate accessible names and a tab order that visits
    invisible buttons.
    - Do **not** re-delete the "Narrator active" span — control-over-the-record Phase 2 owns
      that delete. If it is somehow still present when this phase runs, delete it here and say
      so in the commit body.
    - Keep the `flex-none` comment block, updated: it currently says "the real fix … is to
      collapse controls below `sm`, which is a design change, not a layout tweak" — that
      change is now this phase, and the comment should say so and point here.
    - New optional props `extraControls?: SceneMenuItem[]` and `extraSlot?: React.ReactNode`,
      threaded from `StoryPlayerView`, so anything depth-for-players adds is one array entry.
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — pass the props through; no
    other change.
  - `web/frontend/components/layout/SceneHeader.test.tsx` — existing cases assert Export
    precedes the theme group and that the switch precedes Export. Under the narrow default
    those controls now live in the menu, so the tests must be updated to open the menu first
    (this is a genuine behavior change, not a loosened assertion). Add: at the narrow default
    **every** control is reachable via the `⋯` menu — the play-through tray, Export, both
    theme options, the Inspector toggle, the memory toggle, the shortcut sheet, and any
    `extraControls` entry; a panel-owning item drills down in place and "‹ Back" returns; the
    menu is keyboard-operable and closes on Escape; the model-health indicator and the
    Chat/Graph switch remain **inline** at the narrow default; the health indicator's
    accessible name states its state in words.
  - New `web/frontend/components/feature/SceneMenu.test.tsx`.
  - `docs/component-map.md` and `docs/design-system.md` (§ story player chrome) updated in
    this phase; `docs/checklist.md`'s "Known UI limitations" 320px-clip bullet removed.
- **Rationale:** The checklist records that this is a *design decision*, that shrinking the
  cluster was tried and made the overflow 50–150px worse, and that the Inspector button is
  genuinely unreachable at 320px. This phase makes the decision. It comes after the drawers
  because the drawers establish that the header is no longer the only home for scene controls,
  and it is deliberately built with an ordered item list because this plan lands last and
  must hold the other four plans' header additions without another redesign.
- *Action: Run the validation for this phase — `uv run pytest`, `npm test` in `web/frontend/`,
  `npm run typecheck`, `npm run lint`; plus an accessibility + responsive pass focused on the
  header at 320px (every control reachable by keyboard AND by touch, `scrollWidth ==
  clientWidth`, visible focus on the `⋯` trigger and every menu row, AA contrast, menu
  dismissible by Escape and outside click) and at 375/768/1024 to confirm the inline form is
  unchanged. Once green, commit locally:
  `[Reach] (4/12) Complete: The scene header collapses into an extensible overflow menu below sm; the 320px Inspector clip is gone.`
  Do not push or open a PR.*

---

### Phase 5 — Let phones switch worlds

- **Locations:**
  - `web/frontend/components/layout/AppHeader.tsx:48–55` — remove the `hidden md:block`
    wrapper around `storylineSlot` and the `hidden … md:block` divider. Render the slot at
    every width; keep the divider `md`-gated (it is decoration).
  - `web/frontend/components/feature/StorylineMenu.tsx` — the trigger becomes responsive
    **in CSS, not JS**, so there is no second DOM copy and no hydration swap: the seal glyph
    and the caret stay visible at every width; the storyline title span becomes
    `hidden md:inline` while the trigger keeps an `aria-label` naming the active storyline
    (`Switch storyline — <title>`), so the accessible name is complete at 320px even though
    the visible label is not. The popover panel changes from a fixed `w-[280px]` to
    `w-[min(280px,calc(100vw-24px))]` so it cannot overhang at the 320px floor
    (`components/feature/responsive-floor.test.ts` already forbids an unconditional
    `w-[≥320px]`; 280 passes today but the panel is anchored `left-0` beneath a trigger that
    is already ~40px inset, which is what pushes it over).
  - The per-row action buttons (prompts / documents / edit / delete) are `p-[6px]` around a
    14px icon = 26px — above the WCAG 2.5.8 24×24 floor and grown to 44px on touch by the
    coarse-pointer rule in `motion.css`. Confirm, do not change.
  - `web/frontend/components/feature/StorylineMenu.test.tsx` — add: the trigger exposes the
    active storyline's name as its accessible name even when the visible title is hidden;
    switching still fires `onSwitch`. `web/frontend/components/layout/AppHeader.test.tsx` —
    add: `storylineSlot` renders with no width-gated wrapper.
  - `docs/checklist.md` — remove the "storyline switcher is hidden below `md`" bullet.
    `docs/routes.md` (`/` and `/{storylineId}` rows) — the "mobile" state now includes world
    switching.
- **Rationale:** Deep links already work; the control simply does not exist below `md`, which
  makes a phone a single-world device. This is the cheapest real capability restored in the
  whole plan and it is independent of the story-player work, so it can be validated on its
  own. Doing it in CSS rather than through `useMediaQuery` avoids a hydration swap on the very
  first paint of the Library, which is the app's LCP surface and is measured in Phase 10.
  **Out of scope, stated deliberately:** switching worlds from *inside* a running scene. The
  scene header's `‹ Library` link is that path, and a world switch mid-scene has session
  semantics that belong to whichever plan owns play-throughs.
- *Action: Run the validation for this phase — `uv run pytest`, `npm test` in `web/frontend/`,
  `npm run typecheck`, `npm run lint`; plus an accessibility + responsive pass on the Library
  header (the switcher is reachable and operable by keyboard and touch at 320/375/768/1024,
  its accessible name identifies the active world, the popover does not overhang, visible
  focus, AA contrast). Once green, commit locally:
  `[Reach] (5/12) Complete: The storyline switcher is reachable at every width, so phones can change worlds.`
  Do not push or open a PR.*

---

### Phase 6 — Give the stacked context rail room to breathe

- **Locations:**
  - `web/frontend/components/feature/TriagePanel.tsx` — the sticky top block (Eyebrow + file
    count, the "Add as" upload-target row, the drag-and-drop zone, the Triage button) is
    ~230px of a 42dvh strip, leaving ~34px of list at 320×720. Wrap the *upload-target row and
    the drop zone only* in the repo's existing CSS-only disclosure idiom — the
    `grid grid-rows-[0fr] / grid-rows-[1fr]` + `overflow-hidden` pattern already used by
    `DirectorRail.tsx`'s band legend — collapsed by default below `lg` and forced open with
    `lg:grid-rows-[1fr]` above it. A small `lg:hidden` disclosure button ("＋ Add files",
    `aria-expanded`, `aria-controls`) toggles it. Being CSS-driven means no `useMediaQuery`,
    no hydration swap, and no divergence between the server and client trees.
  - Keep **always visible at every width**: the Eyebrow + file count, the `Triage` button, the
    Draft de-select/re-select strip, and — critically — the `Browse files` `<label htmlFor>`,
    which must move into the always-visible row so file upload is never more than one tap away
    and is never gated behind an animation. The `<input type="file" className="sr-only">` at
    `TriagePanel.tsx:273` moves with it.
  - `web/frontend/features/library/StorylineCreatorView.tsx:274` — raise the stacked strip
    from `max-h-[42dvh]` to `max-h-[52dvh]` below `lg` (unchanged at `lg` and up, where it is
    a `w-[340px]` column). Combined with the collapsed header this takes the document list
    from ~34px to roughly 260px at 320×720. `responsive-floor.test.ts`'s `dvh`-not-`vh` guard
    already covers the unit.
  - `web/frontend/components/feature/TriagePanel.test.tsx` — add: the drop zone is collapsed
    by default and its disclosure button is `aria-expanded="false"`; `Browse files`, `Triage`
    and the Draft strip are present without expanding anything; expanding reveals the upload
    target and updates `aria-expanded`; the file input is still associated with its label.
  - `docs/checklist.md` — remove the "context rail is very cramped below `lg`" bullet.
    `docs/design-system.md` — the Context-files panel description gains the disclosure.
- **Rationale:** The checklist's own measurement (34px of scroll for the doc list) is the
  spec. The panel's four capabilities are not equally urgent — you set an upload target once
  per batch, but you scan the list continuously — so progressive disclosure of the *setup*
  half is the right trade, and it is exactly the trade the panel already makes on desktop by
  having room for both. This phase is independent of Phases 1–5 and touches a different route,
  so it is safe to land here or reorder.
- *Action: Run the validation for this phase — `uv run pytest`, `npm test` in `web/frontend/`,
  `npm run typecheck`, `npm run lint`, and `node utils/scripts/check_frontend_css.mjs`; plus
  an accessibility + responsive pass on `/storylines/new` (the disclosure is keyboard-operable
  with correct `aria-expanded`, the doc list scrolls with real height at 320×720 and 375×812,
  drag-and-drop retains its `Browse files` keyboard alternative, visible focus, AA contrast,
  320/375/768/1024). Once green, commit locally:
  `[Reach] (6/12) Complete: The stacked context rail collapses its upload header so the document list has usable height.`
  Do not push or open a PR.*

---

### Phase 7 — Fix the repo-wide `sr-only` clipping defect once, and pin it

- **Locations:**
  - `web/frontend/app/globals.css` — redefine the utility with Tailwind v4's
    `@utility sr-only { … }`, identical to Tailwind's own definition except
    `position: fixed` in place of `position: absolute`. A `fixed` element's containing block
    is the viewport — or, inside a transformed ancestor such as a Framer `motion.div`, that
    ancestor, which is itself in flow and clipped — so it can never extend the **root**
    scroller the way an `absolute` element laid out against the initial containing block does.
    Document order, and therefore the accessibility tree, is unchanged by positioning. Add a
    comment naming the `TriagePanel` incident (6212px of blank page for 28 files, 2026-08-11)
    so nobody reverts it as a cosmetic tweak. Confirm `not-sr-only` (which sets
    `position: static`) still overrides correctly.
  - `web/frontend/components/feature/TriagePanel.tsx:339–347` — keep the `relative` on the
    scroller and rewrite its comment: it is now belt-and-braces rather than the fix, and the
    comment currently states the old mechanism as the reason.
  - **Sweep the remaining sites** and fix any that are wrong for a *second* reason (an
    `sr-only` element that is also given `absolute`/`inset` utilities would now conflict).
    The 23 current call sites, all to be visually confirmed unchanged:
    `SealModal.tsx:148`, `GraphView.tsx:182,187`, `BuildWorldModal.tsx:196`,
    `TriagePanel.tsx:131,273`, `ContextFilesPanel.tsx:115`, `SceneImageModal.tsx:39`,
    `SourceDocumentsPanel.tsx:112`, `LibraryView.tsx:42`, `DocumentsTable.tsx:58`,
    `DocumentsView.tsx:124`, `CreateImageBar.tsx:75`, `DirectionChecklist.tsx:43`,
    `TranscriptAnnouncer.tsx:89`, `TranscriptBeat.tsx:196`, `StoryPlayerView.tsx:118`,
    `AboutTab.tsx:246`. `GraphView.tsx:187` (the full node + edge table) is the largest and
    must be re-read with a screen reader in Phase 11.
  - `utils/scripts/check_frontend_css.mjs` — extend it with a third assertion beside the two
    it already makes (no self-referential custom property; every referenced motion token
    defined): **the compiled `.sr-only` rule declares `position: fixed`.** This is the right
    home because the script already compiles `globals.css` through the real Tailwind v4
    pipeline with no network, which `next build` cannot do offline.
  - `web/frontend/components/feature/responsive-floor.test.ts` — add an `it(...)` asserting
    that `app/globals.css` contains the `@utility sr-only` override, so the guard fails inside
    `npm test` and not only in the separate CSS gate. Note in the test's comment that jsdom
    performs **no layout**, so the actual root-scroll symptom cannot be reproduced in a unit
    test — the source guard plus the compiled-CSS assertion are the enforceable proxies, and
    the live measurement (`documentElement.scrollHeight == clientHeight` while
    `document.body` is viewport-sized) belongs to Phase 11.
  - `docs/checklist.md` — remove the "`sr-only` inside a clipping container is a repo-wide
    latent bug" bullet. `docs/design-system.md` — record the overridden utility beside the
    other global rules. `docs/workflow.md` — the CSS gate's description now lists three
    assertions.
  - **Fallback if Gaps #9 is decided the other way:** drop the `@utility` override and instead
    add `relative` (or `isolate`) to the nearest scrolling ancestor at each of the 17 files
    above, and change the `responsive-floor.test.ts` guard to a heuristic scan flagging any
    `sr-only` inside a file that also contains `overflow-y-auto` without a `relative` on the
    same element. This is strictly worse — it is 17 diffs, a heuristic guard, and it does not
    protect the next call site — and is recorded only so the decision is reversible.
- **Rationale:** The checklist calls this "a LATENT REPO-WIDE defect" and it is the one bug in
  this plan that can silently ruin every other phase's responsive work: a 6000px phantom
  scroller makes any 320px measurement meaningless. Fixing it *before* the acceptance pass in
  Phase 11 is not optional ordering — it is what makes Phase 11's measurements trustworthy.
- *Action: Run the validation for this phase — `uv run pytest`, `npm test` in `web/frontend/`,
  `npm run typecheck`, `npm run lint`, and `node utils/scripts/check_frontend_css.mjs` (which
  now carries the new assertion); plus an accessibility pass confirming every swept `sr-only`
  region is still announced — in particular the `GraphView` node/edge tables, the
  `TranscriptAnnouncer` status region, and the file inputs' labels — and a live check that
  `documentElement.scrollHeight == clientHeight` on `/storylines/new` with 25+ documents
  loaded. Once green, commit locally:
  `[Reach] (7/12) Complete: sr-only can no longer grow the root scroller, with the fix pinned by the offline CSS gate.`
  Do not push or open a PR.*

---

### Phase 8 — Close the two load-flaky frontend tests

- **Locations:**
  - `web/frontend/features/library/SettingModal.test.tsx` — "drafts a full setting from a seed
    into the form" gets an explicit per-test timeout of `15000`, matching the treatment
    `features/library/CharacterModal.test.tsx:82` already carries, with the same explanatory
    comment naming the real bound (typing the seed plus the ~150ms-per-field
    `use-field-reveal` choreography runs ~4.4s alone, which overruns Vitest's 5s default under
    a loaded parallel suite). "shows draft progress and highlights the field being written" in
    the same file awaits the same choreography and gets the same treatment.
  - Sweep for any other test awaiting `hooks/use-field-reveal.ts`: grep the co-located suites
    for `mytheca-field-active` and for `waitFor` on a field value after a draft call, and
    apply the same per-test timeout where the wait is choreography-bound. Candidates to check:
    `components/feature/ScenarioForm.test.tsx`,
    `features/library/StorylineCreatorView.test.tsx`.
  - **Do not** raise `testTimeout` globally in `web/frontend/vitest.config.ts`, and **do not**
    loosen any assertion. `docs/checklist.md` is explicit that the tests are correct and the
    budget is too tight, and a global bump would hide the next genuinely-hung test.
  - `docs/checklist.md` — remove the "Two frontend tests are load-flaky" bullet and the
    trailing "**The two library-modal flakes above are still open**" sentence attached to the
    resolved `ToastProvider` entry.
- **Rationale:** These two failures make the frontend gate non-deterministic at ~50% under
  full worker concurrency, which means every subsequent phase's "green" is unreliable. It is a
  small phase deliberately placed before the measurement and acceptance work so that a red
  suite from here on means something.
- *Action: Run the validation for this phase — `npm test` in `web/frontend/` **three
  consecutive times at full worker concurrency** (the failure is load-dependent; a single
  green run is not evidence), plus once at `--maxWorkers=4` as the control, and
  `uv run pytest` as a regression check. No UI changed, so no accessibility or responsive pass
  is required — state that explicitly in the commit body. Once green, commit locally:
  `[Reach] (8/12) Complete: Raised the per-test timeout on the choreography-bound library-modal tests; the frontend suite is deterministic again.`
  Do not push or open a PR.*

---

### Phase 9 — Self-host the three fonts so a production bundle can exist offline

- **Locations:**
  - New `web/frontend/app/fonts/` holding the woff2 subsets for **Cinzel** (500/600/700),
    **EB Garamond** (400/500/600 + italic), and **IBM Plex Mono** (400/500) — the exact
    weights and styles `lib/fonts.ts` requests today. All three are OFL-licensed; commit the
    accompanying `OFL.txt` files beside them.
  - `web/frontend/lib/fonts.ts` — swap `next/font/google`'s `Cinzel`, `EB_Garamond` and
    `IBM_Plex_Mono` for `next/font/local`, keeping **the same three exported const names and
    the same three CSS variable names** (`--font-cinzel`, `--font-eb-garamond`,
    `--font-ibm-plex-mono`) and `display: "swap"`. Nothing else in the app changes:
    `app/layout.tsx` applies the variable classes on `<html>` and `styles/themes.css` /
    `app/globals.css` reference the variables.
  - Add `adjustFontFallback` / explicit `fallback` stacks matching the metric-compatible
    fallbacks `next/font/google` was generating, so removing it does not *introduce* the
    layout shift Phase 10 is about to measure.
  - `docs/deployment.md` and `docs/workflow.md` — remove the standing caveat that
    `next build` cannot run without network access to Google Fonts, and remove the
    "Use it whenever `npm run build` is unavailable" framing from the
    `check_frontend_css.mjs` section (the script stays, as a fast offline check; it is no
    longer the *only* option). `docs/design-system.md`'s typography section records that the
    families are now self-hosted.
  - `docs/checklist.md` — the "Deferred verification" entry about `next/font/google` being
    unreachable in this sandbox, and the "temporarily shimmed `lib/fonts.ts` to system
    families" workaround recorded from 2026-08-12, are both now obsolete; remove them.
  - `web/frontend/components/feature/responsive-floor.test.ts` or a new
    `web/frontend/lib/fonts.test.ts` — assert `lib/fonts.ts` imports from `next/font/local`
    and exports the three variables, so a future edit cannot silently reintroduce the network
    dependency.
- **Rationale:** Every deferred verification in `docs/checklist.md` traces back to one root
  cause: `next/font/google` fetches at build time and hard-fails offline, so this repository
  has *never once* produced a production bundle in its own development environment. Screenshots,
  `:focus-visible` rendering, and Core Web Vitals are all downstream of that. Self-hosting is
  the standard fix, it is a genuine LCP improvement (no third-party connection on the critical
  path), and it must land before Phase 10 because there is otherwise nothing to measure.
- *Action: Run the validation for this phase — `npm run build` in `web/frontend/` (this is the
  point of the phase and must now succeed with no network), then `npm test`, `npm run
  typecheck`, `npm run lint`, `node utils/scripts/check_frontend_css.mjs`, and
  `uv run pytest`; plus a visual/responsive pass confirming the three families still render
  and that headings and mono labels have not reflowed at 320/375/768/1024. Once green, commit
  locally:
  `[Reach] (9/12) Complete: Self-hosted the three type families, so next build runs offline and the app has a production bundle.`
  Do not push or open a PR.*

---

### Phase 10 — Measure Core Web Vitals, and record the number where numbers live

- **Locations:**
  - `make new-experiment SLUG=core-web-vitals` → `docs/research/experiments/EXP-2026-08-0NN-core-web-vitals/`,
    where `NN` is **the next free id at implementation time**, not a number fixed here.
    `EXP-2026-08-010-beat-length` is the current maximum, but
    `docs/plans/making-it-legible.md` Phase 12 lands first and claims
    `EXP-2026-08-011-context-compaction`, so this experiment is expected to be **012**. Run
    `ls docs/research/experiments/` before scaffolding and take the next free id. Fill
    `PROTOCOL.md` **before** running: the routes measured (`/` — the Library, which is the LCP
    surface; and `/{storylineId}/{scenarioId}` — the story player, which is the INP surface
    because it streams), the throttling profile (4× CPU per the polish spec's §14), the number
    of loads per route, and the pre-registered thresholds (CLS < 0.1, INP < 200ms,
    LCP < 2.5s).
  - New `web/frontend/components/layout/VitalsProbe.tsx` — mounted from `app/layout.tsx`
    **only** when `process.env.NEXT_PUBLIC_VITALS === "1"`, subscribing to the `web-vitals`
    package's `onCLS`/`onINP`/`onLCP` and pushing entries onto `window.__mythecaVitals`. Add
    `web-vitals` as a **devDependency** in `web/frontend/package.json`. Document
    `NEXT_PUBLIC_VITALS` in `.env.example` and `docs/deployment.md` (the repository rule:
    every new env var goes in both).
  - New `web/frontend/components/layout/VitalsProbe.test.tsx` — the probe renders nothing and
    subscribes to nothing when the flag is unset (so it can never affect a normal build).
  - The runner depends on Gaps #8. If the automated route is chosen, add
    `utils/scripts/research/run_core_web_vitals.mjs` plus its browser devDependency and wire
    it as the manifest's `code.entrypoint`. If the manual route is chosen, `PROTOCOL.md`
    carries the exact DevTools procedure and `code.entrypoint` records the command that served
    the bundle (`npm run build && npm run start` in `web/frontend/`).
  - `docs/research/experiments/EXP-2026-08-0NN-core-web-vitals/manifest.yaml` — every metric
    goes under `metrics.values` with `mean`/`std`/`n`, and into `data/metrics.json`. `RESULTS.md`
    states what was found and, explicitly, what was *not* controlled (one machine, one browser,
    a dev-adjacent bundle). If any route's run fails, the folder is committed with
    `status: failed` and an honest `ISSUES.md` — **and no aggregate is reported over the
    surviving routes**, per the standing rule that survivors are not a random subsample
    (`EXP-2026-08-001` is the worked example).
  - `docs/plans/frontend-polish-acceptance.md` — the Performance table's single **FAIL** row
    is updated with the measured result (or with "attempted, recorded failed, see
    EXP-2026-08-0NN"), and the Summary line's `PASS 18 · PARTIAL 7 · FAIL 1` tally corrected.
  - `docs/checklist.md` — the "Core Web Vitals have never been measured" bullet removed or
    rewritten to whatever is genuinely still open.
  - `docs/research/CLAIMS.md` / `INDEX.md` regenerated via `make research-index`.
- **Rationale:** This is the one outright FAIL against the polish spec and the only phase in
  this plan that produces a *number*. The repository's research contract is unambiguous: a
  metric reported only in chat or a commit message does not exist, failed runs are recorded
  rather than deleted, and `make validate-research` must pass. Placing it after the font work
  is mandatory (no bundle before then) and after Phase 7 is strongly desirable (a 6000px
  phantom root scroller would corrupt CLS).
- *Action: Run the validation for this phase — `make validate-research` (mandatory for any
  experiment run) and `make research-index`, plus `uv run pytest`, `npm test`,
  `npm run typecheck`, `npm run lint`, and a green `npm run build`. No user-facing UI changed
  beyond a flag-gated probe, so the accessibility pass is deferred to Phase 11. Once green,
  commit locally:
  `[Reach] (10/12) Complete: Measured Core Web Vitals against a real production bundle and recorded the Core Web Vitals experiment.`
  Do not push or open a PR.*

---

### Phase 11 — The full accessibility + responsive acceptance pass

- **Locations:** the whole story player and the surfaces this plan changed — measured live at
  **320 / 375 / 768 / 1024**, against `docs/skills/accessibility-mobile/SKILL.md` and
  `docs/skills/ada-compliance/SKILL.md`.
  - **Heading hierarchy.** `features/story-player/StoryPlayerView.tsx:118` renders an
    `sr-only <h1>`, then `SceneHeader`'s scene title is a plain `<div>` and
    `CharacterDossier.tsx:89` jumps straight to `<h3>` — an h1→h3 skip with no h2 anywhere.
    Fix: the rails' content components and the drawers each expose an `<h2>` for their section
    (this is what `Drawer`'s `title` prop is for), and the dossier's name drops to `<h2>` or
    is nested under one. Verify with the accessibility tree, not by reading JSX.
  - **Landmarks.** `CastRail` and `DirectorRail` gained `aria-label`s in Phase 2; confirm the
    story player exposes exactly one `<main>`-equivalent reading region and that the drawers
    do not leave orphaned landmarks in the tree when closed.
  - **Keyboard operability.** Tab order through: back link → scene title region → view switch
    → health indicator → `⋯` menu → transcript → `SceneRailBar` triggers → composer direction
    row → message box → Config → Speaking-as → Ghostwrite → dial → Send. Both drawers trap and
    restore. Every popover (`SceneMenu`, `PlaythroughTray`, `SceneConfigMenu`,
    `PovSelect`, `StorylineMenu`, `MentionMenu`, `ShortcutSheet`) closes on Escape and returns
    focus.
  - **The per-beat control cluster — the highest-risk surface in the app.** By the time this
    phase runs, control-over-the-record has put `BeatControls` (Re-roll · Edit · Rewind here ·
    Branch here · Delete) on every transcript beat, plus `BeatTakePager`, `BeatEditor` and
    `RewindNotice`. Audit specifically: (a) the cluster must **not** be hover-revealed only —
    on touch there is no hover, so a hover-gated cluster is invisible and unreachable, and the
    repo already gates movement-hovers behind `@media (hover: hover)` for exactly this reason;
    (b) five controls × N beats is a tab-order problem — confirm the cluster is either a
    single tab stop with arrow-key navigation (`role="toolbar"` + roving tabindex, the idiom
    `LibraryTabs.tsx` already uses) or is skippable; (c) each control's accessible name must
    identify *which beat* it acts on, not just "Edit"; (d) destructive actions (Delete,
    Rewind) must be confirmable and announced; (e) `BeatEditor`'s textarea must have a real
    associated label and must not be lost behind the composer or a drawer on a phone; (f)
    every control meets 24×24 with a mouse and 44×44 on touch. Report each as its own line.
  - **Single-character shortcuts (WCAG 2.1.4).** making-it-legible binds `/`, `?`, `ArrowUp`
    and `Escape` document-wide via `hooks/use-scene-shortcuts.ts`. `/` and `?` are
    single-character shortcuts, which must be disableable, remappable, **or** active only when
    a component has focus. Their own test asserts "does nothing inside a text field", which is
    a partial mitigation, not the criterion — a screen-reader user browsing the transcript is
    not inside a text field. Verify and report; if unmet, the fix (an Options toggle, or
    scoping the binding to the transcript region) is applied here.
  - **New toolbars and beats from steering-the-scene.** `SceneVerbBar` (`role="toolbar"`,
    roving tabindex — confirm arrow keys move and Tab exits), `DirectionRow` in both its
    narrator and POV forms, the grouped `MentionMenu` (two `role="group"` sections must be
    distinguishable by accessible name, and the menu must be operable without a pointer),
    `CastRequestBeat`'s accept/decline (a decision control inside a live-updating log —
    confirm it is not announced away mid-interaction), and the three-state
    `DirectionChecklist` (state must not be glyph-colour alone).
  - **Visible focus.** `docs/checklist.md` records that `:focus-visible` has never been
    *seen* rendered, because `document.hasFocus()` is false in this browser pane so the
    selector never matches. Attempt it again now that a production bundle exists
    (`npm run start` in a real browser window rather than the automation pane). If it still
    cannot be observed, say so and re-record the deferral rather than claiming a pass — the
    polish spec forbids claiming an unverified pass.
  - **Touch targets.** Re-run the emulated-touch sweep that found 9 sub-44px controls on
    2026-08-12 over every control this plan added (`SceneRailBar`, `SceneMenu` rows, the
    drawer close and handle, the `TriagePanel` disclosure, the compact `StorylineMenu`
    trigger) **and over every control the other three plans added** (`BeatControls`,
    `BeatTakePager`, `TranscriptFootBar`, `GhostwriteButton`, `SceneVerbBar`, `DirectionRow`,
    `PlaythroughTray` rows, `CastRequestBeat`, the health indicator glyph). The zero-specificity
    44px floor in `motion.css` only grows controls that "never expressed an opinion about their
    height", so any new component that sets its own height opts itself out silently — that is
    the failure mode to hunt. Separately measure the WCAG 2.5.8 **24×24** floor with a *mouse*
    pointer, which the coarse-pointer rule does not cover — this is where `TriagePanel`'s
    `py-[2px]` `DocRow` chips will fail (Gaps #10). Report the count; do not silently redesign
    the density the design system specifies.
  - **Live regions.** Count them. By this phase the story player carries
    `TranscriptAnnouncer`, `TurnStatusStrip`, `CreateImageBar`, `DirectionChecklist`,
    `ScenePulse`, `RewindNotice`, and the model-health indicator — seven regions where there
    were four, several of which fire during the same turn. Confirm: streamed prose is
    announced exactly once per completed turn; `TurnStatusStrip`'s `role="status"` is not
    duplicated by a drawer-mounted `ScenePulse` (the `live={false}` prop from Phase 2);
    `DirectionChecklist` does not announce on drawer open; a mutation (rewind, edit, re-roll)
    is announced once and does not re-announce the whole rebuilt transcript; and nothing
    steals focus. If the total is genuinely too chatty, say so and propose a consolidation
    rather than declaring a pass.
  - **Contrast.** No colour token changes in this plan, so `check_contrast.py` should be
    unchanged — run it anyway. Measure the *new* surfaces by hand: the `SceneRailBar` badge,
    the drawer backdrop over the transcript, and disabled treatments.
  - **Root scroller.** At every width and on every route touched, assert
    `documentElement.scrollWidth == clientWidth` and
    `documentElement.scrollHeight == clientHeight` — the `sr-only` symptom from Phase 7 and
    the horizontal-overflow floor in one measurement.
  - **Reduced motion.** With `prefers-reduced-motion: reduce`, both drawers appear and
    disappear instantly and remain fully operable, the `TriagePanel` disclosure snaps, and
    nothing becomes invisible (the rule is: base style = resting state).
  - New `docs/plans/reach-acceptance.md` — the written record, in the same pass/partial/fail
    format as `docs/plans/frontend-polish-acceptance.md`, **with the file and line where each
    line is satisfied**, and no claimed pass that was not verified. Fix what it finds in this
    phase; anything genuinely deferred goes to `docs/checklist.md` with a reason.
- **Rationale:** Every prior phase asserted its own behavior in isolation. This is the phase
  that checks the *composition* — tab order across a header menu, two drawers and a composer
  that did not previously coexist — and it is the phase the repository's validation gate names
  as required for any UI change. It is written as its own phase because a pass folded into
  twelve individual Action lines is a pass nobody ever runs end to end.
- *Action: Run the validation for this phase — `uv run pytest`, `npm test` in `web/frontend/`,
  `npm run typecheck`, `npm run lint`, `node utils/scripts/check_frontend_css.mjs`,
  `uv run python utils/scripts/check_contrast.py`, and a green `npm run build`; plus the full
  accessibility + responsive pass described above at 320/375/768/1024, recorded line by line
  in `docs/plans/reach-acceptance.md`. Once green, commit locally:
  `[Reach] (11/12) Complete: Ran and recorded the accessibility and responsive acceptance pass, fixing the heading hierarchy and every issue it surfaced.`
  Do not push or open a PR.*

---

### Phase 12 — Reconcile the docs and the checklist

- **Locations:**
  - `docs/checklist.md` — the **"Known UI limitations"** block is the main target. Remove:
    "Rails are hidden below `lg` … mobile drawers are unbuilt" (Phase 3), "The storyline
    switcher is hidden below `md`" (Phase 5), "At the 320px floor the scene-header Inspector
    icon clips ~7px…" (Phase 4). Under **"Known defects and rough edges"** remove the
    `sr-only` bullet (Phase 7), the cramped-context-rail bullet (Phase 6), the load-flaky-test
    bullet (Phase 8), and the Core Web Vitals bullet (Phase 10). Under **"Deferred
    verification"** remove the Google-Fonts blocker (Phase 9) and rewrite the live-pass entry
    to point at `docs/plans/reach-acceptance.md`. Keep and restate honestly: the graph
    below-`lg` limitation (out of scope, Gaps #2), whatever Phase 11 genuinely deferred, and
    the two open design questions (Gaps #8 and #10) as new entries. **Expect overlap, not
    conflict:** control-over-the-record's Phase 11 also intends to remove the 320px
    scene-header line, and making-it-legible's G-10 references it. Whichever landed first will
    have taken it; do not re-add a bullet to delete it, and do not assume it is still there.
  - `docs/documentation.md` and `docs/architecture.md` — status lines that describe the app as
    desktop-first, or the rails as `lg`-only, corrected.
  - `docs/component-map.md` — final reconciliation of the component count and ownership after
    `Drawer`, `SceneMenu`, `SceneRailBar`, `VitalsProbe`, `CastRailContent`,
    `DirectorRailContent`, `CharacterDossierContent` and the three new hooks.
  - `docs/structure.md` — `web/frontend/app/fonts/` is a new directory holding binary assets.
  - `CLAUDE.md` — the frontend tables list component and hook counts (23 primitives, 55
    feature components, 4 hooks — already stale) and the "Facts that override stale
    assumptions" block. Update the counts and add: *the rails are no longer `lg`-only.*
  - `docs/research/INDEX.md` — regenerated (`make research-index`) if Phase 10 has not already.
- **Rationale:** The repository's standing rule is that docs are updated in the same change
  that alters behavior, and every phase above does that for its own files. This final phase
  exists for the two things a per-phase update cannot do: reconciling `docs/checklist.md`,
  whose entries span several phases and whose prose cross-references between bullets, and
  correcting the routing tables in `CLAUDE.md` that a reader hits *first*. The checklist was
  rebuilt on 2026-08-04 precisely because per-phase prose accumulated without ever being
  reconciled; leaving twelve half-edited bullets would repeat that.
- *Action: Run the validation for this phase — `uv run pytest`, `npm test` in `web/frontend/`,
  `npm run typecheck`, `npm run lint`, and `make validate-research`; plus a read-through
  confirming no doc still describes a limitation this plan removed and that every remaining
  entry names something genuinely open. No code changed, so no accessibility pass is
  required — state that in the commit body. Once green, commit locally:
  `[Reach] (12/12) Complete: Reconciled the checklist and the routing docs against the twelve phases of mobile and accessibility work.`
  Do not push or open a PR.*

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Shared focus trap | Trap + Escape + scroll lock + focus restore, extracted from `Modal` | `web/frontend/hooks/use-focus-trap.ts` |
| `Drawer` primitive | Portalled, focus-trapped bottom sheet with entrance/exit and an explicit reduced-motion rule | `web/frontend/components/ui/Drawer.tsx` |
| Drawer motion rules | `.drawer-panel` / `.drawer-backdrop`, base = resting state, tokens only | `web/frontend/styles/motion.css` |
| Rail content components | `CastRailContent`, `DirectorRailContent`, `CharacterDossierContent` — rendered by both the `lg` aside and the drawer | `web/frontend/components/feature/{CastRail,DirectorRail,CharacterDossier}.tsx` |
| Rail drawer triggers | `SceneRailBar` — Cast / Scene buttons above the composer, `lg:hidden`, direction badge | `web/frontend/components/feature/SceneRailBar.tsx` |
| Story-player drawer wiring | Drawer state, dossier-in-scene-drawer rule, profile-tap routing | `web/frontend/features/story-player/StoryPlayerView.tsx` |
| Media-query hook | `useSyncExternalStore` over `matchMedia`, SSR-safe narrow default | `web/frontend/hooks/use-media-query.ts` |
| Scene overflow menu | `SceneMenu` with an ordered `items` array + `extraSlot` for the other plans' controls | `web/frontend/components/feature/SceneMenu.tsx` |
| Collapsed scene header | Single-render inline/menu split below `sm`; fake "Narrator active" removed | `web/frontend/components/layout/SceneHeader.tsx` |
| Phone storyline switcher | `storylineSlot` un-gated; compact CSS-only trigger; popover width capped | `web/frontend/components/layout/AppHeader.tsx`, `web/frontend/components/feature/StorylineMenu.tsx` |
| Context-rail disclosure | Upload target + drop zone collapse below `lg`; strip raised to `52dvh` | `web/frontend/components/feature/TriagePanel.tsx`, `web/frontend/features/library/StorylineCreatorView.tsx` |
| `sr-only` repo-wide fix | `@utility sr-only` redefined to `position: fixed` so it cannot grow the root scroller | `web/frontend/app/globals.css` |
| CSS-gate assertion | Compiled `.sr-only` must declare `position: fixed` | `utils/scripts/check_frontend_css.mjs` |
| Self-hosted fonts | `next/font/local` for Cinzel / EB Garamond / IBM Plex Mono; `next build` runs offline | `web/frontend/lib/fonts.ts`, `web/frontend/app/fonts/` |
| Vitals probe | Flag-gated `web-vitals` subscriber (`NEXT_PUBLIC_VITALS=1`), inert by default | `web/frontend/components/layout/VitalsProbe.tsx` |
| CWV experiment record | Protocol, manifest metrics, results, honest ISSUES on failure | `docs/research/experiments/EXP-2026-08-0NN-core-web-vitals/` |
| Acceptance record | Line-by-line pass/partial/fail at 320/375/768/1024 with file+line evidence | `docs/plans/reach-acceptance.md` |
| **Test** — focus trap | Trap both directions, Escape, scroll lock, restore | `web/frontend/hooks/use-focus-trap.test.ts` |
| **Test** — drawer | Trap, Escape, backdrop dismiss, body lock, hydration guard | `web/frontend/components/ui/Drawer.test.tsx` |
| **Test** — media query | SSR-safe default, subscribe/unsubscribe | `web/frontend/hooks/use-media-query.test.ts` |
| **Test** — rail contents | Standalone render of each `…Content`; `live={false}` drops `aria-live` | `web/frontend/components/feature/{CastRail,DirectorRail,CharacterDossier,DirectionChecklist}.test.tsx` |
| **Test** — mobile capability parity | Every capability lost below `lg` today is reachable through the drawers | `web/frontend/features/story-player/StoryPlayerView.drawers.test.tsx` |
| **Test** — rail bar | Triggers, counts, direction badge, `aria-expanded` | `web/frontend/components/feature/SceneRailBar.test.tsx` |
| **Test** — scene menu | Keyboard operation, Escape, extensible items | `web/frontend/components/feature/SceneMenu.test.tsx` |
| **Test** — collapsed header | Every control reachable at the narrow default; no "Narrator active" | `web/frontend/components/layout/SceneHeader.test.tsx` |
| **Test** — switcher | Accessible name carries the active world with the title hidden | `web/frontend/components/feature/StorylineMenu.test.tsx`, `web/frontend/components/layout/AppHeader.test.tsx` |
| **Test** — triage disclosure | Collapsed by default, Browse/Triage/Draft always present, `aria-expanded` correct | `web/frontend/components/feature/TriagePanel.test.tsx` |
| **Test** — `sr-only` guard | `globals.css` carries the override; jsdom's no-layout limit documented | `web/frontend/components/feature/responsive-floor.test.ts` |
| **Test** — fonts | `lib/fonts.ts` uses `next/font/local` and exports the three variables | `web/frontend/lib/fonts.test.ts` |
| **Test** — vitals probe | Renders and subscribes to nothing when the flag is unset | `web/frontend/components/layout/VitalsProbe.test.tsx` |
| **Test** — flake fix | Per-test timeouts on the choreography-bound library-modal tests | `web/frontend/features/library/SettingModal.test.tsx` |
| Docs | Design system, component map, routes, structure, workflow, deployment, documentation, architecture, polish acceptance, `CLAUDE.md`, and a reconciled checklist | `docs/*.md`, `CLAUDE.md` |


---

## Completion record

**All twelve phases complete, 2026-08-22.** Committed one per phase on `play-experience`.

| Phase | Outcome |
| --- | --- |
| 1 | `Drawer` primitive + `use-focus-trap` extracted from `Modal`, which passes its own suite unchanged as the proof. |
| 2 | Rails split into `…Content` + `lg`-only shell. All 50 existing rail cases passed **unmodified**. Both asides gained the accessible name they lacked. |
| 3 | Both rails reachable below `lg` as bottom sheets, mounting the same components with the **same prop objects**. Found live: deriving the sheet state from the width left it stale across the `lg` boundary, so narrowing back raised a modal nobody asked for. |
| 4 | Header collapses into `SceneMenu` below `sm` with drill-down rather than nested popovers. **320px overflow 17px → 0**, while *adding* the health indicator and the shortcut sheet to that width. |
| 5 | Storyline switcher reachable at every width. The plan's prescribed width cap was wrong — the overhang was the trigger's 203px offset — and fixing it properly exposed a 4912px-tall popover with no way to scroll it. |
| 6 | Context rail's upload setup collapses below `lg`; document list **34px → 197px**. The collapsed region is `invisible`, not merely clipped, or its `<select>` stays in the tab order. |
| 7 | `sr-only` fixed repo-wide. The plan's `@utility` form **merged** with the core utility and the CSS gate passed while the browser was still served `absolute` — replaced with a bare unlayered rule and a gate that strips `@layer` bodies before asserting. |
| 8 | The 2026-08-21 flake fix had done **one of each pair**; both siblings now carry the budget. Three consecutive full-concurrency runs green at load average 33. |
| 9 | Three families self-hosted. `next build` verified with every proxy pointed at a closed port. Google serves variable fonts, so 11 files/384KB deduped to 5/176KB. |
| 10 | `EXP-2026-08-012`: the first Core Web Vitals numbers this repository has ever had. All three pre-registered hypotheses held, including the one predicting the single failure (story-player INP). |
| 11 | Acceptance pass at 320/375/768/1024: **PASS 19 · PARTIAL 3 · FAIL 0 · DEFERRED 1**. Five defects fixed, including no `<main>` anywhere, an `h1 → h3` tree, and 57 beat controls in one tab order. WCAG 2.1.4 was unmet and now is. |
| 12 | Checklist and routing docs reconciled against all twelve phases. |

**Not built, and recorded rather than skipped:** nothing in this plan was dropped. Two
findings were deliberately *reported* instead of fixed, per Phase 11's own instruction — 39
controls under 24×24 with a mouse and 14 under the house 44px floor in width — because both
are the density the design system specifies; they are in `docs/checklist.md` with the reason.
`:focus-visible` remains genuinely unverifiable in this environment and is re-recorded as
deferred rather than claimed.
