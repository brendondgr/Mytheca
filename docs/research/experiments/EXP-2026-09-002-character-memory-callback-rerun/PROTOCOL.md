# PROTOCOL — EXP-2026-09-002 · character-memory-callback-rerun

**Written before the run.** Fixed in advance so the analysis cannot be chosen after
seeing the numbers.

**This supersedes `EXP-2026-09-001`, which failed on a confound rather than on a result:
its two arms were separate backend processes started 20 minutes apart, and the repository
changed in between.** The question, the arms, the metrics and the reporting rules are
carried over unchanged — deliberately, so the two are comparable — and exactly two things
are added, both aimed at that failure.

## The question

Does episodic recall (`docs/plans/character-memory-graph.md`, Phases 2–6) cause characters
to reuse *specific prior material* in later turns — and if so, how often?

"Does it read better?" is deliberately **not** the question. This repository has the
cautionary case on file: `EXP-2026-08-018` reported a prose effect and `EXP-2026-08-019`
moved the same unchanged baseline by more than that effect. A quality claim from a handful
of scenes against a nondeterministic model would be noise wearing a number's clothes.

## Primary metric — verbatim callback rate

For every character beat in a play-through: does it contain a span of **quoted speech**, at
least 20 characters long, that also appears verbatim in a beat from an **earlier turn**?

    verbatim_callback_rate = beats containing such a span / character beats after turn 1

Three properties make this worth measuring rather than judging:

- **Deterministic.** A substring comparison over persisted `events.data`, with whitespace
  normalised. No judge model, no rubric, no rater.
- **Uses the engine's own definition of speech.** `prose_guards.quoted_spans` — the same
  function `memory_store.quote_is_real` verifies against — so "a quote" means one thing in
  the harness and in the engine.
- **Turn-scoped, not beat-scoped.** A span reused from the *same* turn is a character
  echoing what was just said, which the transcript already supplied. Only material from a
  turn that has ended requires the memory layer to have carried it.

### The baseline is measured, not assumed

An earlier draft of the plan asserted this rate is "zero by construction" with recall off.
That is too strong and it is not being assumed here. A model given a long transcript can
reuse an earlier line without any memory layer, and how often it does is the number this
experiment exists to establish. **The recall-off arm is a real measurement.**

## Secondary metrics

- `recall_fire_rate` — turns in which recall surfaced at least one memory (from the
  persisted `memory` trace step). Recall firing is a precondition for the primary metric;
  a null primary result means something different if recall never ran.
- `cue_share` — of the memories surfaced, the share that had at least one **subject cue**
  hit rather than being reached by participants alone. This is the direct test of whether
  Phase 5's cue channel earns its place.
- `memories_per_turn` — write volume, to check the salience floor against the concern
  already recorded in `docs/checklist.md`.
- `verbatim_callback_rate_loose` — the same measure at a 12-character span instead of 20.
  A null primary has two very different explanations ("no callbacks happened" and "callbacks
  happened and were shorter than the threshold"), and without a second threshold the write-up
  cannot tell them apart. Declared here **before** the first recorded run, not chosen after.
- `quote_offer_share` — of the memories recall actually surfaced, the share carrying a
  verified quote. The mechanism check: a quote cannot be called back if none was offered, so
  a null primary alongside a low share points at the **write** path rather than at the
  model's willingness to reuse a line.

`quote_verification_failure_rate` (how often the model proposed a quote that was not real)
is **not** collected: rejections are logged at DEBUG and not persisted, so it is not
recoverable from the record without a code change made for the measurement's convenience.

## Arms

| Arm | `MEMORY_RECALL_ENABLED` | Memories written? | Memories recalled? |
| --- | --- | --- | --- |
| `off` | `false` | yes | no |
| `on` | `true` | yes | yes |

Writing stays on in both arms deliberately. It isolates **recall** as the only difference,
and it is also what the kill switch actually does in production.

## What is new in the re-run

1. **Both arms start from the same commit, in the same step.** The arms are two processes
   because `MEMORY_RECALL_ENABLED` is a process global; that makes "which code is this
   process running" a per-arm property, and `manifest.yaml`'s single `code.commit` field
   silently assumes it is not. The commit is recorded here and both servers are launched
   together before any run.
2. **Beat counts are a reported quantity, not a diagnostic.** The failed run's `on` arm
   produced 12 character beats in both runs against the `off` arm's 23 and 31 — a large,
   consistent difference nothing in the design predicts, since memories reach the character
   prompt tail and not the planner's. It may have been the code confound; it may be real. It
   is reported either way, and a repeat of it is a finding rather than an aside.

## Procedure

0. Both backends are started from one commit, in one step, before any run:
   `69f0c83adb0860f7b8db81779afd0437dbfc4848`.
1. One backend per arm, differing only in `MEMORY_RECALL_ENABLED`.
2. Each run builds a fresh throwaway world (identical cast, setting and player directions
   across arms and runs) and plays 4 turns. Four rather than three: recall has nothing to
   work with in turn 1, so a 3-turn scene offers only two opportunities.
3. Metrics are computed from the persisted `events` and `turn_traces` rows — never from
   the stream — so a reload would produce the same numbers.
4. **The worlds are kept, not torn down.** Each run records its `storylineId`, `scenarioId`
   and `sessionId` so the exact rows behind every number can be re-read. A deleted storyline
   takes its events, traces and memories with it, which would leave the record
   un-examinable — the one thing this contract exists to prevent. Cleaning them up later is
   a `DELETE /storylines/{id}` per row in `data/runs.jsonl`.

## Reporting rules

- **Per-run rows are the record.** `manifest.yaml` also carries mean ± std because the
  schema requires it for `n > 1`, and that is not a contradiction as long as the write-up
  says what the std is: the spread of two points, not an estimate of a distribution. The
  rule `EXP-2026-08-001` established — never aggregate over the *survivors* of a partially
  failed run — is a separate and absolute one, and a run whose turns errored is excluded
  from the arm rather than averaged into it (the runner exits non-zero for exactly this).

  *(Clarified after this file was first written and before any run finished — the reporting
  format was under-specified, the analysis is unchanged.)*
- n is small by design. This establishes **existence and rough magnitude**, not a
  distribution, and the write-up must say so rather than implying a measured effect size.
- Provider-side nondeterminism is present at any temperature; two runs per arm cannot
  separate it from the treatment. Any per-run spread is reported, not smoothed.
