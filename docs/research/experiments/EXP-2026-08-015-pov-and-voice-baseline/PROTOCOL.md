# PROTOCOL — EXP-2026-08-015 Point of view under Playwright mode

**Written before the run. Nothing below is edited to match a result.**

## 1. The question

When the player is **not** a character in the scene — Playwright mode, where their message is
direction rather than a person's line — the cast addressed them anyway. *"I look at you"*,
*"your question sits there"*, and from the narrator: *"He reaches out to grab your wrist."*
There is nobody there to grab.

The cause was a **label**, not a vague prompt. A player beat rendered as `You:` in both
transcripts, and the character output contract said, verbatim: *"The line labelled 'You:' is
the person you are talking to — someone standing in the room with you … Write them in the
second person."* The cast was doing what it was told.

That label is not arbitrary and could not simply be reverted:
[`EXP-2026-08-009`](../EXP-2026-08-009-prose-second-person/RESULTS.md) introduced it and
measured it taking *"the player"* out of the prose, from **72 % of character beats to 0 %**.
So the fix relabels a player beat to `Direction:` — a **non-person** — and moves the
second-person rule out of the operator-overridable contract into the prompt tail, where it can
be conditional on whether the player is embodied at all.

This experiment measures whether that worked, and by how much.

## 2. Why this is a two-commit design

The variable is a **label in code**, not a prompt an operator can override, so it cannot be
ablated by configuration. The honest arms are therefore two builds:

| Arm | Commit | What it has |
| --- | --- | --- |
| `pre` | `0d6a60e` | The Playwright rename only. Player beats render `You:`; the contract's second-person clause is unconditional; no reader-address guard; no cross-speaker guard. |
| `post` | `HEAD` of `main` at run time | `Direction:` labelling, the conditional tail clause, third-person-only narrator prompts, and both guards. |

**The confound this buys, recorded up front:** the two commits differ by more than the
label. `post` also removes the `maxTurns` cap and the `beatLength` tiers, so its turns are
longer and its beats vary more in length. Every primary metric here is therefore a **rate per
beat**, not a count, so a different number of beats does not move it. Beat *length* metrics
are reported for both arms and explicitly **not** compared — they measure a different change.

A single-build ablation would have been cleaner science. It would have required a
research-only flag in production code to restore a defect on demand, and that was judged the
worse trade: a permanent branch in the turn loop whose only purpose is to reproduce a bug.

## 3. Hypothesis

**Stated before the run, outcome genuinely unknown.**

1. `addresses_the_reader` on character beats falls from a **majority** in `pre` to **zero or
   near zero** in `post`. A partial effect would be a failure of this design: the mechanism is
   a label, and a label is either there or not.
2. `narrator_addresses_the_reader` follows the same shape — the narrator was the worst
   offender in the informal runs.
3. `names_the_player` stays at **zero in both arms**. `EXP-2026-08-009` closed it, and neither
   arm reintroduces `Player:`; if it moves, something regressed that nobody was watching.
4. No prose-form metric regresses.

## 4. Design

- **Two backends, one per commit**, on separate ports, against the same database and the same
  LLM endpoint.
- **Interleaved turn by turn** — `pre`, `post`, `pre`, … in one wall-clock window. This
  repository has a recorded case of a 66× latency swing that was a disconnected GPU rather
  than the code; block-apart arms would measure the endpoint, not the change.
- **Separate worlds**, because the two builds write different schemas' worth of settings and
  a shared session would let one arm's beats condition the other's prompts.
- **The same scripted player lines** for both, and the same three-character cast. The first
  line names a character on purpose (*"Lily jumps up on the table…"*) — that is the owner's
  own example and the case where the narrator must describe **Lily** doing it rather than
  addressing "you".
- **n = 6 player turns per arm.**

## 5. Metrics

Computed from the recorded transcript. Every guard is imported from
`app.services.prose_guards` **at the `post` commit**, and both arms' transcripts are scored by
that same code — a metric that differed between arms would be measuring itself.

**Primary**

| Metric | Definition |
| --- | --- |
| `addresses_the_reader` | Character beats with a second-person pronoun **outside quoted speech**, over character beats. Quotes are stripped because a character saying *"You are lying, Zoe"* is correct writing aimed at another character. |
| `narrator_addresses_the_reader` | The same, over narration beats. |
| `narrator_first_person` | Narration beats containing `I`/`me`/`we`. The narrator is a voice, not a character. |
| `names_the_player` | Beats containing "the player"/"the user". Must be zero in both arms. |

**Secondary (must not regress)**

`has_speech` · `is_distinct` · `sentences_per_100_words` · `cross_speaker_rate`

**Reported, not compared:** `paragraph_breaks`, `chars`, `beats_per_turn` — these move for a
different reason (§2) and comparing them across arms would be dishonest.

**Discards per arm.** A beat the engine throws away never reaches the transcript and cannot be
scored, which would make a *gate* doing the work look identical to a *prompt* doing the work.
`post` has two guards `pre` does not, so this number is what separates the two explanations.
`EXP-2026-08-009` § Threats named this and its zero-discard result was load-bearing; the same
applies here and more sharply.

## 6. Threats to validity

- **n = 1 session per arm, 6 turns.** Enough to see a total effect, nowhere near enough for a
  rate with an interval. Every number is reported as one run.
- **The two commits differ by more than the variable** (§2). Mitigated by measuring rates, not
  counts, and by refusing to compare the metrics that move for other reasons.
- **`post` scores itself.** Its guards can discard a beat before it is measured. Discard counts
  are reported per arm precisely so a reader can tell the prompt's contribution from the
  gate's; a `post` result with a high discard count would be a much weaker claim.
- **The model matters**, and is recorded in the manifest.

## 7. Failure handling

A partly-failed run is recorded with `status: failed`, an honest `ISSUES.md`, and **per-turn
rows with no aggregate**. Survivors of a partial run are not a random subsample —
`EXP-2026-08-001` is this repository's worked example of getting that wrong.

## 8. Entry point

```bash
uv run python -m utils.scripts.research.run_pov_mode \
  --experiment docs/research/experiments/EXP-2026-08-015-pov-and-voice-baseline \
  --pre-api http://localhost:3356/api --post-api http://localhost:3355/api --turns 6
```

Both backends must be running, one per commit, and the LLM endpoint must be healthy.

## 9. Provenance note

Informal before/after figures exist from `utils/scripts/scene_smoke.py` during the fix
(10 problems → 1 on one scene; 9 of 10 beats addressing the reader → 0). Those are **not** part
of this experiment and must not be quoted as its result: that script is n = 1, has no arms,
and records nothing. They are why the experiment was worth running, not its finding.
