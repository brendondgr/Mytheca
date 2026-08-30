# Free-Text Mode

**Status: built and merged to the branch.** Written 2026-08-30 from the owner's
specification; this header records what actually landed, which is the part worth reading.

| Phase | State |
| --- | --- |
| 1 Scene mode + thinking ladder | **Done.** No Alembic migration was needed for the *thinking* level (per-turn only, no column); `scene_mode` did get one, because `test_alembic.py` requires `upgrade head` and `create_all` to agree. |
| 2 Cached prompt | **Done.** A test pins that a stat change leaves the system message byte-identical. |
| 3 Lookup agent | **Done.** |
| 4 Checklist | **Done**, plus `TurnTasksFrame` on the wire and its frontend mirror. |
| 5–6 Write, grade, continue | **Done, in one commit.** The write and the review are one loop; splitting them would have meant writing it twice. |
| 7 Consequences + guards | **Done.** The consequence path landed with the loop; this phase pinned the guard *selection*, which is the half that fails silently. |
| 8 Frontend | **Done**, and verified against the running app with a real turn on the live endpoint. |
| 9 Kept features + docs | **Done** — and it caught a real defect, see below. |

**Three things the work turned up that the plan did not anticipate:**

1. `turn_setup.prepare_turn` was spending an **intent call and a direction parse on every
   free-text turn**, both feeding machinery that is not running. Both are now skipped: two
   fewer model calls per turn, and no risk of two competing contracts disagreeing about what
   the turn owes.
2. `looks_like_scratchpad` **cannot be reused** for free-text prose. It is a conjunction of
   production vocabulary AND *no first-person pronoun*, which works because a character beat is
   first person and exempts itself; free-text prose is third person by contract, so half the
   conjunction is always true and the rule collapses to a vocabulary test too eager to run on
   prose. `prose_guards.looks_like_briefing` is the stricter standalone rule.
3. **Phase 9 found a pre-existing bug.** `scene_moment._BEAT_TYPES` — the event types a scene
   image reads the moment from — did not include `character_prose`, which is the form a
   character beat has taken since the three-fragment shape was retired. Scene images were being
   composed from the narrator's lines and the player's own with **every character beat invisible
   to them**. Fixed alongside adding `scene_prose`.

Gap 1 below (the passage allowance) was answered at **6,000 tokens per pass**; gap 2 (what
re-roll means for a one-body turn) is recorded in `docs/checklist.md` rather than decided.
Everything still open is in that file, which is the one to read — a plan describes an
intention and the checklist describes the state.

`sceneFlow: "continuous"` is **not** this mode and never was — that path still asks the
planner for a beat list, still decides who speaks when, and still splits the returned text
back into one attributed event per speaker. Free-text removes all three.

---

## 1. Introduction

Mytheca produces a scene by decomposing it: an intent call classifies the player's line, a
planner decides every beat and its speaker, and prose is written against that schedule. That
machinery is staying exactly as it is — the owner's judgement is that the current mode is good
and roughly where it should be.

**Free-text mode is the other thing you can pick instead.** One generation writes the whole
turn as a single unbroken body of prose, the way a chat model answers a message: a character
acts and everyone in the room reacts, all in one passage, with no beat boundaries, no speaker
cards, and no ceiling on how much it may say. There is no scheduling question to answer,
because nothing is being scheduled.

What replaces the planner is a **checklist the model writes for itself and then grades itself
against**. Before writing, it lists what this turn has to accomplish. It writes. It reads back
what it wrote and decides, item by item, whether each was delivered — yes, no, or partially.
If something is missing it continues the same passage from where it stopped, and only then
does the turn end. The loop is the quality mechanism, in place of the structural one.

Three properties fall out of that and are worth naming up front, because every design decision
below serves one of them:

- **It is watchable.** The thinking budget is exposed as a player-facing control, and the
  outline the model writes before it starts — what it is about to say and why — streams live.
