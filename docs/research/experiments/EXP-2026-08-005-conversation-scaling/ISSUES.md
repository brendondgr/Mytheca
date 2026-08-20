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

## 2026-08-19 — 3 of 10 turns died mid-turn, and the cause was a bug in the app

**Impact:** turns 1, 2 and 4 of the conversation run terminated early with an error frame,
so their beat counts and totals describe truncated turns. They are kept in the record and
marked; no aggregate is computed over the survivors.
**Cause:** `The model returned an empty response.` The diagnostic logging added during
this experiment identified it: `0 delta(s), 0 raw answer char(s), 0 reasoning char(s),
finish_reason='length'`. The model had spent its entire budget on reasoning — which the
app could not see, because vLLM streams deliberation as `delta.reasoning` while the parser
read only llama.cpp's `delta.reasoning_content`.
**Resolution:** `llm._reasoning_field` now reads both spellings. Note this fixes the
*diagnosis*, not necessarily the failure: a model that spends its whole budget thinking
still produces no prose. Whether the thinking budget is honoured by this vLLM build is a
separate question, measured below.
**Paper implication:** the pre-fix failure rate (3/10) is a property of the app as shipped
on 2026-08-19, not of the model. Quote it as such.

## 2026-08-19 — The layout probe ran against the pre-fix parser

**Impact:** none on `ttft_s`, which is what the layout comparison uses. The probe's
`cached_tokens` was already unavailable on this endpoint, and its reasoning was never part
of the measurement.
**Cause:** the probe process was started before the `_reasoning_field` fix landed and kept
the old module in memory.
**Resolution:** none needed — disclosed rather than silently re-run, since the metric in
question does not touch the affected code path.

## 2026-08-19 — Two milestone marks can share a timestamp, so one shows a zero gap

**Impact:** cosmetic, in the step-gap table only. `first_visible` and `first_narration`
are recorded at the same instant when narration is the first visible frame; sorting puts
one first and it absorbs the whole gap while the other reads 0.0 s.
**Cause:** `_gaps` attributes the interval to whichever of two equal timestamps sorts
first.
**Resolution:** none — accepted. Read `first_visible` as the milestone and ignore the
paired zero.
