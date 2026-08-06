# Research Record

**Everything that will ever appear in a paper lives here.** A result in a chat log,
a commit message, a notebook cell, or a message to the owner does not exist. If it
is not in this directory, it is not a finding.

The contract every agent and human must follow is
[`AGENT_INSTRUCTIONS.md`](AGENT_INSTRUCTIONS.md). Read it before running anything.

## The honest state of this directory

As of 2026-08-06, **Mytheca has no evaluation results.** Not a partial set — none.
No benchmark, no baseline, no ablation, no metric, no human study, no annotated data,
no analysis script. This is not an omission in the record; it is the record's first
finding, established by the audit at
[`mytheca-research-audit.md`](mytheca-research-audit.md) line 20 and confirmed at the
dependency level (`pyproject.toml` declares no analysis stack).

The consequence: **there was nothing to back-fill.** Every ledger here was seeded
from analysis, and every claim in `CLAIMS.md` starts `unsupported`. That is the real
experiment backlog, and it is meant to look uncomfortable.

## What each file is for

| File | What it holds | Who writes it |
| --- | --- | --- |
| `AGENT_INSTRUCTIONS.md` | The contract. Experiment directory format, figure rules, validation. | Fixed — amend only by decision |
| `INDEX.md` | Table of every experiment. | **Generated.** `make research-index`. Never hand-edit |
| `CLAIMS.md` | Every claim the paper will make → the experiments that support it. | Human, before evidence exists |
| `DECISIONS.md` | Dated ADRs for research decisions: metrics, baselines, exclusions, cuts. | Human, append-only |
| `OPEN_QUESTIONS.md` | Every follow-up from every `RESULTS.md`, plus known weaknesses. | Appended as experiments complete |
| `RELATED_WORK.md` | Running bibliography with a per-entry delta, plus a scoop watch. | Human, whenever a paper surfaces |
| `experiments/` | The unit of record. One directory per experiment, fixed contract. | `make new-experiment` |
| `templates/` | Copied wholesale to start a new experiment or decision. | Fixed |
| `figures/` | **Publication-ready only** — promoted from experiments, with generators in `sources/`. | Promotion, not authoring |
| `tables/` | Publication-ready `.md`/`.tex` fragments. Generated. | Generated |
| `datasets/` | Provenance, licence, version, access. One datasheet per dataset in `cards/`. | Human |
| `paper/` | Outline, venue targets, submission checklists. | Human |
| `mytheca-research-audit.md` | External audit, 3 Aug 2026. **The provenance source for every seeded ledger here.** | Historical — do not edit |

## Provenance of the seeded ledgers

Nothing in `CLAIMS.md`, `OPEN_QUESTIONS.md`, `RELATED_WORK.md`, `DECISIONS.md` or
`paper/` was invented for this directory. Each entry is a transcription from the
audit, with the source section cited:

| Ledger | Audit source |
| --- | --- |
| `CLAIMS.md` C-001…C-007 | §1.6 Implicit research claims (C1–C7) |
| `OPEN_QUESTIONS.md` G1–G8 | §4 Gap Inventory, §6.4 disqualifiers |
| `RELATED_WORK.md` | §9 Bibliography, §3 Closest Prior Work, §0 scoop watch |
| `DECISIONS.md` | §7 path ranking, §7 metric exclusions, §6.4 |
| `paper/OUTLINE.md` | §7 P1 |
| `paper/venue-targets.md` | §8 Venue Strategy |
| `paper/checklists/` | §6.4, §7 minimum viable contribution, §8 artifact badges |

Where the audit could not verify a citation it marked it ⚠ (§10.2). Those markers
are carried through verbatim. Do not launder an unverified reference into a clean
bibliography entry.

## Adding an experiment

```bash
make new-experiment SLUG=my-experiment
```

Then, in order:

1. Fill `PROTOCOL.md` **before running anything**. Pre-registration is what separates
   an experiment from a fishing expedition, and it writes half the methods section.
2. Run via the recorded entrypoint so the manifest captures commit, config hash,
   seeds, environment and compute at write-time.
3. Fill `RESULTS.md`. Mean ± std across seeds, never a single run.
4. `make validate-research && make research-index`.
5. Commit the experiment folder in the same change as any code it depends on.

A finished experiment folder is **immutable**. Corrections go in a new experiment or
an appended `AMENDMENTS` section — never a silent edit.

## Where large artifacts go

Not here. Checkpoints, large parquet, and raw logs live outside this directory;
the experiment stores a pointer plus a hash in `data/POINTERS.md`. Nothing above
~10 MB enters `docs/research/` — it must stay cloneable in seconds.