- **It is cheap in prefix.** Free-text makes several calls per turn, so they are composed to
  share one byte-identical prompt prefix; only the last block differs between them.
- **It degrades to prose.** Every auxiliary step (retrieval, checklist, review, continuation)
  is best-effort. If any of them fails the turn still returns a passage.

### Decisions taken (owner, 2026-08-30)

- **Two top-level modes, not three prose flows.** Everything that exists today —
  `voiced` and `continuous`, the planner, registers, beat decomposition — is collectively
  **one** mode. Free-text is the other. `sceneFlow` keeps its meaning and is only read inside
  the structured mode.
- **One unbroken body.** The turn's prose lands in the transcript as a single passage. No
  per-speaker cards, no portraits or name colours inside it, no attributed sub-beats.
- **The whole cast goes into the prompt.** Not a selected subset — every character's name,
  role, background, manner of speaking, voice samples, **and their statistics**. Statistics
  are explicitly required throughout.
- **Cache is a first-class constraint.** The prompt must be structured so the right
  information sits at the right position and prefix reuse stays as high as possible at all
  times.
- **The checklist is visible**, in the right-hand rail, and it names who is generally expected
  to speak as well as what has to happen.
- **The thinking budget is a chat control**, on six levels, available in the existing mode
  too.
- **Image generation and follow-up suggestions are kept**, working the same way they do now.

---

## 2. Gaps & Unanswered Questions

**Assumptions taken (simple gaps — stated and proceeding):**

- **Existing scenes keep the structured mode.** A `NULL` `scene_mode` column reads as
  `structured`, so no world written before this change moves. The switch is a deliberate act.
  (This is the opposite of how `sceneFlow` defaulted, and deliberately so — that default
  changed behaviour under scenes that never asked for it.)
- **Default thinking levels**: `medium` (512) for the prose call, `low` (256) for the
  retrieval-terms call, `low` for the checklist, `low` for the review. All overridable; the
  prose one is the only one surfaced in the composer.
- **The continuation loop is capped at 2 passes.** Three generations for one turn is already a
  long wait; past that the turn ends and reports what was not delivered, the way the existing
  direction accounting does.
- **`cast_request` does not exist in free-text v1.** It is produced by the intent agent, which
  this mode does not call. Naming an absent character simply has no effect.
- **Consequence blocks must name their subject.** With no speaker attribution the engine
  cannot infer whose stat moved, so `state_update` / `relationship_update` /
  `presence_change` carry an explicit character name in this mode, resolved against the
  roster and **dropped when unresolvable** — consistent with the existing rule that nothing
  the model proposes is trusted.

**Complex gaps — human intervention is needed to answer these:**

1. **How generous is the safety stop?** The owner's requirement is "no limitations to how much
   it can talk", and the engineering constraint is real: one uncapped generation previously
   ran to 48,000 completion tokens over 684 seconds, timed out the relay's health probe three
   times, marked the endpoint failed and returned 400 for the next three turns. A free-text
   body is legitimately many times longer than a beat. This plan proposes **6,000 tokens per
   pass** (roughly 24,000 characters, about eight times the longest honest beat measured) as
   an endpoint-protection stop that will not be reached by writing — but the number is a
   judgement call about how long a passage should be allowed to get, and it is the owner's.
2. **What does re-rolling a free-text turn mean?** `beat_rerun.py` re-runs one beat and keeps
   takes. In this mode the turn *is* the beat, so "re-roll" and "re-roll the turn" collapse
   into one action, and beat-level editing has nothing smaller than the whole passage to edit.
   Either the record controls apply to the whole body (simple, and some fidelity is lost), or
   free-text bodies are exempt from beat-level controls entirely. Phase 8 is written against
   the first reading and is easy to flip.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — The mode switch and the thinking ladder

