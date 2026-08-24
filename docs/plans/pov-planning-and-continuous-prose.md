# Point of View, Planning Mode, and Continuous Prose

**Status:** proposed — not started. Written 2026-08-24 against the code as it stands on
`main` (`0b134ac`).

---

## 1. Introduction

Four complaints from the owner, which look like four features and are really two defects and
two rebuilds:

1. **The direction verb bar is in the way.** *Push it forward · Slow down · Skip ahead · Cut
   to later* and their eleven siblings sit above the composer in every scene. Remove or
   collapse them.
2. **Point of view is wrong in narrator mode.** Characters address the player as *"you"* when
   the player is not in the room; the narrator does not reliably stay in the third person;
   and one character's beat contains another character's speech.
3. **Planning mode is in the wrong place and asks the wrong questions.** It should be a
   first-class control in the composer with an **Auto** / **Plan** split, and the two Pacing
   settings (*how many beats a message produces* and *how much a character says at once*)
   should be replaced by the model adapting to the moment.
4. **Prose should be produced continuously from a plan**, with a token in the stream that
   tells the frontend the speaker changed — instead of one model call per speaker and a
   parser guessing at attribution.

Items 1–3 are bounded changes to prompts, the composer, and the turn settings. Item 4 is an
architectural reversal: the turn loop today makes **one LLM call per speaker**, deliberately,
so voices stay distinct (`character_turn_agent`'s module docstring says so in as many words),
and the incremental parser makes a second prose segment **structurally unrepresentable**
(`EmissionAccumulator._prose_seen`). A single continuous multi-speaker generation is the
opposite of both. It may well read better and parse more cleanly — but it trades away the one
property the codebase already had to add a guard for (`beat_stream.echoes_a_beat` exists
because two characters returned byte-identical passages), so it is built behind a flag and
**measured against the current path before it becomes the default**.

The plan is ordered so the owner gets the quick wins first, the correctness fixes second, and
the architectural bet last, behind a measurement.

### Root causes, located

Three of the four complaints have an exact line of code behind them. Recording them here so
the phases below are fixes rather than guesses:

| Complaint | Cause |
| --- | --- |
| **2A** — characters say "you" in narrator mode | The player's line is pushed to the buffer as `role="player"` (`turn_setup.py:184`), and both transcript renderers label a `player` beat **`You:`** (`character_turn_agent._transcript`, `narrator_agent._recent`). The output contract then says, verbatim: *"The line labelled 'You:' is the person you are talking to — someone standing in the room with you … Write them in the second person."* In **POV** mode the player's line is pushed as `role="character"` instead, so **`You:` only ever appears in narrator mode** — precisely the mode where the player has no body. The cast is doing exactly what it was told. |
| **2B** — the narrator uses first/second person | `_NARRATOR_SYSTEM` and `_NARRATOR_SYSTEM_LONG` both end with *"Narrate them in the second person — 'you', 'your'."* Same cause, same label. |
| **2C** — characters interrupt each other | Nothing checks it. The contract says *"Only your character. Never write anyone else's words"*, and there is **no** detector behind that rule — `emission.py` has guards for degeneration, repetition, scratchpad leakage, mid-sentence openings and the phrase "the player", and none for another cast member's name in front of a line of dialogue. |

The `You:` label is not an accident and must not simply be reverted:
[`EXP-2026-08-009`](../research/experiments/EXP-2026-08-009-prose-second-person/RESULTS.md)
measured it taking "the player" out of the prose from **72 % of character beats to 0 %**. The
fix in Phase 2 therefore replaces the label with a **non-person** one rather than going back
to `Player:`.

---

## 2. Gaps & Unanswered Questions

### Answered here (assumptions taken; say so if any is wrong)

- **"Write mode expands into Auto / Plan."** Read as the **Planning mode** button expanding —
  *Auto* runs the turn straight through, *Plan* shows the plan and waits for approval. There
  is no other control in the composer that "approves and moves on".
- **Collapse, not delete, for the verb bar.** The owner offered collapsing as an acceptable
  alternative and it is strictly better: the fifteen verbs and their gating
  (`lib/sceneVerbs.ts`) are working code with tests, and a scenario author can add their own.
  Phase 1 hides the bar behind a small disclosure that is **closed by default and remembers
  its state**, so the default experience is the one asked for and nothing is thrown away.
- **Adaptive means "the model chooses, the engine still has a backstop".** `max_turns`
  (player-facing, 1–10) is removed as a control. `turn_max_beats` — the runaway backstop at
  `turn_engine.py:269` — stays, is not player-facing, and is not raised. Same for beat length:
  the paragraph directive stops being a player setting, and the token ceiling
  (`_PROSE_TOKENS_BY_LENGTH`) stays as a backstop. Removing the *only* ceiling would be
  irresponsible against the recorded incident where one 48,000-token generation ran 684 s,
  timed out the relay's health probe, and cost the player the rest of the scene.
- **Narrator mode has no player avatar.** Phase 2 treats the player's narrator-mode message as
  **stage direction from outside the fiction**, not as a person's line. This is what "refer to
  characters directly, by name only" requires.

### Needs a human decision

- **Does narrator mode keep *any* embodied player?** The assumption above has a visible
  consequence: today's composer placeholder in narrator mode is *"Speak, or describe what you
  do…"*, which invites a player to write *"I lean across the table"* — and under the new rule
  the cast would have nobody to lean at. Phase 2 changes that copy to a direction-only prompt.
  If the owner wants a scene where they can still *act* without picking a POV character, that
  is a third mode and not a copy change. **Human intervention is needed to answer this.**
- **Is one shared prose call acceptable if voices measurably converge?** Phase 9 will produce
  a number for voice distinctness under the continuous path against the current per-speaker
  path. If continuous prose reads better *and* voices hold, it ships as the default. If voices
  converge, the choice is the owner's: keep per-speaker calls (and get continuity a different
  way), or accept flatter voices for smoother flow. **Human intervention is needed to answer
  this**, and it cannot be answered before Phase 9 has run.
