# Beat Length Control — Short / Medium / Long, in the scene config menu

**Status:** complete (2026-08-21)
**Created:** 2026-08-21
**Owner:** brendondgr
**Evidence:** EXP-2026-08-009's recorded session — character beats averaged **1292 ± 378
characters** across 19 beats, with a longest of ~2,100. The owner's words: *"Some of the
outputs are a little too long. I would prefer it to be that it's controllable in the
drop-down menu that is to the side."*

## 1. Introduction

The passage form is fixed (`docs/plans/prose-that-reads-like-a-scene.md`) and the beats now
carry speech, paragraphs and real sentences. What has no control at all is **how much** a
character says. The only bound today is operational — `_VOICE_PROSE_TOKENS` at 2048, sized
to stop a runaway, not to shape a scene — so a beat lands wherever the model leaves it, and
EXP-2026-08-009 measured that at 66 % longer than the run before it with no way for the
owner to say otherwise.

This plan adds a **per-scenario `beat_length`** with three values, alongside `max_turns`,
`suggestions_count` and `context_beats` in the scene config popover:

| Value | Paragraphs per character beat |
| --- | --- |
| `short` | 1–2 |
| `medium` (default) | 2–4 |
| `long` | 5–6 |

with each paragraph at most 3–4 sentences, **not counting quoted speech** — a line of
dialogue is not a sentence of description and should not be charged as one.

The approach is deliberately two-layered, for a reason established by measurement rather
than taste (see § 2): a **structural prompt directive** in the character prompt's recency
TAIL does the shaping, and a **per-tier token allowance** sits behind it as a backstop so a
tier that the prompt fails to bind cannot run past its neighbour. The setting threads
`Scenario` → migration → schema → `assembler` → `TurnContext` → `character_turn_agent` →
API → `lib/types.ts` → `SceneConfigMenu`, and is verified by a three-arm live experiment
rather than by a test asserting the string reached the prompt.

## 2. Gaps & Unanswered Questions

**The one real risk, and it is evidenced.** EXP-2026-08-007 § "Secondary finding" records
that a *countable* length target already failed on this codebase once: *"a countable
'usually 80–200 words' target moved the average up."* A prompt instruction about length is
therefore not something to assume will work.

Two things make this attempt different, and both are testable rather than hopeful:

1. **Paragraph counts are structural, not numeric.** The failed instruction asked the model
   to count words, which it cannot do while writing. Paragraphs are a thing it is already
   producing reliably and deliberately — EXP-2026-08-009 measured `paragraph_breaks` at
   3.89 ± 1.29, i.e. the model already controls this axis on purpose.
2. **There is a backstop.** `_VOICE_PROSE_TOKENS` becomes per-tier. Even if the directive
   binds weakly, `short` cannot produce a `long` beat.

If the experiment shows the arms overlapping on paragraph count, the plan's conclusion is
that the prompt layer does not work and the tier is enforced by the allowance alone — which
is a worse feature (a hard cut mid-paragraph) and would be reported as such rather than
shipped quietly. **The outcome of Phase 5 is not known in advance.**

**Assumptions taken (simple gaps):**

1. **Characters only, not the narrator.** The owner's words are *"when a person or character
   is trying to speak or say something"*. `narrator_agent` keeps its own 2–3 / 3–5 sentence
   spec, which is already short and already tuned. Extending the control to narration is a
   follow-up, not this plan.
2. **`medium` is the default and matches today's behaviour as closely as possible**, so an
   existing scenario that never touches the dropdown reads the same as before. New column
   defaults to `medium`; existing rows get `medium` via `server_default`.
3. **The value is a string enum, not a number.** `short|medium|long` is what the owner asked
   for and what the UI shows; a number would invite arithmetic the feature does not have.
4. **The setting is per-scenario and persists**, exactly like `max_turns` — changed from the
   popover, `PATCH`ed immediately, applied from the next beat. It is not per-turn.