- **Locations:** `web/backend/app/schemas/play.py` (new `SceneMode` literal; `scene_mode` and
  `thinking` on `TurnOverrides`), `web/backend/app/models/scenario.py` (`scene_mode`,
  `thinking_effort` columns, both nullable), `web/backend/app/services/turn_settings.py`
  (resolve + clamp both, exactly as `scene_flow` is resolved today),
  `web/backend/alembic/versions/` (one migration adding the two columns),
  `web/backend/app/routes/scenarios.py` (accept them on create/update).
- **Rationale:** Nothing can branch on a mode that has no name. The six thinking levels
  already exist in `schemas/reasoning.py` (`QUICK 128 · LOW 256 · MEDIUM 512 · HIGH 1024 ·
  VERY_HIGH 2048 · MAX 4096`) — that enum is the ladder, unchanged; what is new is that a
  turn may carry one instead of every call-site fixing its own. `TurnOverrides` is the right
  home because a thinking level is a property of a message, not of a scene, in the same way
  the pinned register is.
- **Note on the existing mode:** exposing this control lets the player raise the prose call's
  thinking in structured mode, where it is currently `NONE` on purpose — that was set after
  the prose call was found spending 91 % of its output on hidden reasoning. The default stays
  `NONE` there. The control makes it a choice; it must not quietly become the new default.
- **Action:** Run `uv run pytest utils/tests/backend/services utils/tests/backend/api`. Once
  green, commit: `Free-Text Mode (1/9) Complete: scene mode and a per-turn thinking level are
  resolvable settings.`

### Phase 2 — The free-text prompt, composed for cache

- **Locations:** new `web/backend/app/services/freetext_context.py`;
  `web/backend/app/services/assembler.py` (a `full_cast_block` renderer beside
  `format_voice_samples`); `web/backend/app/services/stat_render.py` (reused for live values);
  `web/backend/app/agents/prompt_registry.py` (new key `freetext.output_contract`).
- **What it builds**, and the ordering is the deliverable, not an implementation detail:

  | Region | Contents | Changes when |
  | --- | --- | --- |
  | **System — identical for every call in the scene** | style-guide prose blocks · `WORLD:` + world primer · stat guidance (what each stat *means*, with its bands) · the place as authored · **the full cast**: every character's name, role, background, traits, speech style and voice samples · the free-text output contract | the world, the scene or the roster changes |
  | **User, append-only** | scene memory summary · the block-anchored transcript · the player's line | a turn is added, or the window re-anchors |
  | **User, volatile tail** | **every character's live stat readings in band language** · retrieved lore · tagged files · who the player addressed · **the instruction for this particular call** | every call |

- **Rationale:** free-text makes three to five calls per turn, and the only thing that
  separates them is the last block. Composing them this way means one prefix is paid once and
  every subsequent call in the turn — and every turn of the scene — reads it from cache. Two
  specific decisions inside that:
  - **Character identity is stable; stat *values* are not.** The owner asked for both in the
    prompt. Putting live values in the cached cast block would invalidate the entire prefix
    the first time anyone's trust moved; putting them in the tail costs a few hundred tokens
    re-read per call and protects the largest block in the prompt. Both are present, in the
    region each belongs to.
  - **The per-call instruction is last**, which is both the only correct place for cache and
    the strongest attention position in the prompt.
- **Action:** Run `uv run pytest utils/tests/backend/services/test_freetext_context.py`
  (new — assert byte-identical prefixes across the four call shapes, and that a stat change
  does not alter the system message). Commit: `Free-Text Mode (2/9) Complete: one cached
  prefix carries the whole cast; only the final instruction varies per call.`

### Phase 3 — Looking things up before writing

- **Locations:** new `web/backend/app/agents/lookup_agent.py`;
  `web/backend/app/services/freetext_context.py` (call it, fold the result into the tail);
  `web/backend/app/rag/retriever.py` (unchanged — reused as-is).
