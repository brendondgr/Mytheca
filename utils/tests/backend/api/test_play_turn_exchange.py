"""A room with two people in it does not answer the player with one line.

The ``ps_c015c506b1`` export is the failure this guards: two characters present, the
player asks for a moment between THEM, and turn 2 is one character's beat followed by
"the turn ends — direction satisfied". The second character never answers. The owner's
word for what is missing is "back and forth".

The planner's first ``end`` is refused once when somebody in the room has not spoken and
fewer than two have. Once only, and never for a one-character cast — a floor under the
exchange, not a quota on it.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

PASSAGE = (
    "I let the question sit where it landed. \"You already knew,\" I say, and do not look up."
)


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch_llm(monkeypatch) -> dict:
    """Characters write prose; the planner picks one speaker and then ends.

    This is the export's exact shape: "Fennel is up next" → Fennel speaks → "the turn ends
    — direction satisfied", with Valdar still in the room and silent.
    """
    state = {"plans": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "from inside that character" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": PASSAGE}}]})
        if "scene director running one interactive-story turn" in system:
            state["plans"] += 1
            reply = (
                json.dumps({"action": "speak", "actor": 1, "reason": "responds"})
                if state["plans"] == 1
                else json.dumps({"action": "end", "reason": "direction satisfied"})
            )
            return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return state


def _mid_scene(monkeypatch):
    """Make the turn read as mid-scene rather than a cold open.

    ``scene_opening`` is ``not ctx.recent_beats``, and ``recent_beats`` comes from Redis,
    which is absent under test — so without this every turn is narrator-led and no
    character beat happens at all. What is under test here is a turn that answers with one
    character line, which only exists mid-scene.
    """
    from app.memory import buffer

    monkeypatch.setattr(
        buffer, "anchored_turns",
        lambda session_id, window, block: [
            {"role": "character", "text": "The room has already gone quiet.", "characterId": None},
        ],
    )


def _scene(client, storyline_id, names):
    ids = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in names
    ]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": ids, "settingId": sid},
    ).json()["id"]
    return ids, scid


def _turn(client, scid, text="They look at each other.", session_id=None):
    body = {"text": text, "trace": True}
    if session_id:
        body["sessionId"] = session_id
    resp = client.post(f"/api/play/{scid}/turn", json=body)
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _speakers(events) -> list[str]:
    return [
        e["data"]["characterId"]
        for e in events
        if e["type"] == "character_prose" and e["data"].get("done")
    ]


def test_a_two_hander_gets_two_beats_even_when_the_planner_ends_early(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _mid_scene(monkeypatch)
    _ids, scid = _scene(client, storyline_id, ("Mei", "Kira"))
    events = _turn(client, scid)

    assert len(set(_speakers(events))) == 2, "both characters in the room should answer"


def test_the_refusal_is_traced_rather_than_silent(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _mid_scene(monkeypatch)
    _ids, scid = _scene(client, storyline_id, ("Mei", "Kira"))
    events = _turn(client, scid)

    forced = [
        e for e in events
        if e["type"] == "trace" and e.get("data", {}).get("exchange")
    ]
    assert len(forced) == 1
    assert "register" in forced[0]["data"]  # every speaker step carries it


def test_a_solo_cast_is_left_alone(client, storyline_id, monkeypatch):
    """With one character there is no exchange to force — the turn ends when it ends."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _mid_scene(monkeypatch)
    _ids, scid = _scene(client, storyline_id, ("Mei",))
    events = _turn(client, scid)

    assert len(set(_speakers(events))) == 1
    assert not any(e.get("data", {}).get("exchange") for e in events if e["type"] == "trace")


def test_the_guard_fires_at_most_once_so_a_scene_can_still_end(
    client, storyline_id, monkeypatch
):
    """Three in the room, a planner that always ends: two beats, then the turn stops."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _mid_scene(monkeypatch)
    _ids, scid = _scene(client, storyline_id, ("Mei", "Kira", "Aldous"))
    events = _turn(client, scid)

    assert len(set(_speakers(events))) == 2
    forced = [e for e in events if e["type"] == "trace" and e.get("data", {}).get("exchange")]
    assert len(forced) == 1
