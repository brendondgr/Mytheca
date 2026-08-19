# ISSUES — EXP-2026-08-003

Bugs, anomalies, aborted runs, excluded seeds, and anything that could not be
recovered. One entry per issue, newest last. If nothing went wrong, write
"No issues recorded." — do not delete the file.

## 2026-08-19 — One exploratory turn was timed before the protocol was pre-registered

**Impact:** none on the recorded numbers. The exploratory measurement is not in
`data/metrics.json` and is not cited anywhere.
**Cause:** a single live turn was run against `POST /api/play/salt/turn` while verifying
that the deployed backend had picked up the change, and its frame timings were read off
the stream (`reading` trace at 0.57 s, first narration delta at 7.54 s, 61.5 s total). It
happened before `PROTOCOL.md` was written.
**Resolution:** none — accepted, and disclosed here rather than quietly folded in. It
informed the choice of arms, which is exactly the influence a pre-registration is meant to
make visible. That turn used the deployed `skynet` model on a narrator prompt, so it is not
comparable to the recorded arms in any case.
**Paper implication:** none, provided no number from it is reported as a result.

## 2026-08-19 — A 2-run pilot preceded the recorded 5-run

**Impact:** the pilot's numbers were overwritten by the recorded run and are superseded.
**Cause:** the runner was smoke-tested at `--runs 2` to confirm it drove the real endpoint
and wrote a well-formed manifest before committing to the full wall clock.
**Resolution:** none — accepted. The pilot showed the same qualitative pattern the recorded
run reports (reasoning early, answer late), which is noted here so it is on record that the
finding was not a single-run artefact.
**Paper implication:** none.

## 2026-08-19 — The model under test is not the one the app is configured with

**Impact:** these numbers characterise the relay's `local` upstream
(llama.cpp · `gemma-4-26B-it`), not the deployed configuration.
**Cause:** the app's configured model id is `skynet`, whose relay entry declares
`upstream_model: auto` — its routing can change between calls, which would make a latency
comparison across arms meaningless.
**Resolution:** the model is pinned to `local` and the substitution is stated in
`PROTOCOL.md` and `RESULTS.md`. Not silently swapped.
**Paper implication:** any claim drawn from this must be scoped to one upstream. It says
nothing about how a differently-shaped model (one that thinks less before answering) would
behave — and the central finding here is *specifically* about the shape of the
think-then-answer split, so that scope limit is load-bearing, not boilerplate.

## 2026-08-19 — Arm order is fixed, and confounded with the result

**Impact:** the cross-arm wall-clock and completion-token comparisons are unreliable. The
H2 finding (first reasoning token at 0.55 s vs first answer token at 10.59 s) is unaffected,
because it is a within-call comparison inside a single run.
**Cause:** the runner executes `blocking-uncapped → blocking-capped → streaming-capped` in
that order on every run, so anything that warms across a run — llama.cpp prompt-prefix
cache, page cache, thermal state — systematically favours the later arms. The observed
wall-clock ordering matches arm order exactly, which is what a warming effect looks like.
**Resolution:** none in this run — disclosed in RESULTS.md rather than silently corrected.
A rerun should counterbalance or randomise arm order inside
`utils/scripts/research/run_live_turn_visibility.py`.
**Paper implication:** no cross-arm latency number from this experiment may be reported as
a treatment effect. Only the within-call reasoning-vs-answer gap is citable.

## 2026-08-19 — `completion_tokens` is measured on a second, untimed call

**Impact:** token counts and timings describe different generations, identically
parameterised. At temperature 0.7 they are not the same sample.
**Cause:** `chat_complete_usage` returns prompt tokens only, and widening a production
signature for a measurement was judged worse than issuing a repeat request.
**Resolution:** none — accepted and stated in RESULTS.md §Threats.
**Paper implication:** do not pair a token count with a wall clock from the same row as
though they came from one call.
