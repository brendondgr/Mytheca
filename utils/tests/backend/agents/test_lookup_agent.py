"""What a free-text turn goes and reads before it writes.

The structured engine's keyword gate cannot have the thought this agent exists for — that a
common noun means something specific *in this world* and needs looking up. What is pinned
here is mostly the other half: that every way this can fail leaves the turn writing, because
a grounding step that can break a scene is worse than no grounding step.
"""

from __future__ import annotations

import httpx
import pytest

from app.agents import lookup_agent
from app.core.errors import APIError
from app.services.assembler import CastMember, TurnContext


class FakeSetting:
    name = "The Drowned Lamp"
    atmosphere = ""
    current_state = ""
    desc = ""


class FakeScenario:
    title = "A Debt Comes Due"


def context(**kwargs) -> TurnContext:
    defaults = dict(
        scenario=FakeScenario(),
        session_id="s1",
        storyline_id="w1",
        directed_at=None,
        cast=[
            CastMember(
                id="c1", name="Mei", role="smuggler", traits="", speech="",
                color="#fff", stats={},
            )
        ],
        setting=FakeSetting(),
        stat_defs=[],
        stat_guidance={},
        recent_beats=[],
        subgraph={},
        world_primer="",
        stable_prefix="",
    )
    return TurnContext(**{**defaults, **kwargs})


def reply(monkeypatch, text: str):
    monkeypatch.setattr(
        lookup_agent.llm, "chat_complete", lambda *a, **k: text
    )


def raises(monkeypatch, error: Exception):
    def boom(*a, **k):
        raise error

    monkeypatch.setattr(lookup_agent.llm, "chat_complete", boom)


@pytest.fixture(autouse=True)
def _llm(monkeypatch):
    monkeypatch.setattr(
        lookup_agent, "resolve_llm", lambda db: ("http://x", "k", "m", None)
    )


# ---- deciding what to read -------------------------------------------------


def test_it_returns_the_terms_it_asked_for(monkeypatch):
    reply(monkeypatch, '{"terms": ["ogre", "the Fifth Day"]}')
    assert lookup_agent.terms_for(None, context(), []) == ["ogre", "the Fifth Day"]


def test_an_empty_list_is_the_common_answer_and_not_a_failure(monkeypatch):
    reply(monkeypatch, '{"terms": []}')
    assert lookup_agent.terms_for(None, context(), []) == []


def test_it_will_not_look_up_the_people_and_places_already_in_the_prompt(monkeypatch):
    """Retrieving a character sheet the prefix already holds makes the model read its own
    context back as though it were new information."""
    reply(monkeypatch, '{"terms": ["Mei", "The Drowned Lamp", "ogre"]}')
    assert lookup_agent.terms_for(None, context(), []) == ["ogre"]


def test_duplicates_collapse(monkeypatch):
    reply(monkeypatch, '{"terms": ["ogre", "Ogre", "ogre"]}')
    assert lookup_agent.terms_for(None, context(), []) == ["ogre"]


def test_the_term_count_is_capped(monkeypatch):
    reply(monkeypatch, '{"terms": ["a", "b", "c", "d", "e"]}')
    assert len(lookup_agent.terms_for(None, context(), [])) == lookup_agent.MAX_TERMS


@pytest.mark.parametrize("text", ["not json at all", '{"terms": "ogre"}', "{}"])
def test_a_malformed_reply_grounds_nothing_rather_than_raising(monkeypatch, text):
    reply(monkeypatch, text)
    assert lookup_agent.terms_for(None, context(), []) == []


def test_an_unconfigured_endpoint_is_a_no_op(monkeypatch):
    monkeypatch.setattr(
        lookup_agent, "resolve_llm",
        lambda db: (_ for _ in ()).throw(APIError(400, "bad_request", "no model")),
    )
    assert lookup_agent.terms_for(None, context(), []) == []


def test_a_server_that_rejects_the_schema_is_retried_unconstrained(monkeypatch):
    """An endpoint with no `response_format` support must not lose the whole feature."""
    calls: list[dict] = []

    def answer(*args, **kwargs):
        calls.append(kwargs)
        if kwargs.get("extra_body") is not None:
            raise APIError(400, "bad_request", "response_format unsupported")
        return '{"terms": ["ogre"]}'

    monkeypatch.setattr(lookup_agent.llm, "chat_complete", answer)
    assert lookup_agent.terms_for(None, context(), []) == ["ogre"]
    assert len(calls) == 2
    assert calls[1].get("extra_body") is None


def test_a_genuine_outage_still_lets_the_turn_write(monkeypatch):
    raises(monkeypatch, APIError(502, "upstream", "down"))
    assert lookup_agent.terms_for(None, context(), []) == []


# ---- reading it ------------------------------------------------------------


class Entry:
    def __init__(self, entry_id, name, body):
        self.entry_id = entry_id
        self.name = name
        self.type = "lore"
        self.body = body
        self.score = 1.0


def retrieval(monkeypatch, hits: dict[str, list[Entry]]):
    import app.rag.retriever as retriever

    monkeypatch.setattr(retriever, "retrieve", lambda db, sid, q: hits.get(q, []))


def test_hits_become_one_bounded_reference_block(monkeypatch):
    retrieval(monkeypatch, {"ogre": [Entry("e1", "Ogres", "Bonded labourers, never beasts.")]})
    block = lookup_agent.lore_block(None, "w1", ["ogre"])
    assert "Ogres" in block and "Bonded labourers" in block
    assert "never quote it" in block


def test_the_same_entry_retrieved_twice_appears_once(monkeypatch):
    entry = Entry("e1", "Ogres", "Bonded labourers.")
    retrieval(monkeypatch, {"ogre": [entry], "ogres": [entry]})
    assert lookup_agent.lore_block(None, "w1", ["ogre", "ogres"]).count("Ogres") == 1


def test_no_terms_and_no_hits_both_yield_nothing(monkeypatch):
    retrieval(monkeypatch, {})
    assert lookup_agent.lore_block(None, "w1", []) == ""
    assert lookup_agent.lore_block(None, "w1", ["ogre"]) == ""
    assert lookup_agent.lore_block(None, None, ["ogre"]) == ""


def test_a_down_vector_store_is_a_no_op(monkeypatch):
    import app.rag.retriever as retriever

    def boom(*a, **k):
        raise httpx.ConnectError("qdrant is not running")

    monkeypatch.setattr(retriever, "retrieve", boom)
    assert lookup_agent.lore_block(None, "w1", ["ogre"]) == ""


def test_the_block_is_capped(monkeypatch):
    retrieval(
        monkeypatch,
        {"ogre": [Entry(f"e{i}", f"Entry {i}", "x" * 900) for i in range(20)]},
    )
    assert len(lookup_agent.lore_block(None, "w1", ["ogre"])) < lookup_agent.BLOCK_CHARS + 200
