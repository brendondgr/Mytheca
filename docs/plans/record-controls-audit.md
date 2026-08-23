# Record Controls — Audit and Repair

> **Scope.** Verify, against the live `skynet` relay on `:4000` and the real Postgres /
> Redis / Neo4j stack, that the five record operations shipped by
> `docs/plans/control-over-the-record.md` — **re-roll a beat**, **re-run the turn**,
> **branch from here**, **rewind to here**, **edit a beat** — actually do what their names
> claim. Fix what the tests find. Restrict **Edit** to the player's own lines.

---

## 1. Introduction

`control-over-the-record.md` shipped the record surface: a play-through can be forked,
cut back, rewritten and re-rolled. Its own validation section says every phase was
"exercised against the running app". The owner's report is that the operations *appear*
to work — the transcript changes, the toast fires, the rows go — but that **a rewind does
not make the scene forget**, and that **Edit breaks on beats the player did not write**.

Both reports survive a read of the code, and the read finds five concrete defects rather
than one. They are listed as hypotheses in §2 because the point of this plan is to
*measure* them against a live model, not to assert them. The approach is therefore:
build one scripted live harness that drives the real API through every record operation
and probes what the cast actually remembers afterwards; run it as a **baseline** and
record what fails; fix; re-run the identical harness; record the after-arm. The harness
becomes `EXP-2026-08-014`, because the repository's research contract
(`docs/research/AGENT_INSTRUCTIONS.md`) makes any evaluation run against a live model an
experiment whether or not it was framed as one.

Nothing in this plan invents new product surface. Every fix closes a gap between what a
control is documented to do and what it does.

---

## 2. Gaps & Unanswered Questions

### The five hypotheses under test

Each was found by reading the code, and each is a *hypothesis* until the harness in
Phase 1 shows it live.

**H1 — A rewind does not clear a character's interior state.**
`app/memory/interior.py` stores a per-character disposition + retrospective under
`interior:{session_id}:{character_id}`, written by `services/reflection.py` after every
turn and read straight into the prompt by `assembler._build_cast` (`assembler.py:399`).
The module has **no `clear` function at all**, and `session_state.truncate_session` never
touches it. After a rewind the cast re-enters the scene still carrying the stance the cut
beats produced. This is the owner's "it didn't forget" in its most literal form: the
transcript forgot and the characters did not.

**H2 — A rewind does not drop the direction the cut turn raised.**
`PlaySession.standing_direction` carries what a turn could not deliver so the next turn
re-owes it. `truncate_session` does not touch it either, so a rewind past the turn that
raised a requirement leaves the requirement standing — the scene keeps trying to deliver
something the player un-asked for. `to_standing` stamps each row with `fromTurn`, which
is the turn's opening `Event.seq`, so the correct cut is exact: drop rows with
`fromTurn > after_seq`, keep the rest.

**H3 — A re-roll shows the model the beat it is replacing.**
`turn_setup.context_for_replay` is careful to walk the persisted rows for `turn_beats`,
precisely so the re-run does not see past `through_seq`. But the `TurnContext` it returns
comes from a plain `assembler.assemble_context`, whose `recent_beats` are read from the
**Redis buffer** — which at that moment still holds the target beat and everything after
it. Re-rolling the most recent narration therefore asks the model to narrate again with
its own previous narration as the last thing in the window. The same polluted list feeds
`_build_cast`'s per-speaker `recent_lines` anchors.

**H4 — A character beat that never speaks carries the wrong event id.**
In `turn-stream.ts` a character's `internal_thought` → `character_action` →
`character_dialogue` fold into **one** `SceneMessage`. The message's `id` is set by the
thought, then overwritten by the dialogue. When a character acts without speaking — and
on **reload**, where no `speaker` trace frame opens an id-less pending beat — the merged
message keeps the **`internal_thought`'s** id and has no `text`. `EDITABLE_BEATS` still
offers Edit on it: the editor opens empty and saves the player's new words onto the
*thought* row, silently. `RERUNNABLE_BEATS` still offers Re-roll on it, and the backend
answers `422 A internal thought beat cannot be re-rolled`. This is the reported "it
breaks when you do it for the messages of the AI".

