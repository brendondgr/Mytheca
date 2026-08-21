# PROTOCOL — EXP-2026-08-008 Prose end to end

> Pre-registered before the recorded run. Two earlier runs of the same shape were driven
> during development against `EXP-2026-08-006`'s folder and are disclosed in `ISSUES.md`;
> their numbers are **not** carried into the results here.

## Question

`EXP-2026-08-007` measured the sampler by calling the relay directly, with the shipped
character contract as the only system message. That isolates the sampler and deliberately
leaves out everything the turn engine does: the planner's beat and register, the assembled
context and voice samples, the emission parser, and the four guards that can discard a
passage before a reader sees it.

**Does the prose read like a scene when it comes out of the real turn engine, in a real
multi-turn session, at the owner's settings?** That is the thing the owner looks at, and
the four defects this work fixed were all found by reading it rather than by running a test.

## Hypothesis

Stated ahead of the run. **Yes, and without paying for it in discarded beats.** The
structural fixes (one passage per beat, the opening gate, the echo guard, the runaway stop)
are prompt-independent, and `EXP-2026-08-007` showed the sampler was what broke the form.

Predicted, over the character beats of a six-turn session:

- **every** beat contains at least one paired run of double quotes,
- **every** beat contains at least one paragraph break,
- **no** beat is a byte-identical duplicate of another beat in the session,
- `sentences_per_100_words` lands in the range `EXP-2026-08-007`'s `off` arm produced
  (11.42 ± 3.96), and
- discards stay in single figures — a run that scores well only because the guards threw
  away half its beats has not shown that the prose is good.

A plausible way for this to be wrong: the engine's prompt is far longer than the bare
contract, and a long transcript is exactly where the earlier starved beats appeared. If the
form degrades as the session grows, the fix is incomplete and the per-turn rows will show it.

## Setup

A throwaway world built by the runner (`run_conversation_scaling.build_world`), so the run
does not depend on what is in the dev database: storyline *Salt and Ledgers*, cast Mei /
Kira / Aldous, setting *The Smoldering Hearth*, `maxTurns` 5, `suggestionsCount` 0,
`contextBeats` 100. Six scripted player lines from `PLAYER_LINES`, driven through
`POST /api/play/{id}/turn` with `trace: true` against a locally running backend at its
committed settings — no per-run overrides.

**Model.** Whatever the relay is serving, recorded per run from the response. This matters:
`EXP-2026-08-007` ran entirely on upstream `qwen38-27B-awq`, and the endpoint has since
been restarted onto a different upstream. A result here on a different model is a
**generalisation check**, not a repeat, and `RESULTS.md` must say which it was.

## Data

The beats a live session emits. A delta-streamed event re-emits the same `id` with growing
`text`, so a beat is collected on its `done` frame and keyed by `id`. `narration` beats are
recorded in the transcript but **excluded from the aggregate**: the narrator writes in third
person and is explicitly forbidden dialogue, so scoring it on `has_speech` would score the
contract against a prompt that forbids the thing being counted.

## Metrics

Computed by the runner over the emitted beat text, never by eye. The first five are
`EXP-2026-08-007`'s definitions verbatim, so the two experiments are comparable.

| Metric | Definition | Direction |
| --- | --- | --- |
| `sentences_per_100_words` | `.`/`!`/`?` count ÷ words × 100. The run-on measure. | higher is better |
| `has_speech` | Beat contains ≥1 paired run of double quotes. | higher is better |
| `paragraph_breaks` | Count of `\n\n` in the beat. | higher is better |
| `is_scratchpad` | `emission.looks_like_scratchpad` flags the beat. | lower is better |
| `starts_mid_sentence` | `emission.starts_mid_sentence` flags the beat. | lower is better |
| `chars` | Beat length. Context, not a target. | neither |
| `beats.distinct` | Beats that are not byte-identical to an earlier beat **in the session**. | = `beats.total` |
| discards | Trace beats flagged `scratchpad` / `dropped` / `degenerate` / `skipped`. | lower is better |

`has_speech` and `paragraph_breaks` are **primary** here — they are the owner's complaint in
their own words (*"no new line characters when characters talk, no quotations"*).

## Baselines

The twelve most recent `character_prose` events in the live database before this work, as
recorded in `docs/plans/prose-that-reads-like-a-scene.md` § 1: **3/12** contained a double
quote, **4/12** contained a paragraph break, and **5** were byte-identical duplicates of
another event in the same beat. That baseline is a different model and a different session,
so it is a *before* picture, not a controlled arm — the controlled comparison is
`EXP-2026-08-007`.

## Procedure

```bash
uv run python -m utils.scripts.research.run_prose_end_to_end \
  --experiment docs/research/experiments/EXP-2026-08-008-prose-end-to-end --turns 6
```

The backend must be up and answering before the run starts (`GET /api/storylines` twice —
uvicorn `--reload` restarts on a backend edit, and a run launched mid-restart measures a
half-loaded app). Every beat is written to `logs/transcript.json` so the passages can be
**read**, which is the point of the phase this serves.

**If any turn fails, no aggregate is computed** and the per-beat rows are the result
(the `EXP-2026-08-001` rule).

## Analysis

Mean ± population standard deviation per metric over the character beats, plus the counts
that are the actual claim (`beats.with_speech` / `beats.total`). No significance test: this
is a single-condition observation of shipped behaviour, not a comparison of arms. The
per-turn rows are reported so a degradation as the session grows is visible rather than
averaged away.

## Threats to validity

- **No control arm.** This is an observation of one configuration. It cannot attribute the
  result to any particular fix; `EXP-2026-08-007` is the controlled part of the story.
- **Model.** Whichever upstream the relay serves, recorded but not chosen. A result here
  does not transfer to another model.
- **One session, one cast, one genre.** n is beats, not scenarios.
- **Scripted player lines.** They ship in the runner and are contaminated for held-out use.
- **The metrics are proxies.** "Reads like a scene" is not countable. The transcript is
  written out so the passages are read as well as counted, and that read is unblinded.
