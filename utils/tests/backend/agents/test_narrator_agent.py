"""Narrator agent — the optional interstitial beat (best-effort)."""

from __future__ import annotations

import httpx
import pytest

from app.agents import narrator_agent
from app.models import Scenario
from app.services import assembler, llm, llm_backend


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch(monkeypatch, content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        return httpx.Response(404)

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _ctx():
    cast = [
        assembler.CastMember(id="kira", name="Kira", role="Guard", traits="", speech="", color="#000", stats={}, recent_lines=[])
    ]
    return assembler.TurnContext(
        scenario=Scenario(storyline_id="e", title="S", cast_ids=["kira"], setting_id=""),
        session_id="ps1",
        storyline_id="e",
        directed_at=None,
        cast=cast,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer=None,
        stable_prefix="",
    )


def test_interstitial_returns_prose(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, "  Kira's jaw tightens; the lamplight gutters.  ")
    text = narrator_agent.interstitial(db_session, _ctx(), [{"role": "player", "text": "hi", "characterId": None}])
    assert text == "Kira's jaw tightens; the lamplight gutters."


def test_interstitial_none_when_unconfigured(db_session):
    assert narrator_agent.interstitial(db_session, _ctx(), []) is None
