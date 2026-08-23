# PROTOCOL — EXP-2026-08-014 Record controls — what a rewind forgets, and what a re-roll sees

> Written before the baseline arm was run. The metric definitions, the probes and the
> stopping rule below were fixed first; nothing in this file was edited after seeing a
> number. Corrections, if any, are appended to `ISSUES.md`.

## Question

The five record operations shipped by `docs/plans/control-over-the-record.md` — re-roll a
beat, re-run a turn, branch from here, rewind to here, edit a beat — all change the
transcript visibly. Do they change everything the transcript is derived from? Concretely:
**after a rewind, does the scene still know what happened in the beats it cut?** And
**when a beat is re-rolled, does the model doing the re-rolling see the beat it is
replacing?**

## Hypothesis

Five hypotheses, each stated as a specific failure the run can observe. Each is testable
independently; a failure of one says nothing about the others.

- **H1** — After a rewind, `interior:{session_id}:*` in Redis still holds the
  per-character disposition and retrospective produced by the cut turns, because
  `app/memory/interior.py` has no clear function and `session_state.truncate_session`
  does not call one. The cast therefore re-enters the scene carrying a stance derived
  from beats that no longer exist.
- **H2** — After a rewind, `PlaySession.standing_direction` still carries requirements
  whose `fromTurn` is above the cut seq, so the scene keeps chasing a direction the
  player deleted.
- **H3** — A re-roll's `TurnContext.recent_beats` still contains the text of the beat
  being replaced (and any beats after it), because `turn_setup.context_for_replay` walks
  the persisted rows for `turn_beats` but takes `recent_beats` from the live Redis
  buffer.
- **H4** — A character beat that emits a private thought and an action but no dialogue
  carries the **`internal_thought` row's** event id in the frontend transcript, so the
  Edit control writes onto the thought and the Re-roll control is refused with a 422.
- **H5** — A branch does not copy the parent's `standing_direction`, so forking silently
  cancels what the parent still owed.

The Neo4j leak is **not** a hypothesis — `session_state`'s module docstring already
states that relationship edges written by cut turns are not rolled back. The run
**measures** it so the size of the known gap is on the record.

## Setup

The running dev stack, driven over HTTP at `http://localhost:3345/api`:

- **Backend** — `uv run python app.py backend`, real Postgres (`backend-db-1`), real
  Redis (`backend-redis-1`), real Neo4j (`backend-neo4j-1`), real Qdrant
  (`backend-qdrant-1`).
- **Model** — the local relay on `:4000`, model id `skynet`. The upstream model actually
  served is read from `GET /v1/models` at run time and written to `env/relay-models.json`,
  because the relay hot-swaps endpoints and "skynet" is a route, not a model.
- **Harness** — `utils/scripts/research/run_record_controls.py`, reusing
  `run_conversation_scaling`'s `API` / `_post` / `_patch` / `run_turn` helpers so the
  transport is the same one `EXP-2026-08-005`, `-006` and `-011` used.
- **Arms** — `baseline` (commit `cd094e5`, before any fix in
  `docs/plans/record-controls-audit.md`) and `fixed` (after Phases 2–7). The two arms run
  the **identical** harness against the **identical** scripted player side.

Each probe builds its **own** throwaway world and play-through, so a probe that fails
cannot contaminate the next. Worlds are left in the dev database rather than deleted:
a deleted world cannot be inspected when a number looks wrong.

## Data

No external dataset. The harness generates its own world (three characters, one setting,
one scenario, `contextPolicy: "fixed"`, `contextBeats: 14`) and drives a **fixed**
scripted player side written into the harness source. This is synthetic and ships with
the repository; it is contaminated for any held-out use and no claim of generality over
real play is made from it.

The planted fact and the probe line are deliberately concrete, for the reason
`EXP-2026-08-011` gives: a fact scored by word overlap must be made of words that cannot
arrive by accident.

## Metrics

Reported **per probe**, never aggregated across probes. `n = 1` scene per probe per arm —
these are existence checks on mechanism, not rates.

