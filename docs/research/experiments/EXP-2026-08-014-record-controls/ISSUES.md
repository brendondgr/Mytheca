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

## A-2 · The re-run of the baseline rewind probe is a different scene

The re-run builds its own world and takes its own turns against a nondeterministic
endpoint, so its numbers are not the first run's numbers re-scored. Both rows are reported;
neither is averaged into the other. `n = 1` per row, as the protocol fixed.

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
