# ISSUES — EXP-2026-08-010 Beat length

## A metric was declared and never computed

The runner imports `METRIC_KEYS` from `run_prose_end_to_end`, which lists `is_distinct` — but
that key is filled in by the sibling runner's own loop from a cross-beat `seen` set, not by
`measure()`. Pointed at this runner it produced an aggregate column with nothing in it.

Caught while reading the results, before anything was written up. `ARM_METRIC_KEYS` now drops
it, and duplicates are counted post-hoc by `analyze_run.py` over the recorded transcript
(**none, in any arm**). An empty column claiming to be a measurement is worse than no column,
and a figure panel drawing it as `0 %` — which the first version of `make_figures.py` did —
would have read as "every beat was a duplicate".

## One discarded beat, and it is not what it looks like

The `short` arm produced one beat of 2,802 characters across 10 paragraphs, cut by the runaway
stop at exactly that tier's ceiling (700 tokens × 4). It inflates `short`'s standard deviation
from 0.41 to 1.74 single-handedly.

It is **not** a long passage. It is the model writing its own scratchpad into the prose —
quoting the narrator prompt's second-person rule back to itself and working through its
instructions in the open, ending mid-audit on *"Final check on 'No reuse': Aldous used: …"*.

Both `emission.starts_mid_sentence` and `emission.names_the_player` return `True` on that
text. Neither fired. The trace records only `degenerate`. **This is a pre-existing guard
defect** — the opening gate judges an opening and then releases the passage, so a leak
arriving after release is invisible to it — and the per-tier ceiling introduced by this change
only made the symptom smaller (2,802 characters rather than the 8,192 it would have reached
before). It is recorded as a follow-up in `RESULTS.md` § 7 rather than fixed here, because
diagnosing it is a separate piece of work from the control this experiment measures.

`RESULTS.md` reports `short` **both ways** — with the beat (the result) and without it (a
labelled sensitivity). It is not excluded from the headline: dropping an inconvenient point is
the move this record exists to prevent.

## The arms are unequally powered

n = 20 / 17 / 15 across `short` / `medium` / `long`. That is not sampling noise — `maxTurns`
caps *emitted beats*, so an arm whose beats are longer fits fewer of them into six turns. The
imbalance is a consequence of the thing being measured, which makes it unavoidable here but
also means the arms are not equally precise.

`short` is additionally the least forgiving arm to score: its band is two paragraphs wide, so
a one-paragraph miss costs it 50 % where the same miss costs `long` 17 %.

## Wall-clock is recorded and not interpreted

Per-turn elapsed time ranged from 68 s to 430 s within this run, on one endpoint, with the
arms interleaved. Interleaving spreads that drift across the arms rather than removing it.
**No latency claim is made from this experiment**, and the prose metrics do not depend on
timing. This endpoint has produced a 66× latency shift traced to a disconnected GPU before.

## Known limitations of the recorded run

- One world, one cast, one genre, one model (`gemma4-26B-mtp`). Nothing transfers without
  re-running, and the sampler/prose findings this builds on were measured on a *different*
  upstream (`qwen38-27B-awq`, EXP-2026-08-007).
- Beats within a session are not independent — each conditions on the last.
- The scripted player lines ship in the runner and are contaminated for held-out use.
- `short`'s stated band (1–2 ¶) does not match its observed floor (2 ¶). The dropdown shows
  the stated band to the reader.
- The read of the passages is unblinded, by the author of the change.
