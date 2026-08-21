# ISSUES — EXP-2026-08-009 Second person

## The design is a before/after, and that is a real limitation

This experiment compares two runs made at two times, not two arms interleaved inside one.
The turn engine cannot serve two prompt variants within a session, so an arm-level test was
not available without building a config seam that does not exist. Everything in `RESULTS.md`
should be read with that in mind, and the reason the result is offered as strong evidence is
that the effect is total (72 % → 0 %, 60 % → 0 %) rather than that the design is good. A
20-point shift under this design would not have been reportable.

The one confound the protocol named as disqualifying — a different upstream model between
the runs — did **not** occur: both were served by `gemma4-26B-mtp`, verified per run from a
completion's `model` field rather than from the relay's `/v1/models`, which reports
`upstream_model: auto` for a hot-swapping alias and cannot be trusted for this.

## The guard and the metric share an implementation

`emission.names_the_player` both gates a passage's opening and scores the run. A beat the
gate discarded would be invisible to the metric, so a high discard count would make the
result unreadable. **Discards were zero on every turn**, which is why the result stands and
why the discard count is reported in `RESULTS.md` § 2 rather than buried here. If a future
run of this shape reports a non-zero discard count, its leak metric is not comparable to
this one.

## The detector is a two-phrase regex

`\bthe\s+(?:player|user)(?:'s)?\b` is a narrow proxy for "refers to the reader as a
production object". A model that writes "the human", "the user's input", or "whoever is
typing" passes it. The metric measures the specific failure that was observed, not the class
it belongs to.

## Prompts not covered by this change

`planner_agent`, `director_agent` and `intent_agent` still label the player's line `Player:`.
They were left alone deliberately: their outputs are JSON or structure rather than prose, and
changing a label those parsers and their tests depend on carries risk this experiment had no
reason to take. But `director_agent` writes branch **labels the player reads**, so it is not
categorically safe — it is untested, which is a different thing, and it is recorded as a
follow-up rather than as a decision.

## Wall-clock is recorded and not interpreted

Per-turn elapsed time in this run (34–62 s) was markedly faster than in `EXP-2026-08-008`
(74–549 s) on the same endpoint and the same upstream. Nothing in this change plausibly
explains a 9× difference on a single turn, and this endpoint has produced a 66× latency
shift traced to a disconnected GPU before. **No latency claim is made from either run**, and
the prose metrics do not depend on timing.

## Known limitations of the recorded run

- One session, one cast, one genre, one model; n is beats, and beats within a session are
  not independent.
- The scripted player lines ship in the runner and are contaminated for held-out use.
- The read of the passages is unblinded, by the author of the change.
- `chars` rose 66 % with no hypothesis about it either way (`RESULTS.md` § 6). It is reported
  as an unexplained change, not as part of the result.
