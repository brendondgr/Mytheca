"""A turn that is pure direction — the player steers without speaking.

Under Player POV the message box is the character's own line, so there was no way to push the
scene without also putting words in their mouth. A `guidance`-only turn is that missing shape:
the row is still written (the turn happened, and its traces hang off its seq), but nothing the
player "said" enters the transcript window, because they said nothing.

`docs/plans/control-over-the-record.md` owns the four-way validity rule and
`utils/tests/backend/api/test_play_turn_continuation.py` proves it. What is proved *here* is
what makes a direction-only turn different from a silent one: the direction reaches the engine,
labels the play-through, and is legible in the trace and the export.
"""

from __future__ import annotations

import json as _json

import httpx

from app.services import llm

_EMISSION = (
    "<speaker:1>\n"
    "<thinking>The room shifts.</thinking>\n"
    "Mei stands abruptly.\n"
    '"Enough of this."'
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
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]


def _stream(client, scid, body):
    events = []
    with client.stream("POST", f"/api/play/{scid}/turn", json=body) as resp:
        status = resp.status_code
        if status == 200:
            for line in resp.iter_lines():
                if line.strip():
                    events.append(_json.loads(line))
    return status, events


DIRECTION = "Someone should lose their temper."


def test_a_direction_only_turn_streams_beats(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    status, events = _stream(client, scid, {"text": "", "guidance": DIRECTION})
    assert status == 200
    prose = [e for e in events if e.get("type") in ("character_prose", "narration")]
    assert prose, "a direction with no line must still move the scene"


def test_the_row_records_the_direction_with_an_empty_line(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "guidance": DIRECTION})

    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    history = client.get(f"/api/play/{scid}/sessions/{psid}").json()
    rows = [e for e in history["events"] if e["type"] == "user_turn"]
    assert len(rows) == 1
    assert rows[0]["data"]["text"] == ""
    assert rows[0]["data"]["guidance"] == DIRECTION


def test_the_direction_labels_the_play_through(client, storyline_id, monkeypatch):
    """A direction-only opener is text-less but NOT silent — the player typed something, it
    just went in the other box. The tray must show it rather than an unnamed row."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "guidance": DIRECTION})

    listed = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]
    assert listed["preview"] == DIRECTION


def test_a_spoken_line_still_wins_the_label(client, storyline_id, monkeypatch):
    """The direction is only a fallback: once the player has actually said something, that is
    what the play-through is called."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "guidance": DIRECTION})
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    _stream(client, scid, {"text": "I will not.", "sessionId": psid})

    listed = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]
    assert listed["preview"] == "I will not."


def test_the_turn_trace_shows_the_direction_not_a_blank(client, storyline_id, monkeypatch):
    """The one Inspector row recording what the player asked for must not read "no line from
    you" on the turn where they asked for the most."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "guidance": DIRECTION})

    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    traces = client.get(f"/api/play/{scid}/sessions/{psid}").json()["traces"]
    turn = next(t for t in traces if t["step"] == "turn")
    assert turn["title"] == "You directed the scene"
    assert turn["detail"] == DIRECTION
    assert turn["data"]["directionOnly"] is True


def test_a_true_continuation_still_reads_as_one(client, storyline_id, monkeypatch):
    """Direction-only and *Continue* are different acts and the trace distinguishes them."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "continuation": True})

    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    traces = client.get(f"/api/play/{scid}/sessions/{psid}").json()["traces"]
    turn = next(t for t in traces if t["step"] == "turn")
    assert turn["title"] == "You let the scene continue"
    assert turn["data"]["directionOnly"] is False


def test_the_export_says_direction_only(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "guidance": DIRECTION})
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]

    md = client.get(f"/api/play/{scid}/sessions/{psid}/export?format=md").text
    assert "_(direction only)_" in md
    assert "_(let the scene continue)_" not in md
    assert f"_Direction:_ {DIRECTION}" in md


def test_the_direction_does_not_enter_the_transcript_window(
    client, storyline_id, monkeypatch, db_session
):
    """Nothing was *said*, so nothing the player wrote may sit in the recent-turn buffer as a
    spoken beat — the direction steers the turn, it is not dialogue in it."""
    from app.services import session_state

    _configure_llm(client)
    _patch_llm(monkeypatch)
    scid = _scenario(client, storyline_id)
    _stream(client, scid, {"text": "", "guidance": DIRECTION})
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]

    history = client.get(f"/api/play/{scid}/sessions/{psid}").json()["events"]
    assert session_state.rebuild_buffer(db_session, psid) == len(
        [e for e in history if e["type"] in ("narration", "character_prose")]
    )
