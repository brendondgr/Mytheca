# Prose That Reads Like A Scene — dialogue, paragraphs, and one beat per beat

**Status:** complete (2026-08-21)
**Created:** 2026-08-21
**Owner:** brendondgr
**Evidence:** the `ps_c015c506b1` export ("A Slow Burn in the Golden Grass", turns 1–2) and
session `ps_0f0d1a6900` in the live database, turns 10 and 23.

## 1. Introduction

The passage form shipped. What it produces does not read like a scene. The owner's words
are the specification and they are all reproducible in the data: *"no new line characters
when characters talk, no quotations… the characters don't sound right… it needs to be back
and forth prose."*

Measured over the twelve most recent `character_prose` events in the live database:

| Property | Count |
| --- | --- |
| Contains a double quote (any spoken line at all) | **3 / 12** |
| Contains a paragraph break | **4 / 12** |
| Byte-identical duplicates of another event in the same beat | **5** |

This plan does not add a feature. It fixes four defects, each root-caused below, and then
verifies against live output rather than against a test that asserts the fix compiles.

## 2. Gaps & Unanswered Questions

**Root causes (established from the database and the code, not inferred):**

**1 — One beat became five events.** Session `ps_0f0d1a6900`, turn 10: trace steps 29–36 are
a *single* `speaker` step ("Aldous responds"), one `thinking` step, and then **five**
consecutive `prose` steps whose bodies are byte-identical. One LLM call, five persisted
`character_prose` events. `EmissionAccumulator` is doing this: `_handle_tag` calls
`_close_open()` on a `<thinking>` tag in either direction, and `_consume_text` then opens a
*new* `_PROSE` segment for the text that follows. A model that repeats its whole emission —
scratchpad tag and all — is faithfully split into one event per repetition. The previous fix
for this (ignoring prose-named `<type:>` tags) closed one door; `<thinking>` is another.

**2 — The scratchpad reached the page.** Event `seq=16` of the same session is, verbatim:
*"then main passage then optional structured blocks each opening tag own line JSON below NO
closing tag per instructions AFTER passage may append structured block…"*. That is the model
restating the output contract to itself, persisted and rendered as a character's prose.
`seq=13` opens with a literal `<passage>` tag the model invented. Neither is caught: they are
well-formed language, so `looks_degenerate` passes them, and nothing else looks.

**3 — The sampler is the prime suspect for the broken grammar.** `_VOICE_FREQUENCY_PENALTY`
is 0.4 and `_VOICE_PRESENCE_PENALTY` is 0.3. Those penalties apply to *every* token, and the
tokens prose is made of are the most repeated ones in it: the full stop, the comma, the
double quote, `I`, `the`. The observed failure is exactly what over-penalising them looks
like — 180-word sentences with no full stop, a lowercase `i`, no quotation marks anywhere,
and em-dash fragments substituting for clauses. A two-arm probe against the live endpoint
measures this before anything is changed on a hunch. **This is the one step whose outcome is
not known in advance**; if the penalties are exonerated the phase becomes a contract change
instead, and the measurement is recorded either way.

**4 — The narrator recaps instead of setting up.** In the `ps_c015c506b1` export the narrator
beat lands *after* both characters and summarises what they just did. That ordering is not
the narrator's fault — `direction_agent.schedule` delivered the direction's requirements in
the order they were listed, and the narrator's was third. But the owner's requirement is
about content as much as order: *"what the narrator says is meant to guide the narration for
the next few steps/turns."*

**Assumptions taken (simple gaps):**

1. **A character beat is exactly one `character_prose` event, always.** Not "usually" — the
   parser will make a second one unrepresentable within an emission. A model that repeats
   itself then produces one ugly passage, which is a writing-quality problem the repetition
   guard can act on, rather than five rows that look like five beats.
2. **A leaked scratchpad is a failed generation, not a beat to clean up.** Cutting the meta
   text off the front would leave a passage that starts mid-thought. The beat is regenerated
   once; if it fails again the turn moves on without it, and the existing silent-turn
   backstop covers the empty case.
3. **Dialogue is required when the character is not alone.** The contract asks for speech
   "where you say them", which a model reads as optional. It becomes a rule with a reason
   attached, and the example carries visible quotes and blank lines.
4. **The narrator leads a turn it is part of.** When the planner and the direction schedule
   both want a narrator beat and character beats in the same turn, the narrator goes first.

**Flagged, needs the owner's eye (not blocking):**

