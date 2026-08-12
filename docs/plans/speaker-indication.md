# Plan — Speaker Indication in the Story Player

## Problem

While a turn is streaming, the reading column gives the player almost nothing about
*who is up*. Prose simply appears. There is no signal that a new speaker has been
chosen, that a character is mid-line, that the narrator is setting context, or that the
turn is about to end. The only live speaker signal in the app is the `CastRail`
Thinking/Speaking marker — and that rail is `hidden … lg:block`, so below 1024px there is
no speaker indication at all.

The backend already emits everything needed; nothing reaches the transcript column:

| Signal | Source (backend) | Consumed today |
| --- | --- | --- |
| A speaker was chosen | `trace` step `speaker` (`data.characterId`, `data.name`) | `applyActivity` (Director rail feed) + `applyCharacterActivity` (cast rail) |
| A character is mid-line | `character_dialogue` with `done: false` | `applyCharacterActivity` |
| The narrator is writing | `narration` with `done: false` | nothing |
| The turn is ending | `trace` step `plan`, title `"The turn ends"` / the two limit stops | prose title only — no structured flag |

## Goal

A live **turn status strip** at the foot of the transcript, visible at every breakpoint,
that names who is up and animates while they are working:

- `Mei is about to speak` + animated dots — a speaker has been chosen, nothing written yet
- `Mei is speaking` + dots — their dialogue is streaming
- `Mei is acting` + dots — a physical beat landed for them
- `The narrator is setting the scene` + dots — narration is streaming
- `The turn is ending` — the planner called the turn
- `The scene is unfolding` + dots — streaming, but between beats (no flicker gap)
- nothing at all when no turn is in flight

## Gaps & Decisions

- **Turn-end detection must not parse prose.** `"The turn ends"` is a human title that will
  drift. Decision: the backend stamps `data.end = true` on every trace step that stops the
  beat loop (planner end, POV backstop, scene turn-limit, runaway beat-limit). Additive to
  `data`, so no consumer breaks.
- **One status, not a second activity map.** `applyCharacterActivity` (per-character, for the
  rail) stays as-is. The strip needs *the scene's current focus*, which is a single value —
  a separate small reducer, not a widening of the map.
- **Live-region chattiness.** `TranscriptAnnouncer` already speaks finished beats. The strip
  gets `role="status" aria-live="polite"` on a label that changes at most once per beat;
  the dots are `aria-hidden`. Verified not to duplicate the announcer's text.
- **`TypingDots` is currently private to `CastRail`.** Two consumers now → it moves to
  `components/ui/` per the ownership rule (primitives in `components/ui/`).
- **Assumption:** no new theme tokens. The strip uses existing `--card`/`--hair`/character
  color and the existing `embDots` keyframe, so `check_contrast.py` is not implicated.

---

## Phase 1 — Backend: a structured turn-end flag

**Files:** `web/backend/app/services/turn_engine.py`,
`utils/tests/backend/api/test_play_turn.py` (the Inspector-trace section, where every other
trace test lives), `docs/api-contract.md`

1. Add `data={"end": True}` to the four trace emits that stop the beat loop:
   - `"The turn ends"` (planner `decision.action == "end"`, ~L559)
   - `"The turn ends"` (POV backstop, ~L553)
   - `"Reached the scene's turn limit"` (~L478) — merge into its existing `data`
   - `"Reached the turn's beat limit"` (~L633)
2. Document the flag in `docs/api-contract.md`'s *Diagnostic trace* section: a `plan` step
   with `data.end === true` marks the end of the beat loop.

**Validation:** `uv run pytest utils/tests/backend/api/test_play_turn.py` — a new test drives a
turn and asserts exactly one `plan` trace step carries `data.end is True`, and that it is the
turn's last `plan` step.
**Commit:** `Mytheca — turn engine: flag the turn-ending trace step with data.end`

---

## Phase 2 — Frontend: the `turnStatus` reducer

**Files:** `web/frontend/features/story-player/turn-stream.ts`,
`web/frontend/features/story-player/turn-stream.test.ts`

1. Export `TurnPhase = "idle" | "thinking" | "speaking" | "acting" | "narrating" | "ending"`
   and `TurnStatus = { phase: TurnPhase; characterId?: string; name?: string }`, plus
   `IDLE_TURN_STATUS`.
2. Export `applyTurnStatus(prev: TurnStatus, frame: TurnStreamFrame): TurnStatus` —
   pure, returns the **same reference** when nothing changes (the reducer is called on every
   delta frame; a fresh object per chunk would re-render the strip on every token):
   - trace `speaker` → `thinking` for `data.characterId` / `data.name`
   - trace `plan` with `data.end === true` → `ending`
   - `internal_thought` → `thinking` for that character
   - `character_action` → `acting`
   - `character_dialogue` → `speaking`; `done: true` → `idle`
   - `narration` → `narrating`; `done: true` → `idle`
   - `error` → `idle`; everything else → unchanged
