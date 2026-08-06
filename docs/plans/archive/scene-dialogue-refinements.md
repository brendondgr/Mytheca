# Plan — Scene Dialogue System Refinements

## 1. Introduction

A first round of Scene Dialogue updates shipped (per-scene turn limit, follow-up
suggestions, guided selection, deeper character thinking, composer controls). System
feedback asks for four refinements to how a live scene reads and plays. All four are
surgical changes over the existing turn loop and story-player UI — no new routes, no
schema migrations. The work spans the FastAPI turn engine + director agent (backend) and
the Next.js story player (frontend).

The four requests:

1. **Situation-based path suggestions.** The "choose a path" follow-ups should describe
   *what happens next in the scenario* from a **general, story-wide perspective** — not a
   specific character's next line (we play a general narrator/director, not a POV
   character). Suggestions must match the **tone and pace** of what the player has already
   written or selected, so they read like the player's own moves.
2. **Selection writes into the composer (not auto-send).** Selecting a suggestion should
   drop the suggested text into the player's chatbox for **review/editing**, rather than
   immediately submitting a turn. This keeps the player's writing style consistent and
   under their control. (Consequence: the open-ended `guidance` steer added in the prior
   round is superseded — the chosen text *is* the turn — so its now-dead plumbing is
   retired.)
3. **Max-turns counts narration too.** The per-scene turn ceiling currently counts only
   character replies; narrator interstitials must also count toward the cap so a scene
   truly stops at the configured number of beats.
4. **Formatting reorganization.** Combine a character's **thinking** and **speaking** into
   a **single bubble** at the **same text size** (today the thought is a separate,
   differently-sized block). Any text wrapped in quotation marks inside a chat bubble
   should render **bold** while keeping the quotes visible.

## 2. Gaps & Unanswered Questions

- **"Match tone/pace" source (simple gap → assumption):** the player's own recent
  authored lines are the best available tone signal. We feed the last few `player`-role
  beats (from this turn + committed history) to the suggestion prompt as a voice sample.
- **Scope of quote-bolding (simple gap → assumption):** apply a shared `QuotedText`
  primitive to *all* prose bubbles (narrator, player, character speech + thought), so
  quoted dialogue bolds consistently anywhere it appears — the request names "that chat
  bubble" but consistency across bubbles is lower-risk than a character-only special case.
- **Does narration count include the narrator-led scene opening? (assumption):** yes — any
  emitted narrator beat counts toward the ceiling, including the opening interstitial and
  puppet performances, so "max turns" means total beats, honoring the request literally.
- **Retire vs. keep `guidance` (decision):** retire. After request #2 the selection no
  longer submits, so nothing sets `guidance`; leaving the prompt-injection + "Steering
  toward your choice" trace in place would be dead, misleading code. The legacy `outcome`
  field is orthogonal (already unused by the client) and is left untouched to keep scope
  tight.

## 3. Hierarchical Step-by-Step Instructions

