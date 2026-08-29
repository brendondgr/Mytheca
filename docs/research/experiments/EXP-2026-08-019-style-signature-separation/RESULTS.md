# RESULTS — EXP-2026-08-019 · Separating the Signature from the prefix guide

18/18 runs completed, no failures. Local route only (`llama.cpp · local`, `gemma-4-26B-it`),
75.7 s wall clock, 23,466 input tokens.

## Headline: a null result, and a failed replication

**The three arms cannot be told apart, and — more importantly — this experiment's `baseline`
arm did not reproduce `EXP-2026-08-018`'s `baseline` arm on the same prompts.** The
between-run spread of one unchanged condition is as large as the effect that experiment
reported. Its quantitative claim does not survive.

| Metric | `baseline` | `prefix` | `prefix_signature` |
| --- | --- | --- | --- |
| **proximity_per_1k** (primary) | 8.01 ± 2.11 | 7.29 ± 1.81 | 8.18 ± 3.08 |
| interiority_per_1k | 1.38 ± 1.29 | 0.88 ± 0.97 | 1.62 ± 1.74 |
| dialogue_share | 0.181 ± 0.059 | 0.194 ± 0.046 | 0.185 ± 0.033 |
| chars | 503 ± 253 | 470 ± 186 | 512 ± 211 |

Every interval overlaps every other. Adding the style guide (`prefix`) moved the primary
metric **down**; adding the signature on top moved it back up to where the baseline already
was. None of the three pre-registered outcomes is supported: the answer is that this design
cannot detect the difference, not that one of them is true.

## The replication failure, stated plainly

`baseline` here and `baseline` in `EXP-2026-08-018` are the **same two prompts** — same
contract, same world primer, same scenes, same sampler, same model, same reasoning-off path.
Only the run differs.

```
baseline proximity_per_1k, per run
  EXP-2026-08-018:  0.00  3.82  5.00  5.85  6.84  12.72     mean 5.70
  EXP-2026-08-019:  5.92  6.41  6.54  7.49  10.11  11.59    mean 8.01
```

`EXP-2026-08-018` reported 5.70 → 9.62 as its headline. The same unchanged condition, re-run,
moved 5.70 → 8.01 on its own. **The reported effect is inside the noise of the measurement.**
That experiment already said "direction, not separation" and ran no significance test, so it
did not overclaim — but its primary number should now be read as uninformative rather than
as weak support. An `AMENDMENTS` section has been appended to it.

## What did not change

The qualitative patterns `EXP-2026-08-018` leaned on are **weaker than they looked**, and one
of them is gone. Its cleanest claim was that every baseline doorway beat *announces presence*
while every style beat *offers a physical act*. That does not hold here: this run's baseline
produced "I'll leave the light on in the hall", "I'll have the tea ready when you get back"
and "I'll make coffee" — the offering pattern, unprompted, with no style guide attached.

What survives is narrower and is **post-hoc, not pre-registered**: the style arms *converge*
on one object where the baseline varies.

| doorway runs naming "the kettle" | |
| --- | --- |
| `baseline` | 1/3 |
| `prefix` | 2/3 |
| `prefix_signature` | 3/3 |

Three per cell. This is a shape worth a real experiment, not a result.

One observation does bear on the actual question. The cross-scene texture carry-over that
`EXP-2026-08-018` found most striking — a character volunteering the clicking radiator from
a *different* scene, in the guide's own register ("the words feel too heavy for a Tuesday") —
reproduced here in the **`prefix` arm, with no signature present**. That is a single run, and
it is the only evidence in either experiment that speaks to prefix-versus-tail at all. It
points at the prefix.

## What this means for the feature

- **The style guide's measured effect on prose is unproven.** It remains a reasonable
  authored control — the author asked for it and it does what it says on the tin
  structurally — but no number in this repository supports a claim that it changes output.
  Nothing outside the research record should say otherwise, and the claim has been removed
  from `CLAUDE.md`, `content/style_blocks.py` and the plan.
- **The `signature` field is unjustified by measurement.** It costs tokens on *every beat*,
  it cannot be shown to help, and the one qualitative straw in the wind points at the prefix
  doing the work instead. It is not removed here — an unproven field is not a broken one, and
  removal is a product call — but it is recorded as a deletion candidate in
  `docs/checklist.md`.
- **The measurement design is the thing to fix first.** n=6 per arm on a two-scene fixture
  with a lexicon proxy cannot see an effect this size. A useful successor needs many more
  scenes (the fixed opening anchors too much of the passage), a metric that is not a word
  list, and enough runs to state an interval that means something.

## Method note

Unlike `EXP-2026-08-018`, this harness drives the **shipped** code path —
`style_guide.resolve` → `assembler._build_stable_prefix` → `character_turn_agent._build_user_prompt`
— so the arms differ by one argument rather than by two hand-built strings, and the signature
is fused into the act-now cue by the engine itself. A preflight assertion checks, before any
model call, that the `prefix` arm changes only the system message and the `signature` only the
user message. It caught its own indexing bug on the first attempt (see `ISSUES.md`).
