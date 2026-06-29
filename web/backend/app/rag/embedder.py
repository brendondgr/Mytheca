"""Embedding providers (brief §3) behind a seam.

Two implementations satisfy one ``Embedder`` interface:

* ``FastEmbedEmbedder`` — the real path. fastembed (ONNX, no torch) running
  ``BAAI/bge-large-en-v1.5`` for dense vectors and ``Qdrant/bm25`` for the sparse
  (lexical) channel. CPU by default; an execution-provider selection lets it use
  CUDA/ROCm when configured and available. Models lazy-load (and download once)
  on first use, so importing this module is cheap and offline-safe.
* ``HashEmbedder`` — a deterministic, dependency-free fallback used by the test
  suite and whenever no model is configured. Feature-hashing gives it real
  lexical-overlap cosine signal (similar text → similar vectors), so retrieval
  ranking is meaningful in tests without ever downloading a model.

BGE asymmetry: passages embed raw; queries get the ``QUERY_PREFIX`` instruction.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.rag.const import EMBED_DIM, EMBED_MODEL, QUERY_PREFIX, SPARSE_MODEL

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SPARSE_SPACE = 100_003  # prime; hashed-token index space for the fallback sparse encoder


@dataclass(frozen=True)
class SparseVector:
    """A sparse (lexical) vector: parallel ``indices`` / ``values`` arrays.

    Decouples our pipeline from the fastembed/Qdrant sparse types so the store and
    tests speak one shape.
    """

    indices: list[int]
    values: list[float]


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class Embedder(Protocol):
    """The interface the store/indexer/retriever depend on."""

    dim: int

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, query: str) -> list[float]: ...
    def embed_sparse_passages(self, texts: list[str]) -> list[SparseVector]: ...
    def embed_sparse_query(self, query: str) -> SparseVector: ...


class HashEmbedder:
    """Deterministic feature-hashing embedder (offline / test fallback)."""

    def __init__(self, dim: int = EMBED_DIM) -> None:
        self.dim = dim

    def _dense(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0 if (h >> 17) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _sparse(self, text: str) -> SparseVector:
        counts: dict[int, float] = {}
        for tok in _tokenize(text):
            idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % _SPARSE_SPACE
            counts[idx] = counts.get(idx, 0.0) + 1.0
        return SparseVector(indices=list(counts.keys()), values=list(counts.values()))

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._dense(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._dense(query)  # lexical encoder: no instruction prefix

    def embed_sparse_passages(self, texts: list[str]) -> list[SparseVector]:
        return [self._sparse(t) for t in texts]

    def embed_sparse_query(self, query: str) -> SparseVector:
        return self._sparse(query)


class FastEmbedEmbedder:
    """fastembed-backed dense (bge-large) + sparse (bm25) embedder."""

    def __init__(
        self,
        model: str = EMBED_MODEL,
        sparse_model: str = SPARSE_MODEL,
        dim: int = EMBED_DIM,
        device: str = "cpu",
        cache_dir: str | None = None,
    ) -> None:
        self.dim = dim
        self._model_name = model
        self._sparse_name = sparse_model
        self._device = device
        self._cache_dir = cache_dir
        self._dense_m = None  # lazy: constructing downloads the model on first use
        self._sparse_m = None

    def _device_kwargs(self) -> dict:
        # fastembed selects onnxruntime providers; CPU is the default. CUDA needs
        # onnxruntime-gpu present; ROCm needs a ROCm onnxruntime build. Best-effort:
        # an unavailable provider falls back to CPU inside onnxruntime.
        if self._device == "cuda":
            return {"cuda": True}
        if self._device == "rocm":
            return {"providers": ["ROCMExecutionProvider", "CPUExecutionProvider"]}
        return {}

    @property
    def _dense(self):
        if self._dense_m is None:
            from fastembed import TextEmbedding

            self._dense_m = TextEmbedding(
                self._model_name, cache_dir=self._cache_dir, **self._device_kwargs()
            )
        return self._dense_m

    @property
    def _sparse(self):
        if self._sparse_m is None:
            from fastembed import SparseTextEmbedding

            self._sparse_m = SparseTextEmbedding(self._sparse_name, cache_dir=self._cache_dir)
        return self._sparse_m

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._dense.embed(texts)]

    def embed_query(self, query: str) -> list[float]:
        out = next(iter(self._dense.embed([QUERY_PREFIX + query])))
        return list(map(float, out))

    def embed_sparse_passages(self, texts: list[str]) -> list[SparseVector]:
        return [
            SparseVector(indices=list(map(int, s.indices)), values=list(map(float, s.values)))
            for s in self._sparse.embed(texts)
        ]

    def embed_sparse_query(self, query: str) -> SparseVector:
        encoder = getattr(self._sparse, "query_embed", self._sparse.embed)
        s = next(iter(encoder([query])))
        return SparseVector(indices=list(map(int, s.indices)), values=list(map(float, s.values)))


@lru_cache
def get_embedder() -> Embedder:
    """Return the process embedder, chosen by ``EMBED_PROVIDER`` config.

    ``hash`` → the deterministic fallback (the test default; see conftest);
    anything else → fastembed. Cached per process; ``get_embedder.cache_clear()``
    resets it when config changes.
    """
    s = get_settings()
    if s.embed_provider == "hash":
        return HashEmbedder(dim=s.embed_dim)
    return FastEmbedEmbedder(
        model=s.embed_model,
        dim=s.embed_dim,
        device=s.embed_device,
        cache_dir=str(s.embed_cache_dir) if s.embed_cache_dir else None,
    )
