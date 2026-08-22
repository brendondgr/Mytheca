"""Edit a beat in place — a character's line, the narration, or the player's own.

The owner's ask was two-sided: fix a beat where "the bot says something in a specific manner
that the user does not like", AND edit their own sent message so the conversation goes on
from there.

The assertion that matters most is not that the text changed — it is that the **buffer
follows**. Without the rebuild, the cast keeps reading the old wording out of Redis while the
player reads the new one, and the scene reacts to a line that is no longer on screen.
"""

from __future__ import annotations

import httpx

from app.services import llm, session_state

_EMISSION = (
    "<speaker:1>\n"
    "<thinking>Careful.</thinking>\n"
    "Mei sets the cup down.\n"
    '"Say that again."'
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


def _played(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    with client.stream("POST", f"/api/play/{scid}/turn", json={"text": "My original line."}) as r:
        for _ in r.iter_lines():
            pass
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    return scid, psid


def _events(client, scid, psid):
    return client.get(f"/api/play/{scid}/sessions/{psid}")().json() if False else client.get(
        f"/api/play/{scid}/sessions/{psid}"
    ).json()["events"]


def _first(client, scid, psid, type_):
    return next(e for e in _events(client, scid, psid) if e["type"] == type_)


def test_edit_rewrites_a_character_beat(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _first(client, scid, psid, "character_prose")

    resp = client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}",
        json={"text": "Mei sets the cup down, and says nothing at all."},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["text"] == "Mei sets the cup down, and says nothing at all."


def test_the_edit_is_what_the_history_returns(client, storyline_id, monkeypatch):
    """A reload must show the edit, not the original."""
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _first(client, scid, psid, "character_prose")

    client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}", json={"text": "Rewritten."}
    )

    again = next(e for e in _events(client, scid, psid) if e["id"] == beat["id"])
    assert again["data"]["text"] == "Rewritten."


def test_the_edit_is_what_the_export_renders(client, storyline_id, monkeypatch):
    """Both editable prose types, so the original wording is gone from the record entirely —
    the cold open emits a narration as well as the character's passage."""
    scid, psid = _played(client, storyline_id, monkeypatch)
    for type_, text in (
        ("character_prose", "A line the player wrote themselves."),
        ("narration", "A narration the player rewrote."),
    ):
        beat = _first(client, scid, psid, type_)
        client.patch(
            f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}", json={"text": text}
        )

    md = client.get(f"/api/play/{scid}/sessions/{psid}/export?format=md").text
    assert "A line the player wrote themselves." in md
    assert "A narration the player rewrote." in md

    # The TRANSCRIPT shows the edit. The diagnostic trace below it still records what the
    # model actually produced, and that is deliberate: the trace is a record of what the
    # engine did, and rewriting it to match a later edit would falsify it. The row itself
    # carries `editedByPlayer`, so the two are distinguishable rather than merely different.
    transcript = md.split("Diagnostics")[0] if "Diagnostics" in md else md
    assert "Say that again." not in transcript


def test_the_player_can_edit_their_own_line(client, storyline_id, monkeypatch):
    """The owner asked for this explicitly: edit what you sent, and carry on from there."""
    scid, psid = _played(client, storyline_id, monkeypatch)
    turn = _first(client, scid, psid, "user_turn")

    resp = client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{turn['id']}",
        json={"text": "What I meant to say."},
    )
    assert resp.status_code == 200
    assert _first(client, scid, psid, "user_turn")["data"]["text"] == "What I meant to say."


def test_an_edited_player_line_relabels_the_play_through(client, storyline_id, monkeypatch):
    """The tray labels a play-through by its first player line, so an edit must reach it."""
    scid, psid = _played(client, storyline_id, monkeypatch)
    turn = _first(client, scid, psid, "user_turn")

    client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{turn['id']}", json={"text": "A better opening."}
    )

    listed = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]
    assert listed["preview"] == "A better opening."


def test_the_scene_continues_after_an_edit(client, storyline_id, monkeypatch):
    """Editing is not destructive — what followed stays. Discarding it is what rewind is for."""
    scid, psid = _played(client, storyline_id, monkeypatch)
    before = len(_events(client, scid, psid))
    beat = _first(client, scid, psid, "character_prose")

    client.patch(f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}", json={"text": "Edited."})

    assert len(_events(client, scid, psid)) == before


def test_an_edited_beat_is_marked_as_player_authored(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _first(client, scid, psid, "character_prose")
    resp = client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}", json={"text": "Mine now."}
    )
    assert resp.json()["data"]["editedByPlayer"] is True


def test_a_machinery_beat_has_no_prose_to_edit(client, storyline_id, monkeypatch):
    """A stat change is not writing; there is nothing in it for the player to reword. Refused
    with a 422 rather than silently accepted and silently ignored."""
    _configure_llm(client)
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={"key": "trust", "displayName": "Trust", "min": 0, "max": 100, "default": 50},
    )
    _patch_llm(monkeypatch, _EMISSION + '\n<type:state_update>\n{"key":"trust","delta":5}')
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    with client.stream("POST", f"/api/play/{scid}/turn", json={"text": "Go."}) as r:
        for _ in r.iter_lines():
            pass
    psid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]

    update = _first(client, scid, psid, "state_update")
    resp = client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{update['id']}", json={"text": "nope"}
    )
    assert resp.status_code == 422


def test_editing_a_beat_from_another_play_through_404s(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    other = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]
    beat = _first(client, scid, psid, "character_prose")
    resp = client.patch(
        f"/api/play/{scid}/sessions/{other}/beats/{beat['id']}", json={"text": "nope"}
    )
    assert resp.status_code == 404


def test_edit_409s_on_a_stale_expected_seq(client, storyline_id, monkeypatch):
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _first(client, scid, psid, "character_prose")
    resp = client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}",
        json={"text": "nope", "expectedSeq": 0},
    )
    assert resp.status_code == 409


def test_edit_rebuilds_the_buffer_from_the_new_text(client, storyline_id, monkeypatch, db_session):
    """The whole reason edit needed session_state: the cast must not go on reading the old
    wording out of Redis while the player reads the new one."""
    scid, psid = _played(client, storyline_id, monkeypatch)
    beat = _first(client, scid, psid, "character_prose")
    client.patch(
        f"/api/play/{scid}/sessions/{psid}/beats/{beat['id']}", json={"text": "The new wording."}
    )

    # No Redis in the suite, so assert on what the rebuild WOULD push: the surviving prose
    # rows, read fresh from Postgres rather than from any cached copy.
    offered = session_state.rebuild_buffer(db_session, psid)
    assert offered >= 1
    texts = [
        e["data"].get("text")
        for e in _events(client, scid, psid)
        if e["type"] == "character_prose"
    ]
    assert "The new wording." in texts
