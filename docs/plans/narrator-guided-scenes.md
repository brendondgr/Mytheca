# Narrator-Guided Scenes — Implementation Plan

Make the narrator a **director**. Today the player's line is an opaque stimulus that the
intent agent classifies (puppet / addressed / broadcast / freeform) and the ReAct planner
answers one beat at a time. What the line cannot do is *commit the turn to an outcome*:
"Mei storms out and Aldous tries to stop her, then the lamp goes over" produces whatever
the planner felt like producing, in whatever order, and nothing guarantees it all lands
before the scene's turn cap.

This plan adds a **scene direction** — a structured, budget-scheduled contract between
what the player asked for and what the turn actually emits:

- The direction is parsed into an ordered list of **requirements** (each optionally bound
  to a cast member).
- The planner sees the outstanding requirements and the remaining beat budget every step.
- When the budget gets tight the engine stops asking and **forces** the schedule, so every
  requirement is covered within `scenario.max_turns` beats.
- Each speaker's prompt states *their* requirement as something that must be true by the
  end of their beat — a **guide, not a script**. They still stay in character, still choose
  their own words, still emit the same tagged format.

And it gives POV mode a place to type that direction: a second, smaller text box **above**
the "Speaking as …" composer, so the player can voice a character *and* steer the scene in
the same turn.

## Assumptions and decisions

| # | Decision | Rationale |
| --- | --- | --- |
| D1 | The direction text is `req.guidance` when the player typed one; otherwise, **when POV is off**, the player's own line is the direction. | "Narrator as Director" — in narrator mode the main box already *is* the narrator box. In POV mode the main box is the character's line and must never be read as direction. |
| D2 | In narrator mode the requirements are extracted by **`intent_agent`'s existing call** (one extra JSON field), not a second LLM round-trip. A standalone `direction_agent.parse` call runs only for POV-mode guidance, which is a *different* string. | Local reasoning models are slow (`velora-reasoning-model-llm-budget`); the turn already makes 1 intent + N planner + N character calls. Zero added latency for the common path. |
| D3 | A requirement is **satisfied** when a beat that carried it into the prompt is emitted — deterministic, not an LLM judgement. | An LLM "did that happen?" check per beat would double the turn's call count for a signal the prompt already forced. Testable and predictable. |
| D4 | A requirement bound to an actor who is **absent or is the POV character** is rebound to the narrator (`actor_id = None`). | The AI never voices the POV character (existing lock-out), and a departed character cannot act. Narration can still make the event occur. |
| D5 | When only **one** beat of budget remains and more than one requirement is outstanding, the last beat is a **narrator** beat carrying all of them. | Guarantees "within the specified number of turns" without exceeding `max_turns`, which the scene-cap contract treats as hard. |
| D6 | Sending still requires the main composer text. Guidance alone does not submit a turn. | `validate_turn_inputs` requires `text`, and the optimistic bubble / `user_turn` row are keyed to it. Guidance-only turns are recorded in `docs/checklist.md` as unbuilt. |
| D7 | The guidance box renders **only when POV is active**. | Exactly what was asked for; in narrator mode a second box would duplicate the first. |

### Open gaps (flagged, not guessed)

- **Guidance is not persisted on the `user_turn` row.** It shapes the turn it was sent
  with and is visible in the Inspector trace, but a session reload does not restore the
  guidance text into the box. Recorded in `docs/checklist.md`.
- **Requirement satisfaction is structural (D3).** If a character ignores their stated
  requirement, nothing catches it. A verification pass would be a second LLM call per beat.

---

## Phase 1 — The direction contract

**Goal:** a parsed, roster-constrained `SceneDirection` and a wire field to carry guidance.

1. **`web/backend/app/agents/direction_agent.py`** (new)
   - `DirectionRequirement(id, actor_id: str | None, text: str, satisfied: bool = False)`.
   - `SceneDirection(text: str = "", requirements: list[DirectionRequirement])` with
     `active` (truthy text or requirements), `outstanding()`, and `rebind(present_ids,
     locked_id)` implementing D4.
   - `REQUIREMENTS_SCHEMA` / `REQUIREMENTS_RULES` — the shared prompt fragment describing
     the `requirements` JSON array, imported by `intent_agent` so the two callers cannot
     drift.
   - `resolve_requirements(raw, roster_ids) -> list[DirectionRequirement]` — roster-
     constrained, de-duped, order preserved, unknown actor → `None` (narrator-owned).
   - `parse(db, ctx, text) -> SceneDirection` — one LOW-effort structural call.
     Best-effort: unconfigured/failed/malformed → a single actor-less requirement holding
     the whole guidance text, so the narrator still covers it.
   - `schedule(outstanding, remaining) -> ScheduledBeat(actor_id, requirements)` — the
     deterministic packer (D5): bundle `max(1, len(outstanding) - remaining + 1)`
     same-owner requirements; collapse to a narrator beat when `remaining <= 1` and more
     than one is left.
