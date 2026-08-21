# Scene Planning & Prose Form — a turn that decides where the story goes, written as literature

**Status:** in progress
**Created:** 2026-08-21
**Owner:** brendondgr
**Evidence:** the `ps_0bf9ddc13b` session export ("First Bloom of Two"), turns 1–9.

## 1. Introduction

The turn loop is fast now and its structure is clean, but the exported session shows three
things wrong with what it actually produces.

**It does not plan.** `planner_agent` answers one question — *who speaks next* — at the
lowest thinking budget in the codebase (256 tokens). Nothing decides where the scene is
going, whether this moment wants narration, or how the story should evolve. The trace reads
"Valdar is up next · the direction names them" nine turns running; that is scheduling, not
direction. When the player's intent is genuinely ambiguous the engine guesses instead of
asking.

**Its output is not literature.** A character beat arrives as three labelled fragments — a
`*thinks:*` block, an `*acts*` em-dash line, and a `**Name:**` quote. The reader is asked to
reassemble a paragraph the model already had in its head. The owner's target form is one
flowing first-person passage that mixes interiority, action and speech, with dialogue in
quotes inline — so a character can hold the floor for a real paragraph instead of one line.

**Two turns produced nothing at all.** Turns 8 and 9 emitted no character beat: the trace
goes `intent → planning → "The turn ends"` with no speaker. Root-caused below.

## 2. Gaps & Unanswered Questions

**Root cause of the silent turns (established by reading the code, not inferred):**

The scene runs under Player POV with Valdar as the POV character. Two defects compound:

1. **`intent_agent.interpret` builds its roster from the whole cast, including the POV
   character.** So the intent agent can resolve `addressed` / `actors` to the character the
   player *is*. Turn 8's recorded directive is the proof: *"tell **Valdar** you want to be
   inside of him"* — the player is Valdar. The planner then excludes the POV from its roster
   (correctly — the player voices them), so the only character the turn was aimed at is not
   selectable.
