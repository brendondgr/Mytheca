# Plan: Scene Structure & Feedback

## 1. Introduction

This plan addresses six pieces of play-experience feedback on the live turn loop: (1) scenes
should open with the **narrator**, not a character talking unprompted; (2) generated output —
especially after a branch/path is selected — should **extend further**; (3) there should be
**more narration** overall; (4) a character's **speech and thought** should render as two
distinct chat bubbles that alternate naturally, and the short name-prefix label must stay
short (5–10 words, not ~20); (5) the Turn **Inspector** should be more readable (bigger text,
auto-collapsing completed turns, per-entry dropdowns, color-coded dots); and (6) the name-prefix
label and narrator prose should **not be italic** (the muted color stays).

Within Velora's architecture the work splits cleanly: the backend generation/flow (FastAPI
turn engine, planner, narrator + character agents, the play request schema) drives areas 1–4's
server side; the Next.js story player (scene seed, the turn-stream reducer, `TranscriptBeat`,
`TurnInspectorPanel`) drives areas 1, 4, 5, 6's client side. All changes stay **best-effort** —
an LLM/graph outage must still degrade gracefully.

### Ground truth (verified in code before planning)

- **Opening beat = a character.** `planner_agent._fallback_beat` (`web/backend/app/agents/planner_agent.py:133`)
  returns `speak cast[0]` when nothing has acted; the frontend seed (`scene-data.ts`
  `genericScene`) also renders two character placeholder lines at scene start. The frontend does
  **not** auto-fire a turn on mount.