| Metric | Definition | Direction |
| --- | --- | --- |
| `rewind.interior_keys_after` | Count of `interior:{session}:*` Redis keys present after the rewind returns 200. | lower is better; **0 is correct** |
| `rewind.standing_after` | Count of `PlaySession.standing_direction` rows surviving the rewind whose `fromTurn` is above the cut seq. | lower is better; **0 is correct** |
| `rewind.buffer_leak_beats` | Count of entries in `buffer:{session}` whose text matches a cut beat's text. | lower is better; **0 is correct** |
| `rewind.summary_after` | 1 if `summary_text` survives a cut at or below `summary_through_seq`, else 0. | **0 is correct** |
| `rewind.graph_edges_after` | Neo4j relationship edges between the scenario's cast after the rewind, minus the count before the cut turns ran. | measured, not asserted |
| `rewind.recall_coverage` | `services.direction_check.coverage(probe_answer, planted_fact)` — the fraction of the planted fact's content tokens that appear in the cast's answer to "what do you know". Computed over the **prose the cast emits after the rewind**. | lower is better; a rewind that forgot should score near the pre-plant floor |
| `rewind.recall_floor` | The same coverage measured on a control turn taken **before** the fact was ever planted. The floor the post-rewind score should return to. | reference |
| `reroll.id_stable` | 1 if the re-rolled beat keeps its event `id` and `seq`, else 0. | **1 is correct** |
| `reroll.takes` | `len(data.takes)` after three re-rolls of one beat. | **4 is correct** (original + 3) |
| `reroll.state_update_delta` | `state_update` rows in the session after three re-rolls minus before. | **0 is correct** |
| `reroll.thought_delta` | `internal_thought` rows in the session after three re-rolls minus before. | **0 is correct** |
| `reroll.self_overlap` | `coverage(new_take, previous_take)` — how much of the replaced wording the replacement reuses. High overlap is the signature of a model that was shown the beat it was asked to replace. | lower is better |
| `rerun_turn.user_turn_rows` | `user_turn` rows for that turn's seq after the re-run. | **1 is correct** |
| `rerun_turn.first_new_seq` | The seq of the first beat written after the re-run, versus the opening `user_turn`'s seq. | must be `opening + 1` |
| `branch.source_rows_delta` | Source session's event count after the branch minus before. | **0 is correct** |
| `branch.seqs_identical` | 1 if the fork's seqs equal the source's through the fork seq. | **1 is correct** |
| `branch.ids_fresh` | 1 if no event id is shared between source and fork. | **1 is correct** |
| `branch.standing_inherited` | 1 if the fork's `standing_direction` equals the parent's rows at or below the fork seq. | **1 is correct** |
| `edit.row_text_matches` | 1 if the edited row's `data.text` is the new wording. | **1 is correct** |
| `edit.buffer_text_matches` | 1 if the **Redis buffer** entry for that beat is the new wording. This is the only proof the cast reads what the player reads. | **1 is correct** |
| `edit.player_line_ok` / `edit.ai_line_ok` | The two above, measured separately for a `user_turn` row and an AI prose row. | **1 is correct** |
| `beat_id.thought_claims_beat` | Frontend-only, from the co-located `turn-stream` tests rather than the live run: 1 if a thought-then-action beat carries the thought's id. | **0 is correct** |

`coverage` is `services.direction_check.coverage`, the same crude lexical check
`EXP-2026-08-011` used. It is a **floor** on recall, not a measurement of it, and it errs
identically in both arms. It is not evidence about meaning.

## Baselines

The baseline arm is this repository at commit `cd094e5` — the code as the owner reported
it. There is no external baseline; the comparison is before-fix versus after-fix of the
same system, run through the same harness on the same day against the same relay.

Same-day matters: `docs/checklist.md` records that day-apart comparison on this endpoint
is worthless because the served model has changed under this project between experiments.
Both arms are run in one sitting, and the served upstream model id is recorded for each.

## Procedure

```bash
# The stack must already be up (app.py owns Docker):
uv run python app.py backend

# Baseline arm — before any fix.
uv run python -m utils.scripts.research.run_record_controls \
    --arm baseline \
    --experiment docs/research/experiments/EXP-2026-08-014-record-controls

# ... Phases 2–7 of docs/plans/record-controls-audit.md ...

# Fixed arm — the identical harness.
uv run python -m utils.scripts.research.run_record_controls \
    --arm fixed \
    --experiment docs/research/experiments/EXP-2026-08-014-record-controls

make validate-research && make figures
```

No seeds: the model is served over a relay with provider-side nondeterminism, and the
harness does not set one. Every metric above is a mechanism check (a count, an id, a
row) except `recall_coverage` and `self_overlap`, which are the two the nondeterminism
actually touches — and both are reported per run, never as a mean over arms.

**Stopping rule, fixed here:** one scene per probe per arm. Three re-rolls of one beat.
Three turns before the rewind. These are not extended after seeing a result. If a probe
crashes, it is recorded as `failed` with the traceback in `ISSUES.md` and the surviving
probes are reported **per row, with no aggregate** — the rule `EXP-2026-08-001`
established the hard way.

## What would falsify this

- **H1 falsified** if `rewind.interior_keys_after` is 0 on the baseline arm.
- **H2 falsified** if `rewind.standing_after` is 0 on the baseline arm *while a direction
  was actually raised by a cut turn* — the harness asserts the setup by checking the
  column is non-empty before the rewind, and records the probe as inconclusive rather
  than as a pass if it is not.
- **H3 falsified** if the assembled replay context does not contain the target beat's
  text on the baseline arm.
- **H4 falsified** if a thought-then-action beat already carries the action's id.
- **H5 falsified** if the fork already carries the parent's standing direction.

A fix is only credited if the fixed arm moves the corresponding metric **and** the
baseline arm showed the failure. A metric that was already correct at baseline is
reported as such, not claimed as a repair.
