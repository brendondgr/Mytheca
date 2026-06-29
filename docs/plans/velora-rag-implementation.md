# Velora Hybrid RAG — Implementation Plan

## 1. Introduction

The RAG layer in Velora is currently **theory only**. The `ContextDocument` corpus is persisted (Triage → bulk-create), and every authoring menu can drop reference files — but **nothing embeds or reads that content at runtime**. Character / Setting / Scenario docs are even more ephemeral: they ground a single generation (`docsOverview`) and are then discarded ("Grounds this generation only — not stored yet"). There is no embedding model, no vector store, no retrieval, and saved storyline docs silently vanish from the editor on reload.

This plan makes the RAG real and used end-to-end, following the attached brief (`Documents/Plans/Velora/1.velora-rag-implementation-plan.md`) adapted to Velora's "best-effort / graceful / offline-testable" posture (the same posture as the Neo4j substrate). The approach: a new `web/backend/app/rag/` package that (1) turns any Velora entity or context doc into a front-matter **lore entry** and serializes it with **prefix-fusion**; (2) embeds it with **fastembed** (`BAAI/bge-large-en-v1.5`, ONNX, CPU-default, no torch) behind an `Embedder` seam with a deterministic offline fallback; (3) stores dense + sparse vectors in a new **Qdrant** container (best-effort, lazy, `:memory:` for tests); (4) **ingests on save** for all four authoring menus with **live progress** ("embedding i / N"); (5) **retrieves** via dense + BM25 + **RRF** with metadata pre-filtering and **injects the result into the authoring agents** so the RAG is actually utilized; (6) **persists entity-scoped context files** so they always reappear in the editor; and (7) **removes embeddings on delete**. Cross-encoder rerank (brief §6) and Neo4j `related` KG edges (brief §7) are explicitly deferred.

**Ratified decisions** (see memory `velora-rag-implementation-decisions`): fastembed/bge-large (CPU default, optional GPU); **Qdrant** container; **hybrid baseline** now (defer rerank + KG edges); **all four menus** persist entity-scoped docs.

---

## 2. Gaps & Unanswered Questions

All resolved as assumptions (no blocker); flag if any is wrong:

