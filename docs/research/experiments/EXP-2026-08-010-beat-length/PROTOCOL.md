# PROTOCOL — EXP-2026-08-010 Beat length

> Pre-registered before the run. No pilot: the control was built, the tests passed, and this
> is the first time its output has been measured.

## Question

`beat_length` is a new per-scenario control over how much a character says in one beat —
short 1–2 paragraphs, medium 2–4 (default), long 5–6, each paragraph at most 3–4 sentences
not counting quoted dialogue. It works by stating a paragraph count in the character prompt's
recency TAIL, with a per-tier token allowance behind it as a backstop.

**Do the three tiers actually separate on paragraphs per beat — and does the control cost
anything in the prose form that EXP-2026-08-009 showed was working?**

The second half matters as much as the first. A control that produces short beats by
producing *worse* beats is not the feature the owner asked for.

## Hypothesis

Stated ahead of the run, and **its outcome is genuinely not known**.

A countable length target has already failed on this codebase. EXP-2026-08-007 §
"Secondary finding" records that a "usually 80–200 words" instruction moved the average
passage *up* rather than down. A model cannot count words while writing, so a numeric target
reads to it as a description of a register — long, careful prose — and it obliges.

**The bet:** a paragraph count is different in kind, because it names an axis the model is
already controlling deliberately (`paragraph_breaks` measured 3.89 ± 1.29 in
EXP-2026-08-009, i.e. it produces them on purpose and consistently).

Predicted:

- **paragraphs per beat separates in order**: `short` < `medium` < `long`,
- `short` lands at or below 2, `long` at or above 5,
- `chars` follows the same ordering,
- **no form metric regresses at any tier**: `has_speech` stays at 1.0, `is_distinct` at 1.0,
  `is_scratchpad` / `starts_mid_sentence` / `names_the_player` at 0.0,
- discards stay in single figures at every tier.

**A plausible way for this to be wrong**, and the one the prior evidence points at: the arms
overlap, because the directive is ignored the way the word target was. The token allowance
would then be doing all the work, which enforces a tier by cutting a passage off
mid-sentence — a worse feature, and it would be reported as one rather than shipped quietly.

**A second:** `long` (5–6 paragraphs) is *longer* than anything shipped before this control
(2.28–3.89 paragraphs measured). If `long` regresses on the form metrics while `short` and
`medium` do not, the ceiling rather than the floor is the problem.

## Setup

**A real interleaved arm test, which no previous prompt comparison in this record could
be.** Because the tier is per-scenario, one world holds three scenarios differing in
`beat_length` and in nothing else — same storyline, same cast (Mei / Kira / Aldous), same
setting, same `maxTurns` 5 / `suggestionsCount` 0 / `contextBeats` 100, same six scripted
player lines. The runner asserts every setting landed before playing a turn.

The runner walks them **turn by turn**: short turn 1, medium turn 1, long turn 1, short turn
2, … so a drift in endpoint state spreads across the arms instead of landing on whichever ran
last. EXP-2026-08-009 had to be a before/after across two runs for want of exactly this
seam, and named that as its main weakness; this experiment is the seam existing.

**Model.** Recorded per run from a completion's `model` field, not from the relay's
`/v1/models` (which reports `upstream_model: auto` for a hot-swapping alias).

## Data

The character beats of three six-turn sessions. `narration` is recorded in the transcript but
**excluded from the aggregate**: it is third person, forbidden dialogue, and — importantly —
**not governed by `beat_length` at all**, so including it would dilute the effect under test.

## Metrics

| Metric | Definition | Direction |
| --- | --- | --- |
| **paragraphs per beat** | `paragraph_breaks + 1`. **Primary** — it is the unit the control is stated in. | separates by tier |
| `chars` | Beat length. Secondary; expected to follow the ordering. | separates by tier |
| `has_speech` | Beat contains ≥1 paired run of double quotes. | must not regress |
| `is_distinct` | Not byte-identical to an earlier beat in its session. | must not regress |
| `is_scratchpad`, `starts_mid_sentence`, `names_the_player` | The existing guards' detectors. | must stay 0 |
| `sentences_per_100_words` | Run-on measure, carried over for comparability. | must not regress |
| discards | Trace beats flagged `scratchpad` / `dropped` / `degenerate` / `skipped`. | lower is better |

Paragraphs is primary rather than `chars` because it is what the owner set: a tier that hit a
character count while producing one block of text would satisfy `chars` and fail the feature.

**In-range share** — the fraction of beats falling inside the tier's stated band (1–2 / 2–4 /
5–6) — is reported alongside the mean. A mean of 3 could be "every beat at 3" or "half at 1
and half at 5", and only the first is a working control.

## Baselines

EXP-2026-08-009, which measured the same session shape with no length control at all:
`paragraph_breaks` 3.89 ± 1.29 (so ≈ 4.89 paragraphs), `chars` 1292 ± 378, `has_speech` 1.0,
`is_distinct` 1.0, guards at 0.0. Read out of its recorded files, not retyped.

## Procedure

```bash
uv run python app.py backend    # must answer twice before the run starts
uv run python -m utils.scripts.research.run_beat_length \
  --experiment docs/research/experiments/EXP-2026-08-010-beat-length --turns 6
```

Then **read the passages** in `logs/transcript.json` — specifically whether a `short` beat
reads as a deliberate short beat or as a truncated long one, which no metric here can tell
apart.

**If any turn fails, no aggregate is computed** and the per-beat rows are the result (the
`EXP-2026-08-001` rule).

## Analysis

Mean ± population standard deviation per arm per metric, plus the in-range share. No
significance test: three arms of ~18 beats each, beats within a session are not independent,
and the predicted effect is a clear ordinal separation. If the separation is clean a test
adds nothing; if it is marginal, this design cannot adjudicate it and a test would dress that
up as precision it does not have.

## Threats to validity

- **Beats are not independent.** Each conditions on the last through its own transcript, so
  n is beats but not n independent samples. The ± figures are descriptive spread.
- **One world, one cast, one genre, one model.** Nothing transfers without re-running.
- **The tiers may separate for the wrong reason.** The token allowance differs per tier
  (700 / 1400 / 2048), so an arm could be separated by truncation rather than by the
  directive. **Discards and mid-sentence endings are the tell**, and a `long` beat cut at
  its ceiling would show as a beat ending without terminal punctuation — checked in the read.
- **`short` has the least room to be wrong in.** A one-paragraph difference is a 50 % swing
  at `short` and a 17 % swing at `long`, so the arms are not equally sensitive.
- **The scripted player lines ship in the runner** and are contaminated for held-out use.
- **Unblinded read**, by the author of the change.
