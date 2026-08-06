# RAG-First Ingestion + On-Demand ReAct Lookups (world build)

> **Status: not yet implemented — follow-up to `docs/plans/archive/build-extract-stage-fix.md`.**
> The "Reading Docs" hang / invalid-JSON bug was fixed first (that plan, merged). This
> plan captures the agreed architecture for the larger redesign so it's ready to pick
> up. Decisions locked with the user are in §2.

## 1. Introduction

Today the **Build the whole world** flow feeds uploaded documents to the agents as
**inline grounding text** (`docs_overview`, capped at 32K chars) plus a per-doc
**extraction** pass that lists each subject; nothing is indexed into RAG during the
build, and nothing persists until *Create World*. That means generation can't *look
things up* — a character tied to a location, or belonging to a species, is drafted
from whatever fragment happened to fit the inline budget, and the model guesses when
uncertain.

This plan restructures the pipeline so **full RAG indexing happens first**: every
uploaded document is ingested into the vector store **before** any character/setting
generation begins, and the generation agents then **query the RAG system on demand**
(ReAct-style) to pull the specific lore they need — a location's details, a species'
traits, an unfamiliar world term — instead of guessing. It builds directly on the
existing hybrid-RAG stack (`docs/rag.md`: fastembed + Qdrant, dense+BM25+RRF,
`app/rag/*`) and the turn-loop's proven retrieval pattern.

## 2. Gaps & Unanswered Questions

Locked with the user:

- **Ingestion namespace — ephemeral build-scoped.** The world has no DB row during a
  build. Index all uploaded docs into a **temporary build-scoped RAG namespace**
  (a synthetic `storyline_id` like `build:<uuid>`), query it during generation, and
  on *Create World* **promote** those points to the real storyline id (re-tag /
  re-index) — discard the namespace if the build is abandoned. Preserves the
  "nothing persists until Create World" contract.
- **On-demand lookups — native tool/function calling.** Expose a `rag_search(query)`
  tool to the character/setting agents via the model's function-calling API; a bounded
  reason→call→observe loop lets an agent ask for what it needs mid-draft. (Fallback to
  a text-based query protocol only if the configured local model's tool-calling proves
  unreliable in practice — verify against the operator's vLLM/llama.cpp first.)
- **Ordering — ingest all, then generate.** RAG ingestion of every uploaded doc must
  **complete** (a new `ingest` stage) before the character/setting drafting phase
  starts.

Open questions to resolve at implementation time (flagged — may need input):

- **Tool-call turn budget + latency.** How many `rag_search` calls per entity before
  we force completion? (Bounded loop, e.g. ≤3, to avoid runaway cost on a local model.)
- **Chunking for build docs.** Reuse `app/rag/serializer.py` entry chunking, or a
  lighter per-paragraph chunk for raw uploads? (Likely reuse the existing pipeline.)
- **Promotion vs re-embed on Create World.** Re-tag existing Qdrant points to the real
  storyline id (cheaper) vs re-embedding from the persisted `ContextDocument` rows
  (simpler, already exists via `bulk_create_context_documents`). Prefer the latter if
  the embed cost is acceptable, to keep one ingestion path.
- **Extraction's role.** With docs in RAG + on-demand lookups, does the per-doc
  extraction pass still gate the roster, or does it become one retrieval among many?
  (Likely keep extraction to enumerate *which* entities to draft, then let each draft
  *enrich* itself via `rag_search`.)

## 3. Hierarchical Step-by-Step Instructions (outline — detail at pickup)

### Phase 1 — Ephemeral build-scoped ingestion
- **Locations:** `web/backend/app/rag/{indexer,store}.py` (a build-scoped namespace +
  bulk-ingest of raw upload text), `web/backend/app/agents/build_agent.py` (a new
  `ingest` stage before `extract`, streaming per-doc `BuildStatusEvent`s), a namespace
  id helper. Ingest all `character_docs`/`setting_docs`/`other_docs` into
  `build:<uuid>` before drafting. Best-effort: Qdrant down → fall back to today's
  inline-grounding path (never block the build).
- **Validation & Commit:** `uv run pytest` for `utils/tests/backend/rag/*` +
  `agents/test_build_agent.py` (ingest stage emits, drafting waits on it, offline/no-
  Qdrant fallback). Commit `[RAG-First Build] (1/n) Complete: Ephemeral build-scoped doc ingestion.`

### Phase 2 — `rag_search` tool + ReAct draft loop
- **Locations:** `web/backend/app/agents/_common.py` (a `rag_search` tool schema +
  bounded tool-call loop helper scoped to a namespace), `character_agent.draft_character`
  / `setting_agent.draft_setting` (accept a `rag_namespace`, expose the tool, run the
  loop). `web/backend/app/services/llm.py` (function-calling passthrough:
  `tools`/`tool_choice` + tool-result messages).
- **Validation & Commit:** agent tests with a mocked tool-calling upstream (the agent
  issues a `rag_search`, receives results, folds them into the draft; the loop is
  bounded; no-tool-support fallback). Commit `[RAG-First Build] (2/n) Complete: On-demand rag_search during character/setting drafts.`

### Phase 3 — Promotion on Create World + cleanup
- **Locations:** the commit path (`web/frontend/features/library/storylineCreator.ts`
  `commitWorld` + `routes/storylines.py`): on *Create World*, promote the build
  namespace to the real storyline (re-embed from the persisted `ContextDocument`
  corpus via the existing `bulk_create_context_documents`, then drop the temp
  namespace); on abandon, a best-effort sweep drops orphaned `build:*` namespaces.
- **Validation & Commit:** promotion test (points land under the real id; temp dropped)
  + an orphan-cleanup test. Commit `[RAG-First Build] (3/n) Complete: Promote build namespace on commit + cleanup.`

### Phase 4 — Docs + validation + merge
- **Locations:** `docs/rag.md` (build-time ingestion + on-demand tool lookups),
  `docs/data-flow.md` (the new `ingest`-then-generate build flow), `docs/api-contract.md`
  (tool-calling passthrough + build namespace), `docs/documentation.md`, this plan →
  done. Full backend `pytest`; frontend if the commit flow changes.

## 4. Deliverables Table (outline)

| Deliverable | Description | Location |
| --- | --- | --- |
| Build-scoped ingestion | Ingest all uploads into `build:<uuid>` before generation | `web/backend/app/rag/*`, `web/backend/app/agents/build_agent.py` |
| `rag_search` tool | Native function-calling tool + bounded ReAct loop in the draft agents | `web/backend/app/agents/_common.py`, `character_agent.py`, `setting_agent.py`, `services/llm.py` |
| Namespace promotion | Promote to the real storyline on Create World; cleanup on abandon | commit path + `routes/storylines.py` |
| Tests | rag ingest, tool-call draft loop, promotion/cleanup | `utils/tests/backend/{rag,agents,api}/*` |
