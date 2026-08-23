# ISSUES — EXP-2026-08-014

Everything that went wrong, was amended, or is a known weakness of this run. Recorded as
it happened.

## A-1 · The recall metric was amended after the baseline rewind probe ran

**What happened.** `PROTOCOL.md` defined `rewind.recall_coverage` as
`direction_check.coverage(probe_answer, planted_fact)`. The baseline rewind probe returned
`0.3333` against a floor of `0.0` — but the probe line itself is *"I ask them to repeat
back what I told them about **my debt and my collar**"*, and `collar` is one of the nine
content tokens the planted fact is scored on. A model that merely echoes the question
therefore scores for it, and one ninth of that 0.3333 is not evidence of anything.

**What was done.** A second reading, `recall_coverage_discounted`, was added: the same
coverage over the planted fact's content tokens **minus the probe question's own content
tokens** (nine tokens become eight). The harness now also stores the probe's answer text
(`probe_answer`), so a future re-scoring costs nothing instead of a fifteen-minute re-run —
which is what the omission cost this time.

**Why this is not quiet fitting.** The amendment makes the metric *stricter*, and it was
made before the fixed arm ran, so it cannot have been chosen to flatter a result. The
original baseline row is kept in the `superseded` array of `data/metrics-baseline.json`
rather than deleted, and the re-run of the rewind probe is reported beside it.

**What it does not change.** The two metrics that actually decide H1 and H2 —
`interior_keys_after` and `standing_after_from_cut_turns` — are counts of Redis keys and
JSON rows. They are unaffected by anything the model says.

## A-3 · The replay-window read was added after the baseline arm

`PROTOCOL.md` proposed to detect H3 through `reroll.self_overlap` — how much of the wording a
re-take reuses. The baseline returned 0.341 mean / 0.409 max, which cannot separate "the model
was shown the line it was replacing" from "two versions of one beat share their nouns". A
**direct** read was added instead (`replay_window_holds`): build the same `TurnContext` the
re-roll builds and look for the target's own text in it. No model is involved, so the baseline's
own recorded scene was re-read on the unmodified code rather than re-run — the row is
`reroll_replay_window` in `data/metrics-baseline.json`, and later arms measure it inline.
`self_overlap` is still reported and is still not evidence.

## O-1 · Two incidental defects, observed and NOT fixed here

Both were visible in the fixed arm's recorded scene (`5d4f`) and both are about the **turn
loop's narration**, not the record operations this experiment tests. They are recorded because
seeing them and saying nothing is how they get lost, and carried to `docs/checklist.md`.

1. **One turn wrote the same narration three times.** Rows at seq 6, 7 and 9 of session
   `ps_9e3e4a8b6e` are three distinct `narration` events holding byte-identical text
   ("The partner's grin curdles…"). Not a delta-accumulation artefact of the harness — three
   separate `Event` rows in Postgres.
2. **A narration row carried prompt scaffolding into the transcript.** Seq 4 of the same
   session begins `] ... 'Is this how you greet a business associate?' I ask."). *` — a
   fragment of the emission format rather than prose.

n = 1 scene each; neither is a rate, and neither is investigated here. Scope for this run was
the five record operations.

## A-2 · The baseline's discounted recall was never back-filled

A-1 says the amendment was made "before the fixed arm ran". It was — but the baseline rewind
probe was **not** re-run to obtain the discounted figure for it, so
`recall_coverage_discounted` exists for the fixed arm only and the figure draws the baseline
bar as `n/r` rather than imputing one. Re-running would have meant a second, different scene
against a nondeterministic endpoint, which is not the same number re-scored; and the answer
text was not stored on that first run, which is the omission the amendment also fixed for
next time.

The consequence is stated plainly in RESULTS §4 rather than smoothed over: the two arms'
recall figures come from **different scenes with different floors** (0.000 and 0.111), so the
readable comparison is each arm's coverage *against its own floor*, not against each other.
The mechanism counts, which are what decide H1 and H2, are unaffected.

## K-1 · The graph leak is measured, not fixed

`rewind.graph_edges_after` is reported for completeness. Relationship edges written by cut
turns are **not** rolled back — `services/session_state.py`'s module docstring states this,
and `docs/checklist.md` carries it as open work: the story graph is a best-effort
accumulator with no per-turn provenance index, and inventing one was out of scope for this
plan. Nothing here should be read as "a rewind clears the graph".

## K-2 · One scene per probe per arm

Fixed in `PROTOCOL.md` before the run and not extended after seeing a result. Every row is
an existence check on a mechanism, not a rate. The two model-dependent numbers
(`recall_coverage*`, `reroll.self_overlap`) carry the endpoint's nondeterminism and are
reported per run, never as a mean across arms.
