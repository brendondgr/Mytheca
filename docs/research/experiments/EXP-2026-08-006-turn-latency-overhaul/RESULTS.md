# RESULTS — EXP-2026-08-006 Turn latency overhaul

**Status:** complete · 10 turns, 0 ended early · 2026-08-20
**Endpoint:** the relay at `localhost:4000`, model `skynet` (observed upstream `qwen38-27B-awq`)
**Config:** `maxTurns = 5` · `suggestionsCount = 0` · `contextBeats = 100`
**Baseline:** [EXP-2026-08-005](../EXP-2026-08-005-conversation-scaling/), same endpoint, same config, one day earlier.
**Every number below is read from [`logs/`](logs/) by [`tables/make_tables.py`](tables/make_tables.py) and [`figures/make_figures.py`](figures/make_figures.py).**

---

## Read this first: most of the wall-clock numbers here are not usable

A control probe run immediately after the main run settles it. Same model, one fixed
prompt, temperature 0, six runs — the model produced **identical output** (143 completion
tokens, `finish_reason: stop`) in five of six, and took:

| run | completion tokens | elapsed | rate | served model |
| --- | --- | --- | --- | --- |
| 1 | 143 | 14.6 s | 9.8 tok/s | `qwen38-27B-awq` |
| 2 | 143 | **1.4 s** | 104.6 tok/s | `qwen38-27B-awq` |
| 3 | 143 | 27.6 s | 5.2 tok/s | `qwen38-27B-awq` |
| 4 | 143 | 1.9 s | 75.9 tok/s | `qwen38-27B-awq` |
| 5 | 143 | **90.4 s** | 1.6 tok/s | `qwen38-27B-awq` |
| 6 | 138 | 1.8 s | 78.7 tok/s | `qwen38-27B-awq` |

**A 66× spread on byte-identical work, on one model, within a few minutes.** The prefill
control agrees: replaying EXP-2026-08-005's layout probe today gave 1.58 / 1.87 / 3.91 s
against yesterday's 1.27 / 1.96 / 3.67 s at the same three sizes — unchanged — and then
**30.1 s and 30.3 s** on two prompts that took 1.94 s and 2.22 s yesterday, with an
*identical* cached-token count (4800).

So: **any before/after comparison of seconds between EXP-2026-08-005 and this run is
uninterpretable**, in either direction. The conclusions below are restricted to metrics
that are counts, ratios, or structural facts — things this variance cannot fake. Where a
hypothesis was about seconds, it is marked **not testable here** rather than answered.

This also reframes the baseline. EXP-2026-08-005 attributed two 300 s turns to "the beat
planner stalls". On this evidence that is more likely the same endpoint behaviour reaching
the timeout, not a planner-specific defect. That experiment is not withdrawn — its
per-turn numbers stand as recorded — but its causal reading of the stalls should be treated
as unsupported.

---

## Headline

1. **The prompt cache now works, and this is measured with counters, not clocks.**
   Reusable prefix climbs **72 % → 90 %** across the scene and the server's own hit counter
   reads **62–77 %**, against a baseline that decayed **44 % → 17 %** and reused nothing but
   the 800-token system message. **H3 supported.**
2. **The continuity guard's cost is gone** — 72.3 s over 6 calls in the baseline, a step
   that no longer exists. **H2 supported as a structural fact**; its magnitude is not
   re-measurable here.
3. **Multi-beat planning works but barely pays at this scene configuration.** The model
   honours the contract **6/6** when asked for three beats — but the median turn is **2
   beats** in both runs, so there is almost nothing to look ahead over. Planner calls fell
   only **34 → 27**. **H1 not supported as stated**, for a reason that is not the model's
   fault.
