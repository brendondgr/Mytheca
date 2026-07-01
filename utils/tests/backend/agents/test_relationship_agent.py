"""Relationship extractor — edge parse, type/roster constraint, dedupe, best-effort."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import relationship_agent
from app.schemas.settings import LlmParams
from app.services import llm, llm_backend

_CONN = ("http://localhost:7070/v1", "sk-test", "test-model", LlmParams())
_CAST = [
    {"id": "mei", "name": "Mei", "bio": "A smuggler who distrusts Beth."},
    {"id": "beth", "name": "Beth", "bio": "Resents Mei over an old debt."},
]


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch(monkeypatch, content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_extract_resolves_numbers_to_ids(monkeypatch):
    _patch(
        monkeypatch,
        json.dumps(
            {"edges": [
                {"source": 1, "type": "fears", "target": 2, "reason": "distrust"},
                {"source": 2, "type": "resents", "target": 1, "reason": "old debt"},
            ]}
        ),
    )
    edges = relationship_agent.extract(_CONN, _CAST)
    assert (edges[0].source_id, edges[0].type, edges[0].target_id) == ("mei", "fears", "beth")
    assert (edges[1].source_id, edges[1].type, edges[1].target_id) == ("beth", "resents", "mei")
    assert edges[0].reason == "distrust"


def test_unknown_type_and_self_loop_dropped(monkeypatch):
    _patch(
        monkeypatch,
        json.dumps(
            {"edges": [
                {"source": 1, "type": "despises", "target": 2},  # not an allowed type
                {"source": 1, "type": "trusts", "target": 1},  # self-loop
                {"source": 1, "type": "trusts", "target": 2},  # kept
            ]}
        ),
    )
    edges = relationship_agent.extract(_CONN, _CAST)
    assert len(edges) == 1 and edges[0].type == "trusts"


def test_duplicate_edges_deduped(monkeypatch):
    _patch(
        monkeypatch,
        json.dumps({"edges": [
            {"source": 1, "type": "trusts", "target": 2},
            {"source": 1, "type": "trusts", "target": 2},
        ]}),
    )
    assert len(relationship_agent.extract(_CONN, _CAST)) == 1


def test_out_of_roster_dropped(monkeypatch):
    _patch(monkeypatch, json.dumps({"edges": [{"source": 9, "type": "trusts", "target": 2}]}))
    assert relationship_agent.extract(_CONN, _CAST) == []


def test_malformed_reply_is_empty(monkeypatch):
    _patch(monkeypatch, "not json at all")
    assert relationship_agent.extract(_CONN, _CAST) == []


def test_single_character_is_empty():
    assert relationship_agent.extract(_CONN, _CAST[:1]) == []
