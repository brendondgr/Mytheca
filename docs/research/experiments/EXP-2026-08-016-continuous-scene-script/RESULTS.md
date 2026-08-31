# RESULTS — EXP-2026-08-016 Continuous scene script

> **Written 2026-08-31, seven days after the run.** Read §0 before any number below.

## 0. Why this file was empty, and what filled it

This experiment ran on 2026-08-25 and was never written up. `manifest.yaml` stayed `planned`,
this file stayed a template, and the `INDEX.md` row still read
`<one line, specific enough to read in a table>`.

That did not stop three other documents citing it — `CLAUDE.md`,
[`docs/plans/binding-plan-and-execution-arms.md`](../../../plans/binding-plan-and-execution-arms.md),
and [`EXP-2026-08-017`](../EXP-2026-08-017-bound-plan-execution/PROTOCOL.md)'s protocol — most
specifically for **"turns of 18, 22 and 24 beats on a three-character scene"**. A repository
audit on 2026-08-31 flagged that number as tracing to nothing, because from the folder alone it
did not.

Two sources filled the gap:

1. **The event log**, still in the development Postgres, recovered before the throwaway
   storyline holding it (`47525d8b`, "EXP-016 Scene Flow") was deleted on 2026-08-31. Raw
   export: [`data/events.json`](data/events.json). [`make_metrics.py`](make_metrics.py) computes
   every number below from it.
2. **This experiment's own [`ISSUES.md`](ISSUES.md)**, which turned out to be a far better
   record than the empty RESULTS suggested — it documents the blocked start, a mid-run GPU
   contention change, and, in passing, the fact that identifies the arms.

**Read ISSUES.md's first entry with its date in mind.** Written 2026-08-24/25, it says
*"Nothing ran… It was not tried."* That was true when written and is superseded by the two
entries below it in the same file, which describe the run that then happened. Nothing is being
corrected there — a dated entry is accurate about its date. It is flagged here only because a
reader who stops at the first entry will conclude this experiment never ran, and it did.

**What the recovery licenses.** Beat counts are exact: they are counted from the events the
engine persisted, the same source a live harness would have counted. **Arm attribution is
sound but indirect** — ISSUES.md 2026-08-25 records *"`voiced` turn 3 produced 18 beats and
`continuous` turn 3 produced 3"*, and exactly one session in the log matches each. Everything
else is gone: no latency, no token accounting, and none of the three primary metrics, which
required text analysis that was never run and plan data that was never persisted.

## 1. Headline

The runaway-turn observation is **confirmed, and the quoted figure was the milder half of it**:
the `voiced` arm reached 18, 24 and 22 beats, and the `continuous` arm — tight at 3, 3, 3 and 2
— produced a single **38-beat** turn that appears in none of the three documents citing this
experiment. The primary question, whether a continuous scene script beats per-speaker calls on
attribution and voice, **is not answered and cannot be**: those metrics were never computed.

## 2. Results table

<!-- generated from data/metrics.json by make_metrics.py -->

| arm | turn | beats | composition |
| --- | --- | --- | --- |
| `voiced` | 1 | 4 | 4 prose |
| `voiced` | 2 | 8 | 7 prose · 1 narration |
| `voiced` | 3 | **18** | 12 prose · 6 narration |
| `voiced` | 4 | **24** | 22 prose · 2 narration |
| `voiced` | 5 | **22** | 21 prose · 1 narration |
| `voiced` | 6 | 3 | 3 prose |
| `continuous` | 1 | 3 | 3 prose |
| `continuous` | 2 | 3 | 3 prose |
| `continuous` | 3 | 3 | 3 prose |
| `continuous` | 4 | **38** | 38 prose |
| `continuous` | 5 | 2 | 2 prose |

`voiced` max 24 over 6 turns · `continuous` max 38 over 5 turns.

