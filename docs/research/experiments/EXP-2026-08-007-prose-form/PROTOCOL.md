# PROTOCOL — EXP-2026-08-007 Prose form

> Pre-registered before the recorded run. A three-sample-per-arm pilot was run first and
> is disclosed in `ISSUES.md`; it is what motivated this protocol, and its numbers are
> **not** carried into the results.

## Question

The character passage form ships, and what it produces does not read like a scene: the
prose runs on without punctuation, contains no spoken dialogue, and arrives as one
unbroken block. Are the in-voice sampler penalties — `frequency_penalty` 0.4 and
`presence_penalty` 0.3, applied to every character generation by
`character_turn_agent._voice_params` — the cause?

## Hypothesis

Stated ahead of the run. **The penalties are the cause.** They apply to every token, and
the tokens prose is made of are its most repeated ones: the full stop, the comma, the
double quote, `I`, `the`. Penalising them should show up as exactly the observed failure —
few sentence terminators per hundred words, no quotation marks, and no paragraph breaks.

Predicted direction: removing the penalties **increases** sentences per hundred words,
**increases** the share of passages containing spoken dialogue, and **increases**
paragraph breaks per passage, relative to the shipped setting.

A plausible way for this to be wrong: the penalties are load-bearing against in-character
drift (they were added for that in the turn-loop plan §7), and the run-ons come from the
output contract instead. If the arms are indistinguishable, the hypothesis is refuted and
the fix belongs in the prompt.

## Setup

Direct calls to the live relay, bypassing the turn engine so that only the sampler varies.

- Endpoint: `http://localhost:4000/v1`, model `skynet`.
- System message: the shipped character output contract,
  `prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT)`, verbatim.
- User message: one of five scene prompts (below), in the shape
  `character_turn_agent._build_user_prompt` produces — identity, the transcript so far,
  and the "respond now" cue.
- Fixed across all arms: `temperature` 0.8, `top_p` 0.92, `max_tokens` 2224
  (`budget_for(HIGH)` 1024 + `_VOICE_PROSE_TOKENS` 1200), `thinking_token_budget` 1024.

### Arms

| Arm | `frequency_penalty` | `presence_penalty` | Note |
| --- | --- | --- | --- |
| `shipped` | 0.4 | 0.3 | the setting under test |
| `half` | 0.2 | 0.15 | is the effect graded? |
| `off` | 0.0 | 0.0 | the proposed setting |

Every other field is identical across arms, and the arms run interleaved per prompt so a
drift in endpoint state cannot land on one arm.

## Data

Five scene prompts written for this experiment, covering the registers the planner
assigns (`light`, `neutral`, `tense`, `grave`) plus one two-hander with an explicit
question in the transcript, which is the case where a reply *should* contain speech. They
ship in the runner (`utils/scripts/research/run_prose_form.py`) and are therefore
contaminated for any held-out use. Two samples per prompt per arm: **n = 10 per arm**.

## Metrics

Computed by the runner over the passage text as the turn engine would parse it
(`emission.parse_emission`), never by eye.

| Metric | Definition | Direction |
| --- | --- | --- |
| `sentences_per_100_words` | Count of `.`, `!`, `?` in the passage, divided by its word count, times 100. The run-on measure. | higher is better |
| `passages_with_speech` | Share of passages containing at least one paired run of double quotes. | higher is better |
| `paragraph_breaks` | Count of blank-line separators (`\n\n`) in the passage. | higher is better |
| `scratchpad_rate` | Share of passages `emission.looks_like_scratchpad` flags. | lower is better |
| `chars` | Passage length in characters. Context, not a target — length is not what is being optimised. | neither |

`sentences_per_100_words` is the **primary** metric: it is the one that maps directly to
the complaint ("no new line characters when characters talk, no quotations") without being
satisfiable by a model that simply writes less.

## Baselines

The `shipped` arm is the baseline — it is what the owner is looking at today. The
comparison is fair because every input other than the two penalty fields is byte-identical
across arms and the arms are interleaved.

## Procedure

```bash
uv run python -m utils.scripts.research.run_prose_form \
  --experiment docs/research/experiments/EXP-2026-08-007-prose-form
```

The runner writes `data/metrics.json`, `data/metrics.csv`, every raw passage under
`logs/`, and merges the captured state into `manifest.yaml`. A call that errors is
recorded as a failed row; **if any arm loses a run, no aggregate is computed for that
arm** and the per-run rows are the result (the `EXP-2026-08-001` rule).

## Analysis

Mean ± population standard deviation per arm per metric, over n = 10. No significance
test: with n = 10 and a hypothesis this coarse, the honest reading is the effect size and
the spread, and `RESULTS.md` reports both rather than a p-value that would imply more
precision than the design supports.

## Threats to validity

- **Single model.** Everything here is `skynet` (upstream `qwen38-27B-awq`). Nothing
  generalises to another model without re-running.
- **Prompt contamination.** The scene prompts ship in the repository.
- **Endpoint state.** The relay hot-swaps its upstream endpoint; interleaving the arms is
  the mitigation, not a guarantee. A 66× latency shift on this endpoint has been traced to
  a disconnected GPU before, so wall-clock is recorded but not interpreted.
- **The metrics are proxies.** "Reads like a scene" is not countable. These four are the
  countable shadows of it, and Phase 6 of the plan reads the passages.