- **Behaviour:** a small call at `low` (256 thinking tokens) that reads the player's line and
  the transcript and answers one question: *is there anything here you do not know well enough
  to write about, and what would you search for?* It returns search terms, not prose. The
  engine runs each through the existing hybrid retrieval (dense + BM25, RRF-fused,
  storyline-scoped) and folds the hits into the volatile tail under the existing
  reference-not-direction framing.
- **Rationale:** the current gate is a regex — it fires on a capitalised off-roster word or a
  wh-question paired with a history cue, and skips on doubt. That is right for a mode that
  makes one prose call per beat and cannot afford a lookup call. Free-text can: the owner's
  example is the model meeting an ogre, not knowing what an ogre is *in this world*, and going
  to find the world documents that say. A regex cannot have that thought.
- **Best-effort:** no endpoint, an unparseable reply, or an empty store all yield no lore and
  the turn proceeds ungrounded. This step may never fail a turn.
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_lookup_agent.py` and
  `utils/tests/backend/rag`. Commit: `Free-Text Mode (3/9) Complete: the turn decides what it
  needs to look up, and looks it up.`

### Phase 4 — The checklist

- **Locations:** new `web/backend/app/agents/task_agent.py`; new `tasks` transport frame in
  `web/backend/app/events/stream.py` and its mirror in `web/frontend/lib/events.ts`;
  `web/backend/app/services/turn_emit.py` (trace row).
- **Shape:** a JSON reply, schema-constrained where the endpoint supports it, listing what the
  turn must accomplish and — per the owner — which characters are generally expected to speak:

  `{"tasks": [{"must": "<an outcome that has to be true by the end>", "who": [roster numbers]}]}`

- **What it is not:** it is not a plan. There are no actions, no ordering, no registers, no
  narrate-versus-speak decision, and the engine dispatches on none of it. `who` is a hint the
  writer reads, never a schedule the engine executes. Confusing the two would rebuild the
  planner inside the mode that exists to remove it.
- **Who gets one:** the Playwright path always; the character-POV path only when the player
  wrote instructions in the guidance box. **A character-POV turn with no instructions gets no
  checklist, no review and no continuation** — it is one call and one passage, and that is the
  whole path.
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_task_agent.py`. Commit:
  `Free-Text Mode (4/9) Complete: the turn writes the checklist it will be graded against.`

### Phase 5 — Writing the body

- **Locations:** new `web/backend/app/agents/freetext_agent.py`; new
  `web/backend/app/services/freetext_turn.py` (the loop); new `scene_prose` event in
  `web/backend/app/events/envelope.py` and its mirror in `web/frontend/lib/events.ts`;
  `web/backend/app/services/turn_engine.py` (one branch at the top of `run_turn` that hands
  the whole turn to `freetext_turn.run` and returns).
- **The withheld-checklist rule, which is the crux of the Playwright path:** the checklist is
  written first and then **not shown to the generation**. The prose call receives the player's
  query, the world, the cast and the transcript — and nothing else. Only the review call in
  Phase 6 sees the list. The character-POV-with-instructions path is the deliberate opposite:
  there the list **is** sent along, and the passage is written to satisfy it directly.
- **Streaming:** the body streams as one `scene_prose` event — same id and seq re-emitted with
  each incremental chunk, `done: true` and empty text on the final frame, exactly as prose
  streams today. The thinking outline streams alongside as `TurnReasoningFrame`s, so the
  player watches it decide and then watches it write.
- **Rationale for a new event type:** `narration` renders as a `NarratorCard` and means the AI
  narrator specifically; `character_prose` carries a `characterId` this mode does not have. A
  body that contains the whole room is neither.
- **Action:** Run `uv run pytest utils/tests/backend/services/test_freetext_turn.py` and
  `utils/tests/backend/api/test_play_stream.py`, plus `npm test` for the events mirror and
  `npm run typecheck`. Commit: `Free-Text Mode (5/9) Complete: one call writes the turn as a
  single streamed body.`

### Phase 6 — Reading its own work, and continuing

