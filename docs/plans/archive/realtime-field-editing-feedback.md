# Real-Time Field Editing Feedback

## 1. Introduction

Whenever Mytheca's agentic authoring runs — the New Storyline "Build the whole world"
flow, drafting or editing a Character or Setting, or generating voice samples,
starting stats, and portrait/scene-art prompts — the interface should clearly
showcase **which field is being written at that exact moment**, where we are in the
overall process, and any error, without the author having to guess. Today only the
world-build page streams (fields pop in with a single `aria-live` status line and no
per-field emphasis); the Character/Setting drafts return the whole result at once so
every field lands simultaneously; and errors surface only as a single inline alert.

This plan adds one **shared, reusable feedback layer** on the Next.js frontend and
wires it into every agentic surface: (a) a **field-reveal choreography** that lights
up and fills fields one after another with a live "editing now" highlight, (b) a
compact **process/step indicator** showing the current major step and the next one,
and (c) a **top-right toast** notification system for errors and completions. The
world-build page drives the choreography from its real NDJSON stream events; the
all-at-once Character/Setting drafts drive it from a client-side staged reveal (the
decision locked with the user). **No backend change is required** — the build stream
and its `BuildStatusEvent.stage` vocabulary already exist, and the draft endpoints
stay plain JSON. The work reuses the existing `mythecaGlowPulse`/`.mytheca-glow`
pattern, the `embMsg`/`embFade` keyframes, the global reduced-motion rule, and the
established `aria-live` conventions rather than introducing new dependencies.

## 2. Gaps & Unanswered Questions

Resolved with the user:

- **Scope — all agentic surfaces** (world build + Character + Setting + voice / stats
  / prompt generation), one shared system applied everywhere.
- **Reveal mechanism for all-at-once drafts — choreographed reveal**: after the JSON
  arrives the frontend stages a field-by-field fill + highlight (no backend
  streaming rework). The world-build page uses its genuine stream events.
- **Errors — top-right toast** (from the request: "a popup or a notification in the
  top-right corner"), backed by a new reusable notification system.

Assumptions (simple gaps — proceeding):

- **No backend change.** The build stream already emits structured stages; the
  Character/Setting/voice/stats/prompt endpoints stay plain JSON. Backend `pytest` is
  run only to confirm no regression (expected N/A).
- **Reduced motion:** the field-reveal cadence collapses to an instant, all-at-once
  fill and the glow becomes a static border under `prefers-reduced-motion`, matching
  the app's existing global rule (`.mytheca-themed *` strips `animation`, keeps
  `box-shadow`). No per-feature media query needed.
- **Reveal cadence:** a short per-field interval (~120–180 ms, tunable constant) that
  reads as "being typed in" without feeling slow; fully skippable and non-blocking
  (the underlying draft values are already final — the choreography is purely
  presentational and can be interrupted by the user editing a field).
- **Toast scope:** app-global provider mounted once at the themed root; used for
  agentic errors now, reusable for future success/info toasts.
- **Work happens in a git worktree** off `main`, merged at the end (frontend build
  needs a hardlink-copied `node_modules` per the worktree-build gotcha; backend tests
  run via the repo-root `.venv`).

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Shared feedback primitives (foundation)

Build the reusable layer once, with no surface wired yet, so later phases only
compose it.

- **Locations:**
  - `web/frontend/styles/themes.css` — add a `@keyframes mythecaFieldFill` (a brief
    accent wash/settle) and a `.mytheca-field-active` utility (active-field highlight
    built on the existing `--glow-color` / `mythecaGlowPulse` idiom, defaulting
    `--glow-color: var(--accent)`); confirm the existing reduced-motion block already
    neutralizes both.
  - `web/frontend/hooks/use-field-reveal.ts` — the choreography engine: given an
    ordered `Array<{ key, value }>` it exposes `{ values, activeKey, done, start,
    reset }`, revealing one field per tick on a tunable interval, collapsing to
    instant under reduced motion, and safely aborting on unmount / restart.
  - `web/frontend/hooks/use-toast.ts` + `web/frontend/components/layout/ToastProvider.tsx`
    + `web/frontend/components/ui/Toast.tsx` — a portal-based, top-right, stacking
    toast system (`role="status"` for info, `role="alert"` for errors; `embMsg`
    entrance; auto-dismiss with a manual close; reduced-motion safe). Provider mounted
    once in the themed root layout (`web/frontend/app/layout.tsx` or its themed
    wrapper).
  - `web/frontend/components/feature/ProcessProgress.tsx` — a compact stepper showing
    the ordered stages with `done | active | pending` state, the **current** step, and
    a "Next: …" hint; wrapped in an `aria-live="polite"` region.
