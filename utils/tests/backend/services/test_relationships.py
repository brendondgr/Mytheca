"""Relationship seeding: writes bio-derived edges, idempotent, best-effort no-ops.

Offline: recording/stub fake Neo4j sessions (no container); the extractor LLM is mocked.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import httpx
import pytest

from app.core import neo4j as neo4j_mod
from app.models import Scenario
from app.services import llm, llm_backend, relationships


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


class _Result:
    def consume(self):
        return None


class _WriteRec:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return _Result()


class _ReadStub:
    """Returns edge rows for the EDGES_AMONG query, nothing for NODES_BY_ID."""

    def __init__(self, edges: list[dict] | None = None) -> None:
        self.edges = edges or []

    def run(self, cypher: str, **params):
        if "-[r]->" in cypher:
            return list(self.edges)
        return []


def _cm(obj):
    @contextmanager
    def _c(**kwargs):
        yield obj

    return _c


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch_extract(monkeypatch, edges: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"edges": edges})}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def _cast(client, storyline_id) -> tuple[str, str]:
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    beth = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Beth"}).json()["id"]
    return mei, beth


def _scenario(storyline_id, cast) -> Scenario:
    return Scenario(id="sc1", storyline_id=storyline_id, title="S", cast_ids=cast, setting_id="")


def test_seeds_edges_from_bios(client, db_session, storyline_id, monkeypatch):
    _configure_llm(client)
    mei, beth = _cast(client, storyline_id)
    rec = _WriteRec()
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "read_session", _cm(_ReadStub()))  # nothing seeded yet
    monkeypatch.setattr(neo4j_mod, "write_session", _cm(rec))
    _patch_extract(monkeypatch, [{"source": 1, "type": "fears", "target": 2, "reason": "distrust"}])

    summaries = relationships.ensure_seeded(db_session, _scenario(storyline_id, [mei, beth]))
    # The return is now one human summary per edge (drives the Inspector's Graph trace).
    assert summaries == ["Mei fears Beth — distrust"]
    edges = [p for c, p in rec.calls if "MERGE (a)-[r:$($type)]->(b)" in c]
    assert edges and edges[0]["type"] == "fears"
    assert edges[0]["src"] == mei and edges[0]["tgt"] == beth
    assert edges[0]["metadata"]["origin"] == "seed"


def test_skips_when_already_seeded(client, db_session, storyline_id, monkeypatch):
    _configure_llm(client)
    mei, beth = _cast(client, storyline_id)
    rec = _WriteRec()
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(
        neo4j_mod,
        "read_session",
        _cm(_ReadStub([{"source": mei, "target": beth, "type": "trusts", "props": {}}])),
    )
    monkeypatch.setattr(neo4j_mod, "write_session", _cm(rec))
    # If it tried to extract, this would raise — proving idempotency short-circuits first.
    monkeypatch.setattr(llm, "get_http_client", lambda: (_ for _ in ()).throw(AssertionError("no LLM")))

    assert relationships.ensure_seeded(db_session, _scenario(storyline_id, [mei, beth])) == []
    assert rec.calls == []


def test_noop_when_graph_disabled(db_session, storyline_id):
    # Neo4j is disabled by the conftest fixture → a clean no-op.
    assert relationships.ensure_seeded(db_session, _scenario(storyline_id, ["a", "b"])) == []


def test_noop_for_single_character(client, db_session, storyline_id, monkeypatch):
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    assert relationships.ensure_seeded(db_session, _scenario(storyline_id, [mei])) == []


def test_noop_when_llm_unconfigured(client, db_session, storyline_id, monkeypatch):
    mei, beth = _cast(client, storyline_id)  # created, but no LLM configured
    monkeypatch.setattr(neo4j_mod, "is_enabled", lambda: True)
    monkeypatch.setattr(neo4j_mod, "read_session", _cm(_ReadStub()))
    assert relationships.ensure_seeded(db_session, _scenario(storyline_id, [mei, beth])) == []