- **Locations:** `web/backend/app/agents/task_agent.py` (a `review` function beside the
  generator); `web/backend/app/services/freetext_turn.py` (the loop and its cap).
- **The loop:**
  1. The review call receives the checklist and the body that was just written, and returns a
     verdict per item — `yes` / `no` / `partial` — with a short note.
  2. Everything `yes` ends the turn.
  3. Anything `no` or `partial` triggers a continuation: the model is given what it wrote and
     what is still missing, and told to **continue the passage from where it stopped** — not
     to restart it, recap it, or apologise for it.
  4. The continuation streams **into the same event**, extending the same body. The
     accumulate-by-id contract already supports this, so the reader sees one passage that
     keeps going rather than a second block appearing underneath.
  5. Capped at two continuations. On exhaustion the turn ends and the unmet items are reported
     the way undelivered direction is reported today.
- **Rationale:** this is the mode's entire quality mechanism, standing where the planner stands
  in the other mode. It is also why the review has to be a separate call from the writing: a
  model asked to write and self-assess in one pass grades the essay it wishes it had written.
- **Action:** Run `uv run pytest utils/tests/backend/services/test_freetext_review.py`.
  Commit: `Free-Text Mode (6/9) Complete: the turn grades itself and continues until the
  checklist is met.`

### Phase 7 — Consequences and guards for an unattributed body

- **Locations:** `web/backend/app/services/emission.py` (parse a `character` field on the JSON
  blocks); `web/backend/app/services/turn_effects.py` (resolve it by name against the roster);
  `web/backend/app/services/prose_guards.py` (no new guards — a per-mode selection).
- **Which guards run**, because several of them assume a single-speaker passage and are wrong
  here:

  | Guard | Free-text | Why |
  | --- | --- | --- |
  | Leaked scratchpad | on | Still a failure, and thinking is on in this mode. |
  | Degeneration / repetition | on | Unchanged. |
  | Cross-speaker speech | **off** | A body legitimately contains everyone's speech. This guard exists to catch one character writing another's lines; here that *is* the format. |
  | Second person addressing the reader | on under Playwright, off under POV | Same rule as today, and it reads `player_embodied`, which is already resolved before this point. |
  | Echo of an earlier beat | on | Cheap, and a continuation pass is exactly when a model repeats itself. |

- **Action:** Run `uv run pytest utils/tests/backend/services/test_turn_effects.py
  utils/tests/backend/services/test_prose_guards.py`. Commit: `Free-Text Mode (7/9) Complete:
  named consequences apply, and the guards that assume one speaker stand down.`

### Phase 8 — The frontend

- **Locations:** `web/frontend/components/feature/SceneConfigMenu.tsx` (the mode switch),
  `web/frontend/components/feature/Composer.tsx` (the six-level thinking control, beside
  `PlanModeButton`), `web/frontend/components/feature/DirectorRail.tsx` (the checklist, with
  its verdicts filling in live), `web/frontend/components/feature/TranscriptBeat.tsx` (render
  `scene_prose` as one body), `web/frontend/features/story-player/turn-stream.ts` and
  `useScenePlay.ts` (consume the `tasks` frame and the new event; rehydrate from history),
  `web/frontend/lib/types.ts`.
- **The rail is where the checklist lives**, per the owner. `DirectionChecklist` already
  renders a list of outcomes with delivery states and is the component to reuse rather than
  reimplement — the states map onto `yes` / `partial` / `no` directly.
- **The record controls** (`BeatControls`, `BeatEditor`, `BeatTakePager`) apply to the whole
  body in this mode; see gap 2 above, which this phase is written against and which the owner
  may flip.
- **Action:** Run `npm test` for the touched components, `npm run typecheck && npm run lint`,
  and an accessibility + responsive pass — keyboard operability on the mode switch and the
  thinking control, visible focus, AA contrast, a live-region announcement for the streaming
  body, and layout at 320 / 375 / 768 / 1024. Commit: `Free-Text Mode (8/9) Complete: the mode
  switch, the thinking control, the rail checklist and the one-body transcript.`

