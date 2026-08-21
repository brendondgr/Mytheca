"""A leaked scratchpad never reaches the wire, and the speaker gets one more try.

The passage's opening is withheld until it has proved itself, so a beat that comes back as
notes about the task is discarded before the reader sees a word of it — which is what makes
simply regenerating it safe: there is nothing to un-send and nothing to un-persist.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

LEAK = (
    "then main passage then optional structured blocks each opening tag own line JSON "
    "below NO closing tag per instructions AFTER passage may append structured block each "
    "own opening tag line JSON object beneath NO closing tag yes follow precisely ensure "
    "main answer contains ONLY tagged format meaning thinking tags + prose + blocks"
)
GOOD = (
    "The salt. The word hits me before the sentence finishes, and I do not look at him. "
    "\"You already knew,\" I say, and let it sit there between us on the scarred wood."
)


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


#: A turn makes many model calls — intent, planner, reflection — and only the character
#: ones matter here. The character call is the one carrying the output contract in its
#: system message, so the handler routes on that rather than on call order.
_CONTRACT_MARK = "the way it would appear in a novel"


def _patch_llm_sequence(monkeypatch, replies: list[str]) -> dict:
    """Serve ``replies`` in order to the CHARACTER calls; repeat the last one thereafter."""
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if _CONTRACT_MARK not in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        i = min(state["calls"], len(replies) - 1)
        state["calls"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": replies[i]}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return state


def _scene(client, storyline_id):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    return cid, scid


def _turn(client, scid, cid):
    resp = client.post(f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid})
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _prose(events: list[dict]) -> list[str]:
    return [e["data"]["text"] for e in events if e["type"] == "character_prose"]


def test_the_leaked_passage_never_appears_on_the_wire(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm_sequence(monkeypatch, [LEAK, GOOD])
    cid, scid = _scene(client, storyline_id)
    events = _turn(client, scid, cid)

    assert not any("structured blocks" in text for text in _prose(events))
    assert any("The salt" in text for text in _prose(events))


def test_the_leak_is_never_persisted_either(client, db_session, storyline_id, monkeypatch):
    from app.models import Event

    _configure_llm(client)
    _patch_llm_sequence(monkeypatch, [LEAK, GOOD])
    cid, scid = _scene(client, storyline_id)
    _turn(client, scid, cid)

    bodies = [
        e.data.get("text", "")
        for e in db_session.query(Event).filter(Event.type == "character_prose").all()
    ]
    assert bodies and not any("structured blocks" in b for b in bodies)


def test_the_retry_is_traced_so_the_regeneration_is_not_silent(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm_sequence(monkeypatch, [LEAK, GOOD])
    cid, scid = _scene(client, storyline_id)
    resp = client.post(
        f"/api/play/{scid}/turn", json={"text": "hi", "directedAt": cid, "trace": True}
    )
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    traces = [e for e in events if e["type"] == "trace"]
    assert any(t.get("data", {}).get("scratchpad") for t in traces)


def test_a_beat_that_leaks_twice_is_dropped_rather_than_retried_forever(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    state = _patch_llm_sequence(monkeypatch, [LEAK])
    cid, scid = _scene(client, storyline_id)
    events = _turn(client, scid, cid)

    assert not any("structured blocks" in text for text in _prose(events))
    # Exactly two character calls for the beat: the attempt and its one retry.
    assert state["calls"] == 2


def test_an_ordinary_beat_is_untouched_by_the_gate(client, storyline_id, monkeypatch):
    """The guard must be invisible when nothing is wrong."""
    _configure_llm(client)
    state = _patch_llm_sequence(monkeypatch, [GOOD])
    cid, scid = _scene(client, storyline_id)
    events = _turn(client, scid, cid)

    assert any("The salt" in text for text in _prose(events))
    assert state["calls"] == 1  # no retry, no second generation
