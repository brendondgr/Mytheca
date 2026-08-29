# ISSUES — EXP-2026-08-019

## 1. The preflight caught its own bug before any model time was spent

The first attempt died in the arm-difference assertion: `build_messages` returns a list of
message dicts, and the check indexed `probe[arm][1]` as a string. It failed loudly, before
the first call, and cost nothing. Recorded because the assertion is the point — a harness
whose arms silently collapse into each other is worse than no harness, and this one is the
only thing standing between "the signature does nothing" and "the signature was never in the
prompt". Fixed by keying the probe by message role and asserting all four relations:
`prefix` differs from `baseline` in the system message; the two style arms share a
byte-identical system message; `prefix` leaves the user prompt untouched; and the signature
is the *only* difference in `prefix_signature`'s user prompt.

## 2. This experiment refutes part of its own predecessor

`EXP-2026-08-018`'s `baseline` and this one's are the same prompts, and the two runs differ
by more than that experiment's reported effect. Its primary number is uninformative, not
merely weak. An `AMENDMENTS` section has been appended to it rather than editing its
`RESULTS.md`, per the append-only rule for completed experiments.

This is a finding, not a mistake to hide: it is exactly why the separation was recorded as
owed instead of being waved through.

## 3. The "kettle" convergence is post-hoc

The 1/3 · 2/3 · 3/3 count is not a pre-registered metric. It was noticed while reading the
passages and is reported as a shape to test, never as a result. It is not in
`metrics.values`.

## 4. Unchanged limitations, carried from EXP-2026-08-018

- **Pacing is not exercised.** No planner call is made.
- **Cache behaviour is not observed** across a real turn loop.
- **The fixed scene anchors the opening.** Both experiments reuse two scenes whose first
  sentence the model reproduces near-identically across arms, which suppresses any measurable
  difference in exactly the position style would show first.
- **`total_output_tokens` is 0**: `llm.chat_complete_usage` surfaces `prompt_tokens` and
  `cached_tokens` only. Unrecorded, not zero.