- **Rationale:** every subsequent phase consumes these; building and testing them in
  isolation keeps the surface phases small and lets the reduced-motion / a11y behavior
  be verified once.
- **Action:** Run this phase's validation — frontend component/route tests for the new
  hook + components (`use-field-reveal.test.ts`, `Toast.test.tsx`,
  `ProcessProgress.test.tsx`) plus `tsc` + ESLint; an accessibility pass on the new
  primitives (toast roles/focus, live-region announce, reduced-motion collapse).
  Backend untouched → `pytest` N/A. Once green, commit locally:
  `[Real-Time Field Feedback] (1/5) Complete: Shared field-reveal, toast, and process-progress primitives.`

### Phase 2 — World-build page: live field highlight, progress, toast

Wire the real NDJSON stream into the primitives.

- **Locations:**
  - `web/frontend/features/library/useStorylineCreator.ts` — add `activeField`
    (left-pane key being written, from `meta`/`primer` events; the `meta` event's four
    fields staged through the reveal engine for a sequential feel) and
    `activeEntity { type, index }` (from `character`/`setting` events), plus a
    structured `stage` for the stepper; route build `error` events to a toast.
  - `web/frontend/features/library/StorylineCreatorView.tsx` — apply
    `.mytheca-field-active` to the currently-written left-pane `TextField`/`TextArea`;
    render `ProcessProgress` for the build stages (metadata → primer → blueprint →
    extract → characters → settings → done) with current + next.
  - `web/frontend/components/feature/WorldBuildPanel.tsx` — glow the card at the active
    entity index (and the active pending concept) using `.mytheca-field-active`,
    keeping the existing skeleton/render pulses.
- **Rationale:** this surface already streams, so it proves the primitives against real
  events and delivers the highest-value target first.
- **Action:** Run validation — hook tests (activeField on `meta`/`primer`, activeEntity
  on `character`/`setting`, toast on `error`), `StorylineCreatorView` active-class +
  progress assertions, `WorldBuildPanel` active-card highlight; `tsc` + ESLint; a11y +
  responsive pass at 320/375/768/1024 (or documented deferral per the standing
  shared-dir/CORS constraint). Once green, commit:
  `[Real-Time Field Feedback] (2/5) Complete: World-build page shows live field/entity highlight, step progress, and error toasts.`

### Phase 3 — Character creation/editing: choreographed reveal, progress, toast

