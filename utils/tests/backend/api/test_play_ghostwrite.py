"""The Ghostwriter endpoint — and the property that makes it safe: it persists nothing.

A drafted line the player rejects must leave no trace anywhere, because it never entered the
record. That is structural rather than promised: the route writes no event row, no trace and
no buffer entry. The line becomes part of the story only when the player sends it, through
the ordinary turn path, exactly as if they had typed it.
"""

from __future__ import annotations

import json

import httpx

from app.models import Event, TurnTrace
from app.services import llm


def _patch_llm(monkeypatch, content: str):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _scene(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    psid = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]
    return cid, scid, psid


def _ghostwrite(client, scid, body):
    frames = []
    with client.stream("POST", f"/api/play/{scid}/ghostwrite/stream", json=body) as resp:
        status = resp.status_code
        if status == 200:
            for line in resp.iter_lines():
                if line.strip():
                    frames.append(json.loads(line))
    return status, frames


def test_it_streams_a_drafted_line(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch, "I do not believe you, and I am being polite about it.")
    cid, scid, psid = _scene(client, storyline_id)

    status, frames = _ghostwrite(
        client,
        scid,
        {"sessionId": psid, "intent": "Refuse, but stay civil.", "povCharacterId": cid},
    )

    assert status == 200
    text = "".join(f.get("text", "") for f in frames if f["type"] == "ghostwrite")
    assert "I do not believe you" in text
    assert frames[-1]["done"] is True


def test_it_persists_nothing(client, storyline_id, monkeypatch, db_session):
    """The property the whole design rests on."""
    _configure_llm(client)
    _patch_llm(monkeypatch, "A line the player never sent.")
    cid, scid, psid = _scene(client, storyline_id)

    before_events = db_session.query(Event).filter(Event.session_id == psid).count()
    before_traces = db_session.query(TurnTrace).filter(TurnTrace.session_id == psid).count()

    _ghostwrite(client, scid, {"sessionId": psid, "intent": "Say something.", "povCharacterId": cid})

    assert db_session.query(Event).filter(Event.session_id == psid).count() == before_events
    assert db_session.query(TurnTrace).filter(TurnTrace.session_id == psid).count() == before_traces


def test_it_does_not_show_up_in_the_transcript_or_the_export(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch, "A rejected draft.")
    cid, scid, psid = _scene(client, storyline_id)

    _ghostwrite(client, scid, {"sessionId": psid, "intent": "x", "povCharacterId": cid})

    history = client.get(f"/api/play/{scid}/sessions/{psid}").json()
    assert history["events"] == []
    md = client.get(f"/api/play/{scid}/sessions/{psid}/export?format=md").text
    assert "A rejected draft." not in md


def test_narrator_mode_needs_no_pov_character(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch, "The lamp gutters and the room leans in.")
    _cid, scid, psid = _scene(client, storyline_id)

    status, frames = _ghostwrite(
        client, scid, {"sessionId": psid, "intent": "Set the room.", "mode": "narrator"}
    )

    assert status == 200
    assert "lamp gutters" in "".join(f.get("text", "") for f in frames if f["type"] == "ghostwrite")


def test_an_empty_intent_is_refused_before_the_stream_opens(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _cid, scid, psid = _scene(client, storyline_id)
    resp = client.post(
        f"/api/play/{scid}/ghostwrite/stream", json={"sessionId": psid, "intent": "   "}
    )
    assert resp.status_code == 400


def test_an_unknown_session_is_refused(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _cid, scid, _psid = _scene(client, storyline_id)
    resp = client.post(
        f"/api/play/{scid}/ghostwrite/stream", json={"sessionId": "ps_nope", "intent": "x"}
    )
    assert resp.status_code == 404


def test_an_unconfigured_model_reports_in_band(client, storyline_id):
    """No LLM configured: the player pressed a button, so say so rather than streaming
    nothing and leaving the control looking broken."""
    _cid, scid, psid = _scene(client, storyline_id)
    _status, frames = _ghostwrite(client, scid, {"sessionId": psid, "intent": "x"})
    assert frames and frames[-1]["type"] == "error"
