# RESULTS — EXP-2026-08-018 · Narrative style instructions (romance), before/after

12/12 runs completed, no failures. Local route only (`llama.cpp · local`,
`gemma-4-26B-it`), 51.6 s wall clock, 15,180 input tokens.

## Headline

**A style guide placed in the cached system prefix does reach the prose.** The model reads
it from there; it does not need to ride in the volatile recency tail. That is the
decision-relevant result, because the tail placement would have cost the whole
prefix-cache design.

The lexical counters move in the predicted direction. They do **not** establish the effect
at n=6 per arm, and no significance test was run. The paired passages in
`logs/passages.json` are the evidence; the counters are corroboration.

## Aggregate (n=6 per arm — mean ± population std)

| Metric | `baseline` | `romance` | Predicted |
| --- | --- | --- | --- |
| **proximity_per_1k** (primary) | 5.70 ± 3.81 | **9.62 ± 3.41** | higher ✓ direction |
| interiority_per_1k | 1.73 ± 2.52 | 2.20 ± 2.62 | higher — **noise** |
| named_emotion_per_1k | 0.00 ± 0.00 | 0.00 ± 0.00 | lower — **no signal** |
| dialogue_share | 0.247 ± 0.117 | 0.239 ± 0.077 | unchanged ✓ |
| chars | 379 ± 176 | 437 ± 221 | not predicted |
| has_speech | 1.0 | 1.0 | — |

The primary metric is higher in the style arm in **5 of 6 matched pairs**. The arms
nevertheless **overlap**: the best baseline run (12.72, kitchen s3) beats four of the six
romance runs. This is a direction, not a separation — unlike EXP-2026-08-007, where the
arms did not overlap at all on its primary metric.

`named_emotion_per_1k` is **0.0 in every run of both arms**. The metric is a dud, not a
win: the shipped output contract already produces prose that never names an abstract
feeling, so the guide's "Never narrate a feeling" line had nothing left to suppress. It
should not be reused in this form.

## What actually changed (the qualitative record)

Three of the four blocks show up legibly. Quotations are from `logs/passages.json`.

**Texture — "shared objects carry the history".** The clearest effect, and the one the
counters miss entirely. The style arm converges on a small recurring inventory (the kettle,
the coat, the radiator) and *carries it between scenes*: in `kitchen s2` Nadia thinks the
radiator in her room "has started clicking in a way that sounds like a countdown", and in
`doorway s3` Emile ends his beat with "the radiator in your room is still clicking. I'll
tighten it tomorrow." Nothing in the prompt connected those two beats. The baseline arm
produces no comparable recurring object.

**Voice — "kindness is done, not announced".** Every baseline doorway beat announces
presence: *"I'll be here" · "I'll stay in the kitchen" · "I'll make tea"*. Every romance
doorway beat offers a physical act instead: *"I'll leave the light on" · "I'll leave the
kettle on" · "I'll tighten it tomorrow"*. Three for three, both ways.

**Attention — "the body's small betrayals".** The style arm reaches for a specific,
unflattering physical tell: "winding it around my index finger until the tip turns pink",
"her fingers hovering just a second too long against the cold metal", "my hands staying
deep in my pockets". The baseline arm does this occasionally ("my fingers hovering near the
handle before I pull back") but not reliably.

**Signature — "only one person is brave".** `doorway s3`, style arm, is the pattern
exactly: she almost speaks, lets her hand drop, and he answers with the smaller thing.

## Counter-evidence, stated

- `kitchen s3` inverts the primary metric (baseline 12.72 vs romance 9.56).
- **Both arms open near-identically** — "I lean my shoulder against the doorframe" recurs in
  four of six kitchen beats across *both* arms. The fixed scene anchors the opening far more
  strongly than the style does. Any future run should vary the opening or measure past it.
- The "say slightly less than they mean" line is not clean: `kitchen s2` in the style arm
  spells out the alternatives ("I could tell him that I'm worried about the rent
  increase…"), which is the same move the baseline makes in `kitchen s1`.

## The confound that limits this result

The style arm carried **both** the prefix guide and the tail Signature. This experiment
therefore cannot say which of the two did the work. A three-arm run (`baseline` ·
`prefix-only` · `prefix+signature`) separates them and is the obvious follow-up; until it is
run, "the prefix placement is sufficient" is supported only in the bundle.

Also unmeasured, by design: the **Pacing** block (targets the planner; no planner call
here), cache behaviour across a real turn loop, and scenario-level override composition.

## Conclusion

Proceed with the design as specified: five blocks, style guide in the cached prefix between
the contract and the world primer, Signature in the tail. Drop `named_emotion_per_1k` from
any future measurement. Run the three-arm separation before claiming the tail Signature is
either necessary or redundant.
