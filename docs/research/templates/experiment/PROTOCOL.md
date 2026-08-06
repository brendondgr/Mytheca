# PROTOCOL — <EXP-ID> <title>

> **Write this file BEFORE running anything.** Pre-registering the protocol is what
> separates an experiment from a fishing expedition, and it means the paper's methods
> section is already half-written. If you are filling this in after seeing results,
> stop and say so in `ISSUES.md`.

## Question

What is being asked, in one or two sentences. Not the method — the question.

## Hypothesis

Stated ahead of the run, and specific enough to be wrong. If this is exploratory,
write "exploratory — no prior hypothesis" and do not invent one afterwards.

## Setup

The system configuration under test. Which components are active, which are disabled,
what the arms are. Name real files and functions.

## Data

What is being run over: source, version, size, split, and how it was obtained. State
plainly if it ships with the repository — that makes it contaminated for any
held-out use, and the paper will have to say so.

## Metrics

**Defined, not just named.** For each metric: what exactly is counted, over what
denominator, and what a higher value means. A metric that cannot be computed by
someone else from this description is not yet defined.

| Metric | Definition | Direction |
| --- | --- | --- |
| | | |

## Baselines

What this is being compared against, and why that comparison is fair. If a baseline
arm already exists in the codebase, name the file and function.

## Procedure

The exact commands, in order, including seeds. Someone else should be able to run
this section verbatim.

```bash
```

## What would falsify this

The result that would mean the hypothesis is wrong. Write it down now, while it is
still cheap to be honest about it.