5. **The output contract stops naming a paragraph count.** It currently says *"Put a blank
   line between paragraphs. Two or three of them."* That is a hardcoded `medium` and will
   contradict `short` and `long` in the same prompt. The contract keeps the *rule* (blank
   lines between paragraphs, never one block) and the TAIL supplies the *count*.
6. **Sentence-per-paragraph guidance excludes quotes.** Stated in the directive text in
   those words, so the model is not asked to trade dialogue against description.

**Flagged, needs the owner's eye (not blocking):**

`long` at 5–6 paragraphs is *longer* than what ships today (2.28–3.89 paragraphs measured
across the last two runs). So this control is not only a limiter — picking `long` will make
beats bigger than anything the owner has seen. That is what was asked for and it is built as
asked; it is flagged because "some of the outputs are a little too long" was the motivation,
and the default landing on `medium` is what actually addresses that complaint.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — The column, the migration, and the schema

#### Step 1.1 — `beat_length` on the scenario
- **Locations:** `web/backend/app/models/scenario.py` (a `beat_length` string column beside
  `context_beats`, `default="medium"`, `server_default="medium"`);
  `web/backend/alembic/versions/` (a new revision chained off head `a7b8c9d0e1f2`, using
  `batch_alter_table` like `20260702_140000_scenario_context_beats.py`).
- **Rationale:** the column has to exist before anything can read it. A `server_default`
  means the additive reconciler in `core/bootstrap.py` also handles a dev database that
  never runs Alembic, which is the path most local work takes.

#### Step 1.2 — Validate it on the way in
- **Locations:** `web/backend/app/schemas/scenario.py` (`ScenarioCreate`, `ScenarioUpdate`,
  `ScenarioRead` — a `Literal["short","medium","long"]`, default `"medium"`, `None` on
  update); `web/backend/app/services/crud.py` (`create_scenario` passes it through, the
  patch path already handles arbitrary fields — confirm rather than assume).
- **Rationale:** `context_beats` is clamped with `ge`/`le` at the schema boundary for
  exactly this reason. A `Literal` gives the same guarantee for an enum and returns a 422
  rather than letting an unknown tier reach the prompt builder.

> *Action: `uv run pytest utils/tests/backend/api/test_scenarios.py utils/tests/backend/data/`. Once green, commit locally: `[Beat Length] (1/6) Complete: beat_length on the scenario, migrated and validated.`*

### Phase 2 — Through the context to the prompt

#### Step 2.1 — Carry it on `TurnContext`
- **Locations:** `web/backend/app/services/assembler.py` (`TurnContext.beat_length`, default
  `"medium"`; `assemble_context` reads `scenario.beat_length` and normalises an unknown or
  empty value to `"medium"` rather than trusting the row).
- **Rationale:** the prompt builder takes a `TurnContext`, never a `Scenario`, so this is the
  only way in. Normalising here — not at the prompt — means a legacy row, a hand-edited
  database, or a directly-constructed test context all resolve to a real tier.

