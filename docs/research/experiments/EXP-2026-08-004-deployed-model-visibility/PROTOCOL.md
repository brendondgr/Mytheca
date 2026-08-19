# PROTOCOL — EXP-2026-08-004 What the deployed model actually gives the player

## Question

EXP-2026-08-003 measured the relay's `local` upstream (llama.cpp · `gemma-4-26B-it`) and
found the live reasoning channel arriving ~20× earlier than the first word of prose. The
app is not configured with that model: it is configured with `skynet`, whose relay entry
declares `upstream_model: auto`. **Does the live-visibility work deliver anything on the
model the player is actually using?**

## Hypothesis

Stated before the run, from one exploratory observation (recorded in ISSUES.md): the
`skynet` route returns no `reasoning_content` field and no inline `<think>` block, so the
reasoning channel will be empty, and time-to-first-answer-token will sit at a high fraction
of total wall clock. If so, the visible-progress win on this model comes **entirely** from
the status-strip phases and the pending beat, not from streamed content.

## Setup

Identical to EXP-2026-08-003 — same runner, same prompt, same arms — with `--model skynet`
instead of `--model local`. Everything else is held constant so the two experiments are
directly comparable.

## Data

The same single fixed character-turn prompt, hashed into the manifest. No dataset.

## Metrics

Identical to EXP-2026-08-003: `ttft_s`, `first_reasoning_s`, `wall_clock_s`,
`completion_tokens`. The metric that decides this question is **`ttft_s / wall_clock_s`** —
how far through the generation the first visible word arrives — and whether
`first_reasoning_s` is ever non-null.

## Baselines

EXP-2026-08-003's `streaming-capped` arm on the `local` upstream. The comparison is
between *models*, not between code paths; the code is identical.

## Procedure

```bash
uv run python -m utils.scripts.research.run_live_turn_visibility --runs 3 --model skynet \
  --experiment docs/research/experiments/EXP-2026-08-004-deployed-model-visibility
uv run python docs/research/experiments/EXP-2026-08-004-deployed-model-visibility/figures/make_figures.py
make validate-research
```

`skynet` routes dynamically (`upstream_model: auto`), so the upstream may differ between
runs and even between arms. That is not a flaw to be corrected here — it is the deployed
condition, and it is the thing being characterised. The observed upstream is recorded.

## What would falsify this

`first_reasoning_s` coming back non-null, or `ttft_s` landing at a low fraction of
`wall_clock_s`, would mean the deployed model does benefit from the streamed-content work
and the hypothesis is wrong.
