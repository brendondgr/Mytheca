# Mytheca Hybrid RAG

Mytheca's retrieval layer turns the persisted reference corpus + the world's own
entities into a searchable index, and **uses** it: the authoring agents retrieve
relevant established lore and ground their drafts in it. It is **best-effort**
throughout — exactly like the Neo4j substrate — so CRUD and the test suite run
with no vector store and no embedding model.

Source brief: `Documents/Plans/Mytheca/1.mytheca-rag-implementation-plan.md`.
Implementation plan: `docs/plans/mytheca-rag-implementation.md`.

## Pipeline

```
entity / context-doc → LoreEntry (front matter + body)
   → prefix-fusion serialize (dense embed text + BM25 vocabulary text)
   → embed: fastembed bge-large (dense) + Qdrant/bm25 (sparse)
   → Qdrant point (named dense+sparse vectors, storyline-scoped payload, content hash)
   → retrieve: dense + sparse search → RRF fusion → top-N
   → injected into the character/setting/scenario draft prompts
```

- **One entry = one chunk** (brief §0.1). Each storyline, character, setting,
  scenario, and persisted context document becomes exactly one `LoreEntry`.
- **Prefix-fusion** (brief §2): a compact metadata header + summary is prepended to
  the body before embedding (metadata is *embedded*, not just filtered). A 512-token
  guard keeps the header+summary on the dense vector even for long bodies.
- **BGE asymmetry**: passages embed raw; queries get the instruction prefix
  `"Represent this sentence for searching relevant passages: "`.
- **RRF** (brief §5.2, `k=60`) fuses the two ranked lists on rank, never on the
  incompatible cosine/BM25 score scales. Hand-rolled in our service so it works in
  both Qdrant server and local (`:memory:`) mode.

## Components (`web/backend/app/rag/`)

| File | Role |
| --- | --- |
| `schema.py` | `EntryType`, `Frontmatter` (Pydantic), `LoreEntry` |
| `serializer.py` | `build_embed_text` (dense) / `build_bm25_text` (sparse) |
| `tokens.py` | 512-token budget guard |
| `entries.py` | entity → `LoreEntry` adapters (storyline/character/setting/scenario/context-doc) |
| `embedder.py` | `Embedder` seam: `FastEmbedEmbedder` (real) + `HashEmbedder` (offline fallback) |
| `store.py` | Qdrant collection + upsert/search/delete + uuid5 point ids |
| `indexer.py` | embed-on-save / remove-on-delete hooks + `iter_reindex_storyline` progress |
| `retriever.py` | `retrieve` (dense+sparse→RRF) + `build_filter` metadata pre-filter |
| `const.py` | model + retrieval constants (brief appendix) |

`web/backend/app/core/qdrant.py` is the lazy, best-effort client (mirrors
`core/neo4j.py`): `None` when `QDRANT_URL` is unset/unreachable.

## Embedding (fastembed, CPU-default, no torch)

`BAAI/bge-large-en-v1.5` (1024-dim) runs through **fastembed** (ONNX /
onnxruntime — no torch). CPU by default; `EMBED_DEVICE=cuda`/`rocm` selects an
accelerator execution provider when present (best-effort CPU fallback). The model
downloads once on first use and caches under `EMBED_CACHE_DIR`.

`EMBED_PROVIDER=hash` selects a deterministic feature-hashing fallback
(`HashEmbedder`) — no model download, with real lexical-overlap cosine signal. The
test suite forces it (`utils/tests/backend/conftest.py`), so CI never downloads a
model and retrieval ranking is still meaningful.

## Vector store (Qdrant)

A Qdrant container (`web/backend/docker-compose.yml`, REST `3351` / gRPC `3352`)
started by `app.py` like Postgres/Redis/Neo4j. One `mytheca_lore` collection holds
every entry as a point with **named dense + sparse vectors** and a payload
(`type`, `name`, `tags`, `storyline_id`, `entity_type`, `entity_id`, `body`,
`content_hash`, …). Point ids are `uuid5(namespace, "{entity_type}:{entity_id}")` —
stable across runs (idempotent upsert) and namespaced so types can't collide. Every
search filters on `storyline_id`, so a world only ever retrieves its own corpus.

Tests use `QdrantClient(":memory:")` (in-process, no server) — verified to support
named + sparse vectors, `query_points`, payload filters, and delete.

## Ingest-on-save, delete, and progress

