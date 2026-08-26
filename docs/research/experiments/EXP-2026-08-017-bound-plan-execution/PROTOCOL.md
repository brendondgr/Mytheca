# PROTOCOL — EXP-2026-08-017 Bound plan, two execution arms

**Written before the run. Nothing below is edited to match a result.**

## 1. The question

The turn loop planned **per beat**: plan one, run it, plan again. Three consequences, all
measured or verified before this experiment was designed:

- **The plan was not binding.** `turn_engine`'s `elif not planned:` re-planned whenever the
  queue emptied, so a plan the player approved was a head start, not a contract.
  `EXP-2026-08-016` recorded turns of **18, 22 and 24** beats on a three-character scene, the
  last being the runaway backstop rather than a decision.
- **Deliberation sat at the wrong stage.** Prose ran at `ReasoningEffort.HIGH` (1024) and the
  planner at `QUICK` (128). Measured on the deployed endpoint: **2646 reasoning characters
  for 247 characters of prose — 91 %** of a beat spent on an essay nobody reads.
- **Per-beat planning cannot reuse the prefix cache.** `_build_user_prompt` is ordered
  STABLE (setting + full roster) → APPEND-ONLY (transcript) → VOLATILE (this speaker), which
  is exactly what a prefix cache wants. The server holds **one** KV cache, so interleaving
  `[planner][Lily][planner][Zoe]` overwrites the character prefix on every planner call.

Phases 1-5 changed all three. This experiment asks what that bought, and which of the **two
execution strategies** over a bound plan is better.

## 2. The arms

Both consume the **same bound plan**, produced by one planning call. The only difference is
how the planned beats are written:

| Arm | `sceneFlow` | How the beats are produced |
| --- | --- | --- |
| `continuous` | `continuous` | ONE generation writes the whole planned turn, marking each hand-off with `<speaker:N>`. |
| `voiced` | `voiced` | One generation per beat, stopping at each to feed that beat's speaker, register, stakes and purpose — and continuing straight on, with **no planning call between beats**. |

`voiced` is *not* the old behaviour. The old per-speaker path re-planned between every beat;
this one walks a fixed plan. That is the point: the comparison is now about **how prose is
written**, with planning held constant, which it never was before.

## 3. Hypotheses

**Stated before the run, outcomes genuinely unknown.**

1. **Plan adherence is 1.0 in both arms.** Beats run equals beats planned. This is a
   pass/fail property of Phase 1, not a preference — a value below 1.0 in either arm means
   the contract leaks and the rest of the comparison is not worth reading.
2. **Exactly one planner call per turn, in both arms.**
3. **`continuous` is faster per beat**, since one generation replaces N.
4. **`voiced` reuses more of the prefix cache**, because it makes many calls against a
   deliberately stable prefix where `continuous` makes one long call with nothing to reuse.
   Note this cuts against (3): the arms are expected to win different cost metrics, and
   neither is "the cheap one".
5. **Voice distinctness does not differ materially.** Genuinely uncertain. `continuous` does
   not build a per-speaker prompt at all, so it never receives the register directive,
   register-selected voice samples, the relationship note or carried disposition.

## 4. Design

- **One build, one model, one world, one cast (three characters), identical player lines.**
  The only variable is `overrides.sceneFlow`.
- **Interleaved turn by turn** — `voiced`, `continuous`, `voiced`, … This repository has a
  recorded case of a 66x latency swing that was a disconnected GPU, and `EXP-2026-08-016` had
  a GPU-using application close **mid-run**. Interleaving makes the endpoint a shared
  condition rather than a variable.
- **Separate sessions per arm**, so neither reads the other's beats as history.
- **n = 2 player turns per arm.** Deliberately small, on the owner's instruction. EXP-016 ran
  6 per arm, took over three hours, and was stopped at 10 of 12 turns — a bounding question
  does not need that, and a run nobody finishes answers nothing.

## 5. Metrics

Computed from the recorded stream. Every prose guard is imported from
`app.services.prose_guards`, so the harness cannot hold its own opinion of a violation.

**Primary**

| Metric | Definition |
| --- | --- |
| `plan_adherence` | Character/narration beats run ÷ beats in the turn's `plan` frame. **1.0 or the run has failed**, regardless of anything else. |
| `planner_calls` | Planning traces per turn. Must be 1. |
| `cached_token_rate` | `cachedTokens ÷ promptTokens` over the turn's prose calls — the prefix-cache hit rate, read from the server's own `usage`. |
| `seconds_per_beat` | Wall clock ÷ beats. Per beat, **not per turn**: EXP-016's turn-level seconds were dominated by how many beats the planner chose, which is not a scene-flow property. |

**Secondary (must not regress)**

`cross_speaker_rate` · `misattribution_rate` · `voice_distinctness` ·
`addresses_the_reader` · `names_the_player` · `has_speech` · `paragraph_breaks`

**Discards per arm.** A beat the engine throws away never reaches the stream and cannot be
scored, which would make a *gate* doing the work look like a *prompt* doing the work. Counted
and reported per arm — `EXP-2026-08-009`'s zero-discard result was load-bearing for the same
reason.

## 6. Decision rule — written before the run

`continuous` **stays the default** only if:

- `plan_adherence` is 1.0 in both arms, **and**
- `misattribution_rate` and `cross_speaker_rate` are no worse than `voiced`, **and**
- `voice_distinctness` does not fall by more than **10 %** relative to `voiced`.

A larger fall goes to the owner as a **trade**, not a recommendation. Nothing here flips the
default silently. If `plan_adherence` is below 1.0 in either arm, the answer to this
experiment is "fix the binding first" and no arm comparison is reported.

## 7. Threats to validity

- **n = 1 session per arm, 2 turns.** Enough to catch a gross effect and a broken contract;
  nowhere near enough for a rate with an interval. Every number is reported as one run.
- **`voice_distinctness` is a lexical proxy.** Two characters can share vocabulary and still
  read as different people. A drop is evidence, not proof; a hold is weaker still.
- **`continuous` gets a thinner prompt by construction** (§3.5). If it loses, the honest
  reading is "this implementation of continuous prose loses", not "continuous prose cannot
  work".
- **The cache metric depends on the server reporting it.** vLLM omits
  `prompt_tokens_details`; where it is absent the rate is `None` and is reported as
  unmeasured rather than as zero.
- **The model matters** and is recorded in the manifest. A result on one local model is not a
  result about execution strategies in general.

## 8. Failure handling

A partly-failed run is recorded `status: failed`, with an honest `ISSUES.md` and **per-turn
rows and no aggregate**. Survivors of a partial run are not a random subsample —
`EXP-2026-08-001` is this repository's worked example of getting that wrong, and
`EXP-2026-08-016` is the recent one that had to invoke it.

## 9. Entry point

```bash
uv run python -m utils.scripts.research.run_bound_plan \
  --experiment docs/research/experiments/EXP-2026-08-017-bound-plan-execution --turns 2
```

Requires a backend on `--api` (default `http://localhost:3345/api`) and a healthy LLM
endpoint. Verify the binding is actually in effect before trusting a result — a turn's
`planning` trace must report `planner: upfront`:

```bash
grep -c '"planner": "upfront"' <(…stream…)   # >= 1 per turn
```
