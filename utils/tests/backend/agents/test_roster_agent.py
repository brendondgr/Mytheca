"""Roster agent — the cast/settings proposal that seeds world population.

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport`` returning canned completions, as in ``test_triage_agent``.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import roster_agent
from app.core.errors import APIError
from app.services import llm, llm_backend, settings_store
from app.schemas.settings import LlmConfigUpdate


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch_upstream(monkeypatch, handler):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _configure_llm(db):
    settings_store.update_llm(
        db,
        LlmConfigUpdate(base_url="http://localhost:7070/v1", model="test-model", api_key="sk-test"),
    )


@pytest.fixture
def world(db_session):
    """A persisted world the roster is proposed for (grounding context)."""
    from app.schemas.storyline import StorylineCreate
    from app.services import crud

    _configure_llm(db_session)
    return crud.create_storyline(
        db_session,
        StorylineCreate(
            id="embergate",
            title="Embergate",
            genre="Maritime Intrigue",
            premise="A harbor city where the tide charts are worth more than gold.",
        ),
    ).id


def test_proposes_named_characters_and_settings(db_session, world, monkeypatch):
    reply = json.dumps(
        {
            "characters": [
                {"name": "Maerin Voss", "seed": "A smuggler who owes the harbormaster."},
                {"name": "Harbormaster Cael", "seed": "Keeps the tide charts under lock."},
            ],
            "settings": [{"name": "The Salt Wharf", "seed": "Where cargo changes hands."}],
        }
    )
    _patch_upstream(monkeypatch, lambda req: _completion(reply))

    roster = roster_agent.propose_roster(db_session, storyline_id=world)

    assert [c.name for c in roster.characters] == ["Maerin Voss", "Harbormaster Cael"]
    assert roster.characters[0].seed.startswith("A smuggler")
    assert [s.name for s in roster.settings] == ["The Salt Wharf"]


def test_caps_and_dedupes_the_roster(db_session, world, monkeypatch):
    """Over-long, repeated, nameless, and malformed rows cost their row — not the run."""
    reply = json.dumps(
        {
            "characters": [
                {"name": "Maerin", "seed": "one"},
                {"name": "maerin", "seed": "duplicate spelling"},
                {"seed": "nameless"},
                "not an object",
                {"name": "Cael", "seed": "two"},
                {"name": "Bres", "seed": "three"},
            ],
            "settings": [{"name": "Wharf"}, {"name": "Undercroft"}],
        }
    )
    _patch_upstream(monkeypatch, lambda req: _completion(reply))

    roster = roster_agent.propose_roster(
        db_session, storyline_id=world, max_characters=2, max_settings=1
    )

    assert [c.name for c in roster.characters] == ["Maerin", "Cael"]
    assert [s.name for s in roster.settings] == ["Wharf"]
    assert roster.settings[0].seed == ""


def test_zero_bounds_ask_the_model_nothing(db_session, world, monkeypatch):
    called: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        called.append(req)
        return _completion("{}")

    _patch_upstream(monkeypatch, handler)

    roster = roster_agent.propose_roster(
        db_session, storyline_id=world, max_characters=0, max_settings=0
    )

    assert roster.characters == [] and roster.settings == []
    assert called == []


def test_unparseable_reply_is_fatal(db_session, world, monkeypatch):
    """A roster the run cannot get is fatal — unlike the per-entity failures."""
    _patch_upstream(monkeypatch, lambda req: _completion("I'd rather describe the world."))

    with pytest.raises(APIError) as exc:
        roster_agent.propose_roster(db_session, storyline_id=world)

    assert exc.value.status_code == 502


def test_unconfigured_llm_raises_400(db_session, monkeypatch):
    from app.schemas.storyline import StorylineCreate
    from app.services import crud

    sl = crud.create_storyline(db_session, StorylineCreate(title="Blank", genre="Uncharted"))
    _patch_upstream(monkeypatch, lambda req: _completion("{}"))

    with pytest.raises(APIError) as exc:
        roster_agent.propose_roster(db_session, storyline_id=sl.id)

    assert exc.value.status_code == 400
