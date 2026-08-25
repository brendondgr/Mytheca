"""One failed generation does not take the whole turn with it.

A single character call can come back with nothing in it — most often "the model spent its
whole budget thinking and never answered", which shows up on the SECOND beat of a turn,
where the transcript is longer and the deliberation runs past its (advisory) budget. Two
live verification runs each lost a whole turn that way: the player watched a beat arrive
and then got a terminal error frame instead of a scene.

Once the turn has shown something, a failed beat is traced and skipped. Before that it
still propagates, because a genuinely dead endpoint has to reach the player as an error
rather than as a scene that quietly says nothing.
"""

from __future__ import annotations

import json

import httpx

import pytest

from app.services import llm, llm_backend

# This module asserts on the PER-SPEAKER writer — the register directive, voice samples,
# relationship note, carried disposition and owed-requirements tail all live in the character
# prompt, and a continuous script never builds one. Continuous is the default since
# 2026-08-24, so the mode under test is pinned rather than inherited.
pytestmark = pytest.mark.usefixtures("per_speaker_scenes")


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    """Engine detection is cached per (base_url, model) and would leak between tests."""
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()

PASSAGE = 'I let the question sit. "You already knew," I say, and do not look up.'
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


def _prose(events) -> list[str]:
    """One string per beat — prose delta-streams, so the last frame for an id has it all."""
    latest: dict[str, str] = {}
    for e in events:
        if e["type"] == "character_prose":
            latest[e["id"]] = e["data"].get("text") or latest.get(e["id"], "")
    return [t for t in latest.values() if t]


def _patch_llm(monkeypatch, *, fail_first: bool = False, fail_all: bool = False) -> dict:
    """Return reasoning-with-no-content for a character call, the way the endpoint does.

    Which call fails is keyed on the TRANSCRIPT rather than a call counter: a beat can
    reach the endpoint more than once (a streaming attempt and its non-streaming fallback),
    so counting requests does not reliably mean "the second beat". A user prompt that
    already contains the first beat's passage is by construction a later beat.
    """
    state = {"calls": 0, "plans": 0, "served_failures": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if _CONTRACT_MARK in system:
            state["calls"] += 1
            later_beat = PASSAGE[:40] in body["messages"][1]["content"]
            if fail_all:
                fails = True                      # a dead endpoint: every call
            elif fail_first:
                # Only the opening beat — its attempt and its one retry, after which the
                # scene should carry on with whoever else is in the room. Counted on the
                # failures THIS handler has served rather than on total calls: engine-probe
                # requests share the same transport and would shift a call counter.
                fails = state["served_failures"] < 2
            else:
                fails = later_beat                # the common shape: a LATER beat starves
            if fails:
                state["served_failures"] += 1
                # What the endpoint actually returns: a completion that is all scratchpad.
                return httpx.Response(200, json={"choices": [
                    {"message": {"role": "assistant", "content": "",
                                 "reasoning": "Let me work out what Kira would say here."},
                     "finish_reason": "length"}
                ]})
            return httpx.Response(200, json={"choices": [{"message": {"content": PASSAGE}}]})
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


def _scene(client, storyline_id, names=("Mei", "Kira")):
    ids = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in names
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


def test_a_second_beat_that_fails_does_not_discard_the_first(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _mid_scene(monkeypatch)
    _patch_llm(monkeypatch)
    events = _turn(client, _scene(client, storyline_id))

    prose = [e for e in events if e["type"] == "character_prose" and e["data"].get("done")]
    assert prose, "the beat that succeeded must survive the beat that did not"
    assert not any(e["type"] == "error" for e in events)


def test_the_skipped_beat_is_traced_rather_than_silent(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _mid_scene(monkeypatch)
    _patch_llm(monkeypatch)
    events = _turn(client, _scene(client, storyline_id))

    skipped = [
        e for e in events if e["type"] == "trace" and e.get("data", {}).get("skipped")
    ]
    assert len(skipped) == 1


def test_a_first_beat_that_fails_is_skipped_like_any_other(client, storyline_id, monkeypatch):
    """One starved generation is a skipped beat wherever it lands, including first.

    A live run lost a whole turn to exactly this: the first beat came back empty, and an
    earlier rule that only salvaged failures *after* something had been shown turned it into
    a terminal error frame. The turn had two characters in the room and nothing wrong with
    the endpoint.
    """
    _configure_llm(client)
    _mid_scene(monkeypatch)
    _patch_llm(monkeypatch, fail_first=True, fail_all=False)
    events = _turn(client, _scene(client, storyline_id))

    assert not any(e["type"] == "error" for e in events)
    assert _prose(events), "the other character in the room should still have answered"


def test_an_endpoint_that_fails_every_beat_still_reaches_the_player_as_an_error(
    client, storyline_id, monkeypatch
):
    """A dead or misconfigured endpoint must not read as a quiet scene."""
    _configure_llm(client)
    _mid_scene(monkeypatch)
    _patch_llm(monkeypatch, fail_first=True, fail_all=True)
    events = _turn(client, _scene(client, storyline_id))

    assert any(e["type"] == "error" for e in events)
