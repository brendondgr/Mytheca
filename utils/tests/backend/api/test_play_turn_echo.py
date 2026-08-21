"""A character does not answer by repeating the previous beat word for word.

Live session, five turns: **three pairs of byte-identical passages**, each pair attributed
to two DIFFERENT characters, one pair fourteen seconds apart. Not a parser fault — two
separate calls whose prompts differ only by a name and a role, which is what happens when a
cast has no traits, voice samples or stats to tell them apart. The owner saw the same thing
in their own export, where Valdar's beat restated Fennel's imagery.

The echo is caught on the passage's opening, which is what the scratchpad gate is already
holding, and regenerated through the same retry.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

ECHO = (
    "The cup's ring is still wet when I finally look up, and the room has not moved an inch. "
    "Aldous is still giving me his back, and Kira's hand is still on her belt by the door."
)
FRESH = 'I put my palm flat on the ledger. "Third crate," I say. "Now."'
_CONTRACT_MARK = "the way it would appear in a novel"


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _mid_scene(monkeypatch):
    from app.memory import buffer

    monkeypatch.setattr(
        buffer, "anchored_turns",
        lambda session_id, window, block: [
            {"role": "character", "text": "The room has already gone quiet.", "characterId": None},
        ],
    )


def _patch_llm(monkeypatch, *, always_echo: bool) -> dict:
    """Every character call returns ECHO; the retry returns FRESH unless ``always_echo``."""
    state = {"calls": 0, "plans": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if _CONTRACT_MARK in system:
            state["calls"] += 1
            # Beat 1 is accepted (nothing to echo yet); beat 2 echoes it and is blocked;
            # the retry is the third call and comes back fresh.
            text = ECHO if (always_echo or state["calls"] <= 2) else FRESH
            return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})
        if "scene director running one interactive-story turn" in system:
            state["plans"] += 1
            reply = (
                json.dumps({"action": "speak", "actor": 1, "reason": "responds"})
                if state["plans"] == 1
                else json.dumps({"action": "end", "reason": "done"})
            )
            return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return state


def _scene(client, storyline_id):
    ids = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in ("Mei", "Kira")
    ]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Hearth"}
    ).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": ids, "settingId": sid},
    ).json()["id"]


def _turn(client, scid):
    resp = client.post(
        f"/api/play/{scid}/turn", json={"text": "They look at each other.", "trace": True}
    )
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _bodies(events) -> list[str]:
    """One string per beat. Prose delta-streams — the same id and seq re-emitted with
    growing text — so the last frame for an id carries the whole passage."""
    latest: dict[str, str] = {}
    for e in events:
        if e["type"] == "character_prose":
            latest[e["id"]] = e["data"].get("text") or latest.get(e["id"], "")
    return list(latest.values())


def test_the_second_character_does_not_repeat_the_first_word_for_word(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _mid_scene(monkeypatch)
    _patch_llm(monkeypatch, always_echo=False)
    events = _turn(client, _scene(client, storyline_id))

    bodies = _bodies(events)
    assert len(bodies) == len(set(bodies)), "two beats came back byte-identical"


def test_the_regeneration_is_traced(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _mid_scene(monkeypatch)
    _patch_llm(monkeypatch, always_echo=False)
    events = _turn(client, _scene(client, storyline_id))

    assert any(
        e["type"] == "trace" and e.get("data", {}).get("scratchpad") for e in events
    )


def test_a_beat_that_echoes_twice_is_dropped_rather_than_shown(
    client, storyline_id, monkeypatch
):
    """One retry, then the turn moves on — never the same passage twice."""
    _configure_llm(client)
    _mid_scene(monkeypatch)
    _patch_llm(monkeypatch, always_echo=True)
    events = _turn(client, _scene(client, storyline_id))

    bodies = _bodies(events)
    assert len(bodies) == len(set(bodies))
    assert len(bodies) == 1
