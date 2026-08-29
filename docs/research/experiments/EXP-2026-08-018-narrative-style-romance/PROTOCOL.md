# PROTOCOL — EXP-2026-08-018 · Narrative style instructions (romance), before/after

**Pre-registered.** Written before any call was made. The script implements this file.

## Question

Does attaching a storyline-level **narrative style guide** to the cached system prefix
measurably change the prose a character beat comes back with — on the *local* model, in the
direction the guide asks for — or does the model write the same passage either way?

This is the feasibility check for the feature described in `docs/plans/` (narrative style
instructions). It is deliberately small: one genre (romance, the most obviously-shaped of
the three drafted guides), one storyline, two scenes, one model.

## Hypothesis

Stated before the run. The romance guide asks for proximity and physical specifics, for
interiority, and forbids naming a feeling that could be shown. So:

- **Primary** — `proximity_per_1k` (a lexicon of distance/touch/gaze/breath words, per 1000
  characters of passage) is **higher** in the `romance` arm than in `baseline`.
- Secondary, directional: `interiority_per_1k` **higher**; `named_emotion_per_1k`
  **lower** (the "Never narrate a feeling" line); `dialogue_share` roughly unchanged (the
  guide says nothing about how much people talk).

A null result is a real answer and is reported as one: it would mean the guide needs to
ride in the recency tail rather than the cached prefix, which is the design's main open
trade-off.

## Arms

Two, differing **only** in the style text. Same scene, same cast, same transcript, same
sampler, same `register`, interleaved per sample so endpoint drift cannot land on one arm.

| Arm | System message |
| --- | --- |
| `baseline` | `CHARACTER_OUTPUT_CONTRACT` + `\n\n` + stable prefix (world primer) — **exactly what ships today** |
| `romance` | `CHARACTER_OUTPUT_CONTRACT` + `\n\n` + **style guide** + `\n\n` + stable prefix |

The style guide is inserted *between* the contract and the world primer, which is the
placement the design recommends for prefix-cache reuse (widest sharing scope first).

The `romance` arm additionally appends the one-line **Signature** to the end of the user
prompt — the only piece of the design that rides in the volatile recency tail. The harness
appends it after the act-now cue rather than fusing it into that cue; in the shipped
feature it would be fused. This is a fidelity gap, recorded rather than hidden.

## Not measured here

- **The Pacing block.** It targets the planner's system message, and this harness makes no
  planner call. Whether style changes *turn shape* is a separate experiment.
- **Cache behaviour.** The design's cache claim (`reusable_prefix_chars` unchanged
  beat-to-beat) is a property of the placement, not of the prose, and needs a full turn
  loop to observe. Not run.
- **Scenario-level override composition.** Not exercised.

## Prompts

Two scenes from one invented storyline, both two-handers at a charged-but-not-dangerous
moment — the situation a romance guide is supposed to be good at. Built through the
engine's own `character_turn_agent._build_user_prompt`, so the harness cannot drift from
what the app actually sends. They ship in this repository and are therefore contaminated
for any held-out use.

## Model

The **local** endpoint only — `llama.cpp · local` (`gemma-4-26B-it`) via the relay at
`http://localhost:4000/v1`, model id `local`. No remote route is called. Sampler comes from
`character_turn_agent._voice_params` at `register="neutral"`, so both arms get identical
generation parameters.

## Measures

Crude lexical counters, and they are declared crude: they are shadows of the thing, not the
thing. The **primary evidence is the paired passages**, recorded in full in `data/`. Three
lexicons (proximity, interiority, named-emotion) are defined in the script and are the
pre-registered ones; no lexicon may be edited after seeing the output.

- `chars`, `words`, `paragraph_breaks`, `has_speech` — form, carried from EXP-2026-08-007
- `dialogue_share` — characters inside paired quotes / total characters
- `proximity_per_1k`, `interiority_per_1k`, `named_emotion_per_1k`

## n

2 scenes × 2 arms × 3 samples = 12 calls. Small on purpose: this is a feasibility check,
not a powered comparison. **No significance test will be run and none will be claimed.**
Per-run rows are the result; if any run fails, its arm gets no aggregate
(the EXP-2026-08-001 rule).