- **Locations:**
  - `web/frontend/features/library/useLibraryState.ts` — in `draftCharacter`, feed the
    returned fields into `use-field-reveal` in a natural order (name → role → traits →
    speech → goal → secret → appearance → background → personality), then advance
    through the existing sequential voice-samples and starting-stats sub-steps as named
    stages; expose `activeField` + a `stage` descriptor; route `error` to a toast.
    `proposeVoiceSamples` / `proposeStartingStats` reveal their rows as they populate.
  - `web/frontend/components/feature/CharacterModal.tsx` — apply `.mytheca-field-active`
    to the active field; render `ProcessProgress` ("Drafting identity → Voice & tone →
    Starting stats → Portrait"); highlight the voice/stat rows as they fill; surface
    errors via toast (replacing the bare inline `role="alert"` line, or in addition).
  - `web/frontend/components/feature/VoiceSamplesEditor.tsx` /
    the stats rows — accept an `activeIndex` to glow the row being written.
- **Rationale:** the flagship "create a new character" surface is where the user most
  wants to *see* fields fill in; the choreography turns the all-at-once JSON into the
  requested "this field, then that field" experience with no backend rework.
- **Action:** Run validation — hook tests (reveal order, stage advance through
  voice/stats, reduced-motion instant, error→toast), `CharacterModal` active-class +
  progress + row highlight tests; `tsc` + ESLint; a11y + responsive pass (or documented
  deferral). Once green, commit:
  `[Real-Time Field Feedback] (3/5) Complete: Character create/edit choreographs field-by-field reveal with progress and toasts.`

### Phase 4 — Setting + prompt/image generation: reveal, progress, toast

- **Locations:**
  - `web/frontend/features/library/useLibraryState.ts` — `draftSetting` choreographs
    desc → atmosphere → features → currentState; `generatePortraitPrompts` /
    `generateSceneArtPrompts` reveal positive → negative as they land; errors → toast.
  - `web/frontend/components/feature/SettingModal.tsx` — active-field highlight +
    `ProcessProgress` ("Drafting place → Scene art") + toast.
  - `web/frontend/components/feature/PortraitModal.tsx` +
    `web/frontend/components/feature/SceneArtModal.tsx` — highlight the positive/negative
    prompt fields as they populate, a short progress line ("Writing prompt →
    Rendering image"), and errors via toast.
- **Rationale:** completes the "all agentic surfaces" scope; Setting mirrors Character,
  and the image/prompt modals are the last places an author waits on the agent.
- **Action:** Run validation — `draftSetting` reveal-order tests, `SettingModal` +
  `PortraitModal`/`SceneArtModal` active-class/progress/toast tests; `tsc` + ESLint;
  a11y + responsive pass (or documented deferral). Once green, commit:
  `[Real-Time Field Feedback] (4/5) Complete: Setting + portrait/scene-art prompt generation get field reveal, progress, and toasts.`

### Phase 5 — Docs, full validation, merge

- **Locations:**
  - `docs/design-system.md` — the `mythecaFieldFill` keyframe + `.mytheca-field-active`
    utility, the toast system, and the `ProcessProgress` pattern (with reduced-motion
    behavior).
  - `docs/component-map.md` — new components (`Toast`/`ToastProvider`,
    `ProcessProgress`) and the `activeField`/`activeEntity` additions to the touched
    views/hooks.
  - `docs/data-flow.md` — a note that agentic authoring now emits presentational
    field-reveal + progress + toast state on the frontend (no new backend events).
  - `docs/documentation.md` — status line; `docs/checklist.md` — a "done" entry.
- **Rationale:** docs move in the same change per the project rules; the final pass
  proves the whole feature green before merge.
- **Action:** Run the full gate — backend `uv run pytest` (confirm untouched/green),
  frontend `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`; a
  consolidated a11y + responsive pass at 320/375/768/1024 (keyboard, focus, contrast,
  live-region announce, reduced-motion), documenting any deferral in
  `docs/checklist.md`. Once green, commit:
  `[Real-Time Field Feedback] (5/5) Complete: Docs, full validation, and merge to main.`
  Then merge the worktree into `main`, resolving any conflicts.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Field-active styles | `mythecaFieldFill` keyframe + `.mytheca-field-active` utility (reduced-motion safe) | `web/frontend/styles/themes.css` |
| Field-reveal hook | Choreography engine: ordered field reveal with active-key + done state | `web/frontend/hooks/use-field-reveal.ts` |
| Toast system | Portal, top-right, stacking notifications (info/alert), reduced-motion safe | `web/frontend/components/ui/Toast.tsx`, `web/frontend/components/layout/ToastProvider.tsx`, `web/frontend/hooks/use-toast.ts` |
| Process progress | Compact stepper: current + next major step, `aria-live` | `web/frontend/components/feature/ProcessProgress.tsx` |
| World-build wiring | Live field/entity highlight, step progress, error toasts | `web/frontend/features/library/useStorylineCreator.ts`, `StorylineCreatorView.tsx`, `components/feature/WorldBuildPanel.tsx` |
| Character wiring | Choreographed field reveal + voice/stats stages + toast | `web/frontend/features/library/useLibraryState.ts`, `components/feature/CharacterModal.tsx`, `components/feature/VoiceSamplesEditor.tsx` |
| Setting + prompt wiring | Setting reveal + portrait/scene-art prompt reveal + toast | `web/frontend/features/library/useLibraryState.ts`, `components/feature/SettingModal.tsx`, `PortraitModal.tsx`, `SceneArtModal.tsx` |
| Frontend tests | Hook + component tests for reveal, toast, progress, and each wired surface | co-located `*.test.ts(x)` beside each unit (Vitest) |
| Docs | design-system, component-map, data-flow, documentation, checklist updates | `docs/*.md` |

## 5. Notes

- **Reduced motion & a11y are first-class:** the reveal collapses to instant, the glow
  becomes a static border, toasts announce via `role`/`aria-live`, and the stepper is a
  live region — all verified in Phase 1 and re-checked per surface.
- **Non-blocking choreography:** the revealed values are already final, so the animation
  never gates saving; a user editing a field mid-reveal cancels the choreography for
  that field.
- **No new dependencies, no backend change.** Framer Motion + existing keyframes cover
  motion; the build stream already carries the stage vocabulary.
