# ISSUES — EXP-2026-08-006

Everything that went wrong, was worked around, or would mislead a later reader.

## 1. The endpoint's throughput varies 66× on identical work — the run's dominant problem

Discovered *after* the main run, while trying to explain why turn totals had gone up. Six
calls, one fixed prompt, temperature 0, same served model (`qwen38-27B-awq`), **identical
143-token output** in 5/6 — elapsed 1.4 s, 1.8 s, 1.9 s, 14.6 s, 27.6 s, 90.4 s
([`logs/decode.log`](logs/decode.log)).

The prefill control agrees and adds detail: replaying EXP-2026-08-005's layout probe gave
today/yesterday of 1.58/1.27 s, 1.87/1.96 s, 3.91/3.67 s — indistinguishable — then
**30.1 s and 30.3 s** on two prompts that took 1.94 s and 2.22 s yesterday, with the same
cached-token count (4800) ([`logs/layout.log`](logs/layout.log)).

**Consequence:** every wall-clock comparison in this experiment is unusable, and RESULTS.md
says so before it says anything else. The conclusions are restricted to counts, ratios and
structural facts.

**Consequence for the earlier experiment:** EXP-2026-08-005 read its two ~300 s turns as
"the beat planner stalls". That reading is now unsupported — the same endpoint produces
90 s for 143 tokens with no planner involved. Its recorded numbers stand; its causal
explanation should not be repeated.

**Not chased further here.** Why the endpoint behaves this way is a question about the
relay and the GPU host, not about Mytheca, and it is out of scope for this experiment. It
should be the *first* thing investigated before any further latency work on this app,
because it is plausibly larger than everything measured here.

## 2. An inference stated to the user mid-run, then refuted by direct measurement

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

Turns 6 and 8 both reached their first reasoning token at 62.1 s. The near-identical values
initially looked like two structural-call timeouts (2 × 25 s + intent). Given issue 1 that
attribution cannot be made from this data — a single slow decode explains it equally well —
and no separate measurement was taken while the run was reproducible. Recorded as
unexplained rather than assigned a cause.