#### Step 2.2 — The directive in the recency TAIL
- **Locations:** `web/backend/app/agents/character_turn_agent.py` — a `_BEAT_LENGTH_DIRECTIVES`
  map beside `_REGISTER_DIRECTIVES`, appended in `_build_user_prompt`'s TAIL near the
  register directive (before the "Respond now" line, so it is late enough to carry weight and
  not last, where the beat's owed requirements belong).
- **Rationale:** the TAIL is where per-beat situational facts already live, and it is the
  half of the prompt that changes per scenario — putting a per-scenario value in the STABLE
  head would break the prompt-cache prefix that `test_prompt_cache_prefix.py` guards.
- **Note:** the directive is phrased structurally (*"Write 1 to 2 paragraphs"*), with the
  3–4-sentence-per-paragraph rule and the explicit "quoted dialogue does not count toward
  that" carve-out. No word counts — § 2 records why.

#### Step 2.3 — Stop the contract from hardcoding a count
- **Locations:** `web/backend/app/agents/prompt_registry.py` (`_CHARACTER_OUTPUT_CONTRACT` —
  "Two or three of them" becomes a rule about blank lines without a number).
- **Rationale:** two instructions about paragraph count in one prompt, disagreeing, is worse
  than either alone. The contract owns the *form*; the TAIL owns the *amount*.

> *Action: `uv run pytest utils/tests/backend/agents/ utils/tests/backend/services/`. Once green, commit locally: `[Beat Length] (2/6) Complete: The tier reaches the character prompt, and the contract stops arguing with it.`*

### Phase 3 — The allowance behind the directive

#### Step 3.1 — Per-tier prose allowance
- **Locations:** `web/backend/app/agents/character_turn_agent.py` — `_VOICE_PROSE_TOKENS`
  becomes a per-tier lookup (`_PROSE_TOKENS_BY_LENGTH`), `_voice_params` takes the tier;
  `web/backend/app/services/turn_engine.py` — `_RUNAWAY_CHARS` is derived from the tier's
  allowance rather than from a module constant.
- **Rationale:** § 2's risk. The allowance is set **generously** for each tier — a backstop,
  not the mechanism — because a hard token cut lands mid-sentence and that is a worse
  artifact than a beat one paragraph over. `long` keeps today's 2048; `short` and `medium`
  get proportionally less but still more than their paragraph target needs.
- **Care:** `_voice_params` already adds the thinking budget on top of the prose allowance
  (`budget_for(reasoning) * _SCRATCHPAD_HEADROOM + prose`). That structure must survive —
  shrinking the total rather than the prose half is what starved a live turn before, and
  `docs/api-contract.md` records why.

> *Action: `uv run pytest utils/tests/backend/agents/test_character_turn_agent.py utils/tests/backend/api/`. Once green, commit locally: `[Beat Length] (3/6) Complete: Each tier has its own prose allowance and runaway stop.`*

### Phase 4 — The dropdown

#### Step 4.1 — A select that takes strings
- **Locations:** `web/frontend/components/ui/SceneControlSelect.tsx` (generalise from
  `number` to `string | number` with an optional per-option label; every existing numeric
  caller must keep working unchanged), co-located `SceneControlSelect.test.tsx`.
- **Rationale:** the component coerces with `Number(e.target.value)` today, so it cannot
  carry an enum. Generalising it is smaller than adding a second near-identical select, and
  it is the component the other three controls already use — the new control should look
  like its neighbours because it *is* one.

#### Step 4.2 — Wire it through the player
- **Locations:** `web/frontend/lib/types.ts` (`beatLength` on the scenario type, the
  hand-mirrored contract); `web/frontend/components/feature/SceneConfigMenu.tsx` (the new
  control + its `onBeatLengthChange`); `web/frontend/components/feature/Composer.tsx`
  (pass-through); `web/frontend/features/story-player/StoryPlayerView.tsx` (pass-through);
  `web/frontend/features/story-player/useScenePlay.ts` (state + the `updateScenario` PATCH,
  following `setContextBeats` exactly); co-located tests for `SceneConfigMenu` and
  `StoryPlayerView`.
- **Rationale:** `contextBeats` already traces this exact path; matching it means no new
  pattern to learn and the existing tests describe the shape the new one must have.
- **A11y:** the control is a native `<select>` with a visible mono label, like its three
  neighbours, so keyboard and screen-reader behaviour come for free. The popover is
  264 px wide and gains one more row — check it at 320/375 before calling this done.

> *Action: `cd web/frontend && npm test && npm run typecheck && npm run lint`, plus an accessibility + responsive pass (keyboard into and out of the popover, focus visible, 320/375/768/1024). Once green, commit locally: `[Beat Length] (4/6) Complete: Short/Medium/Long in the scene config menu, wired to the scenario.`*

### Phase 5 — Measure whether the tiers are real

#### Step 5.1 — A three-arm live experiment
- **Locations:** `docs/research/experiments/EXP-2026-08-010-beat-length/` (scaffolded with
  `make new-experiment`), `utils/scripts/research/run_beat_length.py` (drives the same
  six-turn session shape at each tier, reusing `run_prose_end_to_end`'s measurement and
  `run_conversation_scaling.build_world`), a `PROTOCOL.md` written **before** the run.
- **Rationale:** § 2 says the outcome is not known in advance, and a countable length target
  has already failed once on this codebase. The primary metric is **paragraphs per character
  beat**, with `chars` and `sentences_per_100_words` beside it and the EXP-2026-08-009 form
  metrics carried over so a regression is visible. A tier that does not separate from its
  neighbours is a finding, not a bug to hide.
- **Pre-registered prediction:** `short` < `medium` < `long` on paragraphs per beat, with
  `short` at or below 2 and `long` at or above 5, and no form metric regressing.

#### Step 5.2 — Record it and act on it
- **Locations:** the experiment's `RESULTS.md` / `ISSUES.md` / `manifest.yaml`, a generated
  figure, `docs/research/INDEX.md` and `OPEN_QUESTIONS.md`.
- **Rationale:** the research contract. If the arms overlap, `RESULTS.md` says so and the
  plan's § 2 fallback applies.

> *Action: `make validate-research`; read every passage in the run's transcript. Once green, commit locally: `[Beat Length] (5/6) Complete: The three tiers measured end to end.`*

### Phase 6 — Documentation and the gate

#### Step 6.1 — Update the docs that describe this surface
- **Locations:** `docs/api-contract.md` (the scenario body + the character-beat section),
  `docs/data-flow.md` (the character-prompt TAIL description), `docs/component-map.md`
  (`SceneConfigMenu`, `SceneControlSelect`), `docs/documentation.md` and `docs/workflow.md`
  where the per-scene controls are enumerated, `docs/checklist.md` for anything left open.
- **Rationale:** the project rule — docs are updated in the same change that alters
  behaviour, and four separate files enumerate the per-scene controls today.

> *Action: full gate — `uv run pytest`; `npm test`, `npm run typecheck`, `npm run lint`; `check_contrast.py`; `check_frontend_css.mjs`; `make validate-research`. Once green, commit locally: `[Beat Length] (6/6) Complete: Documented and verified.`*

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Column + migration | `beat_length` on the scenario, defaulting to `medium` | `web/backend/app/models/scenario.py`, `web/backend/alembic/versions/` |
| Schema validation | `Literal["short","medium","long"]` on create/update/read | `web/backend/app/schemas/scenario.py` |
| Context threading | Normalised onto `TurnContext` | `web/backend/app/services/assembler.py` |
| Prompt directive | Per-tier paragraph directive in the recency TAIL | `web/backend/app/agents/character_turn_agent.py` |
| Contract fix | The output contract stops naming a paragraph count | `web/backend/app/agents/prompt_registry.py` |
| Per-tier allowance | Prose token budget + runaway stop follow the tier | `web/backend/app/agents/character_turn_agent.py`, `web/backend/app/services/turn_engine.py` |
| Generalised select | `SceneControlSelect` carries string values with labels | `web/frontend/components/ui/SceneControlSelect.tsx` |
| The dropdown | Short/Medium/Long beside Max turns and Suggestions | `web/frontend/components/feature/SceneConfigMenu.tsx` |
| FE threading | Type mirror, pass-through, state + PATCH | `web/frontend/lib/types.ts`, `Composer.tsx`, `StoryPlayerView.tsx`, `useScenePlay.ts` |
| Experiment | Three arms, live, paragraphs per beat as primary | `docs/research/experiments/EXP-2026-08-010-beat-length/`, `utils/scripts/research/run_beat_length.py` |
| Backend tests | Schema, assembler normalisation, prompt directive, allowance | `utils/tests/backend/{api,agents,services}/` |
| Frontend tests | Select, config menu, player wiring — co-located | `web/frontend/components/{ui,feature}/*.test.tsx`, `features/story-player/StoryPlayerView.test.tsx` |
| Docs | Every file that enumerates the per-scene controls | `docs/{api-contract,data-flow,component-map,documentation,workflow}.md` |