**H5 — A branch does not inherit the debt.**
`session_state.copy_history` copies events, traces and stat values, and deliberately
clears the summary. It does not copy `standing_direction`, so forking at a beat silently
cancels whatever the parent still owed the player at that point.

### Decisions taken here (simple gaps)

- **Edit is restricted to the player's own lines in the UI, and the backend keeps its
  breadth.** The owner asked for the button to appear only on what they sent. The
  frontend gate is therefore `player` beats plus POV beats the player authored
  (`fromPlayer`). `session_state.EDITABLE_TYPES` is left alone: it is the record API,
  it is what `PATCH …/beats/{id}` documents, and narrowing it would break the export and
  the re-roll take machinery that share the row. The gate that matters to the owner is
  the one they can click.
- **H4 is fixed anyway, not just hidden behind the Edit gate.** The same wrong id breaks
  **Re-roll**, which stays available on AI beats. A char message must carry the id of its
  *prose* row.
- **Neo4j relationship edges stay un-rolled-back on rewind.** Already recorded as a
  deliberate limitation in `session_state`'s module docstring and `docs/checklist.md`:
  the graph is a best-effort accumulator with no per-turn provenance index. The harness
  **measures** the leak rather than pretending it is closed, and the finding is written
  to the experiment.
- **The harness drives the running dev backend over HTTP**, reusing
  `utils/scripts/research/run_conversation_scaling.py`'s `API` / `_post` / `_patch`
  helpers, the same way `run_context_compaction.py` does. An in-process harness would not
  exercise the routes, which is where three of the five defects live.

### Needing human input

None. Every question this plan raises is answered by a measurement or by an owner
instruction already given in the request.

---

### Ordering note

Phases **6 and 7 are committed before 2–5**. The dev backend runs under
`uvicorn --reload` with `reload_dirs=[web/backend]`, so any backend edit restarts the
server mid-run and would invalidate the baseline arm the moment it touched a file. The
frontend phases are outside `reload_dirs` and can proceed while the live arm runs. The
phase numbers below are unchanged — they are the dependency order, not the clock.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — The live record-controls harness, and the baseline run

- **Locations:** new `utils/scripts/research/run_record_controls.py`; new experiment
  folder `docs/research/experiments/EXP-2026-08-014-record-controls/` scaffolded with
  `make new-experiment SLUG=record-controls`.
- **What it does.** Builds a throwaway world (reusing `build_world`'s shape: three
  characters, one setting, one scenario, `contextPolicy: "fixed"` so depth is not a
  moving target), then runs one scripted play-through per **probe**, each probe an
  independent scene so a failure cannot contaminate the next:
  1. `rewind_forgets` — plant a concrete, checkable fact over two turns, take a third
     turn that *reacts* to it, rewind to the planting turn, then ask the cast to say what
     they know. Records: the surviving `events` rows, the Redis `buffer:{session}` list,
     `PlaySession.standing_direction`, every `interior:{session}:*` key, the Neo4j edge
     count for the pair, and the lexical coverage of the probe's answer against the
     planted fact (`services.direction_check.coverage`, the same crude floor
     `EXP-2026-08-011` used, so it errs identically in both arms).
  2. `reroll_beat` — re-roll the last character beat three times. Records: event id and
     seq stability, `takes` length, `activeTake`, the count of `state_update` rows before
     and after, the count of `internal_thought` rows before and after, and whether the
     new take's text is a *continuation* of the old one (the H2 signature).
  3. `reroll_turn` — re-run a whole turn. Records: rows removed, rows written, whether
     the player's `user_turn` row is written once, and the seq of the first new beat.
  4. `branch` — fork mid-scene. Records: source row count unchanged, fork row count,
     fresh ids, identical seqs, `standing_direction` on both sides, stat values on both.
  5. `edit` — edit a player line and an AI line. Records: the row's `text` and
     `editedByPlayer`, and **the Redis buffer's** copy of that beat, which is the only
     proof the cast reads what the player reads.
