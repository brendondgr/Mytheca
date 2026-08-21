# PROTOCOL — EXP-2026-08-009 Second person

> Pre-registered before the run, after `EXP-2026-08-008` exposed the defect. The comparison
> is **before/after across two runs**, not two arms of one run — see § Threats, because that
> is this design's main weakness and it is not a small one.

## Question

`EXP-2026-08-008` found that **13 of 18 character beats and 6 of 10 narration beats** called
the person in the room *"the player"*. The cause was located in the prompt: both
`character_turn_agent._transcript` and `narrator_agent._transcript` labelled the human's line
`Player:`, and that label was the only name either prompt gave to a person present in the
scene.

**Does relabelling the line `You:`, and asking both prompts for the second person, stop it —
without costing the prose form that EXP-2026-08-008 showed was working?**

The second half of the question is the point. A change that removes the leak by making the
passages worse is not a fix, and the six form metrics are carried over unchanged so that a
regression in any of them is visible rather than invisible.

## Hypothesis

Stated ahead of the run. **The leak goes to zero or near it, and no form metric regresses.**

The label was the mechanism, so removing it removes the supply. Predicted:

- `names_the_player` falls from **0.72 ± 0.45** to **≤ 0.10** over character beats,
- narration naming the player falls from **6/10** toward zero,
- `has_speech` stays at **1.0**, `paragraph_breaks` stays at or above **2.28 ± 0.45**,
  `is_distinct` stays at **1.0**, `is_scratchpad` and `starts_mid_sentence` stay at **0.0**,
- discards stay in single figures.

A plausible way for this to be wrong: `You:` is ambiguous in a transcript where a character
also reads their *own* past lines. If a character mistakes `You:` for themselves, the beats
will answer the wrong speaker — which would not show up in any metric here and has to be
caught by reading the passages. That check is part of the procedure, not an afterthought.

A second: the narrator has **no regeneration seam** — narration delta-streams from its first
token by design, because it is the first thing a new player sees. Its only defence is the
prompt, so if the prompt rule is weak, narration will leak while character beats do not.

## Setup

Identical to `EXP-2026-08-008` in every respect except the change under test — **the same
runner** (`run_prose_end_to_end`, pointed at this folder; a second copy of it would be a
second thing to keep in step and the first would rot), same throwaway world (`Salt and Ledgers`; Mei / Kira / Aldous; `maxTurns` 5,
`suggestionsCount` 0, `contextBeats` 100), same six scripted player lines, same backend at
its committed settings.

**The change under test** (commit `78cd532`):

| | Before (EXP-2026-08-008) | After (this run) |
| --- | --- | --- |
| Transcript label for the player's line | `Player:` | `You:` |
| Character contract | "never write about … the player" | names the label, requires second person |
| Narrator prompts (short + long) | silent on it | names the label, requires second person |
| Opening gate | — | `emission.names_the_player` at `SCRATCHPAD_WINDOW` |

**Model.** Recorded per run from a completion's `model` field. `EXP-2026-08-008` ran on
upstream `gemma4-26B-mtp`. If this run is served by a different upstream, the comparison is
confounded and `RESULTS.md` must say so rather than report a difference.

## Data

The beats of a fresh six-turn session. `narration` is recorded and scored for the leak but
excluded from the form aggregate, exactly as before (it is third person and forbidden
dialogue).

## Metrics

`EXP-2026-08-008`'s metrics verbatim — that is what makes the two runs comparable — with
`names_the_player` now recorded by the runner rather than post-hoc.

| Metric | Definition | Direction |
| --- | --- | --- |
| `names_the_player` | **Primary.** Beat contains "the player"/"the user" (`emission.names_the_player`, whole passage). | lower is better |
| `has_speech` | Beat contains ≥1 paired run of double quotes. | must not regress |
| `paragraph_breaks` | Count of `\n\n`. | must not regress |
| `is_distinct` | Beat is not byte-identical to an earlier beat in the session. | must not regress |
| `sentences_per_100_words` | `.`/`!`/`?` ÷ words × 100. | must not regress |
| `is_scratchpad`, `starts_mid_sentence` | The existing guards' detectors. | must stay 0 |
| `chars` | Length. Context, not a target. | neither |
| discards | Trace beats flagged `scratchpad`/`dropped`/`degenerate`/`skipped`. | lower is better |

Whole passage, not the opening window: 12 of the 13 leaks in `EXP-2026-08-008` were
mid-passage, and measuring only what the gate can see would have reported the defect as one
beat in eighteen.

## Baselines

`EXP-2026-08-008`, cell for cell. Its numbers are read out of its recorded
`manifest.yaml` / `data/leak.json`, not retyped.

## Procedure

```bash
uv run python app.py backend    # must answer twice before the run starts
uv run python -m utils.scripts.research.run_prose_end_to_end \
  --experiment docs/research/experiments/EXP-2026-08-009-prose-second-person --turns 6
```

Then **read every passage** in `logs/transcript.json`, specifically for the `You:` ambiguity
named in the hypothesis. If any turn fails, no aggregate is computed and the per-beat rows
are the result (the `EXP-2026-08-001` rule).

## Analysis

Mean ± population standard deviation per metric over character beats, reported beside
`EXP-2026-08-008`'s cell. No significance test: n = 18-ish beats from a single session, the
beats are not independent, and the predicted effect on the primary metric is 0.72 → ~0. If
the effect is large the test adds nothing; if it is marginal, this design cannot adjudicate
it and a test would only dress that up.

## Threats to validity

- **This is a before/after across two runs, not a controlled A/B.** Everything else was held
  fixed deliberately, but the two runs are separated in time on an endpoint that hot-swaps
  its upstream and whose latency moved 7× *within* the baseline run. A true arm-level test
  would run both labels interleaved in one session, which the turn engine cannot do without
  a config seam that does not exist. **This is the weakest part of the design and the
  result should be read as strong evidence only if the effect is near-total.**
- **Sampling.** One session, one cast, one genre, one model. n is beats, and beats within a
  session condition on each other.
- **Under-powered for rare failures.** Six turns can show a defect that occurs in 70 % of
  beats has gone; it cannot show one occurring in 2 % has.
- **The guard and the metric share an implementation.** `emission.names_the_player` both
  gates the opening and scores the run. It cannot mark a beat it discarded, so a leak that
  the gate catches is invisible to the metric — which is why **discards are reported
  alongside it** and why a non-zero discard count changes the reading.
- **Regex proxy.** "Refers to the player as a production object" is approximated by two
  phrases. A model that invents a third way to do it will pass.
- **Unblinded read**, by the author of the change.