- **What happens to the four scene presets?** `content/scene_presets.py` defines all four
  entirely in terms of `maxTurns` and `beatLength`, both of which Phase 5 removes. Two of the
  four (*Fast banter*, *Interrogation*) exist only to bound length. The plan's assumption is
  that presets are **removed with the settings they wrap**, and the whole preset picker with
  them; the alternative is redefining them as adaptation hints in the plan prompt. Flagged
  because deleting a shipped feature is the owner's call, not the implementer's.

---

## 3. Step-by-Step Instructions

### Phase 1 — Get the direction verbs out of the way

- **Locations:** `web/frontend/components/feature/DirectionRow.tsx` (the row that renders the
  bar through its `children` slot), `web/frontend/components/feature/Composer.tsx` (passes
  `verbs` and renders `SceneVerbBar` inside `DirectionRow`), new
  `web/frontend/hooks/use-verb-bar-open.ts` or a key added to the existing
  `lib/coachMarks.ts`-style `localStorage` helper, and the co-located
  `DirectionRow.test.tsx` / `SceneVerbBar.test.tsx`.
- **What changes:** `DirectionRow` gains a small disclosure control — a single
  `aria-expanded` button reading `Verbs` — that wraps the `children` slot. Closed by default.
  Open state persists per browser, not per scene, so a player who wants them keeps them. The
  bar itself, `lib/sceneVerbs.ts`, the gating rules and the "Someone arrives" cast submenu are
  untouched.
- **Rationale:** this is the owner's "quick first fix" and it is genuinely independent of
  everything below it — it must not be blocked behind the prompt work.
- **Accessibility:** the disclosure is a real `<button>` with `aria-expanded` and
  `aria-controls`; the toolbar keeps its roving tabindex; when closed, its buttons must be out
  of the tab order entirely (unmounted, not merely hidden).
- **Action:** run `npm test` for `DirectionRow`, `SceneVerbBar` and `Composer`, plus
  `npm run typecheck && npm run lint`, and an a11y/responsive pass at 320/375/768/1024. Once
  green, commit: `[POV & Continuous Prose] (1/10) Complete: The direction verbs collapse behind a disclosure, closed by default.`

---

### Phase 2 — Narrator mode: the player is direction, not a person in the room

