# PROTOCOL — EXP-2026-08-019 · Separating the Signature from the prefix guide

**Pre-registered.** Written before any call was made. The script implements this file.

## Question

`EXP-2026-08-018` showed that attaching a narrative style guide changes the prose. Its style
arm carried **two** things at once — the four prose blocks in the cached system prefix *and*
the one-clause `signature` in the volatile recency tail — so it could not say which did the
work. That experiment recorded the separation as owed. This is it.

The decision it feeds: `signature` is the only block re-read on **every beat**. If the
cached prefix is doing all the work, the field is a per-beat cost buying nothing and should
be deleted from the contract rather than left in because it seemed like a good idea.

## Hypothesis

Stated before the run. Two outcomes are interesting and one is not:

- **The prefix carries it.** `prefix` ≈ `prefix+signature`, both above `baseline`. Then the
  signature is redundant and the field comes out.
- **The signature carries it.** `prefix` ≈ `baseline`, `prefix+signature` above both. Then
  the cached-prefix placement is not sufficient and the design's main trade-off was called
  wrong — the guide would have to move into the tail, at a real per-beat cost.
- **Both contribute.** `baseline` < `prefix` < `prefix+signature`. The field stays.

**Primary metric:** `proximity_per_1k`, unchanged from `EXP-2026-08-018` so the two are
comparable. No significance test will be run and none will be claimed.

## Arms

Three, differing **only** in which blocks the resolver is given. Same scene, same cast, same
transcript, same sampler, interleaved per sample.

| arm | style blocks passed to `style_guide.resolve` |
| --- | --- |
| `baseline` | none — byte-identical to what shipped before the feature |
| `prefix` | the romance guide **minus** `signature` |
| `prefix_signature` | the whole romance guide |

## What is different from EXP-2026-08-018

That harness hand-assembled the prompts. **This one drives the shipped code**:
`style_guide.resolve` → `assembler._build_stable_prefix` → `character_turn_agent._build_user_prompt`,
with the signature fused into the act-now cue by the engine itself rather than appended by
the harness. So the fidelity gap recorded in `EXP-2026-08-018`'s ISSUES.md is closed here,
and the arms differ by a single argument rather than by two hand-built strings.

The scenes and the romance guide text are otherwise identical, so the `baseline` and
`prefix_signature` arms are directly comparable to that experiment's two arms.

## Not measured here

- The **Pacing** block (targets the planner; no planner call in this harness).
- Cache behaviour across a real turn loop.
- Whether `named_emotion_per_1k` is worth measuring — `EXP-2026-08-018` found it 0.0 in
  every run of both arms and recorded it as a dead metric. **It is not collected here.**

## Model

The **local** endpoint only — `llama.cpp · local` (`gemma-4-26B-it`) via the relay at
`http://localhost:4000/v1`, model id `local`. No remote route is called. Calls go through
`llm.chat_complete_usage` at `ReasoningEffort.NONE`, matching what a character beat ships
with; a harness that POSTs directly gets a different model (see `EXP-2026-08-018` ISSUES §1).

## n

2 scenes × 3 arms × 3 samples = 18 calls. A separation check, not a powered comparison.
Per-run rows are the result; a failed run means its arm gets no aggregate.