2. **`web/backend/app/agents/intent_agent.py`** — add `requirements: list[DirectionRequirement]`
   to `TurnIntent`, append the shared fragment to `_SYSTEM`, parse via
   `resolve_requirements`. Fallback path yields `[]` (unchanged behavior).
3. **`web/backend/app/schemas/play.py`** — `TurnRequest.guidance: str | None = None`, documented.

**Validation:** new `utils/tests/backend/agents/test_direction_agent.py` (parse happy path,
malformed → whole-text fallback, unconfigured LLM → fallback, roster constraint, `rebind`,
`schedule` packing incl. the `remaining == 1` collapse) + existing
`test_intent_agent.py` still green. Run `uv run pytest utils/tests/backend/agents`.
**Commit:** `[Narrator-Guided Scenes] (1/5) Complete: …`

---

## Phase 2 — Scheduling the direction across the turn budget

**Goal:** the turn engine honors the direction and provably lands it inside `max_turns`.

1. **`web/backend/app/services/turn_engine.py`**
   - Build the direction per D1, then `rebind` it against the present roster and `pov_id`.
   - Emit a `direction` trace step naming the requirements (so the Inspector shows the
     contract, and the player can see it being consumed).
   - Pass the direction text as the narrator `lead` for the scene-opening / branch
     progression passage, consuming the actor-less requirements it covers.
   - Mark requirements bound to a puppeted actor satisfied after the puppet beats.
   - In the ReAct loop, before each planner call: compute `remaining = max_turns - scene_beats`
     and `outstanding`. If `outstanding and len(outstanding) >= remaining`, **skip the
     planner** and run `direction_agent.schedule(...)` instead (trace step says so).
     Otherwise call the planner with the outstanding requirements + remaining budget.
   - A `speak` beat carries the requirements owned by that actor; a `narrate` beat carries
     the next actor-less requirement. Both mark them satisfied.
   - Trace an explicit "direction satisfied" / "direction unmet" summary at turn end.
2. **`web/backend/app/agents/planner_agent.py`** — `next_beat(..., direction=None,
   remaining_beats=None)`. Renders the outstanding requirements and the remaining budget
   into the user prompt. `_fallback_beat` prefers an unsatisfied requirement's actor over
   its current heuristics, so the offline path honors the direction too.
3. **`web/backend/app/agents/prompt_registry.py`** — `_PLANNER_SYSTEM` gains the
   direction rules (follow it closely; schedule everything left into the beats left; the
   direction is the outcome, the characters own the words).

**Validation:** new `utils/tests/backend/api/test_play_turn_direction.py` (the engine is
exercised end-to-end through the turn endpoint, where the other turn-loop suites live) — a
stubbed LLM turn proving (a) every requirement is emitted within `max_turns`, (b) the forced schedule
fires when the budget is tight, (c) a POV-bound requirement is rebound to the narrator,
(d) no direction ⇒ byte-identical planner arguments to today. Plus `test_planner_agent.py`
additions. Run `uv run pytest utils/tests/backend`.
**Commit:** `[Narrator-Guided Scenes] (2/5) Complete: …`

---

## Phase 3 — Characters and the narrator perform the direction

**Goal:** the direction reaches the writing prompts as a guide, never as a script.

1. **`web/backend/app/agents/character_turn_agent.py`** — `generate_line_with_usage(...,
   scene_direction: str = "", requirement: str = "")`.
   - MIDDLE gains "Where the scene is going: …" (the overall direction) so an unassigned
     speaker still plays toward it.
   - TAIL gains the speaker's own requirement, phrased as an outcome to reach in their own
     voice — placed *before* the generic "respond now" line so it reads as the beat's job.
   - Composes with the `directive` (puppet) tail rather than replacing it.
2. **`web/backend/app/agents/prompt_registry.py`** — one rule in
   `_CHARACTER_OUTPUT_CONTRACT`: when the beat states a direction, make it happen this
   beat, in character, in your own words; never quote or narrate the direction itself.
