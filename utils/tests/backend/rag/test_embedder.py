"""Embedder seam — the deterministic fallback + the config factory (brief §3).

The real fastembed path is not exercised in CI (it would download ~1.3 GB); these
tests pin the offline ``HashEmbedder`` behaviour and the provider selection.
"""

from __future__ import annotations

from app.core import config
from app.rag.const import EMBED_DIM
from app.rag.embedder import FastEmbedEmbedder, HashEmbedder, SparseVector, get_embedder


def test_hash_embedder_is_deterministic_and_correct_dim():
    e = HashEmbedder()
    a = e.embed_passages(["the salt below remembers"])[0]
    b = e.embed_passages(["the salt below remembers"])[0]
    assert a == b
    assert len(a) == EMBED_DIM


def test_hash_embedder_is_normalized():
    e = HashEmbedder()
    v = e.embed_passages(["a harbor warden patrols the fog"])[0]
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_hash_embedder_has_lexical_overlap_signal():
    e = HashEmbedder()

    def cos(x, y):
        return sum(a * b for a, b in zip(x, y, strict=True))

    base = e.embed_passages(["harbor warden patrols the fog at dawn"])[0]
    near = e.embed_passages(["harbor warden patrols the fog"])[0]
    far = e.embed_passages(["interstellar trade tariffs and spreadsheets"])[0]
    assert cos(base, near) > cos(base, far)  # similar text → higher cosine


def test_hash_sparse_is_nonempty_and_shaped():
    e = HashEmbedder()
    sp = e.embed_sparse_passages(["warden warden harbor"])[0]
    assert isinstance(sp, SparseVector)
    assert len(sp.indices) == len(sp.values)
    assert sp.indices  # non-empty for non-empty text
    # "warden" appears twice → its hashed term has value 2.0 somewhere
    assert 2.0 in sp.values


def test_factory_returns_hash_when_configured(monkeypatch):
    monkeypatch.setenv("EMBED_PROVIDER", "hash")
    config.get_settings.cache_clear()
    get_embedder.cache_clear()
    assert isinstance(get_embedder(), HashEmbedder)


def test_factory_returns_fastembed_when_configured(monkeypatch):
    # Construction is lazy — no model download — so this is safe offline.
    monkeypatch.setenv("EMBED_PROVIDER", "fastembed")
    config.get_settings.cache_clear()
    get_embedder.cache_clear()
    assert isinstance(get_embedder(), FastEmbedEmbedder)
    config.get_settings.cache_clear()
    get_embedder.cache_clear()
