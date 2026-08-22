"""Play-through record endpoints: create / rename / delete.

These back the story player's play-through tray. Before them a scenario could only ever
hold one story — the client resumed the most recent session unconditionally, and the only
way to open a new one was to send a turn with no ``sessionId``, which it never did.

LLM is offline-mocked in the same idiom as ``test_play_sessions``.
"""

from __future__ import annotations

import httpx

from app.services import llm

_EMISSION = (
    "<speaker:1>\n"
    "<thinking>Hold the line.</thinking>\n"
    "Mei does not move.\n"
    '"Not tonight."'
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
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    return cid, scid


def _turn(client, scenario_id, text, session_id=None):
    body = {"text": text}
    if session_id:
        body["sessionId"] = session_id
    with client.stream("POST", f"/api/play/{scenario_id}/turn", json=body) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_lines():
            pass


# ---- create ---------------------------------------------------------------


def test_create_session_opens_an_empty_playthrough(client, storyline_id):
    _, scid = _scenario(client, storyline_id)
    resp = client.post(f"/api/play/{scid}/sessions", json={"name": "Second run"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["scenarioId"] == scid
    assert body["name"] == "Second run"
    assert body["turnCount"] == 0
    assert body["preview"] == ""
    assert body["parentSessionId"] is None
    assert body["forkSeq"] is None


def test_create_session_does_not_clobber_the_existing_one(client, storyline_id, monkeypatch):
    """The whole point of the endpoint: starting fresh must leave the old story intact."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _, scid = _scenario(client, storyline_id)
    _turn(client, scid, "The first play-through.")

    first = client.get(f"/api/play/{scid}/sessions").json()["sessions"]
    assert len(first) == 1
    assert first[0]["turnCount"] == 1

    client.post(f"/api/play/{scid}/sessions", json={})
    after = client.get(f"/api/play/{scid}/sessions").json()["sessions"]
    assert len(after) == 2
    kept = next(s for s in after if s["id"] == first[0]["id"])
    assert kept["turnCount"] == 1
    assert kept["preview"] == "The first play-through."


def test_create_session_without_a_body_is_unnamed(client, storyline_id):
    _, scid = _scenario(client, storyline_id)
    body = client.post(f"/api/play/{scid}/sessions").json()
    assert body["name"] is None


def test_create_session_rejects_an_unknown_scenario(client):
    assert client.post("/api/play/sc_nope/sessions", json={}).status_code == 404


# ---- rename ---------------------------------------------------------------


def test_rename_session_sets_and_clears_the_label(client, storyline_id):
    _, scid = _scenario(client, storyline_id)
    sid = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]

    named = client.patch(f"/api/play/{scid}/sessions/{sid}", json={"name": "  The kind run  "})
    assert named.status_code == 200
    assert named.json()["name"] == "The kind run"

    cleared = client.patch(f"/api/play/{scid}/sessions/{sid}", json={"name": "   "})
    assert cleared.json()["name"] is None


def test_rename_session_rejects_a_foreign_session(client, storyline_id):
    _, scid_a = _scenario(client, storyline_id)
    _, scid_b = _scenario(client, storyline_id)
    sid = client.post(f"/api/play/{scid_a}/sessions", json={}).json()["id"]
    resp = client.patch(f"/api/play/{scid_b}/sessions/{sid}", json={"name": "nope"})
    assert resp.status_code == 400


def test_rename_session_404s_on_an_unknown_session(client, storyline_id):
    _, scid = _scenario(client, storyline_id)
    resp = client.patch(f"/api/play/{scid}/sessions/ps_nope", json={"name": "x"})
    assert resp.status_code == 404


# ---- delete ---------------------------------------------------------------


def test_delete_session_removes_it_and_its_history(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_llm(monkeypatch)
    _, scid = _scenario(client, storyline_id)
    _turn(client, scid, "A line worth forgetting.")
    sid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]

    assert client.delete(f"/api/play/{scid}/sessions/{sid}").status_code == 204
    assert client.get(f"/api/play/{scid}/sessions").json()["sessions"] == []
    # The history endpoint must agree that it is gone, not 500 on orphaned rows.
    assert client.get(f"/api/play/{scid}/sessions/{sid}").status_code == 404


def test_delete_session_leaves_the_other_playthroughs_alone(client, storyline_id):
    _, scid = _scenario(client, storyline_id)
    keep = client.post(f"/api/play/{scid}/sessions", json={"name": "keep"}).json()["id"]
    drop = client.post(f"/api/play/{scid}/sessions", json={"name": "drop"}).json()["id"]

    client.delete(f"/api/play/{scid}/sessions/{drop}")
    remaining = client.get(f"/api/play/{scid}/sessions").json()["sessions"]
    assert [s["id"] for s in remaining] == [keep]


def test_delete_session_rejects_a_foreign_session(client, storyline_id):
    _, scid_a = _scenario(client, storyline_id)
    _, scid_b = _scenario(client, storyline_id)
    sid = client.post(f"/api/play/{scid_a}/sessions", json={}).json()["id"]
    assert client.delete(f"/api/play/{scid_b}/sessions/{sid}").status_code == 400


# ---- the turn's own inputs are persisted ----------------------------------


def test_user_turn_row_carries_guidance_and_tagged_docs(client, storyline_id, monkeypatch):
    """Direction and attachments used to die with the turn. Rewind and turn-scope re-roll
    both replay the player's line, so the row has to carry what it rode in with."""
    _configure_llm(client)
    _patch_llm(monkeypatch)
    cid, scid = _scenario(client, storyline_id)
    doc = client.post(
        f"/api/storylines/{storyline_id}/context-docs/bulk",
        json={"docs": [{"name": "harbor.md", "content": "The harbor is iced over."}]},
    )
    assert doc.status_code == 201, doc.text
    doc_ids = [d["id"] for d in doc.json()]

    body = {
        "text": "I hold my ground.",
        "povCharacterId": cid,
        "guidance": "Mei should lose her temper.",
        "taggedDocIds": doc_ids,
    }
    with client.stream("POST", f"/api/play/{scid}/turn", json=body) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_lines():
            pass

    sid = client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]
    events = client.get(f"/api/play/{scid}/sessions/{sid}").json()["events"]
    user_turn = next(e for e in events if e["type"] == "user_turn")
    assert user_turn["data"]["guidance"] == "Mei should lose her temper."
    assert user_turn["data"]["pov"] == cid
    assert user_turn["data"]["taggedDocIds"] == doc_ids


def test_preview_skips_an_empty_player_line(client, storyline_id, db_session):
    """A text-less turn is legal (Continue). Labelling a whole play-through with the
    blank string it wrote would make the tray unreadable."""
    from app.services import events_store

    _, scid = _scenario(client, storyline_id)
    session = events_store.create_session(db_session, scid)
    events_store.record_user_turn(
        db_session,
        scenario_id=scid,
        session_id=session.id,
        seq=0,
        text="",
        directed_at=None,
    )
    events_store.record_user_turn(
        db_session,
        scenario_id=scid,
        session_id=session.id,
        seq=1,
        text="The first real line.",
        directed_at=None,
    )
    count, preview = events_store.user_turn_stats(db_session, session.id)
    assert count == 2
    assert preview == "The first real line."
