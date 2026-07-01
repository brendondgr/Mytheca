# Build "Reading Docs" Fix — parallel, fault-tolerant, progress-reporting extraction

## 1. Introduction

The New Storyline **Build the whole world** flow hangs on the "Reading Docs"
(`extract`) stage and then fails with the generic `"The model did not return valid
JSON."`, especially with many (40+) uploaded documents. The extract stage
(`iter_build_world` → `_extract_roster` in `web/backend/app/agents/build_agent.py`)
runs one `extract_agent.extract_entities` LLM call **per document in a sequential
`for` loop**, emits a **single** status event for the whole loop, and lets **any one
doc's** malformed-JSON reply propagate and abort the entire build. So: 40 docs = 40
serial reasoning-model calls with no per-doc output (the "stuck, no status"), and one
bad reply out of 40 kills everything with a message that names no doc.

This plan fixes the extract stage to mirror what the drafting phase already does:
run the per-doc extractions **concurrently** (bounded by the existing
`authoringConcurrency` knob, connection pre-resolved so worker threads never touch
the request `Session`), **isolate failures per doc** (skip a bad doc, don't abort the
build) with a lightweight single retry, and **stream per-doc progress** so the UI
shows movement and names any skipped docs. It also drops the extraction to **LOW**
reasoning effort (a classification/segmentation task, like triage) to cut the hidden-
reasoning token spend that truncates JSON. Backend-only — the per-doc messages ride
the existing `BuildStatusEvent`/`buildStage` wiring, so no frontend change.

The larger **RAG-first ingestion + on-demand ReAct** redesign is a **separate
follow-up plan** (`docs/plans/rag-first-ingestion.md`), per the locked sequencing.

## 2. Gaps & Unanswered Questions

Resolved with the user:

- **Sequencing:** ship this extract-stage fix on its own, merged now; the RAG-first
  redesign is a second plan.
- **RAG-first approach (future):** ephemeral build-scoped RAG namespace.
- **ReAct method (future):** native tool/function calling.

Assumptions (simple gaps — proceeding):

- **LOW reasoning effort for extraction.** Extraction is identify-the-subjects
  segmentation (like triage, which is already LOW). LOW reduces truncation and speeds
  each call; quality impact is negligible for "list the distinct people/places."
- **One retry per doc on a JSON-parse failure**, then skip-with-notice. A single
  retry cheaply salvages transient malformed replies (the "don't silently lose my
  characters" goal) without doubling latency on systemic failures.
- **Deterministic dedup preserved.** Results arrive out of order under concurrency;
  collect into per-doc index slots and dedup in **document order** (first occurrence
  wins) so the roster is stable regardless of completion order.
- **Same concurrency knob.** Extraction uses `authoringConcurrency` (1 → sequential
  for single-slot backends), exactly like the drafting phase.
- **No frontend change.** Per-doc `extract`-stage messages update the existing
  `buildStage` line; the `ProcessProgress` stepper stays on the "Reading docs" step.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Parallel, fault-tolerant, progress-reporting extraction

- **Locations:**
  - `web/backend/app/agents/extract_agent.py` — `extract_entities` gains an optional
    pre-resolved `conn: LlmConn | None = None` (via `_common.resolve_llm_or`, so it
    runs on a worker thread without the `Session`) and uses **`ReasoningEffort.LOW`**
    instead of `DEFAULT_AUTHORING_EFFORT`.
  - `web/backend/app/agents/build_agent.py` — replace the sequential
    `_extract_roster` with a **concurrent** extraction driven inside `iter_build_world`
    (or a generator helper): pre-resolve the `conn` once, run per-doc thunks through
    `concurrency.imap_unordered(max_workers=authoring_concurrency)`, collect results
    into `[None]*N` index slots, **emit a `BuildStatusEvent(stage="extract", …)` per
    doc as it completes** (`Reading {name} ({k}/{N})…`), **skip** a doc whose
    extraction returned `None` (failure-isolated by `imap_unordered`) after a small
    **single-retry** wrapper (`_extract_one`), and finally **dedup across slots in doc
    order**. Emit a closing `extract` status naming how many docs were read / skipped
    so a skipped doc is explained rather than fatal.
  - `web/backend/app/schemas/build.py` — no schema change required (reuse
    `BuildStatusEvent`); if a distinct "skipped docs" signal is wanted it can ride the
    status `message` (no new event type).
- **Rationale:** the drafting phase already proves this exact pattern
  (`imap_unordered` + pre-resolved conn + per-index events); applying it to extraction
  removes the serial stall, the all-or-nothing abort, and the silent stage in one
  focused change, without touching the streaming contract or the frontend.
- **Action:** Run this phase's validation — `uv run pytest` for
  `utils/tests/backend/agents/test_extract_agent.py` (conn param, LOW effort, retry
  then skip on malformed JSON) and `utils/tests/backend/agents/test_build_agent.py`
  (parallel extraction: out-of-order tolerated, a malformed doc is **skipped not
  fatal**, per-doc progress emitted, dedup order preserved, existing multi-entity /
  single-subject tests still pass); `ruff` + `mypy` on the touched files. Once green,
  commit locally: `[Build Extract Fix] (1/2) Complete: Parallel, fault-tolerant, progress-reporting doc extraction.`

### Phase 2 — Docs, validation, merge

- **Locations:**
  - `docs/data-flow.md` — the Build flow's `extract` stage is now **parallel +
    per-doc fault-tolerant + per-doc progress** (a bad doc is skipped, not fatal).
  - `docs/documentation.md` — status line.
  - `docs/checklist.md` — a "done" entry (root-cause + fix), and a pointer to the
    follow-up RAG-first plan.
  - `docs/plans/rag-first-ingestion.md` — **new** follow-up plan capturing the locked
    decisions (ephemeral build-scoped RAG namespace; native tool/function-calling
    ReAct lookups during generation; ingest-all-docs-then-generate ordering) so the
    architecture work is ready to pick up next. Not implemented in this change.
- **Rationale:** docs move with behavior per the project rules; the follow-up plan
  records the design decisions before they're lost.
- **Action:** Run the full gate — backend `uv run pytest` (whole suite green),
  `ruff`/`mypy` on touched files. Frontend untouched → note `npm test` N/A (confirmed
  no FE change: per-doc messages ride existing `buildStage`). Once green, commit:
  `[Build Extract Fix] (2/2) Complete: Docs, follow-up RAG-first plan, validation, merge.`
  Then merge the worktree into `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Concurrent extraction | Per-doc extraction via `imap_unordered`, bounded by `authoringConcurrency`, pre-resolved conn | `web/backend/app/agents/build_agent.py` |
| Fault isolation + retry | One retry then skip-with-notice per doc; build never aborts on a single bad doc | `web/backend/app/agents/build_agent.py` |
| Per-doc progress | `BuildStatusEvent(stage="extract")` per doc ("Reading {name} k/N…") + read/skipped summary | `web/backend/app/agents/build_agent.py` |
| Extraction agent tuning | `conn=` passthrough + `ReasoningEffort.LOW` | `web/backend/app/agents/extract_agent.py` |
| Tests | Agent + build-orchestration tests for parallel/skip/progress/dedup | `utils/tests/backend/agents/test_extract_agent.py`, `utils/tests/backend/agents/test_build_agent.py` |
| Follow-up plan | RAG-first ingestion + native-tool-calling ReAct redesign (not implemented here) | `docs/plans/rag-first-ingestion.md` |