3. Tests: one per transition, plus same-reference stability across repeated delta chunks,
   plus `ending` surviving the trailing `branch_choices`/`commit` frames.

**Validation:** `npm test -- turn-stream` in `web/frontend`.
**Commit:** `Mytheca — story player: a turn-status reducer over the stream`

---

## Phase 3 — Frontend: `TypingDots` primitive + `TurnStatusStrip`

**Files:** `web/frontend/components/ui/TypingDots.tsx` (+ `.test.tsx`),
`web/frontend/components/feature/CastRail.tsx`,
`web/frontend/components/feature/TurnStatusStrip.tsx` (+ `.test.tsx`)

1. Move `TypingDots` out of `CastRail` into `components/ui/TypingDots.tsx` unchanged
   (`aria-hidden`, `data-testid="typing-dots"`, `embDots` inline animation with a visible
   static baseline for reduced motion). Import it in `CastRail`; its existing test keeps
   passing untouched.
2. New `components/feature/TurnStatusStrip.tsx`:
   - props: `status: TurnStatus`, `streaming: boolean`, `charById`
   - renders `null` when `!streaming`
   - resolves the display name: cast lookup → the trace's `name` → `"Someone"`
   - centered strip: small `Monogram` in the character color (omitted for narrator/idle),
     the label, then `TypingDots` (suppressed in the `ending` phase — nothing follows)
   - `role="status" aria-live="polite"`; dots `aria-hidden`
   - Framer Motion entrance with `ENTER_TRANSITION`, matching the transcript beats
3. Tests: each phase's label, the monogram only for character phases, no dots while
   `ending`, and `null` when not streaming.

**Validation:** `npm test -- TypingDots TurnStatusStrip CastRail` + `npm run typecheck`.
**Commit:** `Mytheca — story player: TurnStatusStrip + shared TypingDots primitive`

---

## Phase 4 — Wire it into the live scene

**Files:** `web/frontend/features/story-player/useScenePlay.ts` (+ `.test.ts`),
`web/frontend/features/story-player/StoryPlayerView.tsx` (+ `.test.tsx`)

1. `useScenePlay`: `turnStatus` state seeded `IDLE_TURN_STATUS`, folded in `onFrame`
   alongside the existing activity reducers, reset to idle in `submit(...).finally`
   (beside the existing `setActivityByChar({})`), and returned.
2. `StoryPlayerView`: render `<TurnStatusStrip …/>` inside the transcript column, directly
   below the beat list — where `CreateImageBar` sits when idle, so the two swap cleanly
   (`sending` gates them in opposite directions and the composer never hops).
3. Tests: `useScenePlay` — a streamed `speaker` trace sets `thinking`; a finished turn
   returns to `idle`. `StoryPlayerView` — the strip renders during a stream and not after.

**Validation:** `npm test` (full frontend suite) + `npm run typecheck` + `npm run lint`;
`uv run pytest`; accessibility/responsive pass at 320 / 375 / 768 / 1024 px (the strip is
breakpoint-independent — it is the only speaker signal below `lg`).
**Commit:** `Mytheca — story player: show who is about to speak while a turn streams`

---

## Phase 5 — Docs + close-out

**Files:** `docs/component-map.md`, `docs/data-flow.md`, `docs/design-system.md`,
`docs/checklist.md`, `CLAUDE.md`

1. `docs/component-map.md` — add `TurnStatusStrip` (feature) and `TypingDots` (primitive);
   note `TypingDots` no longer lives inside `CastRail`.
2. `docs/data-flow.md` — the `speaker`/`plan(end)` trace steps now drive a visible transcript
   affordance, not only the Inspector.
3. `docs/design-system.md` — record the turn-status strip as a UI state of the story player.
4. `CLAUDE.md` — component counts (49 feature / 18 primitives).
5. `docs/checklist.md` — record anything deferred.

**Validation:** full gate re-run (`uv run pytest`, `npm test`, `npm run typecheck`, `npm run lint`).
**Commit:** `Mytheca — docs: record the turn-status strip`

---

## Deliverables

| Deliverable | Path |
| --- | --- |
| Turn-end trace flag | `web/backend/app/services/turn_engine.py` |
| Backend test | `utils/tests/backend/api/test_play_turn.py` |
| Turn-status reducer | `web/frontend/features/story-player/turn-stream.ts` |
| Shared dots primitive | `web/frontend/components/ui/TypingDots.tsx` |
| Status strip | `web/frontend/components/feature/TurnStatusStrip.tsx` |
| Wiring | `useScenePlay.ts`, `StoryPlayerView.tsx` |
| Docs | `api-contract.md`, `component-map.md`, `data-flow.md`, `design-system.md`, `CLAUDE.md` |
