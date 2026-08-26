# ISSUES — EXP-2026-08-017

Bugs, anomalies, aborted runs, excluded seeds, and anything that could not be
recovered. One entry per issue, newest last. If nothing went wrong, write
"No issues recorded." — do not delete the file.

## YYYY-MM-DD — <one-line summary>

**Impact:** what this does to the numbers. If a seed was dropped, state the new n.
**Cause:** what actually happened.
**Resolution:** what was done about it, or "none — accepted".
**Paper implication:** what the paper must state because of this. Often "none".

## 2026-08-25 — first run abandoned: the arms were not comparable, and why

The run completed all 4 turns, and is discarded anyway. Per-turn rows as measured:

| arm | turn | beats run / planned | adherence | planner calls |
| --- | --- | --- | --- | --- |
| voiced | 1 | 4 / 1 | 4.0 | 2 |
| continuous | 1 | 3 / 3 | 1.0 | 1 |
| voiced | 2 | 9 / 3 | 3.0 | 2 |
| continuous | 2 | 2 / 4 | 0.5 | 1 |

**PROTOCOL § 6 decides this without a judgement call:** `plan_adherence` was not 1.0, so the
answer is "fix the binding first" and no arm comparison is reported. Publishing a
`continuous`-vs-`voiced` result from these rows would be comparing a bound arm against an
unbound one and calling the difference scene flow.

**The defect it found.** `plan_turn` marked a plan `complete` — and therefore binding — only
when the planner appended an explicit `end`. The planner frequently does not. A plan judged
incomplete reverted to the adaptive loop, which re-planned and ran away: **9 beats against 3
planned**, two planner calls. Whether a turn was bound came down to whether the model
remembered a terminator, which is precisely the unreliability the binding exists to remove.

Fixed by asking a question with a dependable answer: **did the plan come from the model, or
from the fallback?** `plan_beats` now reports its source through an out-parameter, and a
model-written whole-turn plan binds whether or not it ends with `end`. The fallback path —
endpoint unreachable, reply unparseable — still does not bind, because binding a single
scripted beat would turn a model outage into a one-beat scene.

**Also visible, and NOT fixed here:** `continuous` turn 2 ran 2 of 4 planned beats
(adherence 0.5) with one planner call, so the script under-rendered a plan it was given.
That is a property of the continuous writer rather than of the binding, it is exactly what
this experiment exists to measure, and changing it before the run would be tuning an arm to
win. Carried into the re-run as a hypothesis rather than patched.

The `voiced` per-turn cache rates (0.26, 0.40) and `continuous`'s (0.56, 0.00) are **not**
carried forward either: they were measured under different planning behaviour per arm.