The frequency/presence penalties were added deliberately (turn-loop plan §7) to fight
in-character drift on small models. If the probe says they are what is breaking the grammar,
removing them may bring back the drift they were added for. The trade is stated here rather
than made quietly: **grammar first**. A repetitive but well-formed paragraph is readable; a
punctuation-free 180-word sentence is not.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — One beat is one passage

#### Step 1.1 — A prose segment, once opened, is never closed by a tag
- **Locations:** `web/backend/app/services/emission.py` — `EmissionAccumulator._handle_tag`
  (a `<thinking>` tag encountered while a `character_prose` segment is open no longer closes
  it; the thinking body is captured separately or dropped, but the passage stays whole),
  `_consume_text` (untagged text re-enters the open passage rather than opening a new one),
  and `parse_emission` for the batch path, which must agree exactly.
- **Rationale:** this is the defect that turns one beat into five rows. Making a second
  prose segment unrepresentable is the same move that fixed the POV roster: remove the
  ability to be wrong rather than reduce the likelihood.

#### Step 1.2 — Catch a passage that repeats itself
- **Locations:** `web/backend/app/services/emission.py` (a `repeats_itself` check beside
  `looks_degenerate`: a long tail substring that already occurred earlier in the passage),
  `web/backend/app/services/turn_engine.py` `_stream_emission` (cut the stream on it, traced
  like the existing degeneration cut).
- **Rationale:** step 1.1 converts five duplicate rows into one passage containing the
  repetition. That is only an improvement if something then stops it — otherwise the reader
  gets the same paragraph five times in one bubble.

> *Action: `uv run pytest utils/tests/backend/services/`. Commit: `[Prose] (1/6) Complete: One beat is one passage, and a passage that repeats itself is cut.`*

### Phase 2 — The scratchpad never becomes prose

#### Step 2.1 — Recognise a passage that is about the task
- **Locations:** `web/backend/app/services/emission.py` (`looks_like_scratchpad`: contract
  vocabulary — "passage", "opening tag", "JSON", "per instructions", "roster", "the player" —
  concentrated in the opening of the text, where a real passage would be in the scene).
- **Rationale:** the observed leak is unmistakable in its first twenty words and unmistakably
  absent from real prose. Judging the opening, not the whole body, keeps a character who
  genuinely says the word "passage" out of the net.

#### Step 2.2 — Regenerate the beat once, then move on
- **Locations:** `web/backend/app/services/turn_engine.py` (`_generate_speaker` — on a
  scratchpad passage, discard it and retry the same speaker once; trace both attempts).
- **Rationale:** a beat that leaked is a failed generation. Retrying once is cheap relative
  to the turn and honest about what happened; failing twice is rare enough to let the
  existing backstop handle.

> *Action: `uv run pytest utils/tests/backend/services/ utils/tests/backend/api/`. Commit: `[Prose] (2/6) Complete: A leaked scratchpad is a failed beat, not a rendered one.`*

### Phase 3 — Measure the sampler, then set it

#### Step 3.1 — Two-arm probe on the live endpoint
- **Locations:** `docs/research/experiments/EXP-2026-08-007-prose-form/` (created via
  `make new-experiment`), `utils/scripts/research/` for the runner.
- **Rationale:** the penalties are a hypothesis with a strong prior, not a fact. The metrics
  are countable and match the owner's complaints exactly: double quotes per passage,
  paragraph breaks per passage, sentences per hundred words. Recorded under the research
  contract whichever way it comes out.

#### Step 3.2 — Apply the result
- **Locations:** `web/backend/app/agents/character_turn_agent.py`
  (`_VOICE_FREQUENCY_PENALTY`, `_VOICE_PRESENCE_PENALTY`, `_REGISTER_SAMPLER`).
- **Rationale:** the constants carry a comment saying what they were for and what the
  measurement said, so the next person does not re-litigate it from scratch.

> *Action: `uv run pytest utils/tests/backend/agents/`; `make validate-research`. Commit: `[Prose] (3/6) Complete: Set the sampler from a measurement instead of a prior.`*

### Phase 4 — A contract that shows the form

#### Step 4.1 — Rewrite the character output contract around its example
- **Locations:** `web/backend/app/agents/prompt_registry.py`
  (`_CHARACTER_OUTPUT_CONTRACT`), `utils/tests/backend/agents/test_prompt_registry.py`.
