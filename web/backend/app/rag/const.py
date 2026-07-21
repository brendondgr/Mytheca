"""RAG constants (the attached brief's appendix, adapted to Mytheca).

Single source for the embedding/retrieval knobs so the embedder, store, indexer,
and retriever cannot drift. See ``docs/rag.md`` and
``Documents/Plans/Mytheca/1.mytheca-rag-implementation-plan.md``.
"""

from __future__ import annotations

import uuid

# --- embedding ---
EMBED_MODEL = "BAAI/bge-large-en-v1.5"  # fastembed (ONNX, CPU-default, no torch)
EMBED_DIM = 1024
EMBED_MAX_TOK = 512  # BGE truncates here; the token guard keeps the tail off the dense vector
NORMALIZE = True  # cosine similarity → normalized embeddings
SPARSE_MODEL = "Qdrant/bm25"  # fastembed sparse (lexical) model for the BM25 channel

# BGE asymmetry: passages embed raw, queries get this instruction prefix. Not
# cosmetic — the model was trained with it and it measurably shifts retrieval.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# --- retrieval ---
RRF_K = 60  # reciprocal-rank-fusion constant (the standard default)
DENSE_K = 50  # dense candidates fused
SPARSE_K = 50  # sparse (BM25) candidates fused
FUSE_TOP_N = 25  # candidates surviving fusion (handed to the reranker once it lands)
CONTEXT_N = 8  # final entries injected into an agent prompt

# Cross-encoder rerank (brief §6) is a deferred stage; pinned here for when it lands.
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

# Deterministic namespace so an entry's Qdrant point id is stable across runs.
# Qdrant point ids must be uint/UUID; Mytheca ids are prefixed strings, so every
# entry maps id → uuid5(NAMESPACE, f"{entity_type}:{entity_id}").
POINT_NAMESPACE = uuid.UUID("5e10a0a6-1d2c-4b3a-9f80-0a60ad000001")