3. **`web/backend/app/agents/narrator_agent.py`** — `interstitial(..., lead=…)` already
   exists; extend its docstring and let the engine pass a composed lead (direction text +
   the specific requirements this beat owes).

**Validation:** `utils/tests/backend/agents/test_character_turn_agent.py` additions
(direction in MIDDLE, requirement in TAIL, absent when unset, composes with `directive`),
`test_narrator_agent.py` additions. Run `uv run pytest utils/tests/backend`.
**Commit:** `[Narrator-Guided Scenes] (3/5) Complete: …`

---

## Phase 4 — The POV guidance box

**Goal:** a second, smaller text box above the composer input whenever POV is active.

1. **`web/frontend/lib/events.ts`** — `TurnRequestBody.guidance?: string | null`.
2. **`web/frontend/components/feature/Composer.tsx`** — a `guidance` / `onGuidanceChange`
   pair. When both are supplied **and** `pov` is set, render an auto-growing textarea
   (cap ~120px) above the message textarea, separated by a hairline `border-field-bd`
   rule, `aria-label="Scene direction"`, placeholder
   "Guide the scene — what happens next…". Enter sends (Shift+Enter newlines), matching
   the main box. The panel grows upward, which is the "pushes the screen up slightly"
   behavior asked for.
3. **`web/frontend/features/story-player/useScenePlay.ts`** — `guidance` state, sent as
   `guidance` on the turn, cleared alongside the composer on send, and cleared when POV is
   dropped (the box disappears; stale text must not ride along).
4. **`web/frontend/features/story-player/StoryPlayerView.tsx`** — wire the two props.

**Validation:** `Composer.test.tsx` (hidden without POV, shown with POV, typing propagates,
Enter sends, labelled for screen readers), `useScenePlay` coverage via the existing
story-player suite. Accessibility/responsive pass: keyboard order (guidance → message →
config → POV → send), visible focus, AA contrast on the placeholder, layout at
320/375/768/1024. `npm test`, `npm run typecheck`, `npm run lint`.
**Commit:** `[Narrator-Guided Scenes] (4/5) Complete: …`

---

## Phase 5 — Docs, full validation, and the cross-worktree merge

1. Update `docs/api-contract.md` (the `guidance` field), `docs/data-flow.md` (the direction
   contract on the turn path), `docs/component-map.md` (Composer's second box),
   `docs/documentation.md` (agent list gains `direction_agent`), `CLAUDE.md` (the agents
   table), and `docs/checklist.md` (the two gaps above).
2. Full gate: `uv run pytest`, `npm test`, `npm run typecheck`, `npm run lint`.
3. **Merge:** bring `main` in (it may by then carry the character-dialogue-flexibility
   work, which touches the *same* call sites in `planner_agent`, `character_turn_agent`,
   and `turn_engine` with its own additive `register`/`stakes` keyword arguments).
   Resolve by **keeping both** sets of parameters — they are orthogonal (register =
   *how the moment feels*; direction = *what must happen*). Re-run the full gate after the
   merge, then merge into `main` and remove this worktree.
**Commit:** `[Narrator-Guided Scenes] (5/5) Complete: …`

---

## Deliverables

| Path | Change |
| --- | --- |
| `web/backend/app/agents/direction_agent.py` | **new** — requirements, parse, schedule |
| `web/backend/app/agents/intent_agent.py` | requirements on `TurnIntent` |
| `web/backend/app/agents/planner_agent.py` | direction + remaining budget |
| `web/backend/app/agents/character_turn_agent.py` | direction + per-beat requirement |
| `web/backend/app/agents/narrator_agent.py` | composed lead |
| `web/backend/app/agents/prompt_registry.py` | planner + character contract rules |
| `web/backend/app/services/turn_engine.py` | build / schedule / consume the direction |
| `web/backend/app/schemas/play.py` | `TurnRequest.guidance` |
| `web/frontend/lib/events.ts` | `TurnRequestBody.guidance` |
| `web/frontend/components/feature/Composer.tsx` | the POV guidance box |
| `web/frontend/features/story-player/useScenePlay.ts` | guidance state → turn |
| `web/frontend/features/story-player/StoryPlayerView.tsx` | wiring |
| `utils/tests/backend/agents/test_direction_agent.py` | **new** |
| `utils/tests/backend/api/test_play_turn_direction.py` | **new** |
| `web/frontend/app/globals.css` | per-field composer focus indicator |
| `docs/*` | contract, data flow, component map, checklist |
