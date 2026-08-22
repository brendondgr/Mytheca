"""A turn with no line from the player — *Continue*, and the relaxation underneath it.

A turn used to require `text`, which made the player's own line the only way to move a scene:
you could not direct without also speaking, and you could not simply watch. The rule is now
"the turn must ask for *something*" — text, guidance, outcome, or continuation.

`turn_engine.validate_turn_inputs` states that rule once and `docs/plans/control-over-the-record.md`
owns it, so all four accept-paths and the wholly-empty rejection are tested here rather than
being re-proved by every plan that consumes one arm of it.
"""

from __future__ import annotations

import httpx
import pytest

from app.agents import intent_agent
from app.services import llm

_EMISSION = (
    "<speaker:1>\n"
    "<thinking>Let it sit.</thinking>\n"
    "Mei watches the door.\n"
    '"Someone is late."'
)


def _patch_llm(monkeypatch, content: str = _EMISSION):
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


def _scenario(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]


def _stream(client, scid, body):
    events = []
    with client.stream("POST", f"/api/play/{scid}/turn", json=body) as resp:
        status = resp.status_code
        if status == 200:
            import json as _json

            for line in resp.iter_lines():
                if line.strip():
                    events.append(_json.loads(line))
    return status, events


# ---- the rule ---------------------------------------------------------------


def test_a_wholly_empty_turn_is_still_rejected(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    resp = client.post(f"/api/play/{scid}/turn", json={"text": "   "})
    assert resp.status_code == 400
    assert "Continue" in resp.json()["error"]["message"]


@pytest.mark.parametrize(
    "body",
    [
        {"text": "I speak."},
        {"text": "", "guidance": "Someone should arrive."},
        {"text": "", "outcome": "the door opens"},
        {"text": "", "continuation": True},
    ],
    ids=["text", "guidance-only", "outcome-only", "continuation"],
)
def test_a_turn_is_valid_when_it_asks_for_anything(client, storyline_id, monkeypatch, body):
    """All four arms, so the plan that consumes each one does not have to re-prove it."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    status, _events = _stream(client, scid, body)
    assert status == 200


# ---- what a continuation turn actually does ---------------------------------


def test_a_continuation_turn_produces_beats(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _status, events = _stream(client, scid, {"text": "", "continuation": True})

    prose = [e for e in events if e.get("type") in ("character_prose", "narration")]
    assert prose, "a continuation turn must still move the scene"


def test_a_continuation_turn_does_not_call_the_intent_agent(client, storyline_id, monkeypatch):
    """Nothing was said, so there is nothing to interpret. Asking the agent to classify an
    empty string invites it to invent an ask the player never made — and it costs a call on
    the turn path."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    called = False
    real = intent_agent.interpret

    def spy(*a, **k):
        nonlocal called
        called = True
        return real(*a, **k)

    monkeypatch.setattr(intent_agent, "interpret", spy)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "continuation": True})
    assert called is False

    _stream(client, scid, {"text": "But I do speak here."})
    assert called is True


def test_a_continuation_turn_still_writes_its_user_turn_row(client, storyline_id, monkeypatch):
    """The row keeps the turn's trace grouping (traces are keyed by its seq) and its place in
    the export, even though the player said nothing."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "continuation": True})

    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    history = client.get(f"/api/play/{scid}/sessions/{psid}").json()
    turns = [e for e in history["events"] if e["type"] == "user_turn"]
    assert len(turns) == 1
    assert turns[0]["data"]["text"] == ""
    assert history["traces"], "the turn keeps its diagnostic trace"


def test_a_continuation_does_not_label_the_play_through_with_a_blank(client, storyline_id, monkeypatch):
    """Phase 1 made the preview the first NON-EMPTY line for exactly this case — asserted
    here rather than assumed."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "continuation": True})
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    _stream(client, scid, {"text": "Now I speak.", "sessionId": psid})

    listed = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]
    assert listed["turnCount"] == 2
    assert listed["preview"] == "Now I speak."


def test_a_continuation_does_not_poison_the_transcript_window(client, storyline_id, monkeypatch, db_session):
    """A blank player beat pushed into the recent-turn buffer would sit in every later prompt.
    The suite has no Redis, so assert on what a rebuild would offer."""
    from app.services import session_state

    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "continuation": True})
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]

    history = client.get(f"/api/play/{scid}/sessions/{psid}").json()["events"]
    blank_player_beats = [
        e for e in history if e["type"] == "user_turn" and not str(e["data"].get("text") or "").strip()
    ]
    assert blank_player_beats, "the row exists…"
    # …but contributes nothing to the window the model reads.
    assert session_state.rebuild_buffer(db_session, psid) == len(
        [e for e in history if e["type"] in ("narration", "character_prose")]
    )