### Phase 9 — Keeping what already works, and the docs

- **Locations:** `web/backend/app/services/scene_moment.py` and
  `web/backend/app/agents/moment_agent.py` (confirm the scene renderer handles a `scene_prose`
  entry, so in-narrative image generation reads a free-text turn); `web/backend/app/services/
  turn_finalize.py` (confirm the body reaches `turn_beats`, so follow-up suggestions and
  reflection still run); `docs/api-contract.md`, `docs/data-flow.md`, `docs/documentation.md`,
  `docs/architecture.md`, `docs/component-map.md`, `docs/checklist.md`, `CLAUDE.md`.
- **Rationale:** the owner named image generation and the follow-up suggestions as features to
  keep working unchanged. Both read the turn's transcript rather than its beats, so both
  should survive — *should*, which is why this is a phase with tests and not an assumption.
  The docs duty is not optional: `docs/` is the source of truth and a mode this large that is
  documented nowhere is a mode the next reader will re-derive from code.
- **Action:** Run the full gate — `uv run pytest` and `npm test`. Commit: `Free-Text Mode (9/9)
  Complete: image generation and suggestions verified against a free-text turn; docs updated.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Scene mode | `structured` \| `freetext`, per scene and per turn | `web/backend/app/schemas/play.py`, `models/scenario.py`, `services/turn_settings.py` |
| Thinking control | Six-level per-turn budget, reusing the existing effort enum | `web/backend/app/schemas/play.py`, `web/frontend/components/feature/Composer.tsx` |
| Migration | Two nullable scenario columns | `web/backend/alembic/versions/` |
| Cached prompt | One prefix per scene, whole cast + stats, per-call instruction last | `web/backend/app/services/freetext_context.py` |
| Lookup agent | Decides search terms, then retrieves | `web/backend/app/agents/lookup_agent.py` |
| Task agent | Writes the checklist; grades the body against it | `web/backend/app/agents/task_agent.py` |
| Free-text agent | Writes the body | `web/backend/app/agents/freetext_agent.py` |
| Free-text turn | The loop: look up → list → write → review → continue | `web/backend/app/services/freetext_turn.py` |
| `scene_prose` event | One unattributed body, delta-streamed | `web/backend/app/events/envelope.py` + `web/frontend/lib/events.ts` |
| `tasks` frame | The checklist on the wire, for the rail | `web/backend/app/events/stream.py` + `web/frontend/lib/events.ts` |
| Rail checklist | Live verdicts in the right-hand rail | `web/frontend/components/feature/DirectorRail.tsx` |
| Transcript renderer | One body, no speaker cards | `web/frontend/components/feature/TranscriptBeat.tsx` |
| Backend tests | Context ordering, lookup, tasks, review loop, effects, stream | `utils/tests/backend/{services,agents,api}/` |
| Frontend tests | Co-located beside each touched component | `web/frontend/components/feature/*.test.tsx` |

---

## 5. What this mode deliberately does not do

Written down because each one is a thing a future reader will assume is missing by accident:

- **No planner call.** No beats, no registers, no stakes, no speak/narrate/exit decisions.
- **No intent classification.** Nothing decides whether the player puppeted, addressed or
  broadcast, because nothing downstream would use the answer. The checklist call reads the
  player's line directly.
- **No direction requirements.** The checklist replaces them, including the scheduling and the
  lexical delivery check — the review call is the delivery check, and it reads for meaning.
- **No per-speaker isolation.** Every character's voice sample sits in one prompt. That will
  pull the cast together, and hardest on weaker models. It is the accepted cost of one body.
- **No re-planning, no exchange floor, no silent-turn backstop.** Those are the structured
  mode's rules about who speaks; nobody is choosing a speaker here.
