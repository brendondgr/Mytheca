"""Reflection agent — interior record parse: disposition, retrospective, branch-keyed."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import reflection_agent
from app.schemas.settings import LlmParams
from app.services import llm, llm_backend

_CONN = ("http://localhost:7070/v1", "sk-test", "test-model", LlmParams())


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch(monkeypatch, content: str, capture: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        if capture is not None:
            capture["body"] = request.content.decode()
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_reflect_parses_disposition_and_retrospective(monkeypatch):
    _patch(
        monkeypatch,
        json.dumps({"disposition": "Guarded, but curious.", "retrospective": "He pushed; I held."}),
    )
    rec = reflection_agent.reflect(
        _CONN,
        name="Mei",
        role="Smuggler",
        character_id="c_mei",
        stable_prefix="WORLD: Embergate.",
        transcript="Player: I slide the pouch.\nMei: Coin's easy.",
        seq=3,
    )
    assert rec is not None
    assert rec.character_id == "c_mei"
    assert rec.disposition == "Guarded, but curious."
    assert rec.retrospective == "He pushed; I held."
    assert rec.branch_dispositions == {}
    assert rec.seq == 3


def test_branch_dispositions_only_kept_when_branches_offered(monkeypatch):
    capture: dict = {}
    _patch(
        monkeypatch,
        json.dumps(
            {
                "disposition": "Poised.",
                "branches": {"escalate": "Then I walk.", "de-escalate": "Then we talk."},
            }
        ),
        capture,
    )
    rec = reflection_agent.reflect(
        _CONN,
        name="Mei",
        role="Smuggler",
        character_id="c_mei",
        stable_prefix="",
        transcript="Player: choose.",
        branches=[{"label": "Back off", "outcome": "de-escalate"}, {"label": "Press", "outcome": "escalate"}],
    )
    assert rec is not None
    assert rec.branch_dispositions == {"escalate": "Then I walk.", "de-escalate": "Then we talk."}
    # The offered branch tags reach the prompt so the model keys its stances by them.
    assert "escalate" in capture["body"] and "de-escalate" in capture["body"]


def test_branch_dispositions_dropped_when_no_branches(monkeypatch):
    _patch(monkeypatch, json.dumps({"disposition": "Set.", "branches": {"escalate": "walk"}}))
    rec = reflection_agent.reflect(
        _CONN, name="Mei", role="X", character_id="c_mei", stable_prefix="", transcript="x"
    )
    assert rec is not None and rec.branch_dispositions == {}  # no branches offered → dropped


def test_disposition_prompt_captures_emotional_situational_state(monkeypatch):
    # Disposition must carry the character's emotional/situational state forward (shaken, afraid,
    # …) so an adapted manner persists across turns instead of snapping back to the default.
    capture: dict = {}
    _patch(monkeypatch, json.dumps({"disposition": "Shaken."}), capture)
    reflection_agent.reflect(
        _CONN, name="Mei", role="X", character_id="c_mei", stable_prefix="", transcript="x"
    )
    system = json.loads(capture["body"])["messages"][0]["content"]
    assert "FEELING" in system
    assert "snapping back to their default" in system
    # It must have room to say what the character can no longer keep up — that clause is
    # what actually carries an adapted manner into the next beat.
    assert "2-3 sentences" in system
    assert "is not going to survive into the next beat" in system


def test_malformed_reply_yields_none(monkeypatch):
    _patch(monkeypatch, "not json at all")
    assert (
        reflection_agent.reflect(
            _CONN, name="Mei", role="X", character_id="c_mei", stable_prefix="", transcript="x"
        )
        is None
    )


def test_empty_reflection_yields_none(monkeypatch):
    _patch(monkeypatch, json.dumps({"disposition": "", "retrospective": "", "branches": {}}))
    assert (
        reflection_agent.reflect(
            _CONN, name="Mei", role="X", character_id="c_mei", stable_prefix="", transcript="x"
        )
        is None
    )


# ---- the optional durable memory --------------------------------------------


def test_reflect_parses_the_memory_object(monkeypatch):
    _patch(
        monkeypatch,
        json.dumps({
            "disposition": "Shaken.",
            "memory": {
                "gloss": "she went back for the cargo and left me under the water",
                "quote": "I'm not dying for your conscience.",
                "quoteSpeaker": "Mara",
                "salience": 0.9,
                "valence": "Wound",
                "subjects": ["drowning", " the cargo "],
            },
        }),
    )
    rec = reflection_agent.reflect(
        _CONN, name="Dell", role="Runner", character_id="ch_dell",
        stable_prefix="", transcript="...",
    )
    assert rec is not None and rec.memory is not None
    assert rec.memory["quote"] == "I'm not dying for your conscience."
    assert rec.memory["quoteSpeaker"] == "Mara"
    assert rec.memory["salience"] == 0.9
    assert rec.memory["valence"] == "wound"
    assert rec.memory["subjects"] == ["drowning", "the cargo"]


def test_a_turn_with_nothing_worth_carrying_records_no_memory(monkeypatch):
    _patch(monkeypatch, json.dumps({"disposition": "Bored.", "memory": None}))
    rec = reflection_agent.reflect(
        _CONN, name="Dell", role="Runner", character_id="ch_dell",
        stable_prefix="", transcript="...",
    )
    assert rec is not None and rec.memory is None


def test_a_malformed_memory_costs_the_memory_not_the_reflection(monkeypatch):
    """A model that fumbles one optional field must not lose the disposition too."""
    _patch(
        monkeypatch,
        json.dumps({
            "disposition": "Still angry.",
            "memory": {"gloss": "", "salience": "very high", "subjects": None},
        }),
    )
    rec = reflection_agent.reflect(
        _CONN, name="Dell", role="Runner", character_id="ch_dell",
        stable_prefix="", transcript="...",
    )
    assert rec is not None
    assert rec.memory is None and rec.disposition == "Still angry."


def test_salience_is_clamped_and_a_quoteless_memory_drops_its_speaker():
    parsed = reflection_agent._parse_memory(
        {"gloss": "she left", "salience": 4.2, "quoteSpeaker": "Mara"}
    )
    assert parsed["salience"] == 1.0
    assert parsed["quote"] is None and parsed["quoteSpeaker"] is None
    assert reflection_agent._parse_memory({"gloss": "x", "salience": -3})["salience"] == 0.0
    assert reflection_agent._parse_memory("null") is None
    assert reflection_agent._parse_memory({}) is None


def test_a_memory_alone_is_enough_to_keep_the_record(monkeypatch):
    """The empty-reflection guard must not throw away a turn that produced only a memory."""
    _patch(monkeypatch, json.dumps({"memory": {"gloss": "she left me under", "salience": 0.8}}))
    rec = reflection_agent.reflect(
        _CONN, name="Dell", role="Runner", character_id="ch_dell",
        stable_prefix="", transcript="...",
    )
    assert rec is not None and rec.memory is not None