Steps share files (`turn_engine.py` for #3 + guidance retire; `useScenePlay.ts` +
`TranscriptBeat.tsx` for #2/#4), so they run **sequentially** in one worktree rather than
as parallel agents. Each phase ends green + committed.

### Phase 1 — Situation-based suggestions (request #1)

- **Locations:** `web/backend/app/agents/director_agent.py` (`_BRANCH_SYSTEM`,
  `propose_branches`, new `_player_voice` helper). Test:
  `utils/tests/backend/agents/test_director_agent.py`.
- **Rationale:** The suggestion prompt currently asks for "in-character" follow-up *lines*.
  Rewrite it to request **situation-based** moves from a general perspective, and feed the
  player's recent authored lines so tone/pace/length match. The most-recent-line anchor
  (`_latest_line`) stays as the "what just happened" context.
- **Action:** `.venv/bin/python -m pytest utils/tests/backend/agents/test_director_agent.py`.
  Commit: `Scene Dialogue Refinements (1/5) Complete: situation-based, tone-matched path suggestions.`

### Phase 2 — Max-turns counts narration (request #3)

- **Locations:** `web/backend/app/services/turn_engine.py` (the ReAct loop: rename
  `char_beats` → `scene_beats`; increment it for narrator beats + the narrated opening;
  update the cap trace copy). Test: `utils/tests/backend/api/test_play_turn.py`.
- **Rationale:** The user-facing ceiling should bound *all* beats. Narrator interstitials
  (`decision.action == "narrate"` and the pre-loop opening) currently bypass the counter.
- **Action:** `.venv/bin/python -m pytest utils/tests/backend/api/test_play_turn.py`.
  Commit: `Scene Dialogue Refinements (2/5) Complete: max-turns ceiling counts narration beats.`

### Phase 3 — Selection writes to composer + retire the guidance steer (request #2)

- **Locations (frontend):** `web/frontend/features/story-player/useScenePlay.ts` (`choose`
  sets the composer instead of submitting; `submit` drops the `guidance` param),
  `web/frontend/features/story-player/StoryPlayerView.tsx` (focus the composer input after
  a pick — a11y), `web/frontend/components/feature/Composer.tsx` (forward a focus ref),
  `web/frontend/lib/events.ts` (drop `guidance`). Tests:
  `useScenePlay`/`StoryPlayerView.test.tsx`.
- **Locations (backend, retire dead guidance):** `web/backend/app/schemas/play.py`
  (`TurnRequest.guidance`), `web/backend/app/services/assembler.py` (`TurnContext.guidance`),
  `web/backend/app/services/turn_engine.py` (`ctx.guidance` + "Steering toward your choice"
  trace), `web/backend/app/agents/planner_agent.py` (`guidance_note`),
  `web/backend/app/agents/character_turn_agent.py` (guidance tail). Tests:
  `test_play_turn.py`, `test_planner_agent.py`, `test_character_turn_agent.py`.
- **Rationale:** The chosen suggestion text now *is* the player's message, authored in
  their box for review. That supersedes the open-ended steer, whose plumbing becomes dead.
- **Action:** frontend `npm test` + `npm run typecheck`; backend
  `.venv/bin/python -m pytest utils/tests/backend/agents utils/tests/backend/api`; a11y pass
  (focus moves to composer, keyboard-selectable). Commit:
  `Scene Dialogue Refinements (3/5) Complete: suggestion selection writes to composer; retire guidance steer.`

### Phase 4 — Combined think+speak bubble + bold quotes (request #4)

- **Locations:** new `web/frontend/components/ui/QuotedText.tsx` (+ `.test.tsx`);
  `web/frontend/components/feature/TranscriptBeat.tsx` (`CharacterMessage` → one bubble
  holding thought + speech at the same size; apply `QuotedText` to narrator/player/character
  prose). Test: `TranscriptBeat.test.tsx`.
- **Rationale:** Today the thought is a smaller separate block; merge it into the speech
  bubble at matching size, and bold quoted spans everywhere prose renders.
- **Action:** `npm test` + `npm run typecheck` + a11y/responsive pass (contrast of muted
  thought text, 320/375/768/1024). Commit:
  `Scene Dialogue Refinements (4/5) Complete: single think+speak bubble; bold quoted text.`

### Phase 5 — Docs + full validation + merge

- **Locations:** `docs/api-contract.md`, `docs/data-flow.md`, `docs/design-system.md`,
  `docs/component-map.md`, `docs/documentation.md`, `docs/checklist.md`.
- **Rationale:** Record the suggestion-prompt change, the retired `guidance` field, the
  turn-ceiling semantics, and the transcript-formatting tokens in the same change.
- **Action:** full `.venv/bin/python -m pytest` + frontend `npm test`, `npm run typecheck`,
  `npm run lint`, and `next build` (run in the primary checkout after merge). Commit:
  `Scene Dialogue Refinements (5/5) Complete: docs + full validation.` Then merge
  `feat/scene-dialogue-refinements` → `main` (no push).

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Situation-based suggestion prompt | General-perspective, tone-matched follow-ups | `web/backend/app/agents/director_agent.py` |
| Narration-aware turn cap | `max_turns` counts narrator beats | `web/backend/app/services/turn_engine.py` |
| Guidance retirement | Remove superseded open-ended steer | `play.py`, `assembler.py`, `turn_engine.py`, `planner_agent.py`, `character_turn_agent.py`, `events.ts` |
| Select-to-composer | Suggestion fills the chatbox for editing | `web/frontend/features/story-player/useScenePlay.ts`, `StoryPlayerView.tsx`, `Composer.tsx` |
| Combined think+speak bubble | One bubble, same text size | `web/frontend/components/feature/TranscriptBeat.tsx` |
| Quoted-text emphasis | Bold `"…"`/`“…”`, quotes kept | `web/frontend/components/ui/QuotedText.tsx` |
| Backend tests | Director + turn-cap + guidance-retire coverage | `utils/tests/backend/agents/test_director_agent.py`, `utils/tests/backend/api/test_play_turn.py` |
| Frontend tests | Select-to-composer + formatting + QuotedText | `useScenePlay`/`StoryPlayerView.test.tsx`, `TranscriptBeat.test.tsx`, `QuotedText.test.tsx` |
</content>
</invoke>