- **Rationale:** the owner asked for short instructions with specific examples, and the
  current contract is long enough that the model started narrating it back. The example is
  the instruction: two or three paragraphs separated by blank lines, with quoted speech in
  the middle one. Speech becomes a rule with its reason ("a scene where nobody speaks is not
  a scene") rather than a permission.

#### Step 4.2 — Assert the form is asked for
- **Locations:** `utils/tests/backend/agents/test_character_turn_agent.py`.
- **Rationale:** the contract is a prompt, so a test can only assert what is *asked*, never
  what comes back. Phase 6 is where what comes back is checked.

> *Action: `uv run pytest utils/tests/backend/agents/`. Commit: `[Prose] (4/6) Complete: The contract shows the form instead of describing it.`*

### Phase 5 — Back and forth, and a narrator that sets up

#### Step 5.1 — The narrator leads a turn it is part of
- **Locations:** `web/backend/app/agents/direction_agent.py` (`schedule` orders a
  narrator-owned requirement ahead of character-owned ones within a turn),
  `web/backend/app/services/turn_engine.py`.
- **Rationale:** the export's narrator beat summarised two beats that had already been read.
  The same sentences placed first would have set them up.

#### Step 5.2 — Narration points forward
- **Locations:** `web/backend/app/agents/prompt_registry.py` (`_NARRATOR_SYSTEM`,
  `_NARRATOR_SYSTEM_LONG`).
- **Rationale:** the owner's requirement — narration guides the next few beats. The prompts
  already say "progress the story"; they need to say *do not restate what just happened*,
  which is the failure mode actually observed.

#### Step 5.3 — Alternate speakers
- **Locations:** `web/backend/app/agents/prompt_registry.py` (`_PLANNER_SYSTEM`),
  `web/backend/app/agents/planner_agent.py`.
- **Rationale:** turn 10 of `ps_0f0d1a6900` gave one character five consecutive beats. The
  planner already has "do not repeat a character who already had their beat"; the exchange
  the owner is asking for needs it to actively hand the floor back.

> *Action: `uv run pytest utils/tests/backend/agents/`. Commit: `[Prose] (5/6) Complete: The narrator sets up the next beats, and the floor changes hands.`*

### Phase 6 — Read the output, not the tests

#### Step 6.1 — Live run, then read every passage
- **Locations:** `docs/research/experiments/EXP-2026-08-008-prose-end-to-end/`,
  `utils/scripts/research/run_prose_end_to_end.py`, a multi-turn live run at the owner's
  settings.
- **Rationale:** every defect in this plan was found by reading real output and none by
  running the suite. The same metrics from Phase 3 are re-measured end to end, and the
  passages are read.
- **Note (revised during execution):** this was written to land in EXP-2026-08-007's
  `RESULTS.md`. It gets its own experiment instead, for two reasons. EXP-2026-08-007 is a
  *controlled* three-arm measurement against the bare contract; a single-condition
  observation through the whole engine is a different question and does not belong in its
  results. And the development runs behind this phase had been driven through
  `run_conversation_scaling` pointed at EXP-2026-08-006's folder, which overwrote a
  completed experiment's record — restored in `59ba9f5`, disclosed in the new experiment's
  `ISSUES.md`. A measurement with no home of its own is how that happened.

> *Action: full gate — `uv run pytest`; `npm test`, `npm run typecheck`, `npm run lint`; `check_contrast.py`; `check_frontend_css.mjs`; `make validate-research`. Commit: `[Prose] (6/6) Complete: Verified against live output.`*

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| One-passage parser | A prose segment is never split within an emission | `web/backend/app/services/emission.py` |
| Repetition guard | A passage that repeats itself is cut | `web/backend/app/services/emission.py`, `services/turn_engine.py` |
| Scratchpad detector | A passage that is about the task is a failed beat | `web/backend/app/services/emission.py` |
| Single retry | The speaker gets one more attempt, traced | `web/backend/app/services/turn_engine.py` |
| Sampler setting | Penalties set from a measurement | `web/backend/app/agents/character_turn_agent.py` |
| Output contract | Short, example-led, speech required | `web/backend/app/agents/prompt_registry.py` |
| Narrator prompts | Sets up the next beats; never recaps | `web/backend/app/agents/prompt_registry.py` |
| Narrator-first ordering | A narrator requirement leads its turn | `web/backend/app/agents/direction_agent.py` |
| Experiment | Sampler arms + end-to-end prose metrics | `docs/research/experiments/EXP-2026-08-007-prose-form/` |
| Backend tests | Parser, guards, retry, prompts | `utils/tests/backend/{services,agents}/` |
