# ISSUES — EXP-2026-09-001

## Fatal: the two arms ran different code

**Status `failed`. The numbers in `data/runs.jsonl` are real measurements of two systems
that differ by more than the treatment, so they cannot be read as a comparison.**

The arms are two backend processes because `MEMORY_RECALL_ENABLED` is read through a
process-global `get_settings()`. They were started at different times, and the repository
changed in between:

| | started | includes plan Phase 6? |
| --- | --- | --- |
| `on` arm (port 3355) | 22:09:36 | **no** |
| Phase 6 written (`memory_recall.semantic_boosts`, `memory_cues.promotable`, `rag.entries.entry_from_memory`, `reflection._promote_subjects`) | 22:21–22:23 | — |
| `off` arm (port 3357) | 22:30:15 | **yes** |

The intended difference between arms was one boolean. The actual difference was one boolean
plus a phase of the feature.

### The tempting rescue, and why it is refused

There is a real argument that the code difference was *inert here*: the semantic channel
fires only when the cue scan finds nothing, and `cue_share` is 1.0 in both `on` runs, so
cues fired every turn and the gate would have stayed shut. Subject promotion writes to the
graph and is not read by recall at all.

That argument is plausible and it is still refused. It was constructed **after** seeing which
way the numbers went, it rests on a metric (`cue_share`) computed from the same broken run,
and accepting it would mean this experiment's validity is an inference rather than a
property of how it was run. A controlled comparison is cheap to re-do; a rescued one is
permanently unciteable.

### Second, unexplained signal — recorded, not explained

The `on` arm produced **12 character beats in both runs**; the `off` arm produced 23 and 31.
That is a large, suspiciously consistent difference in scene length, and nothing in the
design predicts it — memories reach the *character* prompt tail, not the planner's, so turn
length should not move. Candidate explanations, none tested:

- the code difference above;
- the two backends' differing uptime / warm state;
- ordinary planner variance that happened to land this way twice.

This is the single most interesting thing the run produced and it is exactly what the
re-run must be able to speak to. It is why the re-run keeps beat counts as a reported
quantity rather than a diagnostic.

## Process failure, not just a run failure

The protocol fixed the arms, the metrics and the reporting rules in advance, and said
nothing about **pinning the code the arms run**. `manifest.yaml` has a `code.commit` field
per experiment, which silently assumes one commit for the whole experiment — an assumption
that is false the moment an experiment's arms are separate long-lived processes.

The successor records the commit each arm's process was started from, and starts both from
the same one in the same step.

## What is kept

`data/runs.jsonl` and the four play-throughs it names (`storylineId` per row) are retained.
They are a valid record of *what happened*, and the beat-count signal above is worth being
able to re-read. They are not evidence about recall.