- **Rationale:** the baseline has to exist before any fix, or the after-arm measures
  nothing. Every probe writes a row to `data/metrics.json`; nothing is aggregated across
  probes, per the repository's rule about partially-failed experiments.
- **Also:** `PROTOCOL.md` states the probes, the stopping rule and the scoring **before**
  the run; `manifest.yaml` gets `status: running`; the model id actually served is read
  from `/v1/models` and written to `env/`.
- *Action: run the harness against the live stack
  (`uv run python -m utils.scripts.research.run_record_controls --arm baseline`), then
  `make validate-research`. Commit: `[Record Controls] (1/8) Complete: Added the live
  record-controls harness and recorded the baseline arm against skynet.`*

### Phase 2 — A rewind clears the interior state (H1)

- **Locations:** `web/backend/app/memory/interior.py` (new `clear_session`, mirroring
  `buffer.clear`'s best-effort posture — `SCAN`/`DELETE` over `interior:{session_id}:*`,
  a silent no-op with no Redis); `web/backend/app/services/session_state.py`
  (`truncate_session` calls it beside `rebuild_buffer`; module docstring gains the
  interior row in its "what each store does" table);
  `utils/tests/backend/services/test_session_state.py`.
- **Rationale:** this is the largest of the leaks and the one the owner felt. It belongs
  beside the buffer rebuild for the reason that file already gives: both answer "history
  changed under us", and splitting them across two call sites is how one gets forgotten.
  A rewind clears rather than replays because interior state has no persisted source to
  replay from — it is derived per turn by a model call, and the next turn's reflection
  recomputes it.
- **Tests:** a rewind clears the session's interior keys; a rewind clears only *this*
  session's keys; `clear_session` is a no-op without Redis; a branch's fork starts with
  no interior state of its own.
- *Action: `uv run pytest utils/tests/backend/services utils/tests/backend/api`. Commit:
  `[Record Controls] (2/8) Complete: A rewind now clears the cast's interior state, so
  characters stop carrying the stance the cut beats gave them.`*

### Phase 3 — A rewind drops the direction the cut turns raised (H2)

- **Locations:** `web/backend/app/services/session_state.py` (`truncate_session` prunes
  `PlaySession.standing_direction` to rows whose `fromTurn <= after_seq`, through
  `direction_runtime.save_standing` so the "empty list becomes `None`" rule stays in one
  place); `utils/tests/backend/services/test_session_state.py`,
  `utils/tests/backend/api/test_play_rewind.py`.
- **Rationale:** `fromTurn` is an `Event.seq`, so the cut is exact rather than heuristic.
  A rewind that leaves the debt standing makes the scene keep chasing something the
  player just deleted, which reads as the app ignoring the rewind.
- **Watch for:** an import cycle — `session_state` importing `direction_runtime`.
  `direction_runtime` imports agents and models, not `session_state`, so the direction is
  safe; if that ever inverts, the prune moves to the caller.
- **Tests:** a rewind drops a requirement raised by a cut turn; keeps one raised by a
  surviving turn; a rewind past everything clears the column to `None`; a malformed row
  is dropped rather than raising.
- *Action: `uv run pytest utils/tests/backend/services utils/tests/backend/api`. Commit:
  `[Record Controls] (3/8) Complete: A rewind now cancels the direction the cut turns
  raised, and keeps what surviving turns still owe.`*

### Phase 4 — A branch inherits the debt (H5)

- **Locations:** `web/backend/app/services/session_state.py` (`copy_history` copies the
  parent's `standing_direction`, pruned to `fromTurn <= through_seq` by the same helper
  Phase 3 introduces); `utils/tests/backend/services/test_session_state.py`,
  `utils/tests/backend/api/test_play_branch.py`.
- **Rationale:** a fork is supposed to be the parent up to the fork point. The summary is
  cleared deliberately and for a stated reason; the debt has no such reason, and losing
  it makes "branch here and try again" quietly different from "carry on".
