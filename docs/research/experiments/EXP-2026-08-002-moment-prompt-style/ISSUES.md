# ISSUES — EXP-2026-08-002

Bugs, anomalies, aborted runs, excluded seeds, and anything that could not be
recovered. One entry per issue, newest last. If nothing went wrong, write
"No issues recorded." — do not delete the file.

## 2026-08-11 — Two ad-hoc generations preceded the recorded run

**Impact:** none on the numbers. They are **not** in `n = 3` and contributed no metric.
Two images were generated while the feature was being built — one by `curl` against the
dev backend, one by clicking **Go** in the browser — against the developer's own dev
database (the `embergate` session), not the scripted scene. Both produced landscape
1216×832 WebPs with no cast name in the prompt, which is what prompted writing the
recorded protocol rather than stopping there.
**Cause:** development happened before the experiment folder existed.
**Resolution:** none — accepted, and disclosed here rather than folded into the run.
**Paper implication:** none. If either is ever cited, it must be cited as a
development observation, not as a measurement.

## 2026-08-11 — The keep-alive heartbeat named the wrong stage

**Impact:** none on the numbers (the metrics do not read stage frames), but it is the one
real defect this session's live runs exposed. During the first ad-hoc generation the
stream emitted `stage: "render"` ticks while the *prompt* was still being written, so the
UI would have said "Still painting…" during a stage that had not begun.
**Cause:** the route passed a fixed keep-alive frame to `with_keepalive` instead of one
derived from the stage actually running.
**Resolution:** fixed in `web/backend/app/routes/play.py` (the heartbeat now mirrors the
last stage yielded) and covered by
`utils/tests/backend/api/test_play_moment.py::test_the_keepalive_heartbeat_names_the_stage_actually_running`.
The recorded run post-dates the fix.
**Paper implication:** none.

## 2026-08-11 — Token counts unavailable

**Impact:** `llm.total_input_tokens` / `total_output_tokens` are recorded as 0 and should
be read as **unknown**, not as zero. Cost and token-efficiency comparisons are therefore
not possible from this record.
**Cause:** the local relay returned no `usage` block on these completions, and the
moment agent calls `llm.chat_complete` (which discards usage) rather than
`chat_complete_usage`.
**Resolution:** none — accepted for a verification run.
**Paper implication:** any future cost claim needs the usage-reporting call path.