This is the correctness fix for complaints 2A and 2B, and it is a **label** change plus a
**prompt** change, in that order — `EXP-2026-08-009` is the evidence that the label does the
work and the rule alone does not.

- **Locations:**
  - `web/backend/app/agents/character_turn_agent.py` → `_transcript` (the `role == "player"`
    branch), and the tail builder around `tail.append("The player addressed you directly.")`.
  - `web/backend/app/agents/narrator_agent.py` → `_recent` (the same branch).
  - `web/backend/app/agents/prompt_registry.py` → `_CHARACTER_OUTPUT_CONTRACT`,
    `_NARRATOR_SYSTEM`, `_NARRATOR_SYSTEM_LONG`.
  - `web/backend/app/services/assembler.py` → `TurnContext` gains a `player_embodied: bool`
    (true under POV, false in narrator mode) so both renderers and both prompts read one flag
    rather than each re-deriving it.
  - `web/frontend/components/feature/Composer.tsx` → the narrator-mode placeholder.
- **What changes:**
  - In **narrator mode**, a `player` beat renders as `Direction: …` — a line that is visibly
    not a speaker. `You:` is kept for **POV** mode only, where the player genuinely is in the
    room. Neither mode ever renders `Player:`, so `EXP-2026-08-009`'s finding is preserved.
  - The character contract's `You:` clause becomes conditional on `player_embodied`. In
    narrator mode it is replaced by: the `Direction:` line is an instruction from outside the
    story, addressed to nobody; never answer it, never quote it, never write a second person
    into the scene — everyone present is named.
  - Both narrator prompts drop *"Narrate them in the second person"* in narrator mode and gain
    an explicit third-person-only rule: no `I`, `me`, `my`, `we`, `you`, `your`; characters are
    named.
  - The composer placeholder in narrator mode changes from *"Speak, or describe what you
    do…"* to a direction-only prompt (see the flagged question in §2).
- **New guard:** `emission.py` gains `addresses_the_reader(text, *, window)` — a
  second-person-pronoun detector — used by `beat_stream._pass` exactly the way
  `names_the_player` is: **only when the player is not embodied**, only on the opening window,
  and it discards-and-regenerates rather than rewriting. It is a backstop and a **metric**, not
  the mechanism; Phase 3's experiment reads it.