CRUD writes call best-effort `indexer.sync_*` hooks (mirroring `graph_writer`):
saving a storyline/character/setting/scenario/context-doc embeds it; deleting prunes
its point (a storyline delete drops the whole world's corpus). A **content hash**
makes re-indexing idempotent — an unchanged entry is skipped, not re-embedded.

`POST /storylines/{id}/rag/reindex/stream` re-embeds a world's corpus, streaming one
`embedding` event per entry then a `done` summary (NDJSON). The storyline editor's
footer surfaces this as **"✦ N embedded · Re-embed"** with live "Embedding i / N"
progress. `GET /storylines/{id}/rag/status` reports reachability + the indexed count.
`POST /storylines/{id}/rag/query` inspects retrieval for a query (debug).

**Parallel batch indexing.** The reindex (`iter_reindex_storyline`) and the bulk
corpus commit (`indexer.sync_context_documents`, from `bulk_create_context_documents`)
embed entries **concurrently** via `indexer.index_many` — a bounded thread pool
(`services.concurrency.imap_unordered`, capped by the operator's `authoringConcurrency`
setting). Embedding is the costly step and runs in parallel (fastembed/ONNX releases
the GIL; the `HashEmbedder` test path is pure); the quick Qdrant reads/writes are
serialized under a shared lock, so the store (incl. the in-memory test client) never
sees concurrent access. Workers touch only the client + embedder + already-materialized
`LoreEntry` objects — never a SQLAlchemy `Session`. Reindex `embedding` events are
emitted as each entry *completes* (so `index` is a 1..N completion counter). The
per-single-save `sync_*` hooks stay inline (one embed each).

## Utilization (the agents)

`agents/_common.rag_block(db, storyline_id, query)` retrieves the top entries for a
seed and folds them into a bounded grounding block. It is wired into the
**character / setting / scenario** draft agents and the **storyline-edit** agent
(`agents/storyline_edit/core.py`, the conversational agent that edits an existing
storyline) — the world-genesis storyline agent has no corpus to retrieve yet, so it
alone is unwired. Retrieved lore sits alongside the transient `docs_block`
(dropped-file text), so a draft is grounded in both the established world and any
just-dropped references.

### Retrieval vs. `@` tagging (two different channels)

During play there are two ways a context document can reach the prompt, and they are
deliberately independent:

- **Gated retrieval** — `retrieval_gate.gate` decides per turn whether to query at all
  (it is conservative and skips most turns), and `rag_block` renders each hit as one
  bullet capped at `RAG_SNIPPET_CHARS = 600`. The engine chooses; the player does not.
- **`@` tagging** — the player names the file in the composer. `assembler._tagged_notes`
  loads it whole (bounded at 5 docs / 6 000 characters each / 12 000 total), bypassing
  both the gate and the 600-character cap, and lands it in `TurnContext.tagged_notes` —
  a slot separate from `retrieved_lore`, framed as reference rather than direction.

Tagging does **not** depend on `include_rag`: a document excluded from the retrieval corpus
is still taggable. `@` exists precisely because retrieval routinely failed to surface the
passage the player wanted. See `docs/api-contract.md` and `docs/data-flow.md` for the
guarantees that keep tagged text from steering the scene.

## Entity-scoped context documents

`ContextDocument` carries an optional `entity_type` + `entity_id`. A document is
either **storyline-level** (the Triage default) or scoped to one
character/setting/scenario — in which case it reappears in that editor on re-edit
and is removed (with its embedding) when the entity is deleted. The four editors
persist their dropped files on save (`features/library/entityDocs.ts` reconciles by
name) and the storyline editor re-hydrates its panel on edit (the prior "lost track"
bug). All persisted, RAG-flagged docs feed retrieval.

## Configuration

| Var | Default | Purpose |
| --- | --- | --- |
| `EMBED_PROVIDER` | `fastembed` | `fastembed` (real) or `hash` (offline fallback) |
| `EMBED_MODEL` | `BAAI/bge-large-en-v1.5` | dense embedding model |
| `EMBED_DIM` | `1024` | vector size |
| `EMBED_DEVICE` | `cpu` | `cpu` / `cuda` / `rocm` |
| `EMBED_CACHE_DIR` | (fastembed default) | ONNX model cache |
| `QDRANT_URL` | `http://localhost:3351` | blank disables the vector store |
| `QDRANT_COLLECTION` | `mytheca_lore` | collection name |

## Deferred (brief §6, §7)

- **Cross-encoder rerank** (`bge-reranker-v2-m3`) — the single highest-impact
  upgrade after hybrid search; constants are pinned (`const.RERANK_MODEL`).
- **Neo4j `related` KG edges** + 1-hop expansion — the `related` front-matter field
  exists on `Frontmatter` but is not yet written into the Story Graph.
- **RAGAS eval harness** — once real query traffic exists.

## Played memories are part of the corpus

Everything else indexed here was authored **before** play — storylines, characters, settings,
scenarios, context documents. `rag/entries.entry_from_memory` adds the first thing that
*happened*: one entry per `character_memories` row, indexed by `indexer.sync_memory` from the
post-turn interlude after the Postgres commit.

Scoped per **character**, not per moment. Dell's version and Mara's version of one turn are
two entries because they are two memories, and recall only ever wants the asking character's
own. The entry's front-matter `id` **is** the memory id, which is how
`services/memory_recall.semantic_boosts` intersects search hits with the turn's candidates —
the corpus also holds settings and documents, and only a candidate memory may be lifted.

**The search is gated to the case it exists for.** It fires only when the lexical cue scan
matched *nothing*, because the question this channel answers is "did the exact tags miss?"
and the tags having matched is a direct answer to it. So on most turns it does not run at
all, and when it does it costs one embedding and one search for the whole turn. Results are
fused by **rank** (RRF), never by adding scores — a recall score and a cosine similarity are
on incomparable scales, the same reason `retriever.rrf_fuse` exists.

Best-effort throughout: Qdrant off, unreachable, or empty leaves recall behaving exactly as
it did before this channel existed.
