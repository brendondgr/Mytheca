# PROTOCOL — EXP-2026-08-016 Continuous scene script

**Written before the run. Nothing below is edited to match a result.**

## 1. The question

Mytheca has always made **one model call per speaker**. That is not an accident of
implementation; `character_turn_agent`'s docstring states the reason: *"One LLM call per
active speaker (per-character isolation — no shared multi-POV prompt, so voices stay
distinct)."*

`sceneFlow: "continuous"` reverses it. One call writes every beat of the planned turn,
marking each change of speaker with `<speaker:N>`. It shipped as the **default** on
2026-08-24 on the owner's judgement, before any measurement — this experiment is the
measurement, run after the fact, and it is capable of saying the default is wrong.

The owner's grounds for the reversal, in their words: *"the characters aren't even abiding
by their ideological background, even with all of this being put into place."* If that is
true, the per-speaker architecture pays N calls, N prompts and N re-plans for a property it
is not delivering, and continuous prose costs nothing. If it is false, continuous prose
costs voice distinctness.

There is one piece of prior evidence and it is an anecdote, not a rate:
`beat_stream.echoes_a_beat` exists **because** two characters returned byte-identical
passages, and its docstring blames *"two separate calls whose prompts differ only by a name
and a role"*.

## 2. What is actually different between the arms

Recorded here because "one call instead of N" understates it. The continuous path **does not
build a per-speaker prompt at all**, so a beat written by it never receives:

- the per-register performance directive (`_REGISTER_DIRECTIVES`),
- register-selected voice samples (it gets the first two lines of each character's samples,
  inline on a shared roster),
- the relationship note from the story graph,
- the character's carried disposition from the previous turn's reflection,
- the per-beat owed-requirements tail (the turn's requirements are given once, for the whole
  script),
- a per-beat sampler (one call, so one `top_p`; it takes the first speaker's looseness and
  the plan's opening register).

It also does not hold and judge each speaker's opening the way `stream_emission` does.

## 3. Hypothesis

**Stated before the run, outcome genuinely unknown.**

1. **Attribution improves.** Continuous produces fewer cross-speaker leaks
   (`prose_guards.cross_speaker_speech`), because the writer emits the hand-off token itself
   rather than the engine attributing a passage it did not delimit.
2. **Voice distinctness does not degrade.** This is the one the design is betting on and the
   one most likely to fail. If the owner is right that voices are already indistinct, the
   two arms are level; if the per-speaker prompt is doing real work, continuous is worse.
3. **Wall clock and calls per turn fall**, materially — one generation instead of one per
   beat.
4. **No point-of-view regression.** `addresses_the_reader`, `narrator_speaks_in_first_person`
   and `names_the_player` stay at the levels EXP-2026-08-015 records, in both arms.

## 4. Design

- **Two arms, same build, same model, same world, same scripted player lines.** The only
  difference is `overrides.sceneFlow` on the turn request, so nothing else can vary.
- **Interleaved, turn by turn, in one wall-clock window** — `voiced`, `continuous`,
  `voiced`, … Day-apart or block-apart comparisons on this endpoint are worthless: this
  repository has a recorded case of a 66× latency swing that was a disconnected GPU, not the
  code. Interleaving is what makes the endpoint a shared condition rather than a variable.
- **Separate sessions per arm**, so neither arm reads the other's beats as history. Same
  world and same cast, so the cast is a shared condition.
- **n = 6 player turns per arm** on a **three-character** scene. Three is the floor at which
  a cross-speaker leak is distinguishable from a hand-off, and at which voice distinctness
  has more than one pair to measure.

## 5. Metrics

Every metric is computed by `utils/scripts/research/run_scene_script.py` from the recorded
transcript, and every guard is imported from `app.services.prose_guards` — the harness must
not hold its own opinion about what a violation is.

**Primary**

| Metric | Definition |
| --- | --- |
| `cross_speaker_rate` | Beats containing an attributed spoken line by another present character, over character beats. |
| `voice_distinctness` | Mean pairwise Jensen–Shannon distance between characters' word distributions within one session, over their own beats. Higher is more distinct. |
| `misattribution_rate` | Beats whose `characterId` disagrees with the plan's speaker for that position. Continuous should win this; it is the owner's "fewer parsing issues". |

**Secondary (must not regress)**

`addresses_the_reader` · `narrator_speaks_in_first_person` · `names_the_player` ·
`has_speech` · `paragraph_breaks` · `sentences_per_100_words` · `chars`

**Cost**

`seconds_per_turn` · `beats_per_turn` · `generation_calls_per_turn` · `fallback_rate` (how
often the script came back with no hand-off tokens and the turn re-ran per speaker).

## 6. Decision rule — written before the run

Continuous **stays the default** only if:

- `misattribution_rate` and `cross_speaker_rate` are **no worse** than voiced, **and**
- `voice_distinctness` does not fall by more than **10 %** relative to voiced.

If voice distinctness falls further, the result goes to the owner as a **trade**, not a
recommendation: it is their product decision, and this experiment's job is to make sure it
is made on a number. Nothing here silently flips the default back.

## 7. Threats to validity, stated in advance

- **n = 1 session per arm.** Six turns is enough to see a gross effect and nowhere near
  enough for a rate with a confidence interval. Every number in RESULTS.md is reported as
  what it is: one run.
- **`voice_distinctness` is a lexical proxy.** Two characters can share vocabulary and still
  read as different people (rhythm, sentence length, what they notice). A drop is evidence,
  not proof; a *hold* is weaker evidence still.
- **The guard and the metric share an implementation.** A beat the engine discards never
  reaches the transcript and so cannot be scored — which would make a gate doing the work
  look identical to a prompt doing the work. **Discards are counted per arm and reported**;
  this is the threat `EXP-2026-08-009` § Threats named and the reason its zero-discard result
  was load-bearing.
- **Continuous gets a thinner prompt by construction** (§2). If it loses, the honest reading
  is "this implementation of continuous prose loses", not "continuous prose cannot work" —
  several of the missing inputs could be added to the script prompt.
- **The model matters.** Recorded in the manifest. A result on one local model is not a
  result about continuous prose in general, and specifically must not be quoted as one.

## 8. Failure handling

If an arm fails part way — endpoint down, a turn 500s — the run is recorded with
`status: failed`, an honest `ISSUES.md`, and **per-turn rows with no aggregate**. Survivors
of a partly-failed run are not a random subsample. `EXP-2026-08-001` is the worked example of
getting this wrong in this repository, and it is the reason this sentence is here.

## 9. Entry point

```bash
uv run python -m utils.scripts.research.run_scene_script \
  --experiment docs/research/experiments/EXP-2026-08-016-continuous-scene-script --turns 6
```

Requires a backend on `--api` (default `http://localhost:3345/api`) and a configured,
healthy LLM endpoint.