- **Rationale:** the label is what the model imitates. Fixing the rule and leaving the label is
  the exact mistake `EXP-2026-08-009` § 4 recorded ("naming the concept in a rule while the
  transcript kept supplying the word did nothing").
- **Tests:** `utils/tests/backend/agents/test_transcript_labelling.py` (a `player` beat renders
  `Direction:` in narrator mode and `You:` under POV — one test per renderer);
  `utils/tests/backend/agents/test_prompt_pov.py` (the contract carries the embodied clause
  under POV and the direction clause without it); extend
  `utils/tests/backend/services/test_emission_guards.py` for `addresses_the_reader`.
- **Action:** run `uv run pytest utils/tests/backend/agents utils/tests/backend/services`, plus
  the frontend `Composer` tests. Once green, commit: `[POV & Continuous Prose] (2/10) Complete: In narrator mode the player's line is direction, not a person, and both narrator prompts are third-person only.`

---

### Phase 3 — Measure it, before and after (EXP-2026-08-015)

The owner asked for tests rather than an assumption that it looks right, and named the
priority: *confirming that points of view are not being incorrectly quantified*. Per the
research contract this is an experiment folder, not a chat number.

- **Locations:** `make new-experiment SLUG=pov-narrator-mode` →
  `docs/research/experiments/EXP-2026-08-015-pov-narrator-mode/`; a runner at
  `utils/scripts/research/run_pov_mode.py` **derived from** `run_prose_end_to_end.py` (it
  already builds a throwaway world, drives `POST /api/play/{id}/turn`, reads back every beat
  and counts discards from the trace — do not write a second harness).
- **Metrics**, per beat kind (character / narration) and per mode (narrator / POV):
  - `addresses_the_reader` — a second-person pronoun in a beat produced while the player is
    not embodied. **Primary.**
  - `narrator_first_person` — `I`/`me`/`my`/`we` in a narration beat. **Primary.**
  - `cross_speaker_speech` — quoted dialogue attributed inside the passage to a cast member
    who is not the speaker (Phase 4's detector, used here as the measurement).
  - The `run_prose_form` form metrics that must **not** regress: `has_speech`, `is_distinct`,
    `paragraph_breaks`, `sentences_per_100_words`, `names_the_player`.
  - Discards per turn — a run that scores well only because the gate threw beats away is not a
    run that scores well. This is the threat `EXP-2026-08-009` § Threats already named.
- **Design:** two arms on the **same** deployed model, **interleaved in one session** —
  `pre` (the Phase-1 commit) and `post` (the Phase-2 commit). Day-apart comparisons on this
  endpoint are worthless; see `mytheca-verify-the-environment-before-concluding`. Six player
  turns per arm, narrator mode, a cast of at least three so cross-speaker leakage has somewhere
  to happen.
- **Rationale:** it runs *here*, after Phase 2 and before the rebuilds, because everything from
  Phase 5 on changes the prompts again — a baseline taken later cannot separate the POV fix
  from the planning overhaul.
- **Recording:** `manifest.yaml` + `RESULTS.md` + generated figures; register the claim in
  `docs/research/CLAIMS.md`. Never hand-edit a figure, never hardcode a number in the plotting
  script, and if an arm fails, record it — do **not** aggregate over the survivors
  (`EXP-2026-08-001` is the worked example of getting this wrong).
- **Action:** run `make validate-research`, then `uv run pytest`. Commit: `[POV & Continuous Prose] (3/10) Complete: EXP-2026-08-015 measures the narrator-mode point-of-view fix against its own baseline.`

---

### Phase 4 — One character's beat holds one character's speech

- **Locations:** `web/backend/app/services/emission.py` (new
  `cross_speaker_speech(text, *, speaker_name, other_names, window)`),
  `web/backend/app/services/beat_stream.py` (`_pass`, beside `echoes_a_beat`),
  `web/backend/app/agents/prompt_registry.py` (`_CHARACTER_OUTPUT_CONTRACT`).
- **What changes:** a detector for the shape actually observed — another present cast member's
  name immediately followed by a speech verb and a quotation, or a quoted line on a paragraph
  opening with another cast member's name attached. It joins the same discard-and-regenerate
  path the scratchpad gate uses, judged on the opening window only. The contract's *"Only your
  character"* rule gains the consequence in words: another character may be **looked at,
  answered, or described**, but never quoted.
- **Deliberately narrow.** A character *reporting* what someone said (*"He told me the gate
  was shut"*) is ordinary prose and must survive; only attributed live dialogue is caught. The
  false-negative direction is the safe one — a missed leak costs a reader's eyebrow, a false
  positive costs a regeneration and can silently strip good writing.
- **Rationale:** the owner's example — Zoe speaking during Lily's beat — has no detector behind
  it today. This is the half of complaint 2C that a prompt alone has already failed to fix, on
  this codebase, for the analogous case.
- **Tests:** `utils/tests/backend/services/test_emission_guards.py` — leaked dialogue is
  caught; reported speech, a character quoting *themself*, and a character's name in ordinary
  narration all survive.
- **Action:** `uv run pytest utils/tests/backend/services utils/tests/backend/agents`. Commit:
  `[POV & Continuous Prose] (4/10) Complete: A beat carrying another character's spoken line is caught and re-rolled.`

---

### Phase 5 — Adaptive generation replaces the two Pacing settings

- **Locations:**
  - `web/backend/app/schemas/base.py` (`BeatLength`, `BEAT_LENGTHS`, `DEFAULT_BEAT_LENGTH`),
    `web/backend/app/schemas/play.py` (`TurnOverrides.max_turns`, `.beat_length`),
    `web/backend/app/schemas/scenario.py`.
  - `web/backend/app/services/turn_settings.py` (`TurnSettings.max_turns`, `.beat_length` and
    their clamps), `web/backend/app/services/turn_engine.py` (the `remaining = max_turns -
    scene_beats` accounting and the "Reached the scene's turn limit" trace),
    `web/backend/app/services/direction_runtime.py` (`pace`, which divides requirements by
    remaining beats).
  - `web/backend/app/agents/character_turn_agent.py` (`_BEAT_LENGTH_DIRECTIVES`,
    `_BEAT_LENGTH_SHAPE`, `prose_tokens_for`), `web/backend/app/agents/planner_agent.py`
    (`remaining_beats` in `_plan_prompt`).
  - `web/backend/app/content/scene_presets.py` (see the flagged question in §2).
  - `web/frontend/components/feature/SceneConfigMenu.tsx`,
    `web/frontend/features/story-player/useScenePlay.ts`, `web/frontend/lib/types.ts`.
  - Migration under `web/backend/alembic/versions/` — dropping columns is not additive.
- **What changes:**
  - **Player-facing `maxTurns` and `beatLength` are removed** — from the config popover, from
    `TurnOverrides`, from the pin set (`SceneControlKey`), and from the scenario row.
  - `turn_max_beats` (`turn_engine.py:269`) stays as the runaway backstop and becomes the only
    bound on beats per turn. `_PROSE_TOKENS_BY_LENGTH` collapses to the single `long` allowance
    (2048) as the only bound on a passage.
  - The **planner** gains the pacing decision it was already best placed to make: for each
    beat it returns a `weight` (`brief` | `full` | `extended`) alongside `register` and
    `stakes`, and the character prompt's length directive is built from that per beat rather
    than from a scene-wide tier. The paragraph-count phrasing of `_BEAT_LENGTH_DIRECTIVES` is
    kept verbatim — `EXP-2026-08-007` measured a **word** target moving the average the wrong
    way, and `EXP-2026-08-010` is the beat-length experiment this must not silently undo.
  - The planner prompt is told it is pacing the turn itself: plan as many beats as the moment
    needs and stop when it is done, rather than filling a budget.
- **Rationale:** both settings feed the planning phase, which is exactly where the owner wants
  the adaptation to live. Deleting them without moving the decision somewhere would leave the
  engine with no pacing signal at all.
- **Risk, stated:** the scene cap is today the thing that stops a turn running away in
  wall-clock. `turn_max_beats` is a *backstop*, chosen as a runaway guard, not as a pacing
  number — expect to re-tune it, and record the tuning.
- **Tests:** `utils/tests/backend/services/test_turn_settings.py` (the removed fields no longer
  resolve; an old override envelope carrying them is accepted and ignored rather than 422-ing),
  `utils/tests/backend/agents/test_planner_weight.py` (`weight` parses, an unknown value
  degrades to `None`, and `None` yields today's medium directive),
  `utils/tests/backend/api/test_scenario_settings.py`. Frontend: `SceneConfigMenu.test.tsx`
  and `useScenePlay.test.ts` lose the two controls.
- **Action:** `uv run pytest`, `npm test`, `npm run typecheck && npm run lint`, an a11y pass on
  the shortened popover, and `alembic upgrade head` against a scratch DB. Commit:
  `[POV & Continuous Prose] (5/10) Complete: Beats per message and beat length are gone; the planner paces each beat itself.`

> **Dev-database note:** this drops columns. Per `mytheca-dev-db-column-drift`, the dev
> Postgres is reconciled additively at backend startup and will **not** drop them for you — run
> the migration, or the reloaded server keeps a column the model no longer knows about.

---

### Phase 6 — Planning mode moves into the composer

Pure UI. No engine change, so it can be reviewed on its own.

- **Locations:** `web/frontend/components/feature/Composer.tsx` (the controls bar), new
  `web/frontend/components/feature/PlanModeButton.tsx` + co-located test,
  `web/frontend/components/feature/GhostwriteButton.tsx`,
  `web/frontend/components/feature/SceneConfigMenu.tsx` (the "Turn planning" row leaves),
  `web/frontend/features/story-player/useScenePlay.ts`.
- **What changes:** the controls bar becomes
  `[Config] [POV select] [Plan mode] … [Context dial] [✎ thinking icon] [Send]`.
  - **Plan mode** sits between the POV select and where *Write it* used to be. Collapsed it
    shows the active mode; activated it expands to two buttons — **Auto** (approve
    automatically and move on) and **Plan** (stop for approval). The existing
    `plannerMode: "planner" | "off"` widens to `"auto" | "plan" | "off"`; `"off"` keeps its
    home in the Config popover, because turning planning off changes what the app is and does
    not belong on a two-way toggle.
  - **Write it** loses its label and becomes an icon-only button between the context dial and
    Send. It keeps its accessible name, its `title`, its disabled rule and its Undo state —
    only the visual changes. An icon-only control **must** carry `aria-label`; this is the most
    likely thing to be dropped in this phase.
- **Rationale:** doing the UI before the approval loop means the loop lands against a control
  that already exists and is already tested, and the owner can see the layout early.
- **Tests:** `PlanModeButton.test.tsx` (expands, both options selectable, keyboard operable,
  `aria-expanded` correct), `Composer.test.tsx` (control order; the ghostwrite button keeps its
  accessible name with no visible text).
- **Action:** `npm test`, `npm run typecheck && npm run lint`, a11y + responsive at
  320/375/768/1024 — the controls bar is the row most at risk of overflowing at 320 px. Commit:
  `[POV & Continuous Prose] (6/10) Complete: Plan mode is a composer control with Auto and Plan; Write it is an icon between Context and Send.`

---

### Phase 7 — Plan mode: show the plan, wait for approval

- **Locations:** `web/backend/app/events/stream.py` (a `TurnPlanFrame` transport frame — a
  plan is not a story event and must not be persisted as one),
  `web/backend/app/services/turn_engine.py` (emit the plan and stop when the mode is `plan`),
  `web/backend/app/schemas/play.py` (`TurnRequest` gains `approvedPlan`),
  `web/backend/app/agents/planner_agent.py` (the plan already carries everything needed —
  `actor_id`, `action`, `reason`, `register`, `stakes`, and `weight` from Phase 5),
  `web/frontend/lib/events.ts` (the hand-mirrored contract),
  `web/frontend/features/story-player/turn-stream.ts`, a new
  `web/frontend/components/feature/PlanApproval.tsx`.
- **What changes:** under **Plan**, the turn runs `plan_beats` at full lookahead, emits the
  plan as one frame, and returns without producing prose. The player sees a list — *who acts,
  what they do, how it is pitched* — and either approves it (a second `POST` carrying
  `approvedPlan`, which the engine executes without re-planning) or edits their message and
  sends again. Under **Auto**, nothing changes from today except that the plan frame is still
  emitted for the Inspector.
- **Rationale:** this is what makes the plan in Phase 8 worth generating in depth — the owner
  wants to see *what each character is going to do, say, and how they say it* before the prose
  commits to it.
- **Contract duty:** `docs/api-contract.md` and `docs/data-flow.md` are updated **in this
  commit**. The envelope's TypeScript mirror in `web/frontend/lib/events.ts` is hand-maintained;
  changing one side without the other is the documented way to break this app.
- **Tests:** `utils/tests/backend/api/test_turn_plan_mode.py` (plan mode emits a plan frame and
  no prose events; an approved plan executes without a second planner call — assert on the call
  count, not on wall-clock); `turn-stream.test.ts` for the new frame;
  `PlanApproval.test.tsx`.
- **Accessibility:** the approval panel is a live region — it arrives mid-stream — and its
  approve/edit controls must be reachable without leaving the composer.
- **Action:** `uv run pytest utils/tests/backend/api utils/tests/backend/services`, `npm test`,
  a11y pass. Commit: `[POV & Continuous Prose] (7/10) Complete: Plan mode streams the plan and waits for approval before any prose is written.`

---

### Phase 8 — The continuous scene script (behind a flag, off by default)

The architectural bet. It is built complete and **not** switched on.

- **Locations:**
  - New `web/backend/app/agents/scene_script_agent.py` — one call that renders an **approved
    plan** as continuous prose, with `<speaker:N>` on its own line at every change of speaker
    and `<speaker:0>` for the narrator. The roster numbering is the one `planner_agent` already
    builds, so the token space is shared and no new mapping exists to drift.
  - `web/backend/app/services/emission.py` — `EmissionAccumulator` learns that a `<speaker:N>`
    naming a **different** speaker closes the open prose segment and opens a new one. The
    `_prose_seen` guard is **not** deleted: it is re-keyed to *"no second passage for the
    **same** speaker"*, which keeps the five-identical-beats defect it was written for while
    making a genuine hand-off representable.
  - `web/backend/app/services/beat_stream.py` — the per-segment guards (scratchpad, echo,
    cross-speaker from Phase 4, the reader-address check from Phase 2) run **per speaker
    segment** rather than once per generation, and the runaway ceiling becomes per-script with a
    per-segment ceiling under it.
  - `web/backend/app/services/beat_runner.py`, `turn_engine.py` — a `scene_script` route
    beside the per-speaker route, chosen by `TURN_SCENE_SCRIPT` (new env var, default `false`).
  - `.env.example` + `docs/deployment.md` — every new env var is documented in both.
- **What the frontend needs:** nothing new. Each speaker segment already opens its own event
  with its own `characterId` through `emitter.open_stream`, and `TranscriptBeat` already keys
  the portrait and colour off it — so the "tokenized signal that the speaker changed" is
  delivered as the **existing** event boundary rather than as a new token the client has to
  learn. That is the cheapest correct answer and it is why this phase is backend-only.
- **The known cost, stated plainly:** the per-speaker split exists *because* it keeps voices
  distinct. One prompt holding every speaker's voice samples will pull them together, and it
  will pull hardest on exactly the weaker models the owner wants this to be foolproof for. The
  flag defaults off for this reason and Phase 9 is what decides it.
- **Fallback:** a script whose speaker tokens are missing or unparseable falls back to the
  per-speaker path for that turn rather than emitting one giant mis-attributed beat. A model
  too weak to emit the tokens must degrade to today's behaviour, not to a worse one.
- **Tests:** `utils/tests/backend/services/test_emission_multi_speaker.py` — a two-speaker
  script yields two segments with the right ids, in any chunking, and `push()` + `finish()`
  agree with `parse_emission`; a repeated passage by the *same* speaker still collapses to one;
  a token naming a number not on the roster falls back to the intended speaker.
  `utils/tests/backend/services/test_scene_script_fallback.py` for the degrade path.
- **Action:** `uv run pytest`. Commit: `[POV & Continuous Prose] (8/10) Complete: A plan can be rendered as one continuous multi-speaker script, behind TURN_SCENE_SCRIPT, off by default.`

---

### Phase 9 — Does the continuous script hold the voices? (EXP-2026-08-016)

- **Locations:** `make new-experiment SLUG=continuous-scene-script` →
  `docs/research/experiments/EXP-2026-08-016-continuous-scene-script/`; runner
  `utils/scripts/research/run_scene_script.py`, again derived from `run_prose_end_to_end.py`.
- **Arms:** per-speaker (`TURN_SCENE_SCRIPT=false`) and continuous (`true`), **interleaved in
  one session on the same model**, same world, same player lines, same cast of three or more.
- **Metrics:**
  - **Voice distinctness — primary.** A per-character lexical-profile distance across that
    character's beats versus every other character's, plus the existing `is_distinct` and the
    `echoes_a_beat` fire rate. The hypothesis being tested is that continuous prose does
    **not** reduce it.
  - **Attribution correctness — primary.** Beats attributed to the wrong speaker, and
    `cross_speaker_speech` from Phase 4. This is the owner's "fewer parsing issues" claim, and
    it is the one this design should win on.
  - Turn wall-clock and completion tokens, one call against N.
  - The `run_prose_form` metrics that must not regress.
- **Decision rule, written before the run:** continuous becomes the default **only if**
  attribution improves and voice distinctness does not degrade. Either failing sends the result
  to the owner as a trade rather than a recommendation (see §2).
- **Honesty rules:** record failed runs; never aggregate over the survivors of a partly-failed
  experiment; n per arm is small, so an existence proof is reported as an existence proof and
  not as a rate.
- **Action:** `make validate-research`, then `uv run pytest`. Commit: `[POV & Continuous Prose] (9/10) Complete: EXP-2026-08-016 measures continuous multi-speaker prose against the per-speaker path.`

---

### Phase 10 — Reconcile the docs, then merge

- **Locations:** `CLAUDE.md` (the "Facts that override stale assumptions" list — `SceneVerbBar`
  and `lib/sceneVerbs.ts` are already missing from the component tables and should be added
  while this file is open), `docs/documentation.md`, `docs/architecture.md`,
  `docs/component-map.md`, `docs/api-contract.md`, `docs/data-flow.md`, `docs/routes.md` (only
  if a route changed — it should not have), `docs/deployment.md` + `.env.example`
  (`TURN_SCENE_SCRIPT`), `docs/design-system.md` (the composer controls bar),
  `docs/checklist.md` (whatever this plan leaves open — the flagged human decisions from §2
  belong here if they are still unanswered), `docs/research/INDEX.md` + `CLAIMS.md`.
- **Rule:** delete the sentences that described what was removed. Do not leave the old
  `maxTurns` / `beatLength` prose beside its replacement — that accumulation is exactly why the
  docs were rebuilt on 2026-08-04.
- **Merge:** merge the branch into `main`, resolve conflicts, and remove the worktree. No push,
  no PR, unless asked.
- **Action:** full gate — `uv run pytest`, `npm test`, `npm run typecheck && npm run lint`,
  `uv run python utils/scripts/check_contrast.py`, `node utils/scripts/check_frontend_css.mjs`,
  `make validate-research`. Commit: `[POV & Continuous Prose] (10/10) Complete: Docs reconciled against the shipped behaviour and the branch merged.`

---

## 4. Deliverables

| Deliverable | Description | Location |
| --- | --- | --- |
| Collapsed verb bar | Disclosure around the direction verbs, closed by default | `web/frontend/components/feature/DirectionRow.tsx` |
| Direction labelling | `Direction:` in narrator mode, `You:` under POV only | `web/backend/app/agents/character_turn_agent.py`, `agents/narrator_agent.py` |
| POV-aware contracts | Character + narrator prompts split on `player_embodied` | `web/backend/app/agents/prompt_registry.py` |
| `player_embodied` | One flag both renderers and both prompts read | `web/backend/app/services/assembler.py` |
| Reader-address guard | Second-person detector on the opening window | `web/backend/app/services/emission.py`, `services/beat_stream.py` |
| Cross-speaker guard | Another character's quoted line, caught and re-rolled | `web/backend/app/services/emission.py`, `services/beat_stream.py` |
| Adaptive pacing | `maxTurns` / `beatLength` removed; per-beat `weight` from the planner | `web/backend/app/agents/planner_agent.py`, `services/turn_settings.py`, `services/turn_engine.py` |
| Column drop migration | Non-additive schema change | `web/backend/alembic/versions/` |
| Plan mode control | Auto / Plan in the composer; Write it as an icon | `web/frontend/components/feature/PlanModeButton.tsx`, `feature/Composer.tsx` |
| Plan frame | Transport frame + its hand-mirrored TS type | `web/backend/app/events/stream.py`, `web/frontend/lib/events.ts` |
| Approval loop | Plan streams, turn waits, `approvedPlan` executes it | `web/backend/app/services/turn_engine.py`, `web/frontend/components/feature/PlanApproval.tsx` |
| Scene script agent | One call renders an approved plan with `<speaker:N>` | `web/backend/app/agents/scene_script_agent.py` |
| Multi-speaker parsing | A speaker change opens a new segment; same-speaker repeats still collapse | `web/backend/app/services/emission.py` |
| Backend tests | Labelling · prompts · guards · settings · plan mode · multi-speaker parsing | `utils/tests/backend/{agents,services,api}/` |
| Frontend tests | Disclosure · plan-mode control · plan approval · stream frame | co-located `*.test.tsx` / `*.test.ts` |
| EXP-2026-08-015 | Narrator-mode point of view, before and after | `docs/research/experiments/EXP-2026-08-015-pov-narrator-mode/` |
| EXP-2026-08-016 | Continuous script vs. per-speaker calls | `docs/research/experiments/EXP-2026-08-016-continuous-scene-script/` |
| Research runners | Derived from `run_prose_end_to_end.py`, not rewritten | `utils/scripts/research/run_pov_mode.py`, `run_scene_script.py` |
| Docs | Every file that described the removed behaviour | `docs/`, `CLAUDE.md`, `.env.example` |