- **Tests:** a branch carries the parent's outstanding direction; it carries only what
  was owed at or before the fork seq; the parent's column is untouched.
- *Action: `uv run pytest utils/tests/backend/services utils/tests/backend/api`. Commit:
  `[Record Controls] (4/8) Complete: A branch now inherits what the parent still owed at
  the fork point.`*

### Phase 5 — A re-roll stops seeing the beat it replaces (H3)

- **Locations:** `web/backend/app/services/assembler.py` (`assemble_context` gains an
  optional `through_seq: int | None`; when set, the tail of `recent_beats` is trimmed by
  the number of buffer-eligible rows above that seq, **before** `_build_cast` reads it for
  voice anchors); `web/backend/app/services/session_state.py` (exports the buffer-
  eligibility rule so `assembler` and `rebuild_buffer` cannot disagree about what counts
  as a buffered row); `web/backend/app/services/turn_setup.py`
  (`context_for_replay` passes `through_seq`); `utils/tests/backend/services/`.
- **Rationale:** `context_for_replay`'s docstring already states the intent — "the last
  beat the re-run may see" — and the `turn_beats` half honours it. Only the window half
  does not. Trimming the tail rather than re-deriving the whole window keeps the
  block-anchoring that protects prompt-cache reuse untouched.
- **Tests:** re-rolling the last beat assembles a context that does not contain that
  beat's text; re-rolling a middle beat excludes everything after it; the trim is a no-op
  when `through_seq` is `None` (the ordinary turn path is byte-identical); with no Redis
  the trim cannot go negative.
- *Action: `uv run pytest utils/tests/backend/services utils/tests/backend/api`. Commit:
  `[Record Controls] (5/8) Complete: A re-rolled beat no longer sees itself — the replay
  context is trimmed to the beats before it.`*

### Phase 6 — A character beat carries its prose row's id (H4)

- **Locations:** `web/frontend/features/story-player/turn-stream.ts` (the
  `internal_thought` branch stops claiming the beat's `id` — it sets `thoughtId` only;
  the `character_action` branch adopts `id` when the beat it merges into has none);
  `web/frontend/features/story-player/turn-stream.test.ts`.
- **Rationale:** the beat's `id` is what every record control points at. A thought is not
  the beat's prose; it is a private aside folded into the same bubble. Today a character
  who acts without speaking hands Edit and Re-roll the wrong row — silently for Edit, as
  a 422 for Re-roll. Fixing it here fixes both controls, and it is the only fix that also
  survives the Edit gate in Phase 7.
- **Consequence, stated rather than discovered later:** a beat that is *only* a thought
  now has no `id`, so it shows no controls. That matches the live path today (a pending
  beat opened by a `speaker` trace has no id either) and is the honest answer — a private
  thought is not a beat of the story record.
- **Tests:** a thought-then-action beat carries the action's id; a
  thought-action-dialogue beat carries the dialogue's id; a lone thought carries none; a
  rehydrated transcript agrees with the live one on every beat's id.
- *Action: `cd web/frontend && npm test -- turn-stream` then the full `npm test`, plus
  `npm run typecheck` and `npm run lint`. Commit: `[Record Controls] (6/8) Complete: A
  character's beat now carries its prose row's id, so Edit and Re-roll stop targeting the
  private thought.`*

### Phase 7 — Edit is offered only on the player's own lines

