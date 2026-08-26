# RESULTS — EXP-2026-08-017 Bound plan, two execution arms

**Verdict: the binding property is NOT met. No arm comparison is reported.**

`PROTOCOL.md` § 6 decides this without a judgement call: *"If `plan_adherence` is below 1.0 in
either arm, the answer to this experiment is 'fix the binding first' and no arm comparison is
reported."* It was below 1.0 in both arms. The `continuous`-vs-`voiced` question this
experiment was designed to answer is therefore **still open**.

**On the manifest status.** It reads `complete`, not `failed`: the run finished and produced
usable data on every turn. "The primary hypothesis was refuted" is a result, not a failed run
— `failed` is reserved for a run that could not produce the data, and using it here would put
a broken row in the ledger for an experiment that worked exactly as designed.

## What ran

One run, two arms, interleaved turn by turn, `n = 2` player turns per arm, three-character
scene, `gemma-4-26B-it` via the local relay. Figures: `figures/bound_plan_execution.svg`,
generated from `data/metrics.json`.

## Per-turn rows

| arm | turn | plan beats run / planned | adherence | planner calls | forced beats | cache rate | s/beat | voice |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| voiced | 1 | 4 / 3 | 1.333 | 1 | 1 | 0.559 | 32.8 | 0.909 |
| continuous | 1 | 3 / 3 | **1.000** | 1 | 1 | 0.558 | 43.7 | 0.946 |
| voiced | 2 | 1 / 2 | 0.500 | **3** | 1 | 0.251 | 55.7 | 0.891 |
| continuous | 2 | 1 / 3 | 0.333 | 1 | 1 | **0.000** | 99.8 | 0.912 |

An aggregate is present in `data/metrics.json` because the run completed. It is **not quoted
as the finding**: with the primary property unmet, a mean over two turns would give a
comparison the design says has not earned the right to exist.

## Findings

### 1. One planning call per turn is real, but not yet guaranteed

Three of four turns made exactly one planning call — the property Phases 1-2 were built for,
against a baseline of one call per beat. The exception is decisive: `voiced` turn 2 made
**three**.

The cause is a **conflict between two contracts**, not a bug in either. The player's message
is parsed into direction requirements ("Lily is standing on the table", "Lily is singing")
which the engine guarantees to deliver. When the planner ends a turn with a requirement still
outstanding, the engine discards the plan and schedules the rest itself — which means
re-planning. The binding was deliberately guarded to let the direction win (Phase 2), so this
is the guard firing, working as written.

**It cannot be resolved by tuning.** Either the plan governs the turn and an undelivered
instruction is reported rather than chased, or the direction outranks the plan and a bound
turn can still be extended. That is a product decision and is recorded as one in
`docs/checklist.md`, not settled here.

### 2. The two arms fail adherence in opposite directions

- `voiced` **over-runs** (1.33, then 0.50 — the latter is the re-planning turn above).
- `continuous` **under-renders**: 3/3 on turn 1, then 1 beat against 3 planned.

`continuous` never re-planned. It was handed a correct plan and wrote fewer beats than it
named — the script did not emit the hand-off tokens for beats it was given. This is a
property of the continuous writer, and it is exactly what this experiment existed to measure.
**It was deliberately not patched before the run**, since tuning an arm mid-experiment is how
an experiment produces the answer its author wanted.

### 3. The prefix cache is being reused, and `continuous` cannot use it

Cache hit rates of 0.25-0.56 confirm the mechanism the prompt ordering was designed for and
never got while a planner call sat between every beat. `continuous` turn 2 measured **0.000**:
one long generation has no earlier call to reuse. This is the trade named in the protocol as
hypothesis 4, and it is the one hypothesis this run supports — the arms win different cost
metrics, and neither is simply "the cheap one".

### 4. Run-to-run variance is large enough to matter at this n

Three runs of this harness were made (two discarded, see `ISSUES.md`). The same arm and turn
produced 1 planner call and adherence 1.25 in one run and 3 calls and 0.50 in another, because
the planner writes a different plan each time. **No conclusion here should be drawn from a
single turn**, and the protocol's own n = 2 is the binding limit on what this can say.

## Hypotheses, scored

| # | Hypothesis | Outcome |
| --- | --- | --- |
| 1 | `plan_adherence` = 1.0 in both arms | **Refuted.** 1.0 in one turn of four. |
| 2 | Exactly one planner call per turn | **Partly.** 3 of 4 turns; the exception is the direction conflict. |
| 3 | `continuous` is faster per beat | **Refuted** on this run — it was *slower* per beat in both turns. |
| 4 | `voiced` reuses more prefix cache | **Supported.** 0.40 vs 0.28 mean; `continuous` hit 0.000 on a single-call turn. |
| 5 | Voice distinctness does not differ materially | **Consistent** (0.900 vs 0.929), but unusable while adherence is unmet. |

## What this does not say

- Nothing about which execution arm is better. That question is unanswered and stays open.
- Nothing about beat-length quality. Turn length is now the plan's, and whether the plan
  chooses *well* is a separate question nobody has measured.
- Nothing generalisable beyond `gemma-4-26B-it` on this endpoint.

## Next

1. Decide the direction-versus-plan precedence question (§1). It blocks a clean re-run.
2. Investigate why `continuous` under-renders a plan it was given (§2).
3. Re-run this protocol unchanged once (1) is settled.
