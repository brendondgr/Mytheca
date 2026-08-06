# Plans Archive — historical, not routing

These are the phase-by-phase implementation plans for features that have **already
shipped**. They are retained for design provenance: several record *why* a mechanism
took the shape it did, and that reasoning survives nowhere else in prose form.

**Do not read these while routing a task.** They describe intent at the time of
writing, not current behaviour, and several were superseded by later plans in this
same folder. For what the code does today, use `docs/` — which was rebuilt from a
verified code audit on 2026-08-04 — and the commit series in git history, which is
the authoritative record of what actually landed.

Active plans live one level up, in `docs/plans/`.

## Why they were moved

`docs/plans/` had grown to 76 files and 892 KB — 63% of all of `docs/` — while
`CLAUDE.md` instructed every agent to `ls docs/plans/` when looking for a plan. Only
four plans were referenced by any live document. Archiving the remaining 72 cut the
routing surface from 76 entries to 5 without losing anything.

Moved 2026-08-06 as Phase 0 of `docs/plans/research-record-retrofit.md`.

## Still-active plans (kept at `docs/plans/`)

| Plan | Referenced by |
| --- | --- |
| `rag-first-ingestion.md` | `docs/checklist.md` — the one genuinely open capability |
| `mytheca-rag-implementation.md` | `docs/rag.md` |
| `story-graph-neo4j-substrate.md` | `docs/story-graph-neo4j.md` |
| `turn-loop-runtime.md` | `docs/api-contract.md` |
