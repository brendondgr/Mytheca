# Playwright Mode, Adaptive Pacing, and Continuous Prose

**Status: phases 1–9 shipped and merged; 10–11 outstanding.** Written 2026-08-24, revised the
same day against the owner's decisions, and updated here against what actually landed.

| Phase | State |
| --- | --- |
| 1 Playwright rename | **Done.** |
| 2 Verb bar collapsed | **Done.** |
| 3 Playwright POV fix | **Done** — measured 9/10 beats addressing the reader → 0, and holding at 1 problem in a later 24-beat run. |
| 4 Cross-speaker guard | **Done** — whole-passage, cuts rather than discards. |
| 5 EXP-2026-08-015 | **Not done.** The before/after came from `utils/scripts/scene_smoke.py` (n=1, no arms, recorded nowhere), which is a smoke test and explicitly not a measurement. The experiment folder, the voice-distinctness baseline and the recorded claim do not exist. |
| 6 Adaptive pacing | **Done**, plus a fix the plan did not anticipate: removing `maxTurns` revealed the planner almost never chose to end (4 beats on one run, **24** on another). It is now told what the turn has spent. Measured after: 7 beats, 0 problems. |
| 7 Plan mode in the composer | **Done.** |
| 8 Plan approval loop | **Done** — never exercised against a live model. |
| 9 Continuous scene script | **Done, defaulting OFF** (`sceneFlow: "voiced"`). Never run against a live model. |
| 10 EXP-2026-08-016 | **Not done**, and phase 9's default cannot honestly be flipped until it is. |
| 11 Docs + merge | Docs done in each phase's own commit; the branch is merged. |

Everything still open is in `docs/checklist.md`, which is the file to read rather than this
one — a plan describes an intention and the checklist describes the state.

---

## 1. Introduction

Four complaints from the owner, which look like four features and are really one naming
error, two defects, and two rebuilds:

1. **The direction verb bar is in the way** — *Push it forward · Slow down · Skip ahead · Cut
   to later* and their eleven siblings, above the composer in every scene.
2. **Point of view is wrong when the player is not in the scene.** The cast addresses the
   player as *"you"* when the player has no body; the narrator does not reliably stay in the
   third person; and one character's beat contains another character's speech.
3. **Planning mode is in the wrong place and asks the wrong questions.** It belongs in the
   composer with an **Auto** / **Plan** split, and the two Pacing settings (*beats per
   message*, *how much a character says at once*) should be replaced by the model adapting to
   the moment.
4. **Prose should be produced continuously from a plan**, so the scene flows and attribution
   stops being guesswork.

Underneath all of it is a word doing two jobs. **"Narrator"** currently names both the AI that
speaks third-person prose inside the scene *and* the player's own non-POV mode. Those are
opposite things — one is in the fiction, the other is outside it giving instructions — and
the confusion is not merely cosmetic: it is the reason the player's line is labelled `You:`
in the transcript, which is the literal cause of complaint 2. So the rename comes first, and
everything after it is written in the corrected vocabulary.

### Decisions taken (owner, 2026-08-24)

- **The player's non-POV mode is the Playwright.** It writes what happens in the scene and
  never appears in it. **"Narrator" from here on means only the AI narrator that speaks in the
  scene** — `narrator_agent`, the `narration` event, `NarratorCard`, `role="narrator"` all
  keep their names and are untouched by the rename.
- **The narrator's job is to say what the named characters are doing.** *"Lily jumps up and
  down while singing"* must come back as Lily doing it — either routed to Lily's own beat or
  narrated in the third person **naming her**. Never as "you".
- **Continuous prose becomes the default, not an experiment.** The turn stops re-planning
  between speaker changes and stops running a separate voiced call per character. The old
  per-speaker path survives as a **toggle**, because it changes how the scene is presented.
- **Max turns, beat length and the four scene presets are removed.** The owner's judgement:
  the current system is counter-intuitive and works against the app in the long run.

### The one thing this plan is genuinely betting on

The owner's reason for wanting per-character voicing skipped is that *"the characters aren't
even abiding by their ideological background, even with all of this being put into place."*
If that is true, the per-speaker architecture is paying full price — N model calls, N prompts,
N re-plans — for a property it is not delivering, and continuous prose is free. If it is
false, continuous prose costs voice distinctness.

The codebase has a hint that the owner is right: `beat_stream.echoes_a_beat` exists **because**
two characters returned byte-identical passages, and its docstring records the cause as
"two separate calls whose prompts differ only by a name and a role". That is one anecdote, not
a measurement. **Phase 5 measures it on the current system before anything replaces it** — so
the switch to continuous is made on a number, not on either party's impression.

### Root causes, located