4. **No turn reached the generation timeout** (worst 172 s against the baseline's 355 s),
   and **0 of 10 turns ended early** in both runs.

![overhaul](figures/overhaul.png)

## Per turn

Full table: [`tables/per-turn.md`](tables/per-turn.md).

| turn | prompt tokens | prompt reuse | server cache hit | beats | planner calls |
| --- | --- | --- | --- | --- | --- |
| 1 | 1771 | 0 % | — | 3 | 1 |
| 2 | 2585 | 72 % | 31 % | 2 | 1 |
| 3 | 3404 | 72 % | 71 % | 4 | 5 |
| 4 | 3582 | 79 % | 67 % | 1 | 2 |
| 5 | 4183 | 79 % | 76 % | 3 | 5 |
| 6 | 4702 | 79 % | 68 % | 1 | 2 |
| 7 | 4669 | 88 % | 69 % | 2 | 3 |
| 8 | 4771 | 90 % | 67 % | 1 | 2 |
| 9 | 5179 | 85 % | 62 % | 2 | 3 |
| 10 | 5369 | 87 % | 74 % | 2 | 3 |

Turn 1's 0 % is correct and not a gap: it is the first character call of the session, so
there is no previous prompt to share a prefix with.

The shape of the reuse column is the whole finding. In the baseline the equivalent column
went **down** every turn as the prompt grew, because only the fixed system message could
ever be reused. Here it goes **up**, because the transcript — the part that grows — is now
inside the reusable region, and the block-anchored window stops its first line from moving.

## Where a turn's time goes

Full table: [`tables/step-costs.md`](tables/step-costs.md). **Shares are comparable;
absolute seconds are not** (see the variance section above).

| step | before: share, calls | after: share, calls |
| --- | --- | --- |
| beat planner (`plan`) | 66 %, 36 calls | 25 %, 30 calls |
| continuity guard (`consistency`) | 7 %, 6 calls | **step no longer exists** |
| end-of-turn reflection | 6 %, 10 calls | 21 %, 10 calls |
| reading the player's line (`intent`) | 4 %, 10 calls | 9 %, 10 calls |

Even the shares deserve care: they are shares of a total that the endpoint's variance also
distorts. The one reading that survives is **compositional** — the guard's share is gone,
and reflection is now the largest single non-planner cost. Reflection was deliberately left
untouched in this work; if it is revisited, `TURN_ASYNC_FINALIZE` already exists to move it
off the request path.

`intent` is worth naming as the internal control that first exposed the variance: its
prompt is byte-identical between the two runs (roster + the same scripted player line, no
transcript), and it went from 3.7 s to 8.2 s per call. Nothing in this change set touches
it. A fixed prompt taking twice as long is the endpoint, not the app.

## Multi-beat planning: the mechanism works, the configuration does not use it

The conversation run alone would have suggested the model ignores the multi-beat contract.
A direct probe says otherwise — six calls asking for three beats, six `{"beats": [...]}`
replies with three entries each ([`logs/plan.log`](logs/plan.log)). That metric is a
**count**, so the throughput variance cannot touch it.

The real reason is in the per-turn table: **median 2 beats per turn, in both runs.** Each
turn also needs one final planner call that returns `end`, so with 10 turns at least 10 of
the 27 calls are unavoidable. Productive planner calls fell 24 → 17. Looking three beats
ahead cannot save calls on a turn that only ever has one or two.

This is a finding about the *scene configuration*, not the mechanism: lookahead should pay
progressively more as `maxTurns` rises and turns get longer. At `maxTurns = 5` with this
cast it mostly does not. Recorded rather than tuned — changing `maxTurns` to make a
measurement look better would be measuring the wrong thing.

## What the player actually waits for

Median time to the first *thinking* on screen was **8.25 s** against **14.84 s** to the
first word of prose, so live reasoning does roughly halve the blank wait. Two caveats,
both important:

* Both numbers are seconds, so both are contaminated. The *ratio* is more defensible than
  either value.
* 8.25 s is far from the ~0.4 s EXP-2026-08-003 measured for a first reasoning token. That
  figure was a single isolated call; here the number includes everything before the
  character call starts — reading the message and planning the beat. Live reasoning covers
  the *generation* wait, not the pre-generation one.

## Writing quality after the reorder

The reorder moved the speaker's identity and voice samples from the front of the prompt to
the back. **This was read, not assumed.** Across the ten turns the transcript stays in
voice: characters remain distinguishable, keep their roles and manner, and the beats follow
from the player's line. No case appeared of a character adopting another's voice, losing
their role, or addressing the player as a system.

Stated honestly, this is a **read, not a measurement**: n = 1 scene, unblinded, by the
author of the change. It is enough to say "no obvious regression" and not enough to say
"quality is unchanged". A blinded comparison against the old ordering on matched scenes is
the experiment that would settle it, and it has not been run. Given C-001's status in
`CLAIMS.md` — the voice-distinctness claim is itself unsupported — this is consistent with
the rest of the record rather than a new gap.

## Hypotheses, judged

| | Prediction | Verdict |
| --- | --- | --- |
| H1 | Planner share below 25 %, call count down ~3× | **not supported** — 25 % share but calls only 34 → 27; the mechanism complies 6/6, the scene has too few beats to exploit it |
| H2 | The guard's 11 % is gone | **supported structurally** — the step does not exist; the baseline's 72.3 s over 6 calls is removed |
| H3 | Reuse above 60 % from turn 3, not decaying | **supported** — 72 % → 90 %, rising; server hit 62–77 % vs 44 % → 17 % |
| H4 | No turn near 300 s | **supported** — worst 172 s; but see the variance section, a 90 s decode on 143 tokens was observed directly |
| H5 | Reasoning frames appear and land far ahead of prose | **supported** — median 8.25 s vs 14.84 s, though not the ~0.4 s of an isolated call |
| — | Wall-clock improvement | **not testable here** — the endpoint varies 66× on identical work |

## Threats to validity

1. **The endpoint's throughput is not stable** — 1.4 s to 90.4 s on identical work. This is
   the dominant threat and it invalidates every cross-run timing comparison. It is written
   up first rather than last for that reason.
2. **The arms are code versions measured on different days**, not a within-run comparison,
   so nothing controls for drift in the endpoint, the machine, or anything else running on
   it. A flag-gated A/B inside one run would have avoided this; the prompt reorder is not
   flag-gated, so it was not available.
3. **The relay routes `skynet` with `upstream_model: auto`.** The decode control confirms
   `qwen38-27B-awq` was served on all six runs, but nothing pins it for the conversation
   run itself.
4. **One prompt, one conversation, one run per arm.** No repetition, so a single-turn
   outlier cannot be separated from noise.
5. **`beats` varies 1–4 per turn**, so `total_s` is not comparable turn to turn.
6. **The quality read is unblinded, n = 1, by the author.** See above.
7. **The baseline log is the post-fix EXP-2026-08-005 re-run** (10 turns, 0 errors, two
   ~300 s turns), not the earlier run whose table appears in that experiment's RESULTS.md.
   That is the correct comparison — same code as its final state — but the two tables in
   the two documents describe different runs, which is a trap for a later reader.
