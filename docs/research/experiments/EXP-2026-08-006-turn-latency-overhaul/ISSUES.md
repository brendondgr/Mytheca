# ISSUES — EXP-2026-08-006

Everything that went wrong, was worked around, or would mislead a later reader.

## 1. WITHDRAWN — "the endpoint's throughput varies 66× on identical work"

This experiment originally concluded that the inference endpoint was intrinsically unstable
(1.4 s to 90.4 s for byte-identical 143-token output) and that app-side latency work was
therefore unmeasurable. **That conclusion was wrong.** The intended GPU was not connected;
the operator identified this. Repeating the identical probe on the right hardware gave
1.37–4.22 s across 12 runs (mean 1.67 ± 0.78) — stable.

Both logs are kept: [`decode-pass1-uncontrolled.log`](logs/decode-pass1-uncontrolled.log)
(degraded) and [`decode-pass2-idle.log`](logs/decode-pass2-idle.log) (healthy). The claim
C-010 raised from the first is withdrawn in `CLAIMS.md`.

**Two process failures produced this, and they are worth more than the retracted finding:**

* The probe was run to explain an unexpected result, and its output *confirmed* the
  explanation being reached for. Nothing checked whether the machine was the expected one —
  the served model string was verified, the hardware was not.
* It was written up as a claim about the endpoint's nature on the strength of a single
  uncontrolled session. The owner's pushback ("might it be something else running on it?")
  was the control that should have been run first.

The correct reading of the degraded run is much narrower: **it measured the wrong hardware
and its timings say nothing about anything.** Its counter-based results (prompt reuse, cache
hit, planner call counts) stand, because a count does not depend on host speed.

## 1c. The healthy "before" run was interrupted and its log never written

The 10-turn run on healthy hardware *before* the single-deliberation fix was stopped at turn
9 to apply that fix. `run_conversation_scaling` writes its log only at the end, so no log
exists. Its per-turn rows survive in this session's transcript and its step costs in the
`turn_traces` table; the step figures quoted in RESULTS.md ("before: thinking 35.5 s/beat")
come from that query, not from a log file. That is weaker provenance than everything else
here and is flagged rather than smoothed over. Recorded rows:

```
turn 1: first_visible=6.080s  total=97.289s  beats=1  reuse=0.00  plan_calls=2
turn 2: first_visible=28.382s total=111.398s beats=2  reuse=0.80  plan_calls=3
turn 3: first_visible=101.378s total=300.942s beats=3 reuse=0.82  plan_calls=5
turn 4: first_visible=8.841s  total=137.528s beats=5  reuse=0.80  plan_calls=3
turn 5: first_visible=14.831s total=210.358s beats=2  reuse=0.73  plan_calls=5
turn 6: first_visible=20.038s total=99.647s  beats=2  reuse=0.89  plan_calls=3
turn 7: first_visible=22.903s total=111.257s beats=2  reuse=0.93  plan_calls=3
turn 8: first_visible=38.189s total=155.228s beats=2  reuse=0.93  plan_calls=3
turn 9: first_visible=94.578s total=178.165s beats=2  reuse=0.60  plan_calls=3
```

## 2. An inference stated to the user mid-run## 2. An inference stated to the user mid-run, then refuted by direct measurement

While the run was in flight, turn 3's "5 planner calls for 4 beats" was read as *the model
ignoring the multi-beat contract*, and that was said out loud before it was checked. The
direct probe refuted it: 6/6 calls returned a well-formed three-entry `beats` array
([`logs/plan.log`](logs/plan.log)). The actual reason planner calls barely fell is that the
median turn is 2 beats, so there is nothing to look ahead over.

Recorded because the wrong explanation is the more interesting one: it would have led to
"fix compliance with guided decoding", which would have been effort spent on a
non-problem.

## 3. The comparison is between code versions on different days, not arms in one run

The prompt reorder is not flag-gated, so a within-run A/B was not available without adding
a switch that would then have to be maintained. Given issue 1, this is a serious weakness:
day-to-day drift is exactly what cannot be controlled for, and it turned out to be huge.
Any future latency comparison on this app should be run as interleaved arms inside a single
session, or not at all.

## 4. The baseline log and the baseline write-up describe different runs

`EXP-2026-08-005/logs/conversation.log` holds its **post-fix re-run** (10 turns, 0 errors,
two ~300 s turns). The per-turn table in that experiment's RESULTS.md is an **earlier** run
(3 errors, totals 24.6–67.8 s). This experiment compares against the log, which is the
right choice — it is that experiment's final state — but a reader who compares this table
against that document's table is comparing different runs. Called out here and in RESULTS.md
threat 7.

## 5. The manifest was overwritten by later probes

`run_conversation_scaling.py` calls `update_manifest` on every invocation, so the four modes
run for this experiment (`conversation`, `layout`, `decode`, `plan`) each rewrote the
`code`/`status`/`n_runs`/`compute` block in turn. The manifest was authored by hand
afterwards to describe the experiment as a whole, with `n_runs` covering the primary
conversation run. The per-mode entrypoints are all recorded in their own log files.

## 6. The quality read is not a measurement

The prompt reorder moved identity and voice samples from primacy to recency. The output was
read across all ten turns and showed no obvious regression — but that is n = 1, unblinded,
and by the author of the change. It is reported as a read, not a result. The blinded
matched-scene comparison that would settle it has not been run.

## 7. Two turns showed ~62 s before the character call started

Turns 6 and 8 of the degraded run both reached their first reasoning token at 62.1 s. That
run measured the wrong hardware, so no cause can be assigned and none is. Not reproduced on
healthy hardware: the worst pre-character delay there was 29.5 s.

## 8. The interleaved planner A/B was built but not run

With the character beat fixed, the planner is now 56 % of turn time. Whether asking it for
three beats costs more per call than it saves is the obvious next question, and `--mode plan`
implements it as interleaved 1-vs-3 arms in a single session — the methodology issue 3 says
is required. It was not run to completion. Recorded as unfinished rather than left implied.