| Complaint | Cause |
| --- | --- |
| **2A** — the cast says "you" when the player is not in the scene | The player's line is stored as `role="player"` ([turn_setup.py:184](../../web/backend/app/services/turn_setup.py)) and both transcript renderers print it as **`You:`** ([character_turn_agent.py:716](../../web/backend/app/agents/character_turn_agent.py), [narrator_agent.py:176](../../web/backend/app/agents/narrator_agent.py)). The output contract then says, verbatim: *"The line labelled 'You:' is the person you are talking to — someone standing in the room with you … Write them in the second person."* Under POV the player's line is stored as their character's own beat instead — so **`You:` appears only in Playwright mode**, precisely where the player has no body. The cast is obeying instructions. |
| **2B** — the narrator drifts out of third person | `_NARRATOR_SYSTEM` and `_NARRATOR_SYSTEM_LONG` both end with *"Narrate them in the second person — 'you', 'your'."* Same label, same cause. |
| **2C** — characters speak during another's beat | Nothing checks it. `emission.py` guards degeneration, repetition, scratchpad leakage, mid-sentence openings and the phrase "the player" — and **not** another cast member's name in front of a line of dialogue. The contract's *"Only your character"* rule has no enforcement behind it. |

`You:` is not an accident and must not simply be reverted:
[`EXP-2026-08-009`](../research/experiments/EXP-2026-08-009-prose-second-person/RESULTS.md)
measured it taking "the player" out of the prose from **72 % of character beats to 0 %**.
Phase 3 replaces it with a **non-person** label rather than going back to `Player:`.

---

## 2. Gaps & Unanswered Questions

### Settled

- **Mode name: Playwright.** Chosen over *Director* — which is not free (`director_agent`,
  `DirectorRail`, and the "Director" tab in Options → Prompts are all live) and would have
  moved the overload rather than removed it, at a cost of ~99 files.
- **Verb bar: collapse, don't delete.** The owner offered collapsing as acceptable and it is
  strictly better — the fifteen verbs, their availability gating and the scenario-authored
  verbs (`lib/sceneVerbs.ts`) are working, tested code, and an author can add their own. It
  collapses closed by default and remembers its state.
- **Adaptive means "the model chooses, the engine keeps a backstop."** `max_turns` goes as a
  *control*; `turn_max_beats` ([turn_engine.py:269](../../web/backend/app/services/turn_engine.py)) stays
  as the runaway guard, is not player-facing, and is not raised. Same for length: the
  paragraph directive stops being a player setting; the token ceiling stays. Removing the only
  ceiling would be reckless against the recorded incident where one 48,000-token generation ran
  684 s, timed out the relay's health probe, and cost the player the rest of the scene.
- **Presets are removed with the settings they wrapped.** All four are defined purely in terms
  of `maxTurns` + `beatLength`; with those gone there is nothing left to name.

### Still open

- **Does Playwright mode allow the player to act at all?** Today's composer placeholder is
  *"Speak, or describe what you do…"*, which invites *"I lean across the table"* — and under
  the new rule the cast has nobody to lean at. Phase 3 changes that copy to instruction-only,
  matching the owner's *"we're just informing or instructing what the scene does"*. If a mode
  where the player acts **without** picking a POV character is wanted, that is a third mode and
  a separate plan. **Assumed instruction-only; say so if that is wrong.**
- **How much of the presentation changes in continuous mode?** Phase 9 renders a whole turn as
  one flowing script. Discrete per-beat cards are the right rendering for discrete beats and
  probably the wrong one for a continuous script — but "probably" is not a spec, and the owner
  has locked visual references (`docs/CharacterFrontpage/`). Phase 9 ships continuous prose
  inside the **existing** beat cards (correct, conservative, no visual regression) and records
  a tighter continuous rendering as follow-up work in `docs/checklist.md`. **Human intervention
  is needed** to decide how far that rendering should go.

---

## 3. Step-by-Step Instructions

### Phase 1 — One word, one meaning: Playwright

Mechanical and first, so that nothing built afterwards is written in the ambiguous vocabulary.

- **Locations:**
  - `web/frontend/components/feature/PovSelect.tsx` — the `null` row's label and
    `NarratorAvatar` → `PlaywrightAvatar`; the trigger's fallback text.
  - `web/frontend/components/feature/Composer.tsx` — `pov === null` comments, the mode
    placeholder, the `hasDirection`/`showGuidance` prose.
  - `web/frontend/components/feature/DirectionRow.tsx` — the `mode: "narrator" | "pov"` union
    becomes `"playwright" | "pov"`, and the strip's copy.
  - `web/frontend/features/story-player/useScenePlay.ts`, `StoryPlayerView.tsx` — comments and
    any user-visible string.
  - `web/backend/app/services/turn_setup.py`, `turn_engine.py`, `beat_runner.py`,
    `agents/character_turn_agent.py`, `agents/narrator_agent.py` — docstrings and **trace
    strings** that say "Narrator Mode" meaning the player.