2. **`planner_agent._fallback_beat` counts the POV character as having "already responded".**
   The engine pre-marks `acted = [pov_id]` so a broadcast never re-selects the player's own
   character. But the fallback's last resort is `if not acted and not scene_opening: →
   somebody responds`, and `acted` is never empty under POV. So it falls through to
   `end("direction satisfied")` — the exact string in turns 8 and 9.

The net effect: **under Player POV, a freeform line that addresses nobody selectable ends the
turn in silence.** The player gets no prose and no explanation.

**Assumptions taken (simple gaps):**

1. **A new `character_prose` story event rather than overloading `character_dialogue`.** The
   frontend already folds thought + action + speech into one bubble, so the *visual* target
   exists; what changes is that the model writes one passage instead of three fragments.
   Overloading `character_dialogue` would leave the Inspector, the export and the contract
   all calling a narrated paragraph "dialogue". A ninth event type is the honest cost.
2. **The old three types keep parsing.** Persisted sessions replay through the same reducers,
   and a model that ignores the new contract still produces something usable rather than a
   dead turn.
3. **Planning thinking budget = 1024 (`ReasoningEffort.HIGH`).** The owner's ceiling is "a
   thousand tokens"; HIGH is the existing tier at 1024 and adding a 1000-token tier for a
   24-token difference is not worth a new enum member.
4. **The planner asks via `branch_choices`, not a new channel.** A clarifying question needs
   to reach the player and come back as a steer. `branch_choices` already streams, renders
   and round-trips; it gains an optional `prompt` so the question rides with the options.

**Flagged, needs the owner's eye (not blocking):**

**Merging interiority into the visible passage makes it public.** Today `internal_thought` is
`private_to_user` and is deliberately kept out of `turn_beats`, so other characters never
condition on it. A single first-person passage cannot preserve that — the thought is *in* the
prose the next speaker reads. That is how a novel works and it is what the target form
implies, but it is a real change to what characters know about each other. This plan takes
it deliberately and says so in the docs rather than letting it happen quietly.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Stop the silent turns

#### Step 1.1 — The intent agent must not see the character the player is playing
- **Locations:** `web/backend/app/agents/intent_agent.py` (`interpret` gains `locked_id` and
  drops that member from the roster it shows and from `roster_ids`);
  `web/backend/app/services/turn_engine.py` (pass `pov_id`).
- **Rationale:** under POV the player *is* that character, so "addressed: Valdar" is never a
  meaningful reading of Valdar's own line. Removing them from the roster makes the
  misresolution unrepresentable rather than merely unlikely.

#### Step 1.2 — The POV character must not count as "someone already answered"
- **Locations:** `web/backend/app/agents/planner_agent.py` (`_fallback_beat` takes
  `locked_id` into account when testing whether anyone has actually taken a beat).
- **Rationale:** the pre-marked `acted = [pov_id]` exists to stop re-selection, not to signal
  that the turn has been served. Conflating the two is what ends the turn in silence.

#### Step 1.3 — A turn never ends having shown nothing
- **Locations:** `web/backend/app/services/turn_engine.py` (the beat loop tracks whether any
  visible beat was produced; on an `end` with none, run one fallback beat — the addressed or
  first present non-POV character, else a narrator interstitial — and trace why).
- **Rationale:** this is the defence that does not depend on diagnosing every upstream cause.
  Whatever the planner decides, a player who typed a line gets a scene back.

> *Action: `uv run pytest utils/tests/backend/agents/ utils/tests/backend/api/`. Commit: `[Scene Planning] (1/5) Complete: A turn can no longer end without showing the player anything.`*

### Phase 2 — A planner that plans the scene, not just the speaker

#### Step 2.1 — Raise the planner to a real thinking budget and ask it for a direction
- **Locations:** `web/backend/app/agents/planner_agent.py` (`PLANNER_EFFORT` → `HIGH`;
  `ScenePlan` carries `direction`, `narration_needed` and the beat list);
  `web/backend/app/agents/prompt_registry.py` (the planner prompt asks where the scene is
  going and how it should evolve, not only who is next).
- **Rationale:** 256 thinking tokens buys a scheduling decision. The owner is asking for
  judgement about the story, and judgement needs room.

#### Step 2.2 — Surface the plan so the player can see it was made
- **Locations:** `web/backend/app/services/turn_engine.py` (the `planning`/`plan` trace steps
  carry the scene direction), `docs/api-contract.md`.
- **Rationale:** the complaint is "it doesn't seem like anything is planned". A plan that
  exists but is invisible reads exactly like no plan.

> *Action: `uv run pytest utils/tests/backend/agents/test_planner*.py`; frontend tests for the touched components. Commit: `[Scene Planning] (2/5) Complete: The planner decides where the scene goes, with room to think about it.`*

### Phase 3 — Ask the player when the direction is genuinely unclear

#### Step 3.1 — An `ask` action on the plan
- **Locations:** `web/backend/app/agents/planner_agent.py` (`ask` action + `question`),
  `web/backend/app/events/envelope.py` (`BranchChoicesData.prompt`),
  `web/backend/app/services/turn_engine.py` (emit and end the turn cleanly),
  `web/frontend/lib/events.ts`, `components/feature/TranscriptBeat.tsx` (render the prompt
  above the choices).
- **Rationale:** the owner asked for this explicitly. Reusing `branch_choices` means the
  question arrives, renders and round-trips through machinery that already works.

#### Step 3.2 — Guard it against becoming a stall
- **Locations:** `planner_agent.py`.
- **Rationale:** a planner that can ask will ask too often. It may only ask when nothing has
  been established this turn, and never twice in a row — otherwise a scene stops moving,
  which is worse than a mediocre guess.

> *Action: `uv run pytest utils/tests/backend/`; frontend tests + a11y pass on the prompt. Commit: `[Scene Planning] (3/5) Complete: The planner asks the player when the direction is genuinely ambiguous.`*

### Phase 4 — One first-person passage instead of three fragments

#### Step 4.1 — The `character_prose` event
- **Locations:** `web/backend/app/events/envelope.py`, `web/backend/app/services/emission.py`
  (parse `<type:character_prose>`, keep the old three), `web/frontend/lib/events.ts`,
  `features/story-player/scene-data.ts`, `components/feature/TranscriptBeat.tsx`,
  `web/backend/app/services/session_export.py`.
- **Rationale:** the contract, its hand-mirrored TypeScript twin and the renderer have to
  agree before anything can stream.

#### Step 4.2 — Rewrite the character output contract
- **Locations:** `web/backend/app/agents/prompt_registry.py`.
- **Rationale:** the model must be asked for the target form directly — first person, present
  tense, interiority and action and speech in one passage, dialogue in double quotes inline,
  and permission to hold the floor for a paragraph rather than a line.

#### Step 4.3 — Thread it through the turn loop
- **Locations:** `web/backend/app/services/turn_engine.py` (`_emit_segment_delta` streams the
  passage; `turn_beats` receives it), `docs/data-flow.md`, `docs/api-contract.md`,
  `docs/component-map.md`.
- **Rationale:** including the passage in `turn_beats` is what lets the next speaker react to
  it — and is the point at which interiority stops being private. Documented, not silent.

> *Action: `uv run pytest`; `npm test`, `npm run typecheck`, `npm run lint`; a11y + responsive pass on the transcript. Commit: `[Scene Planning] (4/5) Complete: A character beat is one first-person passage.`*

### Phase 5 — Verify against the session that prompted this

#### Step 5.1 — Replay the failing shape and read the output
- **Locations:** `utils/tests/backend/api/test_play_turn_pov.py` (a regression test for the
  silent turn), a short live run at the same settings.
- **Rationale:** the bug was found in a real session, so the fix is confirmed in one — a
  freeform POV line with nobody addressed must produce a scene, and the beats must read as
  the target form.

> *Action: full gate — `uv run pytest`; `npm test`, `npm run typecheck`, `npm run lint`; `check_contrast.py`; `check_frontend_css.mjs`; `make validate-research`. Commit: `[Scene Planning] (5/5) Complete: Verified against the session that prompted the work.`*

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| POV-safe intent | The player's own character is not in the intent roster | `web/backend/app/agents/intent_agent.py` |
| POV-safe fallback | The POV character no longer counts as having answered | `web/backend/app/agents/planner_agent.py` |
| Silent-turn backstop | A turn always shows the player something | `web/backend/app/services/turn_engine.py` |
| Scene plan | Direction + narration judgement at a 1024-token budget | `web/backend/app/agents/planner_agent.py`, `prompt_registry.py` |
| Clarifying question | `ask` action → `branch_choices` with a prompt | `planner_agent.py`, `events/envelope.py`, `TranscriptBeat.tsx` |
| `character_prose` | One first-person passage per beat | `events/envelope.py`, `services/emission.py`, `lib/events.ts` |
| Output contract | The prompt that asks for the target form | `web/backend/app/agents/prompt_registry.py` |
| Backend tests | Silent turn, POV intent, prose parsing, ask-action | `utils/tests/backend/{agents,api,services}/` |
| Frontend tests | Prose rendering, question prompt | co-located `*.test.tsx` |
