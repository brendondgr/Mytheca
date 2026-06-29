"""Hybrid retrieval — RRF fusion, ranking, storyline scope, pre-filter (brief §5)."""

from __future__ import annotations

import pytest

from app.models import Character, Setting, Storyline
from app.rag import indexer, store
from app.rag.embedder import HashEmbedder
from app.rag.entries import entry_from_character
from app.rag.retriever import build_filter, retrieve, rrf_fuse
from app.rag.store import StoreHit


def _hit(eid: str) -> StoreHit:
    return StoreHit(entry_id=eid, score=1.0, payload={"entry_id": eid, "name": eid, "type": "character", "body": eid})


def test_rrf_fuse_rewards_agreement_across_channels():
    dense = [_hit("a"), _hit("b"), _hit("c")]
    sparse = [_hit("b"), _hit("a"), _hit("d")]
    fused = rrf_fuse(dense, sparse)
    ids = [i for i, _ in fused]
    assert set(ids[:2]) == {"a", "b"}  # present high in both lists → top two


@pytest.fixture
def mem_client():
    from qdrant_client import QdrantClient

    c = QdrantClient(":memory:")
    store.ensure_collection(c)
    return c


def _seed(client, embedder):
    for ch in (
        Character(id="c1", storyline_id="w1", name="Maerin", role="Warden",
                  appearance="patrols the foggy harbor at dawn"),
        Character(id="c2", storyline_id="w1", name="Doran", role="Captain",
                  appearance="commands a desert caravan inland"),
        Character(id="cx", storyline_id="w2", name="Intruder", role="x",
                  appearance="patrols the foggy harbor"),
    ):
        indexer.index_entry(client, embedder, entry_from_character(ch))


def test_retrieve_ranks_the_lexical_match_first(db_session, mem_client):
    e = HashEmbedder()
    _seed(mem_client, e)
    res = retrieve(db_session, "w1", "who patrols the foggy harbor", client=mem_client, embedder=e)
    assert res and res[0].entry_id == "c1"


def test_retrieve_respects_storyline_scope(db_session, mem_client):
    e = HashEmbedder()
    _seed(mem_client, e)
    res = retrieve(db_session, "w1", "foggy harbor", client=mem_client, embedder=e)
    assert res and all(r.entry_id != "cx" for r in res)  # w2's point is filtered out


def test_retrieve_is_empty_without_a_store(db_session):
    assert retrieve(db_session, "w1", "anything") == []  # QDRANT disabled → []


def test_build_filter_matches_a_named_setting(db_session):
    sl = Storyline(id="w1", title="W", genre="g")
    sl.settings.append(Setting(id="s1", storyline_id="w1", name="The Wharf", type="Harbor", desc="x"))
    db_session.add(sl)
    db_session.commit()
    assert build_filter(db_session, "w1", "what happens at The Wharf tonight")  # condition built
    assert build_filter(db_session, "w1", "a generic unrelated question") is None


def test_prefilter_falls_back_when_it_would_over_narrow(db_session, mem_client):
    # The setting exists in the DB but is not in the store; a location pre-filter
    # would match zero points, so retrieve must fall back to storyline-only.
    sl = Storyline(id="w1", title="W", genre="g")
    sl.settings.append(Setting(id="s1", storyline_id="w1", name="The Wharf", type="Harbor", desc="x"))
    db_session.add(sl)
    db_session.commit()
    e = HashEmbedder()
    indexer.index_entry(mem_client, e, entry_from_character(
        Character(id="c1", storyline_id="w1", name="Maerin", role="Warden", appearance="seen near The Wharf")))
    res = retrieve(db_session, "w1", "Maerin near The Wharf", prefilter=True, client=mem_client, embedder=e)
    assert res  # graceful fallback, not starved to empty
