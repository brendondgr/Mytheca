"""A `hidden` stat's change is recorded but never shown.

`StatDefinition.visibility` has existed since the stat system shipped and, until this phase,
meant nothing at play time — an author who marked a stat hidden watched it announce itself in
the transcript anyway. The rule is: **persisted, traced, exported; not streamed.** The
Inspector is a diagnostic surface and shows everything; the transcript is the story and does
not.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm

_EMISSION = (
    "<speaker:1>\n"
    '"You would not like what I am thinking."\n'
    "<type:state_update>\n"
    '{"key":"suspicion","delta":12,"reason":"the lie landed"}'
)


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch_llm(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "direct", "directive": "press"}))
        if "SITUATION-BASED follow-up" in system:
            return _resp(json.dumps({"choices": []}))
        if "step-by-step loop" in system:
            return _resp(json.dumps({"action": "speak", "actor": 1}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp("A hush falls.")
        return _resp(_EMISSION)

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _scene(client, storyline_id, *, visibility: str):
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={
            "key": "suspicion",
            "displayName": "Suspicion",
            "min": 0,
            "max": 100,
            "default": 50,
            "visibility": visibility,
        },
    )
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    return cid, scid


def _run(client, scid, cid):
    return _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "I accuse her.", "directedAt": cid, "trace": True},
        )
    )


def test_a_hidden_stat_change_is_not_streamed(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id, visibility="hidden")

    events = _run(client, scid, cid)

    assert all(e["type"] != "state_update" for e in events)


def test_a_hidden_stat_change_is_still_persisted(client, storyline_id, monkeypatch):
    """The row stays in the log — the Inspector, the export and a rewind's replay need it."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id, visibility="hidden")

    events = _run(client, scid, cid)
    session_id = next(e["sessionId"] for e in events if e.get("sessionId"))
    history = client.get(f"/api/play/{scid}/sessions/{session_id}").json()

    row = next(e for e in history["events"] if e["type"] == "state_update")
    assert row["visibility"] == "hidden"
    assert row["data"]["stat"]["key"] == "suspicion"


def test_the_trace_step_still_shows_it(client, storyline_id, monkeypatch):
    """The Inspector is a diagnostic surface: it shows everything, including what the
    transcript is deliberately not told."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id, visibility="hidden")

    events = _run(client, scid, cid)
    step = next(e for e in events if e["type"] == "trace" and e["step"] == "stat")

    assert step["data"]["key"] == "suspicion"
    assert step["data"]["delta"] == 12


def test_the_value_still_moved(client, storyline_id, monkeypatch):
    """Hidden means unseen, not inert."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id, visibility="hidden")

    events = _run(client, scid, cid)
    session_id = next(e["sessionId"] for e in events if e.get("sessionId"))
    history = client.get(f"/api/play/{scid}/sessions/{session_id}").json()
    row = next(e for e in history["events"] if e["type"] == "state_update")
    assert row["data"]["stat"]["value"] == 62  # default 50 + 12


def test_a_public_stat_is_streamed_as_before(client, storyline_id, monkeypatch):
    """The control: without it the first two assertions would pass on a broken emitter."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scene(client, storyline_id, visibility="public")

    events = _run(client, scid, cid)

    update = next(e for e in events if e["type"] == "state_update")
    assert update["data"]["stat"]["key"] == "suspicion"
