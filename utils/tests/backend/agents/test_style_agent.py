"""The style-drafting agent: two outcomes, and every way the model can get it wrong.

Two things matter more than the happy path. First, this runs *during world creation*, so
every failure has to resolve to "no style" rather than to an error — an optional feature must
never cost the author their world. Second, the one thing a writing agent will reach for
unprompted is a length count, which is exactly what `EXP-2026-08-007` measured moving prose
the wrong way and why the `beatLength` tiers were removed.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import style_agent
from app.content import style_presets


@pytest.fixture
def configured(client):
    """Point the settings store at an endpoint so ``resolve_llm`` succeeds."""
    res = client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://llm.test/v1", "model": "m", "apiKey": "k"},
    )
    assert res.status_code == 200, res.text


def _reply(monkeypatch, content: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST":  # engine/version probes
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    transport = httpx.MockTransport(handler)
    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)


def _fail(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="down")

    transport = httpx.MockTransport(handler)
    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)


# ---- the written-guide path -------------------------------------------------------


def test_a_written_guide_comes_back_as_blocks(configured, db_session, monkeypatch):
    _reply(
        monkeypatch,
        json.dumps({"attention": "Dwell on hands.", "voice": "Plain.", "signature": "Low."}),
    )
    blocks = style_agent.draft_style_guide(db_session, "A rain-soaked harbour city.")
    assert blocks == {"attention": "Dwell on hands.", "voice": "Plain.", "signature": "Low."}


def test_unknown_keys_are_dropped(configured, db_session, monkeypatch):
    _reply(monkeypatch, json.dumps({"voice": "Plain.", "cadence": "invented", "plot": "no"}))
    assert style_agent.draft_style_guide(db_session, "A city.") == {"voice": "Plain."}


def test_text_is_canonicalised(configured, db_session, monkeypatch):
    _reply(monkeypatch, json.dumps({"voice": "  Plain.  \r\n\r\n\r\nShort.  "}))
    assert style_agent.draft_style_guide(db_session, "A city.") == {"voice": "Plain.\n\nShort."}


# ---- the preset path --------------------------------------------------------------


def test_a_chosen_preset_resolves_to_its_text_not_its_id(configured, db_session, monkeypatch):
    """Copied, never referenced — editing the preset later must not rewrite this world."""
    _reply(monkeypatch, json.dumps({"preset": "romance"}))
    blocks = style_agent.draft_style_guide(db_session, "Four tenants in a terrace house.")
    assert blocks["signature"].startswith("Close and unsaid")
    assert blocks == {k: v for k, v in style_presets.ROMANCE.blocks.items()}


def test_an_unknown_preset_id_falls_back_to_the_written_blocks(
    configured, db_session, monkeypatch
):
    _reply(monkeypatch, json.dumps({"preset": "noir-hallucinated", "voice": "Plain."}))
    assert style_agent.draft_style_guide(db_session, "A city.") == {"voice": "Plain."}


def test_an_unknown_preset_id_with_nothing_else_yields_no_style(
    configured, db_session, monkeypatch
):
    _reply(monkeypatch, json.dumps({"preset": "noir-hallucinated"}))
    assert style_agent.draft_style_guide(db_session, "A city.") == {}


def test_the_shelf_is_shown_to_the_model(configured, db_session, monkeypatch):
    """The agent cannot recognise a fit it was never shown."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "POST":
            return httpx.Response(200, json={})
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    transport = httpx.MockTransport(handler)
    real = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": transport})
    )
    style_agent.draft_style_guide(db_session, "A city.")
    user = seen["body"]["messages"][-1]["content"]
    assert "romance — Romance" in user and "mystery — Mystery" in user


# ---- the no-counts rule -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Keep each beat to two paragraphs.",
        "Write 3 sentences and stop.",
        "Answer in one to two lines.",
        "Give the scene four beats.",
    ],
)
def test_a_block_containing_a_length_count_is_dropped(
    configured, db_session, monkeypatch, text
):
    _reply(monkeypatch, json.dumps({"voice": "Plain.", "pacing": text}))
    blocks = style_agent.draft_style_guide(db_session, "A city.")
    assert blocks == {"voice": "Plain."}, f"a count survived: {text!r}"


def test_dropping_one_block_keeps_the_rest(configured, db_session, monkeypatch):
    """Five good blocks and a missing one is a usable guide; the author writes the sixth."""
    _reply(
        monkeypatch,
        json.dumps({"attention": "Hands.", "voice": "Plain.", "pacing": "Two beats a turn."}),
    )
    blocks = style_agent.draft_style_guide(db_session, "A city.")
    assert set(blocks) == {"attention", "voice"}


# ---- failure is an ordinary state -------------------------------------------------


def test_an_unreachable_endpoint_yields_no_style_rather_than_raising(
    configured, db_session, monkeypatch
):
    _fail(monkeypatch)
    assert style_agent.draft_style_guide(db_session, "A city.") == {}


def test_an_unparseable_reply_yields_no_style(configured, db_session, monkeypatch):
    _reply(monkeypatch, "I think a moody noir feel would work nicely here!")
    assert style_agent.draft_style_guide(db_session, "A city.") == {}


def test_a_json_list_yields_no_style(configured, db_session, monkeypatch):
    _reply(monkeypatch, json.dumps(["attention", "voice"]))
    assert style_agent.draft_style_guide(db_session, "A city.") == {}


def test_no_world_yet_makes_no_call(db_session, monkeypatch):
    def explode(*_a, **_k):
        raise AssertionError("the agent called the model with nothing to read")

    monkeypatch.setattr(style_agent.llm, "chat_complete", explode)
    assert style_agent.draft_style_guide(db_session, "", "") == {}


# ---- the route --------------------------------------------------------------------


def test_the_route_returns_block_text(client, configured, monkeypatch):
    _reply(monkeypatch, json.dumps({"preset": "action"}))
    res = client.post("/api/storylines/style", json={"premise": "A siege."})
    assert res.status_code == 200, res.text
    assert res.json()["styleBlocks"]["signature"].startswith("Fast, physical")


def test_the_route_answers_empty_rather_than_failing(client, configured, monkeypatch):
    _fail(monkeypatch)
    res = client.post("/api/storylines/style", json={"premise": "A siege."})
    assert res.status_code == 200
    assert res.json()["styleBlocks"] == {}