**No mean is reported, per arm or across arms.** Across arms it would average two different
conditions. Within an arm, n = 5 and n = 6 with a single outlier carrying the result is not a
sample a mean describes — quoting one would be the
[`EXP-2026-08-001`](../EXP-2026-08-001-planner-vs-oneshot-director/) error in new clothes. The
raw sequences are the result.

## 3. Figures

None. Eleven rows fit in the table above and a figure would carry no information the table does
not. The contract asks for figures that inform, not figures that decorate.

## 4. Interpretation

Turn length was not bounded by anything a plan was accountable to. `TURN_MAX_BEATS` was 24, but
the effective ceiling is `max(TURN_MAX_BEATS, 2 × cast + 6)` and `continuous` turn 4 reached
**38** — so on a three-character scene the nominal 24 was never the operative limit. The loop
asked "anyone else?" until something said stop, and on that turn nothing did.

This is the observation the bound plan shipped on 2026-08-26 was built to remove: plan the whole
turn in one call and make the plan a contract, so length is chosen once by a planner that can
see the whole turn. [`EXP-2026-08-017`](../EXP-2026-08-017-bound-plan-execution/) measured that
change and found its binding property not yet met.

A tempting reading — *`continuous` runs tighter turns* (3, 3, 3, 2 against 4, 8, 18, 24, 22) —
**is not supported**. Beat count is the planner's decision, taken before a prose token exists,
and `sceneFlow` governs how the planned beats are *written*, not how many are planned. Four
tight turns and one of 38 is more consistent with planner variance than with an arm effect, and
n = 5 could not separate the two anyway.

## 5. Threats to validity

- **Post-hoc reconstruction.** Every number was computed seven days later from a source the
  protocol did not nominate. The counts are exact, but a metric chosen after seeing the data is
  weaker than one pre-registered, and only one of the protocol's metrics is even present.
- **Arm attribution rests on one sentence** in ISSUES.md. It is unambiguous against the log, but
  it is a single line of prose, not a recorded label.
- **n = 11 turns, 2 sessions.** Under-powered in plain words. Two turns carry the whole result.
- **GPU contention changed mid-run** (ISSUES.md, 2026-08-25): a GPU-using application was closed
  between `continuous` turn 3 and `voiced` turn 4. This does not touch beat counts — the planner
  decides those before generation — but it is why no timing is reported here at all.
- **One model, one scene, one cast size.** Three characters, one storyline, one relay endpoint.
  Cast size is the variable most likely to matter, given the `2 × cast + 6` term.
- **Survivorship.** This log survived only because a dev database went a week without cleaning.
  Deleted earlier, the audit's finding would have been unresolvable.

## 6. What surprised us

That the quoted number was **too low, and from one arm**. "18, 22 and 24" travelled through three
documents for a week. The worst turn in the run was 38, in the other arm, and appears in none of
them. The figure that got repeated came from the session someone happened to be looking at.

Second, and worth more: an experiment can be cited as authoritative by three documents while its
own folder reads `status: planned` and holds no data. Nothing caught that for a week, and it was
found by an audit that was not looking for it.

Third: **ISSUES.md was doing the real record-keeping all along.** The write-up was missing, but
the failure log was detailed, dated, and honest enough to reconstruct the experiment from. The
contract's insistence that failures are recorded rather than deleted is what made this file
recoverable at all.

## 7. Follow-ups

- [ ] `continuous` vs `voiced` is unanswered by this experiment and by EXP-017. Carried to
      `OPEN_QUESTIONS.md`.
- [ ] Should `make validate-research` fail when a document cites an experiment whose status is
      `planned`? That check would have caught this on the day.
- [ ] Should the harness persist `data/events.json` for every run, so an unwritten experiment is
      recoverable by design rather than by luck?

## 8. Reproduction

The run is **not reproducible**: its storyline was deleted on 2026-08-31 and the per-beat planner
it exercised was replaced on 2026-08-26. The analysis of the surviving log is:

```bash
python3 docs/research/experiments/EXP-2026-08-016-continuous-scene-script/make_metrics.py
```
