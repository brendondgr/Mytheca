# Authoring Parallelism — parallel world-build drafting + parallel RAG indexing (configurable)

## 1. Introduction

The "Build the whole world" flow (`agents/build_agent.iter_build_world`) drafts each character and setting **one at a time** — N sequential LLM round-trips — and the RAG indexer embeds entities **one at a time** too. On a backend that can serve concurrent requests (vLLM), this leaves a lot of wall-clock on the table. This plan adds **configurable parallelism**: individual characters/settings are drafted concurrently (bounded by a user-set limit), and the RAG batch-embed runs concurrently as well. **Image generation stays strictly sequential** (single-GPU ComfyUI), which is already the case on the frontend and is left untouched.

The concurrency limit is a **user setting** in the Options menu (so operators on a single-slot llama.cpp set it to 1, and vLLM operators raise it). One knob (`authoringConcurrency`) governs both the parallel entity drafting and the parallel RAG embedding.

The design is enabled by three facts confirmed during exploration: (a) the frontend already places build `character`/`setting` events by their `index` field (`storylineCreator.upsertAt`), so the backend may emit them **out of order** as parallel drafts complete; (b) in the build, `draft_character`/`draft_setting` run with `storylineId = None`, so `_common.world_context`/`rag_block` are no-ops and the only DB touch is `resolve_llm` — **pre-resolving the LLM connection once** makes the drafting workers pure (no thread-unsafe `Session` access); (c) fastembed/ONNX embedding releases the GIL and is thread-safe, so concurrent embedding is a real win — we serialize only the quick Qdrant upsert (a lock) to stay safe with the in-memory test store.

## 2. Gaps & Unanswered Questions

- **Where the setting lives (resolved, assumption):** add `authoringConcurrency` to the **LLM** settings namespace (it fundamentally describes how many concurrent requests the configured LLM backend can serve), surfaced in the Options **Language Models** tab with a hint (vLLM → raise it; single-slot llama.cpp → 1). Default **3**, seeded from a new env `Settings.build_max_concurrency`.
- **One knob or two (resolved):** a single `authoringConcurrency` bounds **both** parallel drafting and parallel RAG embedding — simplest for the user; matches "the parallelism needs to be configurable" (singular).
- **Thread-safety of drafting (resolved):** pre-resolve `resolve_llm(db)` once in the main thread; pass the connection into the agent calls so workers never touch the request `Session` (`world_context`/`rag_block` are no-ops for `storyline_id=None`).
- **Thread-safety of embedding (resolved):** concurrent embedding (ONNX releases the GIL / HashEmbedder is pure), **serialized Qdrant writes** via a lock (safe with the in-memory test client and prod alike). Workers operate on pre-materialized `LoreEntry` objects — no `Session` in threads.
- **Per-entity draft failure under parallelism (decision):** treat as **best-effort skip** (log, drop that one entity) rather than aborting the whole build — consistent with the build's existing best-effort nature (voice samples, images). The storyline/primer/blueprint drafts run *before* the parallel loop and still surface a `BuildErrorEvent`, so a fully-misconfigured LLM still fails loudly up front.
- **Frontend commit stays sequential (decision):** entity *creation* in `commitWorld` stays a sequential `await` loop (avoids `_next_position` races / concurrent graph+RAG writes per request). Parallel RAG lands in the **batch** paths (`iter_reindex_storyline`, `bulk_create_context_documents`) which operate on pre-materialized entries and are safe. The per-single-create inline embed stays inline (one embed, not a batch bottleneck).
- **No complex gaps requiring human intervention.**

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — The configurable concurrency knob (full-stack) + an as-completed helper

- **Locations:**
  - `web/backend/app/core/config.py` — add `build_max_concurrency: int = 3` (env `BUILD_MAX_CONCURRENCY`); the default the DB setting seeds from.
  - `web/backend/app/schemas/settings.py` — add `authoring_concurrency: int` to `LlmConfigRead` and `LlmConfigUpdate` (optional on update).
  - `web/backend/app/services/settings_store.py` — `_llm_defaults()` seeds `authoring_concurrency` from `get_settings().build_max_concurrency`; `update_llm` persists it (clamped to ≥1).
  - `web/backend/app/services/concurrency.py` — add `imap_unordered(thunks, *, max_workers) -> Iterator[tuple[int, T | None]]`: yields `(original_index, result)` as each thunk completes; `max_workers <= 1` or a single item runs **inline in order**; a raising thunk yields `(i, None)` (failure-isolated), mirroring `run_all`.
  - `web/frontend/lib/api.ts` — add `authoringConcurrency: number` to `LlmConfig` and `LlmConfigUpdate`.
  - `web/frontend/features/options/tabs/LanguageModelsTab.tsx` — render a number field ("Max parallel authoring requests", min 1, max ~16) with a one-line hint; save via the existing `saveLlm`.
- **Rationale:** Everything downstream reads this one setting; land the knob (and the streaming-friendly concurrency primitive) first, verifiable on its own.
- **Action:** `uv run pytest` for `utils/tests/backend/api/test_options.py` + `utils/tests/backend/services/test_concurrency.py`; frontend `npm test` for the options + api client, `npm run typecheck`. Commit: `[Authoring Parallelism] (1/4) Complete: configurable authoringConcurrency setting + imap_unordered helper.`

