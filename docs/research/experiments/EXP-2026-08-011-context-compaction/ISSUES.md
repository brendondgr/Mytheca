# ISSUES — EXP-2026-08-011

Written during and after the run. `PROTOCOL.md` is not edited to match what was learned;
that is what this file is for.

## 1. H1 is stated backwards, and the run exposed it

`PROTOCOL.md` states H1 as *"with compaction on, a late-scene player line referring to a fact
established before the verbatim window will be answered consistently more often than with
compaction off."*

**That comparison cannot come out the way it is written, and I should have seen it before the
run.** Arm A is a *fixed 100-beat window* — at this experiment's scale (10 turns, roughly 25
beats) the planted fact never leaves arm A's verbatim context at all. Arm A is therefore not
"compaction off with the fact dropped"; it is "the fact is still being read verbatim". A
control that keeps everything will win a recall comparison by construction.

The first row confirms it: **arm A scored 0.778 and hit.** That number says the probe works,
not that compaction failed to help.

**The question the design actually answers** — and the one it should have been written to ask —
is not "does B beat A" but **"does B match A while reading far less?"** Arm B's window is fitted
to a 4096-token context (≈1600 tokens of transcript), so the plant *does* fall out of it; if
arm B still answers the probe, the summary is what carried the fact. That is the useful result,
and it is the one `RESULTS.md` reports.

The falsification criterion that survives is therefore: **arm B failing the probe that arm A
passes** means compaction did not preserve the fact. H2 and H3 are unaffected.

This is recorded rather than fixed in place because the protocol is the pre-registration. Any
follow-up run should state H1 as an equivalence, and should push arm A past its own window
(more turns, or a smaller fixed `contextBeats`) so the two arms are genuinely comparable on
recall.

## 2. Run 1 did not exercise the treatment at all — it is a failed run

**`recap_calls: 0` in arm B.** Compaction never fired once, so run 1 tested "fitted window,
compaction available but never triggered" against "fixed window". It is **not** a result about
compaction and must not be read as one.

The cause is arithmetic I should have checked before spending 27 minutes on it.
`history_compaction.maybe_compact` deliberately waits for a **whole anchor block** to fall out
of the window (`fit.dropped_beats >= TURN_TRANSCRIPT_ANCHOR_BLOCK`, 20) — compacting on every
beat that falls off would cost a model call per turn *and* move the summary line on a turn the
window did not re-anchor, breaking the prompt-cache prefix twice instead of once. That is the
right behaviour. But a 10-turn scene at `maxTurns: 2` produces roughly 20 beats **in total**,
so 20 beats can never *drop*. The scene was shorter than the threshold.

Both arms scoring an identical `probe_score: 0.778` is consistent with this: neither arm lost
the fact, because neither arm dropped it.

Recorded rather than quietly re-run: the same dead end is exactly what this file exists to stop
someone walking into twice. **Run 2 raises the turn count so the window is genuinely exceeded**;
its parameters are in `manifest.yaml` and its result — whatever it is — is what `RESULTS.md`
reports.

Run 1's rows, kept:

| Arm | probe_score | hit | prompt_tokens_mean | reusable_prefix_share | recap_calls | s/turn |
| --- | --- | --- | --- | --- | --- | --- |
| A (fixed 100) | 0.778 | yes | 2963.6 | 0.7094 | 0 | 80.4 |
| B (auto)      | 0.778 | yes | 2541.9 | 0.6275 | **0** | 79.8 |

The one thing run 1 does establish, weakly and at n=1: the **fitted** window is cheaper than a
fixed 100-beat one (2542 vs 2964 mean prompt tokens) without losing the probe. That is a result
about Phase 3, not Phase 4, and it is n=1.

## 3. Scale is small, and deliberately so (run 1; run 2's is §7)

`--scenes 1 --turns 10` is **one scene per arm**. At roughly 80 s per turn on this hardware, a
scene costs about 13 minutes; the fuller design in `PROTOCOL.md` (2+ scenes per arm) is hours.
n=1 per arm supports **no** claim about a rate. The rows are reported individually and the
aggregate block, where present, is a restatement of two numbers rather than a statistic.

## 4. Uncommitted changes at run time

`code.dirty: true` in the manifest. The run was started from the working tree of the same
commit series that introduced compaction, before the phase's final commit. The relevant code
paths (`services/context_budget`, `services/history_compaction`, `agents/recap_agent`) were
unchanged between the run's start and the recorded commit.

## 5. The configured model was down; the run is on a different one

The endpoint's configured alias `skynet` was unreachable for the whole of 2026-08-22 — the
relay reported itself healthy, routed the alias to `auto`, and returned 503 after seven
minutes. The app was pointed at the relay's `local` model (**gemma-4-26B-it**) and both arms
ran on it, interleaved, in one process.

This is exactly the drift `docs/checklist.md` warns about and the reason the arms alternate
inside one run: the comparison here is between two configurations on one model on one
afternoon, and it is not comparable to EXP-2026-08-007 (`qwen38-27B-awq`) or EXP-2026-08-008
(`gemma4-26B-mtp`). The manifest records the model actually served, not the one configured.

## 6. Run 2 found a defect in the thing it was measuring

`maybe_compact` gates on `fit.dropped_beats < block` — beats dropped **in total**, not beats
dropped **since the last summary**. Once a block has ever fallen out of the window the gate
never closes again, so the summary is rewritten on almost every subsequent turn: 16 rewrites
over 30 turns, folding 20 beats, then 9, then 2 and 3 repeatedly, against the 4 that H2
predicted. The comment immediately above the condition describes the intended behaviour
correctly, which is how it read as right.

Consequences for how this experiment may be cited:

- The **16 rewrites** and the **44.6 % reusable prefix** are honest measurements of the code at
  `code.commit`, and they are what H2 was falsified by. They are **not** measurements of
  "compaction bounded to one call per anchor block" — that design has never been run.
- The **H1 result is unaffected**. What the summary retained is a property of the recap agent's
  output, not of how often it was called; if anything, summarising more often should favour
  arm B's recall, and it still lost the fact.

The fix is recorded as a follow-up in `RESULTS.md` §7 and in `../../OPEN_QUESTIONS.md` rather
than applied inside this folder: a completed experiment is append-only, and code that changes
after the run belongs to the next run, not this one.

## 7. Run 2's scale, and what it cost

`--scenes 1 --turns 30`, both arms complete, `failed: 0`. Arm A took 87.9 min and arm B 52.8
min — 140.6 min of local inference for **two rows**. The protocol's fuller design (2+ scenes per
arm) is most of a day on this hardware, and the honest reading of that is in `RESULTS.md` §5:
this experiment is under-powered, deliberately, and says so rather than dressing two numbers as
a rate.
