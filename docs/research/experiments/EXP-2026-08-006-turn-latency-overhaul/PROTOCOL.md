# PROTOCOL — EXP-2026-08-006 Turn latency overhaul

> Written before the run. The comparison arm (EXP-2026-08-005) was measured on 2026-08-19
> against the same endpoint and the same scene configuration.

## Question

Five changes were made to the turn loop on the strength of
[EXP-2026-08-005](../EXP-2026-08-005-conversation-scaling/RESULTS.md)'s cost breakdown.
Do they actually reduce what a player waits through — and does the prompt cache, which
that experiment showed was entirely unused, now get reused as a scene lengthens?

## Hypothesis

Stated ahead of the run, per change, against EXP-2026-08-005's measured numbers:

* **H1 — the planner's share falls.** It was 41 % of all turn time at ~4.9 s × 31 calls
  over ten turns. Deciding up to 3 beats per call should cut the call count roughly
  threefold; its share should fall below 25 %.
* **H2 — the continuity guard's 11 % is gone entirely.** It was ~10 s each time a second
  character spoke. There is no `consistency` step to measure any more, so this is a
  prediction about the *total*, not about a step.
* **H3 — the prompt is reused.** The reordering + block-anchored window should show a
  reusable prefix that is a large fraction of the prompt and does **not** decay across
  turns, against a hit rate that fell 44 % → 17 % before. Concretely: mean
  `reusablePrefixChars / promptChars` above 60 % from turn 3 onward.
* **H4 — no turn stalls for the full generation window.** Two of ten turns in the baseline
  took 355 s and 272 s, dominated by a single planner call that hit `LLM_GEN_TIMEOUT_SECONDS`
  exactly. With a 25 s ceiling on structural calls, no per-turn total should exceed ~120 s.
* **H5 — time to *something visible* collapses.** Not time to prose: with reasoning
  visibility defaulting to `full`, the first reasoning token (~0.4 s measured in
  EXP-2026-08-005) is what the player now sees first, against ~10 s to first prose.

Deliberately **not** hypothesised: that time-to-first-*prose* improves. Nothing in this
work shortens the model's deliberation, and H1's saving lands on the beats after the first.

## Setup

Arms are **code versions**, not runtime flags, so this is a before/after against a recorded
baseline rather than a within-run comparison. That is a real weakness and is listed under
threats.

| | Baseline (EXP-2026-08-005) | This run |
| --- | --- | --- |
| Structural-call timeout | shared 300 s prose window | `llm_decision_timeout_seconds` = 25 s |
| Continuity guard | `services/consistency.py`, ~10 s per later speaker | removed |
| Beat planning | `planner_agent.next_beat`, one call per beat | `plan_beats`, `TURN_PLANNER_LOOKAHEAD` = 3 |
| Prompt order | identity + live stats → transcript → act-now | setting/roster → transcript → volatile |
| Transcript window | `buffer.recent_turns` (slides one beat per turn) | `buffer.anchored_turns`, block 20 |
| Reasoning visibility | `summary` (no live reasoning on the wire) | `full` |
| Reflection | inline, end of turn | **unchanged** (explicitly out of scope) |

Endpoint: the relay at `http://localhost:4000/v1`, model `skynet` — the remote GPU
(observed upstream `qwen38-27B-awq`). Same as the baseline.

## Data

A storyline, cast, setting and scenario created by the runner itself
(`utils/scripts/research/run_conversation_scaling.py`, `--mode conversation`) so the run
does not depend on the dev database's contents, followed by ten player turns from a fixed
script. The player lines ship in the runner and are identical to the baseline's, so the
two runs are driven by the same input. Nothing here is held-out data; no model is trained.

## Metrics

| Metric | Definition | Direction |
| --- | --- | --- |
| `first_visible_s` | Seconds from request start to the first **prose** delta of the turn (narration or character dialogue). Excludes trace and reasoning frames. | lower better |
| `total_s` | Seconds from request start to the last frame of the turn. | lower better |
| `beats` | Count of visible character/narrator beats produced in the turn. Context for `total_s`, which is not comparable turn to turn without it. | — |
| step share | Σ of the gaps between consecutive trace milestones attributed to one step, ÷ Σ over all steps, across the ten turns. | lower better per step |
| planner calls | Count of `planning` trace steps across the ten turns. The direct test of H1. | lower better |
| `prompt_tokens_max` | Largest server-reported `usage.prompt_tokens` in the turn. | context |
| reuse ratio | `data.reusablePrefixChars ÷ data.promptChars` on the `context` trace — the share of a character prompt byte-identical to the previous character call in the session. Computed locally, so it exists even when the endpoint omits its cache counter. | higher better |
| `cached_tokens_max` | Server-reported `usage.prompt_tokens_details.cached_tokens`. Recorded when present; **absent is not zero** on this endpoint. | higher better |

## Baselines

[EXP-2026-08-005](../EXP-2026-08-005-conversation-scaling/RESULTS.md), same endpoint, same
`maxTurns = 5` / `suggestionsCount = 0` / `contextBeats = 100` / 10 turns, run one day
earlier. Its per-turn table and step-cost table are the comparison. Its logs are in that
experiment's `logs/`, unmodified.

## Procedure

```bash
# 1. Backend running with the post-overhaul code, pointed at the relay.
uv run python app.py backend

# 2. Ten real turns through POST /api/play/{id}/turn at the configured settings.
uv run python -m utils.scripts.research.run_conversation_scaling \
  --mode conversation --turns 10 --max-turns 5 --suggestions 0 --context-beats 100 \
  --base-url http://localhost:4000/v1 --model skynet \
  --experiment docs/research/experiments/EXP-2026-08-006-turn-latency-overhaul

# 3. Figures + validation.
make figures
make validate-research
```

No seed is set: the endpoint is sampled at the operator's configured temperature (0.7),
matching the baseline. This is a source of variance and is listed under threats.

## What would falsify this

* **H1** — the planner still accounts for ≥ 35 % of turn time, or the `planning` step count
  is not materially below the baseline's 31.
* **H2** — total turn time does not fall on multi-speaker turns.
* **H3** — the reuse ratio is near zero, or decays across turns the way the baseline's hit
  rate did. This is the one that would say the reordering is cosmetic.
* **H4** — any turn total lands near 300 s again.
* **H5** — no reasoning frames appear on the wire.

A result where latency improves but the reordered prompt produces visibly worse writing is
**not** a success. The quality read is recorded in RESULTS.md alongside the timings, and if
it is bad the recommendation is to revert the reorder, not to keep the speed.