### Phase 2 — Parallel character/setting drafting in the build

- **Locations:**
  - `web/backend/app/agents/character_agent.py` — add an optional pre-resolved `llm: tuple[str, str, str, LlmParams] | None = None` to `draft_character` and `propose_voice_samples` (when provided, skip `resolve_llm(db)`; else resolve as today — backward compatible).
  - `web/backend/app/agents/setting_agent.py` — same optional `llm=` for `draft_setting`.
  - `web/backend/app/agents/build_agent.py` — in `iter_build_world`: read `n = settings_store.get_llm(db).authoring_concurrency`; pre-resolve `conn = resolve_llm(db)` once; build per-entity thunks (each drafts one character incl. voice samples, or one setting) closing over `conn`; drive them with `concurrency.imap_unordered(thunks, max_workers=n)`; **emit `BuildCharacterEvent`/`BuildSettingEvent` out of order by `index` as each completes**; collect final `characters`/`settings` into index-ordered lists (drop `None` / failed). Keep the `BuildStatusEvent("characters"/"settings")` stage messages.
- **Rationale:** The main wall-clock win. Depends only on Phase 1's helper + setting; the frontend already tolerates out-of-order events (`upsertAt`).
- **Action:** `uv run pytest` for `utils/tests/backend/agents/test_build_agent.py` (add: parallel path assembles the full proposal with a shuffled-completion mock; `authoringConcurrency=1` stays sequential; a failing per-entity draft is skipped, not fatal; images untouched). Commit: `[Authoring Parallelism] (2/4) Complete: parallel character/setting drafting in the world build (images stay sequential).`

### Phase 3 — Parallel RAG indexing

- **Locations:**
  - `web/backend/app/rag/indexer.py` — add `index_many(client, embedder, entries, *, max_workers) -> tuple[int, int]` (indexed, skipped): a bounded thread pool where each worker builds texts + **embeds concurrently**, and the content-hash check + `store.upsert_entry` run under a shared `threading.Lock` (serialized Qdrant writes). Rewrite `iter_reindex_storyline` to use `imap_unordered` over per-entry index thunks (concurrent embed, locked upsert), yielding `("embedding", …)` progress as each **completes** and a terminal `("done", …)`; bound by the caller-supplied concurrency.
  - `web/backend/app/routes/rag.py` — the reindex route reads `settings_store.get_llm(db).authoring_concurrency` and passes it into `iter_reindex_storyline`.
  - `web/backend/app/services/crud.py` — `bulk_create_context_documents` indexes its created docs via the parallel `index_many` (bounded by the setting) instead of the per-doc `sync_context_document` loop.
- **Rationale:** Makes "adding to RAG" parallel for the batch operations, bounded by the same configurable knob; safe (workers touch only client+embedder+entry, never the `Session`; Qdrant writes serialized).
- **Action:** `uv run pytest` for `utils/tests/backend/rag/test_indexer.py`, `utils/tests/backend/api/test_rag_routes.py`, `utils/tests/backend/api/test_context_documents.py` (add: reindex embeds every entry with concurrency>1 against in-memory Qdrant; progress totals correct; bulk context docs all indexed). Commit: `[Authoring Parallelism] (3/4) Complete: parallel (concurrent-embed, serialized-write) RAG indexing bounded by authoringConcurrency.`

### Phase 4 — Docs + full validation + merge

- **Locations:** `docs/api-contract.md` (LLM settings `authoringConcurrency` + reindex-is-parallel note), `docs/data-flow.md` (parallel build + parallel RAG), `docs/workflow.md` + `.env.example` (`BUILD_MAX_CONCURRENCY`), `docs/documentation.md` (status), `docs/checklist.md` (this entry + any deferrals). Merge `feat/authoring-parallelism` → `main`.
- **Action:** Full backend `uv run pytest` + frontend `npm test`/`typecheck`/`lint`/`next build` green. Commit: `[Authoring Parallelism] (4/4) Complete: docs + validation; merge configurable authoring parallelism to main.` Merge to `main` (no push).

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Env default | `build_max_concurrency` | `web/backend/app/core/config.py` |
| Setting field | `authoringConcurrency` on LLM config (schema + store) | `web/backend/app/schemas/settings.py`, `web/backend/app/services/settings_store.py` |
| As-completed helper | `imap_unordered` (streaming, bounded, failure-isolated) | `web/backend/app/services/concurrency.py` |
| Options UI | Number field in the Language Models tab | `web/frontend/lib/api.ts`, `web/frontend/features/options/tabs/LanguageModelsTab.tsx` |
| Parallel drafting | Pre-resolved LLM + `imap_unordered` in the build | `web/backend/app/agents/{build_agent,character_agent,setting_agent}.py` |
| Parallel indexing | `index_many` (concurrent embed / serialized write) + parallel reindex + bulk-context | `web/backend/app/rag/indexer.py`, `web/backend/app/routes/rag.py`, `web/backend/app/services/crud.py` |
| Tests | settings, imap_unordered, parallel build, parallel reindex/bulk | `utils/tests/backend/{api,services,agents,rag}/...`, `web/frontend/**/*.test.*` |
| Docs | contract, data-flow, workflow, env, status, checklist | `docs/*.md`, `.env.example` |