- **Output is NOT token-limited.** `_common.gen_params` floors `max_tokens` to `GEN_MIN_TOKENS =
  8192` for both the character voice call (`_voice_params`) and the narrator. Short output comes
  from the **prompts** (narrator: "ONE short beat (1-2 sentences)"; character contract: "one beat,
  the spoken line"), not the budget.
- **Branch selection is a plain turn.** `useScenePlay.choose` submits the branch label as ordinary
  turn text; the backend has no signal that it was a branch, so it can't extend.
- **`internal_thought` is withheld.** The engine emits it `visibility="hidden"`, and
  `_Emitter.emit` drops hidden events from the stream (it only surfaces in the Inspector's
  `thinking` trace step). The frontend `mergeFrame` has no case for it either.
- **The prefix label = `character_action`**, rendered italic `text-[13px] text-mute2` next to the
  name. Its length has no explicit cap in the contract. Narrator prose renders italic in
  `NarratorCard`.
- **Inspector** (`TurnInspectorPanel.tsx`) renders every step always-expanded, tiny text
  (8.5–13px), no per-entry dropdown, no auto-collapse, and two-tone (accent/muted) tags — no
  per-type color dots.

## 2. Gaps & Unanswered Questions

- **Embergate demo seed** (`scenario.id === "embergate"`) is a curated visual reference, not user
  content. **Assumption:** leave it as-is; apply the narrator-only opening to the `genericScene`
  path that every real (created) scenario uses. Documented as an intentional exception.
- **When is a character allowed to open?** **Assumption:** the scene's very first beat is
  narrator-only *only* when the player's opening input doesn't direct/address a character and
  isn't a group broadcast (puppet/addressed/`scope=="all"` still act). Freeform input **with
  prior history** still gets a character responder (unchanged) — the narrator-only rule is scoped
  to the true cold open (`not ctx.recent_beats`).
- **Thought-bubble visibility semantics.** **Assumption:** emit `internal_thought` as
  `visibility="private_to_user"` (streams to the player, semantically "shown to you, not the other
  characters") and keep it **out of `turn_beats`** so later speakers still never condition on it.
- **Branch-expansion signal.** **Assumption:** add an optional `outcome` field to `TurnRequest`
  (the branch's narrative-direction tag); when present the engine opens with a fuller "progression"
  narration and folds the outcome into the planner directive so the scene plays out over several
  beats. No new dice/mechanics (D11 preserved).

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend turn flow: narrator-led openings, more & longer narration, branch expansion, streamed thoughts, short action labels

- **Locations:**
  - `web/backend/app/schemas/play.py` — add `outcome: str | None = None` to `TurnRequest`.
  - `web/backend/app/agents/planner_agent.py` — `_SYSTEM` (bias narration between speakers; open a
    fresh scene with `narrate`, don't force a character); `next_beat(..., scene_opening=False)`
    (nudge the user prompt on a cold open); `_fallback_beat(..., scene_opening=False)` (gate the
    `not acted → speak cast[0]` branch on `not scene_opening`).
  - `web/backend/app/agents/narrator_agent.py` — `interstitial(..., lead: str | None = None,
    long: bool = False)`: default beat lengthened to 2–3 sentences; `long` → a vivid paragraph
    (3–5 sentences) that advances the story; `lead` folds a branch outcome / opening cue into the
    user prompt.
  - `web/backend/app/agents/character_turn_agent.py` — `_OUTPUT_CONTRACT`: cap `character_action`
    to **≤10 words**; allow the spoken line to run 1–3 sentences where natural (still "tight,
    in-voice").
  - `web/backend/app/services/turn_engine.py` — compute `scene_opening = not ctx.recent_beats`;
    on a cold open with no puppet/addressed/broadcast, emit one opening narration (narrator opens,
    no character forced); when `req.outcome` is set, emit a fuller `long`/`lead` progression
    narration and fold `outcome` into the effective directive; pass `scene_opening` to the planner;
    thread `lead`/`long` through `_narrator_interstitial`; change the `internal_thought` emit from
    `visibility="hidden"` to `visibility="private_to_user"` (stream it) while keeping it out of
    `turn_beats`; refresh the module docstring + inline comments.
- **Rationale:** These are the server-side levers for areas 1–4. Centralizing them in one phase
  keeps the flow coherent and testable in a single backend suite before any UI depends on it
  (streamed thoughts, the `outcome` field).
- **Action:** Run `uv run pytest utils/tests/backend/agents utils/tests/backend/api` (add/adjust:
  `test_planner_agent.py` — cold-open freeform ends vs. history speaks, broadcast/addressed still
  speak; `test_narrator_agent.py` — `long`/`lead` still returns text; `test_play_turn.py` — cold
  freeform yields `narration` + no `character_dialogue`, `internal_thought` now on the stream,
  `outcome` turn yields narration). Recommended: `ruff` + `mypy web/backend`. Commit:
  `Scene Structure & Feedback (1/4) Complete: narrator-led openings, richer/longer narration, branch expansion, streamed thoughts, short action labels.`

### Phase 2 — Frontend: narrator-only seed opening, thought bubbles, de-italicized labels, branch outcome

- **Locations:**
  - `web/frontend/features/story-player/scene-data.ts` — `genericScene` opens with the narrator
    line only (drop the two seeded `char` lines); add `"thought"` to `SceneMessageKind`.
  - `web/frontend/lib/events.ts` — `TurnRequestBody.outcome?: string | null`; update the
    `InternalThoughtEvent` doc (now streamed as the thought bubble, `private_to_user`).
  - `web/frontend/lib/api.ts` — `postTurn` forwards `outcome`.
  - `web/frontend/features/story-player/turn-stream.ts` — `mergeFrame`: `case "internal_thought"`
    → push `{ kind: "thought", who, text }` (its own bubble; never merged into a speech bubble).
  - `web/frontend/features/story-player/useScenePlay.ts` — `submit(text, outcome?)`; `choose(c)`
    passes `c.outcome`.
  - `web/frontend/components/feature/TranscriptBeat.tsx` — remove `italic` from `NarratorCard`'s
    `<p>` and from `CharacterMessage`'s action label (keep the muted colors); add a `ThoughtBubble`
    renderer (a quiet, visually-distinct "thinking" bubble) and route `kind: "thought"` to it.
- **Rationale:** Consumes Phase 1's streamed thoughts and `outcome` field, and delivers areas 1
  (seed), 4 (bubbles + de-italicized label), 6 (narrator italics) on the client.
- **Action:** Run `npm test` (add/adjust: `turn-stream.test.ts` — internal_thought → a separate
  `thought` message, thought-then-dialogue = 2 messages; `useSceneData.test.ts` — generic opening
  has no `char` messages). Web/UI → accessibility + responsive pass: thought-bubble & label
  contrast (AA) without relying on italics, focus/keyboard unaffected, layouts at 320/375/768/1024.
  Recommended: `npm run typecheck` + `npm run lint`. Commit:
  `Scene Structure & Feedback (2/4) Complete: narrator-only openings, separate thought bubbles, de-italicized labels/narrator, branch outcome wired.`

### Phase 3 — Inspector panel: readability, auto-collapse, per-entry dropdowns, color dots

- **Locations:**
  - `web/frontend/components/feature/TurnInspectorPanel.tsx` — full rewrite: larger text (tags
    ~10–11px, titles ~14px, detail ~13px); a per-step **color** map (Stat/Plan/Speaker/Thinks/
    Speaks/…) rendered as a **colored dot on the left, text on the right**; **auto-collapse
    completed turns** (only the newest/active turn expanded; a turn is complete once a newer turn
    opens — older turns collapse to a clickable header); each entry is a keyboard-operable
    `<button>` with `aria-expanded` that **expands to reveal `detail`** (dropdown).
  - `web/frontend/components/feature/TurnInspectorPanel.test.tsx` — update/extend for the new
    interactions (expand an entry, collapse older turns, dots render per type).
- **Rationale:** Area 5, isolated to one component + its test so it can't regress the transcript.
- **Action:** Run `npm test`. Web/UI → accessibility + responsive pass: expand/collapse operable
  by keyboard with visible focus, dot+text contrast (AA), 320/375/768/1024. Recommended:
  `npm run typecheck` + `npm run lint`. Commit:
  `Scene Structure & Feedback (3/4) Complete: Inspector — larger text, auto-collapsing turns, per-entry dropdowns, color-coded dots.`

### Phase 4 — Docs, full validation, merge to main

- **Locations:** `docs/api-contract.md` (internal_thought streamed as `private_to_user`;
  `TurnRequest.outcome`; narration length note), `docs/data-flow.md` (narrator-led opening, branch
  expansion, visible thoughts), `docs/design-system.md` (thought bubble, de-italicized label +
  narrator, Inspector color coding), `docs/checklist.md` (this feature + any deferrals).
- **Rationale:** Docs move in the same change that alters behavior; the merge lands the feature on
  `main`.
- **Action:** Full `uv run pytest` + `npm test`; recommended `ruff`/`mypy`/`tsc`/lint. Merge the
  `turn-loop-runtime` worktree into `main`, resolving conflicts. Commit:
  `Scene Structure & Feedback (4/4) Complete: docs updated; feature validated and merged to main.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Narrator-led openings | Cold-open scene starts with narration; no character forced | `web/backend/app/services/turn_engine.py`, `web/backend/app/agents/planner_agent.py` |
| Richer/longer narration | Longer default + paragraph "progression" beats; more narration bias | `web/backend/app/agents/narrator_agent.py`, `planner_agent.py` |
| Branch expansion | `TurnRequest.outcome` → fuller continuation over several beats | `web/backend/app/schemas/play.py`, `turn_engine.py`, `web/frontend/lib/{events,api}.ts`, `useScenePlay.ts` |
| Streamed thoughts | `internal_thought` emitted `private_to_user` (kept out of `turn_beats`) | `web/backend/app/services/turn_engine.py` |
| Short action label | `character_action` capped ≤10 words in the contract | `web/backend/app/agents/character_turn_agent.py` |
| Narrator-only seed | Generic scene opens with narrator only | `web/frontend/features/story-player/scene-data.ts` |
| Thought bubbles | Distinct thought vs. speech bubbles; de-italicized label + narrator | `web/frontend/components/feature/TranscriptBeat.tsx`, `turn-stream.ts` |
| Inspector rewrite | Bigger text, auto-collapse, per-entry dropdowns, color dots | `web/frontend/components/feature/TurnInspectorPanel.tsx` |
| Backend tests | Opening/planner/narrator/turn behavior | `utils/tests/backend/agents/test_planner_agent.py`, `.../test_narrator_agent.py`, `utils/tests/backend/api/test_play_turn.py` |
| Frontend tests | Reducer thought split, seed opening, Inspector interactions | `web/frontend/features/story-player/turn-stream.test.ts`, `.../useSceneData.test.ts`, `web/frontend/components/feature/TurnInspectorPanel.test.tsx` |
| Docs | Contract/data-flow/design-system/checklist updates | `docs/api-contract.md`, `docs/data-flow.md`, `docs/design-system.md`, `docs/checklist.md` |
