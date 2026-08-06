# Plan — Narration-Driven Progression + Scene Configuration Menu

## 1. Introduction

Two related pieces of scene-play feedback. **(A) Behavior:** in the ReAct turn loop the
narrator lingers on setting/atmosphere and characters talk too much — even in action
moments where a beat should be *acted* (or thought) rather than spoken. The narrator's real
job is to **drive the scene to the next beat** (say what each character is *doing*, move the
story forward), and dialogue should follow once the scene has actually progressed. This is a
**prompt-engineering** change across the three turn-loop agents (`narrator_agent`,
`planner_agent`, `character_turn_agent`) — no new endpoints, no schema.

**(B) Feature:** replace the two inline composer dropdowns (Max turns · Suggestions) with a
full **configuration menu** exposing Max turns, Max suggestions, and a new **Number of beats**
(the per-scene context-window depth, 5–100) with a **live estimated token count** for the
selected beats. "Number of beats" is the same context window the character conditions on
(today the hardcoded `_TRANSCRIPT_MAX_BEATS = 14`); this makes it per-scene and adjustable. It
mirrors the existing `max_turns` / `suggestions_count` per-scene plumbing (model → schema →
crud → migration → frontend) and the buffer must retain enough history to honor up to 100.

## 2. Gaps & Unanswered Questions

- **"Number of beats" meaning (assumption):** it is the **context-window depth** the agents
  condition on — the character transcript slice (currently `_TRANSCRIPT_MAX_BEATS = 14`) and
  the buffer-fetch depth. This is exactly the "how much context does the character get" the
  user just asked about. Scope it to the character transcript + the assembler's buffer fetch;
  leave the planner/narrator/director's short structural windows (10/6/6) untouched.
- **Buffer retention (assumption):** to support up to 100 beats of context, bump the global
  `turn_buffer_size` (12 → 100) so the Redis buffer retains enough; the assembler fetches the
  scene's `context_beats` from it. Default `context_beats = 14` (parity with today).
- **Token estimate (assumption):** frontend-only approximation, `beats × AVG_CHARS_PER_BEAT /
  CHARS_PER_TOKEN` reusing `lib/contextBudget.ts` (`CHARS_PER_TOKEN = 4`). "General
  approximation is fine" — a constant average beat length, updated live as the slider moves.
- **Menu shape (assumption):** a labelled "Config" button left of the input opens an
  accessible popover (Esc/outside-click close, keyboard-operable) holding the three controls +
  the token readout; beats uses a range slider (5–100), turns/suggestions keep dropdowns.
- **Behavior is prompt-only (assumption):** correctness is validated by asserting the new
  guidance in the prompts + that the emission parser already supports action-only / thought-only
  beats (it does). Live model behavior can't be unit-tested; the prompt intent is the contract.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Narration drives progression; characters act/think, don't over-talk (backend prompts)

- **Locations:** `web/backend/app/agents/narrator_agent.py` (`_SYSTEM`, `_SYSTEM_LONG`),
  `web/backend/app/agents/planner_agent.py` (`_SYSTEM` rules),
  `web/backend/app/agents/character_turn_agent.py` (`_OUTPUT_CONTRACT` dialogue rule). Tests:
  `utils/tests/backend/agents/test_narrator_agent.py`, `test_planner_agent.py`,
  `test_character_turn_agent.py`.
- **Rationale:** (narrator) narrate what each character is *doing* and **push to the next
  beat** — narrate action sequences directly (swing→miss→dodge→grab→hit), don't linger on
  setting/mood; (planner) prefer **narration that progresses** the scene, especially during
  action, and let a character **speak only after** the scene has moved and there's a real POV
  reaction to share — not every beat; (character) keep the always-on in-voice `<thinking>`,
  but make spoken `character_dialogue` **optional** — in action moments act and/or think
  without a forced line, so characters stop over-talking. Preserve `<thinking>` / "never
  shown" / "short paragraph" / "full paragraph" phrasings the tests pin.
- **Action:** `.venv/bin/python -m pytest utils/tests/backend/agents`. Commit:
  `Scene Config & Narration (1/4) Complete: narration drives progression; characters act/think over talk.`

### Phase 2 — Per-scene `context_beats` (5–100) + wire the context window + buffer retention

