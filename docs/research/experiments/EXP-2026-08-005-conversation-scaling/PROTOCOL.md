# PROTOCOL — EXP-2026-08-005 Conversation-scaling latency and prompt-cache reuse

## Question

Two halves of one question:

1. **How does turn latency change over a 10-turn conversation** at the configuration in
   use — `maxTurns = 5`, `suggestionsCount = 0`, `contextBeats = 100` — measured at every
   step of each turn rather than as one number per turn?
2. **Is the prompt laid out so the inference server can reuse the conversation between
   turns?** If not, every turn re-reads the whole scene from scratch and latency grows with
   conversation length — which is the reported symptom.

## Hypothesis

Stated before the run.

1. Per-turn total will grow across the 10 turns, roughly with transcript length.
2. The pre-generation steps (`reading`, `planning`) will stay roughly flat, because they
   do not carry the transcript; the growth will be in the character calls.
3. The prompt cache will be **largely wasted**. `character_turn_agent._build_user_prompt`
   places the volatile block — identity, register-selected voice samples, and **current
   stat values** — in the HEAD of the user message, ahead of the transcript in the MIDDLE.
   Any stat change therefore invalidates the cache for everything after it, including the
   entire transcript. Moving the volatile block after the transcript should measurably
   improve prefill on a growing conversation.

## Setup

**Endpoint: the remote GPU behind the relay — model id `skynet`** (observed upstream
`qwen38-27B-awq`), which is what the app is configured with. This is a deliberate change
from EXP-2026-08-003, which pinned the `local` llama.cpp route.

**Mode `conversation`** drives the real `POST /api/play/{id}/turn` endpoint against the
running backend, over a scenario the runner creates itself at the configured settings
(and verifies were applied, since the schema clamps). Ten scripted player lines, one per
turn, in a single session.

**Mode `layout`** removes the app and compares two prompt orderings over a transcript that
grows by two realistic beats per turn:

| Layout | Order | Corresponds to |
| --- | --- | --- |
| `volatile-first` | identity + current stats → transcript → act-now | what the app does today |
| `volatile-last` | transcript → identity + current stats → act-now | the proposed reordering |

Passes alternate which layout runs first and carry a pass-specific salt in the system
preamble, so no pass inherits a warm cache from an earlier one. That is a direct fix for
the ordering confound that made EXP-2026-08-003's cross-arm numbers unusable.

## Data

No dataset. Ten fixed player lines and one fixed beat template, both inline in
`utils/scripts/research/run_conversation_scaling.py`.

## Metrics

| Metric | Definition | Direction |
| --- | --- | --- |
| `first_visible_s` | Seconds from POST to the first frame carrying visible prose. | lower better |
| `reading_s`, `planning_s`, `first_speaker_s` | Seconds to those trace steps — the pre-generation phases. | lower better |
| `total_s` | Seconds to the last frame of the turn. | lower better |
| `beats` | Completed visible beats the turn produced. Context for the timings: a 5-beat turn should cost more than a 2-beat turn. | — |
| `prompt_tokens_max` | Largest prompt any character call in the turn sent. The honest measure of how big the context has become. | — |
| `cached_tokens_max` / `cache_hit_ratio` | Prefix-cache reuse, **where the endpoint reports it**. | higher better |
| `ttft_s` (layout mode) | Time to the first token of any channel — dominated by prefill, so the behavioural proxy for cache reuse. | lower better |

**`skynet` reports `prompt_tokens_details: null`**, so `cached_tokens` is unavailable on
the endpoint under test and `ttft_s` is the only available evidence there. This is a
limitation of the endpoint, not a choice, and it is why the layout mode measures latency
rather than counters.

## Baselines

Turn 1 is the baseline for the conversation mode: the same scene with the least history.
`volatile-first` is the baseline for the layout mode — it is what the code does now.

## Procedure

```bash
uv run python -m utils.scripts.research.run_conversation_scaling --mode conversation \
  --turns 10 --max-turns 5 --suggestions 0 --context-beats 100 --model skynet \
  --experiment docs/research/experiments/EXP-2026-08-005-conversation-scaling

uv run python -m utils.scripts.research.run_conversation_scaling --mode layout \
  --turns 10 --passes 2 --model skynet \
  --experiment docs/research/experiments/EXP-2026-08-005-conversation-scaling
```

No aggregate is computed over turns, deliberately: the question is how the numbers *change*
from turn to turn, and a mean over a growing series hides exactly that.

## What would falsify this

- Per-turn `total_s` staying flat across ten turns → the scene does not slow down and H1
  is wrong.
- `volatile-last` showing no prefill advantage over `volatile-first` as the transcript
  grows → the prompt ordering is not what is costing the cache, and H3 is wrong.
- Growth appearing in `reading_s`/`planning_s` rather than in the character calls → the
  cost is somewhere other than the transcript-carrying prompt, and H2 is wrong.