- **Locations:** `web/frontend/features/story-player/StoryPlayerView.tsx`
  (`EDITABLE_BEATS` becomes the player's own lines: `player`, plus a `char` beat with
  `fromPlayer`, which is a POV line the player wrote); `BeatControls`'s `onEdit`
  docstring; `web/frontend/features/story-player/StoryPlayerView.test.tsx`;
  `docs/api-contract.md` and `docs/component-map.md` (the control's scope).
- **Rationale:** the owner's instruction, and it is also the right line to draw. Editing
  the model's prose puts words in a character's mouth that the character's own state was
  never conditioned on; the record's answer to "I don't like that line" is **Re-roll**,
  which regenerates it in place and keeps the old take. The player's own words are the
  one thing they are unambiguously the author of.
- **Accessibility:** the beat toolbar's roving tabindex is built from the *rendered*
  controls, so dropping Edit from AI beats needs no index change — but the a11y pass has
  to confirm one tab stop per beat still, and that the cluster is still reachable on a
  beat whose only controls are Re-roll / Branch / Rewind.
- *Action: `cd web/frontend && npm test`, `npm run typecheck`, `npm run lint`, plus the
  accessibility + responsive pass (keyboard into and out of the beat toolbar, visible
  focus, 320 / 375 / 768 / 1024). Commit: `[Record Controls] (7/8) Complete: Edit is
  offered only on the lines the player wrote; the answer to a bad AI line is Re-roll.`*

### Phase 8 — The after-arm, the docs, and the record

- **Locations:** re-run `utils/scripts/research/run_record_controls.py --arm fixed`;
  `docs/research/experiments/EXP-2026-08-014-record-controls/` (`RESULTS.md`,
  `manifest.yaml` → `status: complete`, `data/metrics.json`, `figures/make_figures.py`
  regenerating every figure from the recorded metrics, `ISSUES.md` for anything the run
  hit); `docs/research/CLAIMS.md`; `docs/checklist.md` (the Neo4j edge leak, stated with
  its measurement); `docs/api-contract.md`; `docs/data-flow.md` (rewind's forgetting
  contract); `docs/plans/control-over-the-record.md` (an `AMENDMENTS` note pointing here
  — that plan is complete and append-only).
- **Rationale:** the before/after arms are the whole evidence, and the contract says a
  number that lives only in chat does not exist. The checklist entry matters most: after
  this plan a rewind clears Postgres, Redis, the summary, the stats, the traces and the
  debt — and *not* the graph. That last clause has to be written down where the next
  reader will find it.
- *Action: `uv run pytest`, `cd web/frontend && npm test`, `npm run typecheck`,
  `npm run lint`, `node utils/scripts/check_frontend_css.mjs`, `make validate-research`,
  `make research-index`, `make figures`. Commit: `[Record Controls] (8/8) Complete:
  Recorded the fixed arm, reconciled the docs and the checklist against what a rewind now
  forgets.`*

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Live harness | Drives the real API through all five record operations and probes what the cast remembers | `utils/scripts/research/run_record_controls.py` |
| Experiment | Baseline + fixed arms, protocol, metrics, figures | `docs/research/experiments/EXP-2026-08-014-record-controls/` |
| Interior clear | `clear_session`, best-effort, mirroring `buffer.clear` | `web/backend/app/memory/interior.py` |
| Rewind forgets | Interior cleared + standing direction pruned on truncate | `web/backend/app/services/session_state.py` |
| Branch inherits | The fork carries the parent's debt at the fork seq | `web/backend/app/services/session_state.py` |
| Replay window | `assemble_context(through_seq=…)` trims the tail; `context_for_replay` passes it | `web/backend/app/services/assembler.py`, `turn_setup.py` |
| Beat id | A char beat carries its prose row's id, not the thought's | `web/frontend/features/story-player/turn-stream.ts` |
| Edit gate | Edit offered only on the player's own lines | `web/frontend/features/story-player/StoryPlayerView.tsx` |
| Backend tests | Interior, standing direction, branch debt, replay window | `utils/tests/backend/services/test_session_state.py`, `utils/tests/backend/services/test_replay_context.py`, `utils/tests/backend/api/test_play_rewind.py`, `test_play_branch.py` |
| Frontend tests | Beat id folding, Edit gating | `web/frontend/features/story-player/turn-stream.test.ts`, `StoryPlayerView.test.tsx` |
| Docs | Rewind's forgetting contract, Edit's scope, the graph leak | `docs/api-contract.md`, `docs/data-flow.md`, `docs/checklist.md`, `docs/plans/control-over-the-record.md` |
