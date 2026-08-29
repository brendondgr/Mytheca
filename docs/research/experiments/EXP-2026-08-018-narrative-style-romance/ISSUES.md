# ISSUES — EXP-2026-08-018

## 1. First run aborted: the harness left the reasoning channel on (recorded, not deleted)

The first attempt hung. `run_style_guide.call` was a hand-rolled `POST /chat/completions`
that sent the sampler fields and nothing else — no reasoning control. The local route
(`llama.cpp · local`, `gemma-4-26B-it`) **is a reasoning model**: it answers with
`reasoning_content`, and with no budget key the server default applies
(`--reasoning-budget -1`, unlimited). A 16-token probe made it plain — the whole budget went
to `reasoning_content` and `content` came back empty:

```
{"finish_reason":"length","message":{"content":"","reasoning_content":"The user wants me to say \"OK\".\nThe input is"}}
```

A character beat ships with the channel explicitly **off**
(`character_turn_agent.TURN_EFFORT` is `ReasoningEffort.NONE`), so the harness was not
measuring what the app does. It was killed with no rows written and no partial data kept.

**Fix:** `call()` now goes through the engine's own `llm.chat_complete_usage` with
`reasoning=ReasoningEffort.NONE`, which applies the backend-specific reasoning-off that the
app applies. Per-call latency went from "hung past 120 s" to ~3 s. This is the same lesson
as `mytheca-relay-model-shapes`: both relay routes expose a reasoning channel, and a harness
that bypasses the engine's LLM layer silently gets a different model.

## 2. Fidelity gaps, stated rather than hidden

- The **Signature** line is appended after the act-now cue rather than fused into it. The
  shipped feature would fuse it. Position in the tail is near-identical; the wording seam is
  not.
- The **Pacing** block is not exercised at all — it targets the planner's system message and
  this harness makes no planner call.
- `dirty: true` in the manifest: the entrypoint script and this experiment folder were
  uncommitted at run time. Nothing under `web/backend/app/` was modified — the arms differ
  only by the style text passed into an unmodified prompt builder.

## 3. n is 12

A feasibility check, not a powered comparison. No significance test was run and none is
claimed. The paired passages in `logs/passages.json` are the primary evidence; the lexical
counters are crude proxies, pre-registered in `PROTOCOL.md` and not edited after seeing
output.

## 4. `named_emotion_per_1k` measured nothing

0.0 in all 12 runs, both arms. The shipped output contract already yields prose that never
names an abstract feeling, so the romance guide's "Never narrate a feeling" line had nothing
to suppress. Recorded as a dead metric so it is not reused in this form.

## 5. `total_output_tokens` is 0 in the manifest

`llm.chat_complete_usage` fills `usage_out` with `prompt_tokens` and `cached_tokens` only —
it does not surface `completion_tokens`. The figure is unrecorded rather than zero. Passage
lengths in characters are in `data/metrics.csv` and are the usable proxy.