- **Device selection.** fastembed runs on ONNX/onnxruntime. `EMBED_DEVICE` config defaults to `cpu` (per the user's "default to CPU"); `cuda` enables the CUDA execution provider when `onnxruntime-gpu` is installed and a device is present; ROCm is best-effort and falls back to CPU. No torch dependency.
- **Offline + test path.** The real fastembed embedder downloads a ~1.3 GB ONNX model on first use (cached under `EMBED_CACHE_DIR`/HF cache). Tests must never download: a deterministic **`HashEmbedder`** (+ pure-python sparse) is injected, and Qdrant runs as `QdrantClient(":memory:")`. Same pattern as LLM-mocked agent tests and the disabled-Neo4j test path.
- **Qdrant point ids.** Qdrant requires uint/UUID point ids; Velora ids are prefixed strings. Map every entry id → `uuid5(NAMESPACE, entry_id)` deterministically and keep the original id in the payload.
- **Sparse vectors in local mode.** `:memory:` Qdrant supports named sparse vectors and per-vector search; if a sparse query is unsupported/raises, retrieval **degrades to dense-only** (best-effort). RRF is hand-rolled in our service (two ranked lists → `rrf_fuse`), so we never depend on server-only fusion.
- **One collection, storyline-filtered.** A single `velora_lore` collection; every point carries `storyline_id` in its payload and retrieval filters on it, so a storyline only ever retrieves its own corpus.
- **Entity-scoped docs on create.** A brand-new Character/Setting/Scenario has no id until saved. Flow: save the entity → get id → persist its context docs with `entity_type`/`entity_id` → index. On edit, re-fetch by scope.
- **Corpus = entity entries + doc entries.** Saving an entity indexes a structured **entity entry** (front matter from its fields + body from its descriptive fields). Attached context docs with `include_rag` index as their **own** entries. Both are retrievable.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Front matter schema, prefix-fusion serializer, entry adapters
- **Locations:** new package `web/backend/app/rag/` — `__init__.py`, `schema.py` (`EntryType` enum + `Frontmatter` Pydantic model, brief §1.3), `serializer.py` (`build_embed_text`, `build_bm25_text`, brief §2), `entries.py` (adapters `entry_from_storyline` / `_character` / `_setting` / `_scenario` / `_context_document` → `(Frontmatter, body)`), `tokens.py` (approx token count + 512-token guard that embeds `header+summary` when the body overflows). No infra, pure functions.
- **Rationale:** The serializer and entry adapters are the deterministic core everything else consumes; building them first lets every later phase be tested against stable text.
- **Tests:** `utils/tests/backend/rag/test_serializer.py` (prefix-fusion determinism, metadata ≈10% guard, query-prefix asymmetry constant), `test_entries.py` (each of the 5 adapters maps fields → front matter + body correctly; nullable fields tolerated).
- **Action:** Run `uv run pytest utils/tests/backend/rag`. Once green, commit: `Velora RAG (1/8) Complete: front-matter schema + prefix-fusion serializer + entity entry adapters.`

### Phase 2 — Embedding + sparse providers (fastembed, CPU-default, offline fallback)
- **Locations:** `web/backend/app/rag/embedder.py` — an `Embedder` protocol (`embed_passages`, `embed_query`, `embed_sparse`), `FastEmbedEmbedder` (dense `BAAI/bge-large-en-v1.5` + sparse `Qdrant/bm25`, device selection, BGE query-prefix handling), `HashEmbedder` (deterministic 1024-dim + pure-python sparse for tests/unconfigured), and a cached `get_embedder()` factory keyed on config. Config in `web/backend/app/core/config.py`: `embed_provider` (`fastembed|hash`), `embed_model`, `embed_dim` (1024), `embed_device` (`cpu`), `embed_cache_dir`. Add `fastembed` to `pyproject.toml`. `.env.example` entries.
- **Rationale:** The store/indexer need vectors; the seam keeps the heavy model out of tests and lets the system ship + run on CPU today, upgradeable to GPU/another endpoint via config.
- **Tests:** `utils/tests/backend/rag/test_embedder.py` — `HashEmbedder` determinism + dim + non-zero sparse; factory returns the fallback when `embed_provider=hash`; query vs passage paths differ. (Real fastembed is import-guarded and not exercised in CI.)
- **Action:** Run `uv run pytest utils/tests/backend/rag` (+ `uv sync`). Once green, commit: `Velora RAG (2/8) Complete: fastembed/bge-large embedder + sparse encoder behind a seam with an offline hash fallback.`

### Phase 3 — Qdrant container + best-effort client + collection
- **Locations:** `web/backend/docker-compose.yml` (add `qdrant` service, REST 3351 / gRPC 3352, named volume); `app.py` (`ensure_docker_services` pulls/starts Qdrant alongside Postgres/Redis/Neo4j; preflight best-effort connectivity log); `web/backend/app/core/qdrant.py` (lazy singleton best-effort client mirroring `core/neo4j.py`: `QDRANT_URL` enables; blank disables; `:memory:` for tests; never raises into CRUD); `web/backend/app/rag/store.py` (`ensure_collection` with named dense `1024/COSINE` + sparse vectors; `upsert_entry`; `delete_entry`; `delete_by_filter`; `dense_search`; `sparse_search`; uuid5 id mapping; payload schema: `entry_id,type,name,faction,location,tags,storyline_id,entity_type,entity_id,doc_id,body,bm25_text,content_hash`). Config `qdrant_url`; add `qdrant-client` dep; `.env.example`; `VELORA_SKIP_DOCKER` already skips containers.
- **Rationale:** Storage must exist before indexing; making it best-effort/lazy keeps `pytest` and no-Qdrant dev working exactly like the Neo4j seam.
- **Tests:** `utils/tests/backend/rag/test_store.py` — against `QdrantClient(":memory:")` + `HashEmbedder`: ensure_collection idempotent; upsert→dense_search returns the point; sparse_search returns it; `delete_entry` removes it; `storyline_id` filter isolates corpora; disabled client → graceful no-ops.
- **Action:** Run `uv run pytest utils/tests/backend/rag`. Once green, commit: `Velora RAG (3/8) Complete: Qdrant container + best-effort client + dense/sparse collection store.`

### Phase 4 — Indexer + ingest-on-save with live progress
- **Locations:** `web/backend/app/rag/indexer.py` (`index_entry(entry)`, `index_entity(db, kind, id)`, `index_context_doc(db, doc)`, `remove_entry(entry_id)`, `remove_entity`, `reindex_storyline(db, id)`; content-hash short-circuit so unchanged entries skip re-embed; honors `include_rag`). Hook **best-effort** calls into `web/backend/app/services/crud.py` create/update/delete for storyline/character/setting/scenario and for context docs (single + bulk + update + delete). Progress: `web/backend/app/schemas/rag.py` (`RagProgressEvent{stage,index,total,name}`, `RagDoneEvent{indexed,skipped}`); streaming route `POST /storylines/{storyline_id}/rag/reindex/stream` (NDJSON) in `web/backend/app/routes/rag.py`; the world-build/commit + entity-save flows surface the same "embedding i / N" events.
- **Rationale:** This is the user's core ask — "when saving, emphasize it is converting/embedding it, how many done, then add it." CRUD hooks make every menu ingest automatically; the stream gives the UI its progress.
- **Tests:** `utils/tests/backend/rag/test_indexer.py` (`:memory:` Qdrant + hash embedder): create indexes a point; update re-embeds; identical content is skipped (hash); delete removes; `reindex_storyline` reports counts; `utils/tests/backend/api/test_rag_routes.py` (reindex stream emits progress + done).
- **Action:** Run `uv run pytest utils/tests/backend`. Once green, commit: `Velora RAG (4/8) Complete: embed-on-save with live progress + delete-from-index hooks in CRUD.`

### Phase 5 — Retrieval (dense + BM25 + RRF + pre-filter) and agent utilization
- **Locations:** `web/backend/app/rag/retriever.py` (`retrieve(db, storyline_id, query, k, filters)` → `dense_search` + `sparse_search` → `rrf_fuse` (brief §5.2, `RRF_K=60`) → top-N records; `build_filter` matches query terms against the storyline's known factions/locations/tags, brief §5.3). Utilization: `web/backend/app/agents/_common.py` gains `rag_block(db, storyline_id, query)` (bounded, like `docs_block`); wire it into `storyline_agent` (draft + World Primer), `character_agent.draft_character`, `setting_agent.draft_setting`, `scenario_agent.draft_scenario` so retrieved lore is injected alongside the transient `docs_overview`. Debug/visibility: `POST /storylines/{storyline_id}/rag/query` returns ranked records. Constants in `web/backend/app/rag/const.py` (brief appendix).
- **Rationale:** Retrieval + injection is what makes the corpus *used* rather than merely stored — closing the "we don't actually do anything with it" gap.
- **Tests:** `test_retriever.py` (hash embedder ranking is deterministic; RRF fuses dense+sparse; storyline filter respected; `build_filter` narrows by faction/location); agent tests assert the retrieved block reaches the prompt (offline-mocked LLM), extending existing `utils/tests/backend/agents/*`.
- **Action:** Run `uv run pytest utils/tests/backend`. Once green, commit: `Velora RAG (5/8) Complete: hybrid retrieval (dense+BM25+RRF+pre-filter) wired into the authoring agents.`

### Phase 6 — Entity-scoped context docs + the edit-reload visibility fix
- **Locations (backend):** `web/backend/app/models/context_document.py` (+ nullable `entity_type`, `entity_id`, index on `(entity_type, entity_id)`); `web/backend/app/schemas/context_document.py` (carry the two fields); `web/backend/app/services/crud.py` (scoped list/create; cascade-remove docs + their embeddings when a character/setting/scenario is deleted); routes accept `?entityType=&entityId=` (list) + body scope (create); Alembic migration under `web/backend/alembic/versions/`. **(frontend):** `web/frontend/features/library/useStorylineCreator.ts` — convert `existingDocs → CreatorDoc[]` and **merge into `docs`** on edit-load (fixes the "lost track" bug); `web/frontend/features/library/useLibraryState.ts` `submit()` — after saving a character/setting/scenario, persist its `_docFiles` as entity-scoped docs (+ kick the index) and on `editX` re-fetch them; `web/frontend/components/feature/ContextFilesPanel.tsx` — load persisted docs, update footer copy from "not stored yet" to reflect persistence + embedding; `web/frontend/lib/api.ts` scoped client calls.
- **Rationale:** Satisfies "context files always available … editing of that particular setting at all times" and makes every menu feed the RAG, not just the storyline.
- **Tests:** backend `test_context_documents.py` (entity scope CRUD; entity delete cascades docs + index removal); frontend `useStorylineCreator.test.ts` (edit-load shows saved docs), modal tests (docs persist on save, reappear on edit). Web/UI a11y + responsive pass (320/375/768/1024; keyboard, focus, contrast) on the changed panels.
- **Action:** Run `uv run pytest utils/tests/backend` + `npm test`/`typecheck` + a11y/responsive pass. Once green, commit: `Velora RAG (6/8) Complete: entity-scoped persistent context docs across all four menus + storyline edit-reload fix.`

### Phase 7 — Delete-from-index everywhere + RAG management surface
- **Locations:** consolidate + verify every delete path (`crud.delete_*` for the 4 entities, `delete_context_document`) removes Qdrant points; a per-doc "Remove" control in `ContextFilesPanel`/`TriagePanel` deletes the persisted doc **and** its embedding; a small **RAG status** surface (Options "About" Maintenance section or per-storyline) showing indexed count + a "Re-embed corpus" button driving the Phase-4 reindex stream. `web/backend/app/routes/rag.py` (`GET /storylines/{id}/rag/status`).
- **Rationale:** The user's explicit "delete it from the embedding in the RAG after we delete it" ask, plus an operator view of what is indexed and a manual re-embed.
- **Tests:** backend delete-removes-embedding assertions; status endpoint count; frontend control tests. Brief a11y pass on the new control/status.
- **Action:** Run `uv run pytest utils/tests/backend` + `npm test`. Once green, commit: `Velora RAG (7/8) Complete: delete-from-index across all delete paths + RAG status/re-embed surface.`

### Phase 8 — Docs, full validation, merge
- **Locations:** new `docs/rag.md` (the implemented system); update `docs/documentation.md` (status + stack: vector DB now live), `docs/structure.md` (`app/rag/`, Qdrant), `docs/workflow.md` + `docs/deployment.md` + `.env.example` (Qdrant + embed env/commands), `docs/architecture.md`, `docs/data-flow.md` (ingest/retrieve/delete flows), `docs/api-contract.md` (rag routes + events + scoped context-doc shapes), `docs/checklist.md` (this entry + any deferrals). Then merge `worktree-rag-implementation` → `main`, resolving conflicts (esp. `MultiSelect.tsx` / any concurrent edits).
- **Rationale:** Docs-in-the-same-change is a hard project rule; the merge is the delivery.
- **Action:** Full `uv run pytest` + `npm test` + `typecheck`/`build` + final a11y/responsive pass. Once green, commit: `Velora RAG (8/8) Complete: docs + full validation.` Then merge to `main`.

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| RAG core | Front-matter schema, prefix-fusion serializer, entry adapters, token guard | `web/backend/app/rag/{schema,serializer,entries,tokens,const}.py` |
| Embedder seam | fastembed bge-large (CPU/GPU) + sparse + hash fallback | `web/backend/app/rag/embedder.py` |
| Qdrant store | Container + best-effort client + dense/sparse collection | `web/backend/docker-compose.yml`, `app.py`, `web/backend/app/core/qdrant.py`, `web/backend/app/rag/store.py` |
| Indexer + progress | Embed-on-save, idempotent, delete hooks, NDJSON progress | `web/backend/app/rag/indexer.py`, `web/backend/app/routes/rag.py`, `web/backend/app/schemas/rag.py`, `web/backend/app/services/crud.py` |
| Retriever + utilization | Dense+BM25+RRF+pre-filter; injected into agents | `web/backend/app/rag/retriever.py`, `web/backend/app/agents/_common.py` (+ 4 agents) |
| Entity-scoped docs | Model/migration/routes + frontend persistence + edit-reload fix | `web/backend/app/models/context_document.py`, `…/alembic/versions/*`, `web/frontend/features/library/{useStorylineCreator,useLibraryState}.ts`, `web/frontend/components/feature/ContextFilesPanel.tsx` |
| Delete-from-index + status | All delete paths prune embeddings; status/re-embed surface | `web/backend/app/services/crud.py`, `web/backend/app/routes/rag.py`, Options/Triage UI |
| Tests | RAG unit + route + agent + frontend tests | `utils/tests/backend/rag/*`, `utils/tests/backend/api/test_rag_routes.py`, `utils/tests/frontend/*` |
| Docs | New `docs/rag.md` + updates across the doc set | `docs/*` |

## 5. Validation Gate (every phase)

Backend `uv run pytest` (affected `utils/tests/backend/...`) green; frontend `npm test` + `npm run typecheck` for UI phases; web/UI phases additionally pass an accessibility + responsive pass (keyboard, focus, contrast AA, 320/375/768/1024). RAG infra is **best-effort**: CRUD and `pytest` must pass with Qdrant/embedding model absent. Commit per phase; no push/PR; merge to `main` only at Phase 8.
