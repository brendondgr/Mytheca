# Conversation-Scaling Latency & Prompt-Cache Correctness

**Status:** planned — not started
**Created:** 2026-08-19
**Owner:** brendondgr

## 1. Introduction

EXP-2026-08-003/004 measured a *single* generation. They say nothing about what the player
actually complains about: that a conversation gets slower as it goes, and that the first
reply takes too long. This plan measures a **10-turn back-and-forth** under a specific
scenario configuration and, in the same pass, establishes whether the prompt is laid out so
the inference server's prefix cache can actually be reused between turns.

The two questions are one question. A turn's prompt grows with the transcript, so if the
cacheable prefix survives from turn to turn the cost of re-reading the conversation is
near-zero and latency should scale with *output* length only. If it does not, every turn
re-processes the entire conversation from scratch and latency scales with conversation
length — which is exactly the reported symptom.

An exploratory probe against the live endpoint (recorded in the experiment's ISSUES.md)
already shows the mechanism is real: repeating a prompt hits ~99 % cached, appending to the
end of it still hits ~98 %, but changing a single character-stat value that sits *before*
the transcript drops the hit rate to ~46 %. `character_turn_agent._build_user_prompt` places
current stat values, register-selected voice samples and the speaker's recent lines in the
**HEAD** of the user message, ahead of the transcript in the MIDDLE.

## 2. Gaps & Unanswered Questions

**Resolved by inspection:**

1. **Is the cacheable region actually stable?** The *system* message
   (`output contract + ctx.stable_prefix`) is built from the world title/genre, world primer
   and stat *guidance* — all authored once and never rewritten during play. It is
   byte-identical across speakers and across turns. That part of the design works.
2. **Where does it break?** In the *user* message. `_build_user_prompt` orders HEAD
   (identity, voice samples, **current stat values**, recent lines) → MIDDLE (setting,
   roster, lore, **transcript**) → TAIL (act-now cue). Everything volatile sits in front of
   the largest and most append-only block.
3. **Can the endpoint report cache hits?** Yes — `usage.prompt_tokens_details.cached_tokens`.
   `llm._prompt_tokens` currently reads `prompt_tokens` only and discards it.
4. **What config does the measurement use?** The one the request named:
   `suggestionsCount = 0`, `maxTurns = 5`, `contextBeats = 100`, 10 player turns.

**Needs human input:** none for the measurement. Whether to *act* on a confirmed
cache-ordering problem is a separate decision, deliberately left out of scope here — see
Phase 4.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Make the cache observable

#### Step 1.1 — Capture `cached_tokens` from the usage payload
- **Locations:** `web/backend/app/services/llm.py` — `_prompt_tokens` gains a sibling that
  reads `usage.prompt_tokens_details.cached_tokens`; `chat_complete_usage` and
  `chat_complete_stream` return it alongside `prompt_tokens`.
- **Rationale:** the investigation cannot be run, or re-run later, against a number nobody
  records. This also makes a future cache regression visible instead of silent.

#### Step 1.2 — Surface it on the existing `context` trace step
- **Locations:** `web/backend/app/services/turn_engine.py` (the `context` trace already
  carries `promptTokens`; add `cachedTokens`), `docs/api-contract.md`.
- **Rationale:** the Inspector already renders this step per turn, so the cache-hit rate
  becomes visible per beat with no new UI.

> *Action: `uv run pytest utils/tests/backend/services/test_llm.py utils/tests/backend/services/test_llm_streaming.py utils/tests/backend/api/`. Commit: `[Conversation Scaling] (1/4) Complete: The prompt-cache hit rate is captured and traced.`*

### Phase 2 — Drive a real 10-turn conversation and measure every step

#### Step 2.1 — Build the conversation runner
- **Locations:** `utils/scripts/research/run_conversation_scaling.py`.
- **Rationale:** it must drive the **real** `POST /api/play/{id}/turn` endpoint, not the
  agent in isolation, because the question is about the whole turn — assemble, intent,
  planner, per-beat character calls — not one completion. It creates its own storyline,
  cast, setting and scenario at the configured settings so the run is reproducible and does
  not depend on the dev database's contents.

#### Step 2.2 — Record per-turn and per-beat timings
- **Rationale:** "measure it at every step of the way" is the request. Per turn: time to
  first frame, to first visible prose, to each trace step, and total. Across turns: prompt
  tokens, cached tokens, and beat count, so the growth curve is visible.

> *Action: run it; `make validate-research`. Commit: `[Conversation Scaling] (2/4) Complete: A 10-turn conversation is measured end to end at the configured settings.`*

### Phase 3 — Isolate the cache-ordering effect

#### Step 3.1 — A controlled layout comparison
- **Locations:** the same runner, second mode.
- **Rationale:** the conversation run shows *what* happens; this shows *why*. Same token
  count, same content, two layouts — volatile-before-transcript (what the app does) and
  volatile-after-transcript — measuring cached-token ratio across a growing transcript.

> *Action: run it. Commit: `[Conversation Scaling] (3/4) Complete: The prompt-layout effect on cache reuse is isolated.`*

### Phase 4 — Report

#### Step 4.1 — Record and reconcile
- **Locations:** `docs/research/experiments/EXP-2026-08-005-conversation-scaling/`,
  `docs/checklist.md`, `docs/data-flow.md` if the prompt-layout finding is confirmed.
- **Rationale:** a confirmed ordering defect is a finding to record, not a refactor to
  perform inside a measurement task. Reordering `_build_user_prompt` changes what every
  character sees and in what order — a prompt-engineering change with quality consequences
  that must be evaluated on quality, not only on latency. It is written up as a
  recommendation with its expected saving, and left as an explicit decision.

> *Action: full gate. Commit: `[Conversation Scaling] (4/4) Complete: Findings recorded.`*

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Cache capture | `cached_tokens` read from usage on both transports | `web/backend/app/services/llm.py` |
| Cache trace | `cachedTokens` on the `context` trace step | `web/backend/app/services/turn_engine.py` |
| Conversation runner | Drives 10 real turns; records per-turn + per-beat timings | `utils/scripts/research/run_conversation_scaling.py` |
| Layout comparison | Volatile-first vs volatile-last cache reuse | same runner, `--mode layout` |
| Experiment | Protocol, results, figures, issues | `docs/research/experiments/EXP-2026-08-005-conversation-scaling/` |
| Backend tests | Cache capture on both transports | `utils/tests/backend/services/` |
