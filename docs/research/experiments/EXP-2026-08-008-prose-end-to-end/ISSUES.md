# ISSUES — EXP-2026-08-008 Prose end to end

## Earlier runs of this shape were driven before this experiment existed

While `docs/plans/prose-that-reads-like-a-scene.md` was being executed, several multi-turn
live runs were driven to check each fix by reading the output. They were run with
`run_conversation_scaling --mode conversation`, pointed at
`docs/research/experiments/EXP-2026-08-006-turn-latency-overhaul` because that runner
requires an `--experiment` target and no folder for this measurement existed yet.

Two things were wrong with that, and both are disclosed rather than quietly fixed:

1. **It overwrote a completed experiment's record.** `EXP-2026-08-006` was `status:
   complete` on `main` with a recorded finding. Five commits on the prose branch replaced
   its `manifest.yaml`, `data/metrics.{json,csv}` and `logs/conversation.log` with runs
   that had nothing to do with its question, flipping it to `status: failed` and leaving
   its `RESULTS.md` reporting numbers its own data no longer contained. Those four files
   have been **restored from `main`**, and `EXP-2026-08-006` again holds only the runs its
   protocol describes.
2. **The numbers were read from a runner that does not measure prose.** The conversation
   runner records latency and prompt-cache metrics; the prose form was measured by hand
   off the resulting session. Hand measurement is exactly what
   `AGENT_INSTRUCTIONS.md` § 1.4 forbids, which is why
   `utils/scripts/research/run_prose_end_to_end.py` exists.

**None of those runs' numbers are carried into `manifest.yaml`, `data/metrics.json` or
`RESULTS.md` here.** They are development observations, and they are why the hypothesis in
`PROTOCOL.md` is stated in a direction rather than as exploratory. For the record, and
**not to be quoted as a result**, the last two of them observed: 13 beats / 13 distinct /
12 with speech / 12 with breaks, with one beat at 11,998 characters (which is what motivated
tying the runaway stop to the passage allowance); then 10 beats / 10 distinct / 10 with
speech / 10 with breaks, averaging 831 characters — in a run that lost one turn entirely to
a starved first beat, which is what motivated the final commit before this experiment.

## The first attempt at the recorded run was scrapped for a runner bug

The runner's first version read a beat's text off its `done` frame. That is wrong: a
delta-streamed beat re-emits the same `id` with an **incremental** chunk, and
`TurnEmitter.close` sends the final frame as `_frame("", done=True)` — an *empty* string. So
every streamed beat was measured as `""`, and turn 1 scored `speech=0/3` on prose that
plainly contained speech.

The run was killed after turn 1, the runner fixed to accumulate chunks by `id` (and to drop
any beat that never sent a `done` frame rather than score a fragment), and the experiment
re-run from scratch. **No numbers from the scrapped attempt appear anywhere in this
folder.** It is recorded because a run that was started and abandoned is recorded, not
deleted.

The bug came from `CLAUDE.md`, which described delta streaming as re-emitting "with growing
`text`" — `docs/api-contract.md` § Streaming modes had it right the whole time. `CLAUDE.md`
has been corrected in the same change.

## The endpoint changed model between EXP-2026-08-007 and this run

`EXP-2026-08-007` ran entirely on upstream `qwen38-27B-awq` (all 30 recorded rows carry it
in `served_model`). The relay was restarted before this experiment and came back serving a
different upstream. This run is therefore a **generalisation check** of the shipped form on
a second model, not a repeat of the sampler finding on the same one. `RESULTS.md` names the
model that actually served it.

The sampler finding itself has **not** been re-measured on the new model, and
`EXP-2026-08-007`'s own limitations section already says nothing there transfers without
re-running. If the penalties are ever reconsidered, that experiment has to be re-run, not
extrapolated from this one.

## Wall-clock is recorded and not interpreted

Per-turn elapsed time in this run moved by an order of magnitude — 74 s, 129 s, 140 s, then
549 s — while a one-token probe against the same endpoint answered in 0.8 s throughout. This
endpoint has produced a 66× latency shift traced to a disconnected GPU before, and the
upstream was restarted shortly before this run. The prose-form metrics do not depend on
timing, `elapsed_s` is recorded per turn for completeness, and **no latency claim is made
from this experiment.** EXP-2026-08-005 and EXP-2026-08-006 are where turn latency is
measured, under protocols designed for it.

## Known limitations of the recorded run

- **No control arm.** One configuration, observed. Nothing here attributes the result to a
  particular fix.
- **One session, one cast, one genre.** n is beats, not scenarios, and the beats within a
  session are not independent — they condition on each other through the transcript.
- **The scripted player lines ship in the runner** and are contaminated for held-out use.
- **The read of the passages is unblinded**, by the same author who made the changes.
