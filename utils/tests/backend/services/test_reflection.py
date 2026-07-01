"""Read-time reflection service: writes interior per character, concurrent, best-effort."""

from __future__ import annotations

import json

import httpx
import pytest

from app.memory import interior
from app.models import Scenario
from app.services import assembler, llm, llm_backend, reflection


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    def get(self, key: str) -> str | None:
        return self.store.get(key)


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch_reflection(monkeypatch, by_name: dict[str, dict]):
    """Mock the LLM so each character's reflection returns a name-specific JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        user = body["messages"][1]["content"]
        for name, payload in by_name.items():
            if f"You are {name}" in user:
                return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _member(cid: str, name: str) -> assembler.CastMember:
    return assembler.CastMember(
        id=cid, name=name, role="X", traits="", speech="", color="#000", stats={}, recent_lines=[]
    )


def _ctx(cast) -> assembler.TurnContext:
    return assembler.TurnContext(
        scenario=Scenario(storyline_id="e", title="S", cast_ids=[c.id for c in cast], setting_id=""),
        session_id="ps1",
        storyline_id="e",
        directed_at=None,
        cast=cast,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[{"role": "player", "text": "I push the matter.", "characterId": None}],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer=None,
        stable_prefix="WORLD: Embergate.",
    )


def test_run_reflection_writes_interior_for_each_character(client, db_session, monkeypatch):
    _configure_llm(client)
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    _patch_reflection(
        monkeypatch,
        {
            "Mei": {"disposition": "Guarded.", "retrospective": "He pushed."},
            "Kira": {"disposition": "Amused.", "retrospective": "Watched it unfold."},
        },
    )
    cast = [_member("c_mei", "Mei"), _member("c_kira", "Kira")]
    reflection.run_reflection(db_session, _ctx(cast), cast, [], seq=2)

    mei = interior.get_interior("ps1", "c_mei")
    kira = interior.get_interior("ps1", "c_kira")
    assert mei is not None and mei.disposition == "Guarded." and mei.seq == 2
    assert kira is not None and kira.disposition == "Amused."


def test_branch_keyed_reflection_when_fork_offered(client, db_session, monkeypatch):
    _configure_llm(client)
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    _patch_reflection(
        monkeypatch,
        {"Mei": {"disposition": "Poised.", "branches": {"escalate": "Then I walk.", "de-escalate": "Terms."}}},
    )
    cast = [_member("c_mei", "Mei")]
    reflection.run_reflection(
        db_session,
        _ctx(cast),
        cast,
        [],
        branches=[{"label": "Press", "outcome": "escalate"}, {"label": "Back off", "outcome": "de-escalate"}],
    )
    mei = interior.get_interior("ps1", "c_mei")
    assert mei is not None
    assert mei.branch_dispositions == {"escalate": "Then I walk.", "de-escalate": "Terms."}


def test_unconfigured_llm_is_a_clean_noop(db_session, monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    cast = [_member("c_mei", "Mei")]
    reflection.run_reflection(db_session, _ctx(cast), cast, [])  # no LLM configured
    assert interior.get_interior("ps1", "c_mei") is None
    assert fake.store == {}


def test_disabled_reflection_knob_skips(client, db_session, monkeypatch):
    _configure_llm(client)
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    _patch_reflection(monkeypatch, {"Mei": {"disposition": "x"}})
    monkeypatch.setenv("TURN_REFLECTION_ENABLED", "false")
    from app.core import config

    config.get_settings.cache_clear()
    try:
        cast = [_member("c_mei", "Mei")]
        reflection.run_reflection(db_session, _ctx(cast), cast, [])
        assert fake.store == {}  # knob off → no interior written, no LLM call
    finally:
        config.get_settings.cache_clear()


def test_no_targets_is_noop(client, db_session, monkeypatch):
    _configure_llm(client)
    fake = _FakeRedis()
    monkeypatch.setattr(interior, "_redis", lambda: fake)
    reflection.run_reflection(db_session, _ctx([]), [], [])
    assert fake.store == {}
