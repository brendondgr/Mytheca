"""A turn never ends having shown the player nothing.

Turns 8 and 9 of the `ps_0bf9ddc13b` session produced no character beat at all — the trace
ran intent → planning → "the turn ends", and the player got silence for a line they typed.
Two defects compounded, both fixed here, plus a backstop that does not depend on having
diagnosed every upstream cause.
"""

from __future__ import annotations

import json
import re

import httpx

from app.agents import planner_agent
from app.agents.intent_agent import TurnIntent
from app.agents.planner_agent import BeatDecision
from app.services import llm


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _cast(client, storyline_id):
    valdar = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Valdar"}).json()["id"]
    lyriel = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Lyriel"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Twinemeads"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Bloom", "castIds": [valdar, lyriel], "settingId": sid, "suggestionsCount": 0},
    ).json()["id"]
    return valdar, lyriel, scid


def _patch(monkeypatch, *, intent_payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "You interpret" in system:
            return _resp(json.dumps(intent_payload))
        if "private inner voice" in system:
            return _resp("{}")
        if "step-by-step loop" in system:
            # The planner ends immediately — the failure shape under test.
            return _resp(json.dumps({"action": "end", "reason": "direction satisfied"}))
        if "narrator of an interactive scene" in system:
            return _resp("The meads hold their breath.")
        m = re.search(r"You are \[(\d+)\]", user)
        num = m.group(1) if m else "1"
        return _resp(f'<speaker:{num}>\nShe answers, and the air moves. "Something is said."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _mid_scene(monkeypatch):
    """Make the turn look mid-scene rather than opening.

    ``scene_opening`` is ``not ctx.recent_beats``, and ``recent_beats`` comes from Redis —
    absent under test, so every turn would otherwise be a cold open and the narrator would
    speak. The silence under test happens *mid-scene*, which is where turns 8 and 9 were.
    """
    from app.memory import buffer

    monkeypatch.setattr(
        buffer, "anchored_turns",
        lambda session_id, window, block: [
            {"role": "character", "text": "The clearing is quiet.", "characterId": None},
        ],
    )


def _visible(events: list[dict]) -> list[dict]:
    return [
        e for e in events
        if e.get("type") in ("narration", "character_prose", "character_dialogue", "character_action")
    ]


def test_a_pov_turn_that_addresses_nobody_still_produces_a_scene(
    client, storyline_id, monkeypatch
):
    """The exact failure: POV on, planner ends at once, nobody addressed."""
    _configure_llm(client)
    valdar, _lyriel, scid = _cast(client, storyline_id)
    _patch(monkeypatch, intent_payload={"kind": "direct", "directive": "ask what they want"})

    _mid_scene(monkeypatch)
    events = _stream(client.post(
        f"/api/play/{scid}/turn",
        json={"text": "What is it you want from me?", "povCharacterId": valdar, "trace": True},
    ))
    assert all(e["type"] != "error" for e in events)
    assert _visible(events), "the turn ended without showing the player anything"
    # And it says why on the wire rather than quietly papering over it.
    assert any(
        e["type"] == "trace" and (e.get("data") or {}).get("backstop") for e in events
    )


def test_the_backstop_never_voices_the_pov_character(client, storyline_id, monkeypatch):
    """The player voices their own character; the backstop must not do it for them."""
    _configure_llm(client)
    valdar, lyriel, scid = _cast(client, storyline_id)
    _patch(monkeypatch, intent_payload={"kind": "direct", "directive": "ask what they want"})

    _mid_scene(monkeypatch)
    events = _stream(client.post(
        f"/api/play/{scid}/turn",
        json={"text": "What is it you want from me?", "povCharacterId": valdar},
    ))
    speakers = {e["data"].get("characterId") for e in _visible(events) if e.get("data")}
    assert valdar not in speakers
    assert lyriel in speakers


def test_the_intent_roster_hides_the_pov_character(client, db_session, storyline_id, monkeypatch):
    """Under POV the player IS that character, so they cannot be the one addressed.

    In the session that prompted this, the player wrote as Valdar and the intent came back
    "tell Valdar you want to be inside of him" — a target the planner then could not pick.
    """
    from app.agents import intent_agent
    from app.services import assembler, events_store, crud

    _configure_llm(client)
    valdar, lyriel, scid = _cast(client, storyline_id)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        seen["user"] = body["messages"][1]["content"]
        # Name roster slot 1 — whoever that is — as the addressed character.
        return _resp(json.dumps({"kind": "direct", "addressed": [1], "directive": "ask"}))

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    scenario = crud.get_scenario(db_session, scid)
    session = events_store.create_session(db_session, scid)
    ctx = assembler.assemble_context(db_session, scenario, session.id)

    intent = intent_agent.interpret(db_session, ctx, "What do you want?", locked_id=valdar)
    assert "Valdar" not in seen["user"].split("Player's line:")[0]
    assert intent.addressed == [lyriel]  # slot 1 is now Lyriel, not the POV character


def test_the_pov_character_does_not_count_as_having_answered(db_session):
    """`acted` is pre-marked with the POV id to stop re-selection, not to end the turn."""
    from app.models import Scenario
    from app.services import assembler

    members = [
        assembler.CastMember(id=i, name=i.title(), role="X", traits="", speech="", color="#000", stats={})
        for i in ("valdar", "lyriel")
    ]
    ctx = assembler.TurnContext(
        scenario=Scenario(storyline_id="e", title="S", cast_ids=["valdar", "lyriel"], setting_id=""),
        session_id="ps-silent",
        storyline_id="e",
        directed_at=None,
        cast=members,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[{"role": "player", "text": "earlier", "characterId": None}],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer=None,
        stable_prefix="",
    )
    # No LLM configured → the heuristic runs. POV is Valdar and he is marked acted.
    decision = planner_agent.next_beat(
        db_session, ctx, TurnIntent(kind="direct"), [], ["valdar"], locked_id="valdar"
    )
    assert decision.action == "speak" and decision.actor_id == "lyriel"
