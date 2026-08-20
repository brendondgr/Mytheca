# ISSUES — EXP-2026-08-005

## 2026-08-19 — The endpoint under test reports no cache counter

**Impact:** `cached_tokens` / `cache_hit_ratio` are unavailable for any call the relay
routes to a vLLM upstream, so the layout comparison rests on `ttft_s` (a prefill proxy)
rather than on a counter.
**Cause:** `skynet` returns `usage.prompt_tokens_details: null` (observed upstream
`qwen38-27B-awq`). The `local` llama.cpp route does report it. The app is configured with
`skynet`, and the request was explicitly to measure the remote GPU, not `local`.
**Resolution:** none — the runner records the counter when it is offered and falls back to
latency when it is not. Both are written to the log.
**Paper implication:** any cache claim on this endpoint is behavioural. Do not present a
`ttft_s` difference as a measured cache-hit rate.

## 2026-08-19 — `skynet` routes dynamically, so the upstream can change mid-experiment

**Impact:** rows within one run are not guaranteed to have hit the same model, and some
rows carry a `cached_tokens` figure while others do not — which is itself evidence the
route moved.
**Cause:** the relay entry for `skynet` declares `upstream_model: auto`.
**Resolution:** none — this is the deployed condition and the thing being characterised.
Recorded per row.
**Paper implication:** results describe "the deployed skynet route on 2026-08-19".

## 2026-08-19 — A first attempt was stopped after turn 1 and its instrumentation widened

**Impact:** none on the recorded numbers; the aborted run's single turn is not in the
record.
**Cause:** the first runner recorded only three step milestones per turn, which cannot
answer "measure it at every step of the way". It was stopped after turn 1 and extended to
record every step's offset *and* the gap since the previous step, plus per-occurrence
marks for the steps that repeat once per beat.
**Resolution:** re-run from scratch with the wider instrumentation. Disclosed rather than
silently replaced.
**Paper implication:** none.

## 2026-08-19 — The aborted run's beat counter counted thoughts as beats

**Impact:** it reported 6 beats against a `maxTurns` of 5, which reads as the cap being
exceeded. It was not — the counter was wrong.
**Cause:** `internal_thought` was included in the beat tally. A character's thought and
their spoken line are one beat, not two.
**Resolution:** fixed before the recorded run; `internal_thought` still counts toward
"first visible" (it is the first thing a player sees) but not toward the beat cap.
**Paper implication:** none, but it is a reminder that a cap "exceeded" by one is more
often an instrument error than an engine error.