- **Locations:** `web/backend/app/models/scenario.py` (new `context_beats` column, default
  14, server_default), new `web/backend/alembic/versions/…_scenario_context_beats.py`
  (down_revision `c3d4e5f6a7b8`), `web/backend/app/schemas/scenario.py`
  (Base/Update/Read, `ge=5, le=100`), `web/backend/app/services/crud.py` (`create_scenario`
  wiring), `web/backend/app/core/config.py` (`turn_buffer_size` 12 → 100),
  `web/backend/app/services/assembler.py` (`TurnContext.context_beats`; fetch
  `recent_turns(session_id, limit=context_beats)`), `web/backend/app/agents/character_turn_agent.py`
  (`_transcript` slices to `ctx.context_beats`, `_TRANSCRIPT_MAX_BEATS` kept as fallback
  default). Tests: `test_scenarios.py`, `test_buffer.py` (cap now 100), `test_assembler.py`
  (fetch honors context_beats), `test_character_turn_agent.py` (transcript window follows it).
- **Rationale:** make the context depth a per-scene, bounded (5–100) setting the UI drives; the
  buffer must retain ≥ the max so a high setting isn't silently clipped.
- **Action:** `.venv/bin/python -m pytest utils/tests/backend`. Commit:
  `Scene Config & Narration (2/4) Complete: per-scene context_beats (5–100) drives the transcript window.`

### Phase 3 — Frontend configuration menu (turns/suggestions/beats) + live token estimate

- **Locations:** `web/frontend/lib/contextBudget.ts` (new `estimateBeatsTokens(beats)` +
  `AVG_CHARS_PER_BEAT`), `web/frontend/lib/types.ts` (`Scenario.contextBeats`), new
  `web/frontend/components/feature/SceneConfigMenu.tsx` (accessible popover: Max turns +
  Suggestions dropdowns, a beats range slider 5–100, live `~N tok` readout),
  `web/frontend/components/feature/Composer.tsx` (swap the two inline dropdowns for the menu),
  `web/frontend/features/story-player/useScenePlay.ts` (`contextBeats` state + persist via
  `updateScenario`), `web/frontend/features/story-player/StoryPlayerView.tsx` (passthrough).
  Tests: `contextBudget.test.ts`, new `SceneConfigMenu.test.tsx`, `Composer.test.tsx`,
  `StoryPlayerView.test.tsx`.
- **Rationale:** the requested full config menu; the beats slider needs its own control (5–100
  is too many for a dropdown) and shows the live token estimate.
- **Action:** `npm test` + `npm run typecheck` + a11y/responsive pass (popover keyboard +
  Esc/outside-click, slider aria, 320/375/768/1024). Commit:
  `Scene Config & Narration (3/4) Complete: scene config menu with beats slider + live token estimate.`

### Phase 4 — Docs + full validation + merge

- **Locations:** `docs/api-contract.md` (`contextBeats` on the scenario shape),
  `docs/data-flow.md` (per-scene context window + config menu, narration-progression note),
  `docs/design-system.md` (config menu + token readout), `docs/component-map.md`
  (`SceneConfigMenu` + `estimateBeatsTokens`), `docs/workflow.md` (if `turn_buffer_size`
  default is documented), `docs/checklist.md`.
- **Action:** full `.venv/bin/python -m pytest` + frontend `npm test`, `npm run typecheck`,
  `npm run lint`, and `next build` (in the primary checkout after merge). Commit:
  `Scene Config & Narration (4/4) Complete: docs + full validation.` Then merge
  `feat/scene-config-and-narration` → `main` (no push).

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Narrator-progression prompt | Narrate character action, drive to next beat | `web/backend/app/agents/narrator_agent.py` |
| Planner progression bias | Narrate-to-progress; dialogue only after movement | `web/backend/app/agents/planner_agent.py` |
| Optional-dialogue character contract | Act/think in action moments, don't over-talk | `web/backend/app/agents/character_turn_agent.py` |
| `context_beats` per-scene setting | 5–100 context-window depth | `scenario.py` (model/schema), `crud.py`, alembic, `config.py`, `assembler.py` |
| Scene config menu | Turns · Suggestions · Beats + token readout | `web/frontend/components/feature/SceneConfigMenu.tsx`, `Composer.tsx`, `useScenePlay.ts` |
| Beats token estimate | Live approximate tokens for N beats | `web/frontend/lib/contextBudget.ts` |
| Tests | Prompts, context_beats plumbing, buffer cap, menu + estimate | `utils/tests/backend/...`, co-located frontend tests |
</content>