- **Explicitly NOT renamed** — these are the AI narrator and stay exactly as they are:
  `narrator_agent.py`, `prompt_registry.NARRATOR_SYSTEM(_LONG)`, the `narration` event type,
  `role="narrator"`, `NarratorCard`, `TranscriptAnnouncer`'s `"Narrator."`, `BeginSceneModal`'s
  "Narrator" (it previews the AI's opening line), and the Options → Prompts "Narrator" tab.
- **Rationale:** the whole point is that "Narrator" survives with **one** meaning. A rename
  that also touched the agent would defeat itself.
- **Guard against the obvious mistake:** after the rename, `grep -rn "Narrator" web/frontend
  web/backend/app` should return only AI-narrator hits. Add that as a note in the commit body,
  not as a test.
- **Tests:** update `PovSelect.test.tsx`, `Composer.test.tsx`, `DirectionRow.test.tsx` and any
  backend test asserting on a trace string.
- **Action:** `uv run pytest`, `npm test`, `npm run typecheck && npm run lint`. Once green,
  commit: `[Playwright & Continuous Prose] (1/11) Complete: The player's non-POV mode is the Playwright; "Narrator" now means only the AI narrator.`

---

### Phase 2 — Get the direction verbs out of the way

- **Locations:** `web/frontend/components/feature/DirectionRow.tsx` (renders the bar through
  its `children` slot), `web/frontend/components/feature/Composer.tsx`, a small
  `localStorage`-backed hook beside `hooks/use-shortcuts-enabled.ts`, and the co-located
  `DirectionRow.test.tsx` / `SceneVerbBar.test.tsx`.
- **What changes:** `DirectionRow` gains a disclosure — one `aria-expanded` button reading
  `Verbs` — wrapping the `children` slot. **Closed by default**, state remembered per browser.
  `SceneVerbBar`, `lib/sceneVerbs.ts`, the gating rules and the "Someone arrives" cast submenu
  are untouched.
- **Rationale:** the owner's "quick first fix", and genuinely independent of everything below —
  it must not be blocked behind the prompt work.
- **Accessibility:** a real `<button>` with `aria-expanded` + `aria-controls`; the toolbar
  keeps its roving tabindex; when closed its buttons are **unmounted**, not merely hidden, so
  they leave the tab order.
- **Action:** `npm test` for `DirectionRow`, `SceneVerbBar`, `Composer`; `npm run typecheck &&
  npm run lint`; a11y + responsive at 320/375/768/1024. Commit:
  `[Playwright & Continuous Prose] (2/11) Complete: The direction verbs collapse behind a disclosure, closed by default.`

---

### Phase 3 — The Playwright is not in the room

The correctness fix for 2A and 2B. A **label** change, then a **prompt** change, in that order
— `EXP-2026-08-009` is the evidence that the label does the work and the rule alone does not.

- **Locations:**
  - `web/backend/app/agents/character_turn_agent.py` → `_transcript` (`role == "player"`), and
    the tail line `"The player addressed you directly."`
  - `web/backend/app/agents/narrator_agent.py` → `_recent` (same branch).
  - `web/backend/app/agents/prompt_registry.py` → `_CHARACTER_OUTPUT_CONTRACT`,
    `_NARRATOR_SYSTEM`, `_NARRATOR_SYSTEM_LONG`.
  - `web/backend/app/services/assembler.py` → `TurnContext` gains `player_embodied: bool`
    (true under POV, false under Playwright), so both renderers and all three prompts read one
    flag rather than each re-deriving it.
  - `web/frontend/components/feature/Composer.tsx` → the Playwright placeholder.
  - **`web/backend/app/agents/ghostwriter_agent.py` → `_recent`.** Found during Phase 1: it
    still labels a player beat **`The player:`** — the exact string `EXP-2026-08-008` measured
    leaking into 72 % of character beats, and which every other transcript renderer was fixed
    to stop emitting. It was missed because the ghostwriter is not on the turn path, so no
    prose experiment ever scored it. Same treatment as the others: `Direction:` under
    Playwright, `You:` under POV.
- **What changes:**
  - Under **Playwright**, a `player` beat renders as `Direction: …` — visibly not a speaker.
    `You:` is kept for **POV** only, where the player really is in the room. Neither mode ever
    renders `Player:`, so `EXP-2026-08-009`'s result is preserved.
  - The character contract's `You:` clause becomes conditional on `player_embodied`. Under
    Playwright it is replaced by: *the `Direction:` line is an instruction from outside the
    story, addressed to nobody — never answer it, never quote it, and never write a second
    person into the scene; everyone present is named.*
  - Both narrator prompts drop *"Narrate them in the second person"* under Playwright and gain
    an explicit third-person-only rule — no `I`, `me`, `my`, `we`, `you`, `your`; characters
    are named.
  - **The narrator's job is stated positively**, per the owner: narrate what the **named**
    characters are doing. A direction naming a character is delivered either as that
    character's own beat or as third-person narration **naming them** — never as an
    instruction echoed back, and never in the second person. `direction_agent` already binds a
    requirement to an `actor_id`; this makes the prose contract agree with it.
  - The composer placeholder under Playwright becomes instruction-only (see §2).
- **New guard:** `emission.addresses_the_reader(text, *, window)` — a second-person-pronoun
  detector — wired into `beat_stream._pass` exactly as `names_the_player` is: **only when the
  player is not embodied**, only on the opening window, discarding-and-regenerating rather
  than rewriting. It is a backstop and a **metric**, not the mechanism.
- **Tests:** `utils/tests/backend/agents/test_transcript_labelling.py` (a `player` beat renders
  `Direction:` under Playwright and `You:` under POV — one per renderer);
  `utils/tests/backend/agents/test_prompt_pov.py` (the contract carries the embodied clause
  under POV and the direction clause without it); extend
  `utils/tests/backend/services/test_emission_guards.py`.
- **Action:** `uv run pytest utils/tests/backend/agents utils/tests/backend/services` + the
  frontend `Composer` tests. Commit: `[Playwright & Continuous Prose] (3/11) Complete: Under Playwright the player's line is direction, not a person, and the narrator is third-person only.`

---

### Phase 4 — One character's beat holds one character's speech

- **Locations:** `web/backend/app/services/emission.py` (new
  `cross_speaker_speech(text, *, speaker_name, other_names, window)`),
  `web/backend/app/services/beat_stream.py` (`_pass`, beside `echoes_a_beat`),
  `web/backend/app/agents/prompt_registry.py` (`_CHARACTER_OUTPUT_CONTRACT`).
- **What changes:** a detector for the shape actually observed — another present cast member's
  name followed by a speech verb and a quotation, or a quoted line on a paragraph opening with
  another cast member's name attached. It joins the discard-and-regenerate path the scratchpad
  gate already uses, judged on the opening window only. The contract's *"Only your character"*
  rule gains its consequence in words: another character may be **looked at, answered or
  described**, but never quoted.
- **Deliberately narrow.** *Reported* speech (*"He told me the gate was shut"*) is ordinary
  prose and must survive; only attributed live dialogue is caught. The false-negative direction
  is the safe one — a missed leak costs a raised eyebrow, a false positive silently strips good
  writing and costs a regeneration.
- **Rationale:** the owner's example — Zoe speaking during Lily's beat — has no detector behind
  it today, and a prompt rule alone has already failed on this codebase for the analogous case.
- **Carries forward:** this detector is reused in Phase 9 **per speaker segment**, where it
  becomes the primary attribution check for continuous prose. Build it to take an explicit
  speaker rather than reading one off the context.
- **Tests:** `utils/tests/backend/services/test_emission_guards.py` — leaked dialogue caught;
  reported speech, a character quoting *themself*, and a character's name in ordinary narration
  all survive.
- **Action:** `uv run pytest utils/tests/backend/services utils/tests/backend/agents`. Commit:
  `[Playwright & Continuous Prose] (4/11) Complete: A beat carrying another character's spoken line is caught and re-rolled.`

---

### Phase 5 — Measure both claims before rebuilding on them (EXP-2026-08-015)

The owner asked for tests rather than an assumption that it looks right, and named the
priority: *confirming that points of view are not being incorrectly quantified*. Per the
research contract this is an experiment folder, not a number in chat. It answers **two**
questions, because Phase 9's design depends on the second.

- **Locations:** `make new-experiment SLUG=pov-and-voice-baseline` →
  `docs/research/experiments/EXP-2026-08-015-pov-and-voice-baseline/`; runner
  `utils/scripts/research/run_pov_mode.py`, **derived from** `run_prose_end_to_end.py` — it
  already builds a throwaway world, drives `POST /api/play/{id}/turn`, reads back every beat
  and counts discards from the trace. Do not write a second harness.
- **Question 1 — did the POV fix work?** Two arms, `pre` (Phase 2's commit) and `post`
  (Phase 4's commit):
  - `addresses_the_reader` — a second-person pronoun in a beat produced under Playwright.
    **Primary.**
  - `narrator_first_person` — `I`/`me`/`my`/`we` in a narration beat. **Primary.**
  - `cross_speaker_speech` — Phase 4's detector, used here as the measurement.
  - `narrates_the_named_actor` — when a direction names a character, does the turn's prose
    actually name them? This is the owner's Lily-jumping-and-singing case, scored.
  - Form metrics that must **not** regress: `has_speech`, `is_distinct`, `paragraph_breaks`,
    `sentences_per_100_words`, `names_the_player`.
- **Question 2 — are the voices distinct today, on the per-speaker path?** Measured on the
  `post` arm, which is the shipped system:
  - A per-character lexical-profile distance: each character's beats against every other
    character's, within one session.
  - The `echoes_a_beat` fire rate and `is_distinct`.
  - **This is the baseline Phase 10 compares against**, and it is what decides whether the
    per-speaker architecture is earning its N calls. State the expectation before running:
    the owner predicts the voices are already indistinct.
- **Discards per turn are reported on every arm.** A run that scores well only because the gate
  threw beats away is not a run that scores well — the threat `EXP-2026-08-009` § Threats
  already named, where the guard and the metric share an implementation.
- **Design:** both arms on the **same** deployed model, **interleaved in one session**.
  Day-apart comparisons on this endpoint are worthless — a 66× latency swing once read as
  endpoint instability and was a disconnected GPU. Six player turns per arm, Playwright mode,
  a cast of at least three so cross-speaker leakage and voice comparison both have somewhere to
  happen.
- **Recording:** `manifest.yaml` + `RESULTS.md` + generated figures; register the claims in
  `docs/research/CLAIMS.md`. Never hand-edit a figure, never hardcode a number in a plotting
  script. If an arm fails, record it and report per-run rows — **do not aggregate over the
  survivors** (`EXP-2026-08-001` is the worked example of getting this wrong).
- **Action:** `make validate-research`, then `uv run pytest`. Commit:
  `[Playwright & Continuous Prose] (5/11) Complete: EXP-2026-08-015 measures the Playwright POV fix and baselines voice distinctness on the per-speaker path.`

---

### Phase 6 — Adaptive generation replaces max turns, beat length and the presets

- **Locations:**
  - `web/backend/app/schemas/base.py` (`BeatLength`, `BEAT_LENGTHS`, `DEFAULT_BEAT_LENGTH`),
    `schemas/play.py` (`TurnOverrides.max_turns`, `.beat_length`), `schemas/scenario.py`,
    `schemas/settings.py` (`ScenePresetValues`, `ScenePresetRead`).
  - `web/backend/app/services/turn_settings.py` (the fields and their clamps),
    `services/turn_engine.py` (`remaining = max_turns - scene_beats` and the "Reached the
    scene's turn limit" trace), `services/direction_runtime.py` (`pace`, which divides
    requirements by remaining beats).
  - `web/backend/app/agents/character_turn_agent.py` (`_BEAT_LENGTH_DIRECTIVES`,
    `_BEAT_LENGTH_SHAPE`, `prose_tokens_for`, `_PROSE_TOKENS_BY_LENGTH`),
    `agents/planner_agent.py` (`remaining_beats` in `_plan_prompt`).
  - `web/backend/app/content/scene_presets.py` and `routes/options.py` (`GET /scene-presets`).
  - `web/frontend/components/feature/SceneConfigMenu.tsx`,
    `features/story-player/useScenePlay.ts`, `lib/types.ts`, `lib/api.ts`.
  - A migration under `web/backend/alembic/versions/` — dropping columns is not additive.
- **What changes:**
  - **`maxTurns` and `beatLength` are removed** from the config popover, from `TurnOverrides`,
    from the pin set (`SceneControlKey`), and from the scenario row.
  - **The four scene presets go with them.** `BUILTIN_SCENE_PRESETS` is emptied and the
    `scene_preset` column deprecated; `GET /api/options/scene-presets` returns `[]`, which the
    composer already treats as "hide the picker" — so the UI needs no special case. The
    deprecation is recorded in `docs/checklist.md`, not silently dropped.
  - `turn_max_beats` stays as the runaway backstop and becomes the only bound on beats per
    turn. `_PROSE_TOKENS_BY_LENGTH` collapses to the single `long` allowance (2048) as the only
    bound on one passage.
  - **The planner gains the pacing decision** it was always best placed to make: each beat
    returns a `weight` (`brief` | `full` | `extended`) beside `register` and `stakes`, and the
    length directive is built per beat from that instead of from a scene-wide tier. The
    **paragraph-count phrasing is kept verbatim** — `EXP-2026-08-007` measured a *word* target
    moving the average the wrong way, and `EXP-2026-08-010` is the beat-length experiment this
    must not silently undo.
  - The planner prompt is told it is pacing the turn itself: plan as many beats as the moment
    needs and stop when it is done, rather than filling a budget.
- **Rationale:** both settings fed the planning phase, which is where the owner wants the
  adaptation to live. Deleting them without moving the decision would leave the engine with no
  pacing signal at all.
- **Risk, stated:** the scene cap is today the only thing bounding a turn's wall clock.
  `turn_max_beats` was chosen as a *runaway guard*, not as a pacing number — expect to re-tune
  it, and record the tuning rather than quietly editing the default.
- **Tests:** `utils/tests/backend/services/test_turn_settings.py` (the removed fields no longer
  resolve; an **old override envelope carrying them is accepted and ignored**, never a 422 —
  a saved client must not start failing); `utils/tests/backend/agents/test_planner_weight.py`
  (`weight` parses, an unknown value degrades to `None`, `None` yields today's medium
  directive); `utils/tests/backend/api/test_scenario_settings.py`. Frontend:
  `SceneConfigMenu.test.tsx` and `useScenePlay.test.ts` lose the two controls and the picker.
- **Action:** `uv run pytest`, `npm test`, `npm run typecheck && npm run lint`, an a11y pass on
  the shortened popover, and `alembic upgrade head` against a scratch DB. Commit:
  `[Playwright & Continuous Prose] (6/11) Complete: Beats per message, beat length and the scene presets are gone; the planner paces each beat itself.`

> **Dev-database note:** this drops columns. Per `mytheca-dev-db-column-drift`, the dev
> Postgres is reconciled **additively** at backend startup and will not drop them for you —
> run the migration, or the reloaded server keeps a column the model no longer knows about.

---

### Phase 7 — Planning mode moves into the composer

Pure UI, reviewable on its own.

- **Locations:** `web/frontend/components/feature/Composer.tsx` (the controls bar), new
  `web/frontend/components/feature/PlanModeButton.tsx` + co-located test,
  `components/feature/GhostwriteButton.tsx`, `components/feature/SceneConfigMenu.tsx` (the
  "Turn planning" row leaves), `features/story-player/useScenePlay.ts`.
- **What changes:** the controls bar becomes
  `[Config] [Playwright/POV select] [Plan mode] … [Context dial] [✎ icon] [Send]`.
  - **Plan mode** sits between the POV select and where *Write it* was. Collapsed it shows the
    active mode; activated it expands to **Auto** (approve automatically and move on) and
    **Plan** (stop for approval). `plannerMode: "planner" | "off"` widens to
    `"auto" | "plan" | "off"`; `"off"` stays in the Config popover, because turning planning
    off changes what the app *is* and does not belong on a two-way toggle.
  - **Write it** loses its label and becomes icon-only between the context dial and Send. It
    keeps its accessible name, `title`, disabled rule and Undo state — only the visual changes.
    An icon-only control **must** carry `aria-label`; that is the most likely thing to be
    dropped in this phase.
- **Rationale:** doing the UI before the approval loop means the loop lands against a control
  that already exists and is already tested, and the owner sees the layout early.
- **Tests:** `PlanModeButton.test.tsx` (expands, both options selectable, keyboard operable,
  `aria-expanded` correct); `Composer.test.tsx` (control order; the ghostwrite button keeps its
  accessible name with no visible text).
- **Action:** `npm test`, `npm run typecheck && npm run lint`, a11y + responsive at
  320/375/768/1024 — the controls bar is the row most at risk of overflowing at 320 px. Commit:
  `[Playwright & Continuous Prose] (7/11) Complete: Plan mode is a composer control with Auto and Plan; Write it is an icon between Context and Send.`

---

### Phase 8 — Plan mode: show the plan, wait for approval

- **Locations:** `web/backend/app/events/stream.py` (a `TurnPlanFrame` **transport** frame — a
  plan is not a story event and must not be persisted as one),
  `web/backend/app/services/turn_engine.py` (emit the plan; stop when the mode is `plan`),
  `web/backend/app/schemas/play.py` (`TurnRequest.approvedPlan`),
  `web/backend/app/agents/planner_agent.py` (the plan already carries `actor_id`, `action`,
  `reason`, `register`, `stakes`, plus `weight` from Phase 6),
  `web/frontend/lib/events.ts` (the hand-mirrored contract),
  `features/story-player/turn-stream.ts`, new
  `web/frontend/components/feature/PlanApproval.tsx`.
- **What changes:** under **Plan**, the turn runs `plan_beats` at full lookahead, emits the plan
  as one frame, and returns without producing prose. The player sees *who acts, what they do,
  how it is pitched* and either approves (a second `POST` carrying `approvedPlan`, executed
  without re-planning) or edits their direction and sends again. Under **Auto** nothing changes
  except that the frame is still emitted, for the Inspector.
- **Rationale:** this is what makes a deep plan worth generating — the owner wants to see what
  each character is going to do, say, and how they say it, before the prose commits to it. It
  is also the input Phase 9 renders.
- **Contract duty:** `docs/api-contract.md` and `docs/data-flow.md` are updated **in this
  commit**. The envelope's TypeScript mirror in `web/frontend/lib/events.ts` is hand-maintained;
  changing one side without the other is the documented way to break this app.
- **Tests:** `utils/tests/backend/api/test_turn_plan_mode.py` (plan mode emits a plan frame and
  no prose events; an approved plan executes **without a second planner call** — assert on call
  count, never on wall clock); `turn-stream.test.ts` for the new frame; `PlanApproval.test.tsx`.
- **Accessibility:** the approval panel arrives mid-stream, so it is a live region, and its
  approve/edit controls must be reachable without leaving the composer.
- **Action:** `uv run pytest utils/tests/backend/api utils/tests/backend/services`, `npm test`,
  a11y pass. Commit: `[Playwright & Continuous Prose] (8/11) Complete: Plan mode streams the plan and waits for approval before any prose is written.`

---

### Phase 9 — Continuous prose, default on, with the voiced path as a toggle

The rebuild. It reverses a deliberate decision — `character_turn_agent`'s docstring says *"One
LLM call per active speaker (per-character isolation — no shared multi-POV prompt, so voices
stay distinct)"* — on the owner's judgement that the isolation is not delivering, with Phase 5
as the measurement.

- **The toggle.** One scene control, `sceneFlow`:
  - **`continuous`** (**default**) — the approved plan is rendered in **one** generation. No
    re-plan between speaker changes, and no separate voiced call per character.
  - **`voiced`** — today's path: one call per speaker, carrying that character's voice samples,
    register and relationship note.
  It lives beside "Turn planning" in the Config popover, and its help text states the trade in
  words, the way `plannerMode`'s does: continuous flows and attributes cleanly; voiced spends N
  calls to keep the voices apart.
- **Locations:**
  - New `web/backend/app/agents/scene_script_agent.py` — renders an approved plan as continuous
    prose with `<speaker:N>` on its own line at every change of speaker, `<speaker:0>` for the
    narrator. It reuses the roster numbering `planner_agent` already builds, so there is no
    second mapping to drift.
  - `web/backend/app/services/emission.py` — `EmissionAccumulator` learns that a `<speaker:N>`
    naming a **different** speaker closes the open prose segment and opens a new one. The
    `_prose_seen` guard is **not deleted**: it is re-keyed to *"no second passage for the same
    speaker"*, which keeps the five-identical-beats defect it was written for while making a
    genuine hand-off representable.
  - `web/backend/app/services/beat_stream.py` — the guards (scratchpad, echo, Phase 4's
    cross-speaker check, Phase 3's reader-address check) run **per speaker segment** rather than
    once per generation; the runaway ceiling becomes per-script with a per-segment ceiling
    under it.
  - `web/backend/app/services/beat_runner.py`, `turn_engine.py` — the `scene_script` route
    beside the per-speaker route, chosen by `sceneFlow`.
  - `schemas/play.py`, `schemas/scenario.py`, a migration, `lib/types.ts`,
    `SceneConfigMenu.tsx`, `useScenePlay.ts`.
- **What the frontend needs for speaker switching: nothing new.** Each speaker segment already
  opens its own event with its own `characterId` through `emitter.open_stream`, and
  `TranscriptBeat` already keys the portrait and colour off it. The "tokenized signal that the
  speaker changed" is delivered as the **existing event boundary** — the cheapest correct
  answer, and why this phase is backend-only apart from the toggle.
- **Presentation:** continuous prose ships inside the existing beat cards. A tighter continuous
  rendering is recorded in `docs/checklist.md` as follow-up (see §2) rather than guessed at
  against the owner's locked visual references.
- **Fallback, and it is load-bearing:** a script whose speaker tokens are missing or
  unparseable falls back to the per-speaker path **for that turn**, rather than emitting one
  giant mis-attributed beat. The owner asked for this to be foolproof on less intelligent
  models; a model too weak to emit the tokens must degrade to today's behaviour, never to
  something worse.
- **Tests:** `utils/tests/backend/services/test_emission_multi_speaker.py` — a two-speaker
  script yields two segments with the right ids **in any chunking**, and `push()` + `finish()`
  agree with `parse_emission`; a repeated passage by the *same* speaker still collapses to one;
  a token naming a number not on the roster falls back to the intended speaker.
  `test_scene_script_fallback.py` for the degrade path.
  `utils/tests/backend/services/test_scene_flow_toggle.py` — `voiced` reproduces today's call
  pattern exactly.
- **Action:** `uv run pytest`, `npm test`, `alembic upgrade head`. Commit:
  `[Playwright & Continuous Prose] (9/11) Complete: A plan renders as one continuous multi-speaker script by default, with the voiced per-speaker path as a toggle.`

---

### Phase 10 — Did continuous prose cost anything? (EXP-2026-08-016)

Phase 9 ships continuous **on the owner's decision**, not on a measurement. This phase supplies
the measurement, so the decision is either confirmed or revisited on evidence.

- **Locations:** `make new-experiment SLUG=continuous-scene-script` →
  `docs/research/experiments/EXP-2026-08-016-continuous-scene-script/`; runner
  `utils/scripts/research/run_scene_script.py`, again derived from `run_prose_end_to_end.py`.
- **Arms:** `continuous` and `voiced`, **interleaved in one session on the same model**, same
  world, same player lines, same cast of three or more.
- **Metrics:**
  - **Attribution — primary.** Beats attributed to the wrong speaker, plus
    `cross_speaker_speech`. This is the owner's "fewer parsing issues" claim and the one this
    design should win on.
  - **Voice distinctness — primary**, against **Phase 5's baseline**, which is what makes this
    interpretable: if the voiced path was already indistinct, continuous costs nothing and the
    owner's judgement is confirmed. If voiced was distinct and continuous is not, that is a real
    trade and it goes back to the owner.
  - Turn wall clock and completion tokens — one call against N.
  - Fallback rate: how often the speaker tokens failed and the turn degraded.
  - The form metrics that must not regress.
- **Decision rule, written before the run:** continuous **stays** the default unless voice
  distinctness degrades against the Phase 5 baseline *and* attribution did not improve. Either
  half failing is reported to the owner as a trade, not as a recommendation.
- **Honesty rules:** record failed runs; never aggregate over the survivors of a partly-failed
  experiment; n per arm is small, so an existence proof is reported as an existence proof and
  never as a rate.
- **Action:** `make validate-research`, then `uv run pytest`. Commit:
  `[Playwright & Continuous Prose] (10/11) Complete: EXP-2026-08-016 measures continuous prose against the voiced path and the Phase 5 baseline.`

---

### Phase 11 — Reconcile the docs, then merge

- **Locations:** `CLAUDE.md` (the "Facts that override stale assumptions" list — and add
  `SceneVerbBar` / `lib/sceneVerbs.ts`, already missing from the component tables),
  `docs/documentation.md`, `docs/architecture.md`, `docs/component-map.md`,
  `docs/api-contract.md`, `docs/data-flow.md`, `docs/design-system.md` (the composer controls
  bar), `docs/deployment.md` + `.env.example` (any new var), `docs/checklist.md` (the open
  questions from §2, the preset deprecation, the continuous rendering follow-up, and the
  `turn_max_beats` re-tune), `docs/research/INDEX.md` + `CLAIMS.md`.
- **The terminology sweep lands here too:** every doc that says "Narrator mode" meaning the
  player says **Playwright**. `grep -rn "Narrator" docs/` should afterwards return only AI
  narrator hits.
- **Rule:** delete the sentences that described what was removed. Do not leave the old
  `maxTurns` / `beatLength` / preset prose beside its replacement — that accumulation is
  exactly why the docs were rebuilt on 2026-08-04.
- **Merge:** merge the branch into `main`, resolve conflicts, remove the worktree. No push, no
  PR, unless asked.
- **Action:** full gate — `uv run pytest`, `npm test`, `npm run typecheck && npm run lint`,
  `uv run python utils/scripts/check_contrast.py`, `node utils/scripts/check_frontend_css.mjs`,
  `make validate-research`. Commit: `[Playwright & Continuous Prose] (11/11) Complete: Docs reconciled against the shipped behaviour and the branch merged.`

---

## 4. Deliverables

| Deliverable | Description | Location |
| --- | --- | --- |
| Playwright rename | The player's non-POV mode; "Narrator" left to the AI alone | `web/frontend/components/feature/PovSelect.tsx`, `feature/DirectionRow.tsx`, `feature/Composer.tsx` |
| Collapsed verb bar | Disclosure around the direction verbs, closed by default | `web/frontend/components/feature/DirectionRow.tsx` |
| Direction labelling | `Direction:` under Playwright, `You:` under POV only | `web/backend/app/agents/character_turn_agent.py`, `agents/narrator_agent.py` |
| POV-aware contracts | Character + narrator prompts split on `player_embodied`; narrator names who acts | `web/backend/app/agents/prompt_registry.py` |
| `player_embodied` | One flag both renderers and all three prompts read | `web/backend/app/services/assembler.py` |
| Reader-address guard | Second-person detector on the opening window | `web/backend/app/services/emission.py`, `services/beat_stream.py` |
| Cross-speaker guard | Another character's quoted line, caught and re-rolled; reused per segment in Phase 9 | `web/backend/app/services/emission.py`, `services/beat_stream.py` |
| Adaptive pacing | `maxTurns` / `beatLength` / presets removed; per-beat `weight` from the planner | `web/backend/app/agents/planner_agent.py`, `services/turn_settings.py`, `services/turn_engine.py`, `content/scene_presets.py` |
| Migrations | Column drops for the removed settings and the new `sceneFlow` | `web/backend/alembic/versions/` |
| Plan mode control | Auto / Plan in the composer; Write it as an icon | `web/frontend/components/feature/PlanModeButton.tsx`, `feature/Composer.tsx` |
| Plan frame | Transport frame + its hand-mirrored TS type | `web/backend/app/events/stream.py`, `web/frontend/lib/events.ts` |
| Approval loop | Plan streams, turn waits, `approvedPlan` executes it | `web/backend/app/services/turn_engine.py`, `web/frontend/components/feature/PlanApproval.tsx` |
| Scene script agent | One call renders an approved plan with `<speaker:N>` | `web/backend/app/agents/scene_script_agent.py` |
| Multi-speaker parsing | A speaker change opens a new segment; same-speaker repeats still collapse | `web/backend/app/services/emission.py` |
| `sceneFlow` toggle | `continuous` (default) vs `voiced`, with the trade stated in the copy | `web/frontend/components/feature/SceneConfigMenu.tsx`, `web/backend/app/schemas/play.py` |
| Backend tests | Labelling · prompts · guards · settings · plan mode · multi-speaker · fallback · toggle | `utils/tests/backend/{agents,services,api}/` |
| Frontend tests | Disclosure · plan-mode control · plan approval · stream frame · config popover | co-located `*.test.tsx` / `*.test.ts` |
| EXP-2026-08-015 | Playwright POV fix, and the voice-distinctness baseline | `docs/research/experiments/EXP-2026-08-015-pov-and-voice-baseline/` |
| EXP-2026-08-016 | Continuous script vs. the voiced per-speaker path | `docs/research/experiments/EXP-2026-08-016-continuous-scene-script/` |
| Research runners | Derived from `run_prose_end_to_end.py`, not rewritten | `utils/scripts/research/run_pov_mode.py`, `run_scene_script.py` |
| Docs | Every file that described the removed behaviour or the old vocabulary | `docs/`, `CLAUDE.md`, `.env.example` |
