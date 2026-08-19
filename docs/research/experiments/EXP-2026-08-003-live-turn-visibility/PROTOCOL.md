# PROTOCOL — EXP-2026-08-003 Live turn visibility

## Question

A player turn in Mytheca showed nothing at all until the whole beat had been generated,
and frequently died at the 300 s generation timeout. Two changes were made. How much does
each contribute, separately, to (a) how long the player waits before seeing anything and
(b) how long the generation takes in total?

## Hypothesis

Stated before this run.

1. **Capping the reasoning shortens generation.** The configured endpoint is an
   OpenAI-protocol relay that answers neither the vLLM `/version` nor the llama.cpp
   `/props` probe, so `llm_backend.get_backend()` returned `UNKNOWN` and
   `apply_reasoning()` was a no-op — every per-operation `ReasoningEffort` in the codebase
   was discarded. Sending a budget should reduce completion tokens and wall clock.
2. **Streaming collapses time-to-first-token to near the connection latency**, and does so
   *independently* of (1): it changes when text becomes visible, not how much is produced.
3. Streaming should not change total completion wall clock beyond noise.

## Setup

Three arms, all issuing the identical chat completion against the live relay through
`web/backend/app/services/llm.py`. Nothing is mocked; this is the real endpoint the app
uses.

| Arm | Call | Reasoning budget |
| --- | --- | --- |
| `blocking-uncapped` | `llm.chat_complete_usage(..., reasoning=None)` | none — reproduces the pre-fix behaviour exactly (an endpoint classified `UNKNOWN` received no budget key, which is identical to passing no `reasoning`) |
| `blocking-capped` | `llm.chat_complete_usage(..., reasoning=MEDIUM)` | 512 thinking tokens, both engine keys |
| `streaming-capped` | `llm.chat_complete_stream(..., reasoning=MEDIUM)` | 512 thinking tokens, both engine keys |

`blocking-uncapped → blocking-capped` isolates the Phase 1 detection/budget fix.
`blocking-capped → streaming-capped` isolates the Phase 2/4 transport change.

The prompt is a real character-turn prompt shape (system output-contract + world primer
stand-in, user asks for one in-character beat), held byte-identical across arms and runs.

## Data

No dataset. One fixed prompt pair, defined inline in the runner
(`utils/scripts/research/exp_live_turn_visibility.py`) and hashed into the manifest. This
is a systems-latency measurement, not a quality evaluation — nothing here says the output
got *better*, only when it arrives and how much is produced.

## Metrics

| Metric | Definition | Direction |
| --- | --- | --- |
| `ttft_s` | Seconds from issuing the HTTP request to the first delta containing non-empty **answer** text. For the blocking arms nothing is visible until the completion is whole, so this equals `wall_clock_s` by construction — that identity is the thing under test, not an artefact. | lower is better |
| `wall_clock_s` | Seconds from issuing the request to the finished, scrubbed completion text. | lower is better |
| `completion_tokens` | `usage.completion_tokens` reported by the endpoint — reasoning tokens included. This is what the budget is supposed to move. | lower is better |
| `first_reasoning_s` | Seconds to the first `reasoning_content` delta. Streaming arm only; `null` elsewhere, since the blocking arms cannot expose it. | lower is better |

## Baselines

`blocking-uncapped` **is** the baseline: it is the behaviour every Mytheca turn had before
2026-08-19, reproduced through the current code path rather than by checking out an old
commit, so the two differ only in the arguments named above.

## Procedure

```bash
# The relay must be reachable at http://localhost:4000/v1.
uv run python utils/scripts/research/exp_live_turn_visibility.py \
  --runs 5 --out docs/research/experiments/EXP-2026-08-003-live-turn-visibility
uv run python utils/scripts/research/fig_live_turn_visibility.py \
  --exp docs/research/experiments/EXP-2026-08-003-live-turn-visibility
make validate-research
```

Model is pinned to the relay's `local` id (llama.cpp · `gemma-4-26B-it`). The app's
configured model is `skynet`, whose relay entry declares `upstream_model: auto` — its
routing can change between calls, which would make a latency comparison meaningless. That
substitution is a deliberate deviation from the deployed configuration and is restated in
RESULTS.md, because it means these numbers characterise *one* upstream, not whatever
`skynet` happens to select.

No seeds: the endpoint exposes none. Temperature is pinned at 0.7 (the app's default), so
run-to-run variance is expected and is why n = 5 per arm with std reported.

## What would falsify this

- `blocking-capped` shows no reduction in `completion_tokens` versus `blocking-uncapped`
  → the budget keys are accepted but ignored by this upstream, and Phase 1 fixed nothing
  observable on it.
- `streaming-capped` shows `ttft_s` not materially below its own `wall_clock_s` → the
  transport is not actually delivering early tokens.
- `streaming-capped` shows `wall_clock_s` materially above `blocking-capped` → streaming
  costs total throughput, which would be a real trade-off to disclose.
