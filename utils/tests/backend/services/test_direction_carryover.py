"""A direction outlives the turn it rode in on.

Diagnosis cause 6: a requirement the beats could not reach simply vanished at the end of the
turn. Not because the engine mis-scheduled it — because nothing survived to re-owe it. That
is most of "right now it forgets what happens so often".

What is asserted here is the debt's whole lifecycle: written on the turn that failed it,
re-owed ahead of whatever is asked next, cleared by delivery, cancellable by the player, and
bounded so it cannot grow without limit.
"""

from __future__ import annotations

import json

import httpx

from app.services import llm


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _route(monkeypatch, *, requirements, narrator: str):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "You read the player's DIRECTION" in system:
            return _resp(json.dumps({"requirements": requirements}))
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "role-playing AS a specific character" in system:
            return _resp(json.dumps({"choices": []}))
        if "SITUATION-BASED follow-up" in system:
            return _resp(json.dumps({"choices": []}))
        if "step-by-step loop" in system:
            return _resp(json.dumps({"action": "end"}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp(narrator)
        return _resp('<speaker:1>\n<type:character_dialogue>\n"Something else."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _scenario(client, storyline_id, *, max_turns=2):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    return client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid, "maxTurns": max_turns},
    ).json()["id"]


def _turn(client, scid, guidance, session_id=None):
    events = []
    body = {"text": "", "guidance": guidance, "trace": True}
    if session_id:
        body["sessionId"] = session_id
    with client.stream("POST", f"/api/play/{scid}/turn", json=body) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.strip():
                events.append(json.loads(line))
    return events


def _session_id(client, scid):
    return client.get(f"/api/play/{scid}/sessions").json()["sessions"][0]["id"]


def _standing(client, scid, psid):
    return client.get(f"/api/play/{scid}/sessions/{psid}").json()["standingDirection"]


LAMP = [{"actor": None, "must": "the lamp goes over"}]
OFF_TOPIC = "They talk quietly about the weather."


def test_an_undelivered_requirement_is_written_to_the_session(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")

    psid = _session_id(client, scid)
    standing = _standing(client, scid, psid)
    assert [s["text"] for s in standing] == ["the lamp goes over"]
    # Stamped with the turn it was first asked for, so "carried over" can mean age.
    assert standing[0]["fromTurn"] == 0


def test_the_debt_is_re_owed_on_the_next_turn(client, storyline_id, monkeypatch):
    """The whole point: the next turn owes it again without the player re-typing it."""
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")
    psid = _session_id(client, scid)

    # A second turn asking for something else entirely.
    _route(monkeypatch, requirements=[{"actor": None, "must": "a bell rings"}], narrator=OFF_TOPIC)
    events = _turn(client, scid, "A bell rings.", session_id=psid)

    carried = [
        e for e in events
        if e.get("type") == "trace" and e.get("step") == "direction" and e["data"].get("carried")
    ]
    assert carried, "the earlier debt must be announced"
    assert carried[0]["data"]["carried"][0]["text"] == "the lamp goes over"
    # And it is owed FIRST — the older debt is the one most at risk of never landing.
    opening = next(
        e for e in events
        if e.get("type") == "trace"
        and e.get("step") == "direction"
        and e["data"].get("requirements")
    )
    assert opening["data"]["requirements"][0]["text"] == "the lamp goes over"


def test_delivering_it_clears_the_debt(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")
    psid = _session_id(client, scid)
    assert _standing(client, scid, psid)

    _route(monkeypatch, requirements=[], narrator="The lamp goes over with a crash.")
    _turn(client, scid, "Carry on.", session_id=psid)
    # The lamp is settled. (The second turn's own guidance becomes a requirement of its own
    # via the whole-text fallback, so the list is not empty — what matters is that the debt
    # this test is about is gone.)
    assert "the lamp goes over" not in [s["text"] for s in _standing(client, scid, psid)]


def test_restating_the_same_direction_does_not_double_the_debt(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")
    psid = _session_id(client, scid)
    _turn(client, scid, "The lamp goes over.", session_id=psid)

    assert len(_standing(client, scid, psid)) == 1


def test_the_player_can_cancel_what_the_scene_still_owes(
    client, storyline_id, monkeypatch
):
    """A debt the player cannot cancel is a bug, not a feature."""
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")
    psid = _session_id(client, scid)
    item_id = _standing(client, scid, psid)[0]["id"]

    resp = client.post(
        f"/api/play/{scid}/sessions/{psid}/standing-direction", json={"itemIds": [item_id]}
    )
    assert resp.status_code == 200
    assert resp.json()["standingDirection"] == []
    assert _standing(client, scid, psid) == []


def test_clearing_everything_takes_a_null_item_list(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")
    psid = _session_id(client, scid)

    resp = client.post(
        f"/api/play/{scid}/sessions/{psid}/standing-direction", json={"itemIds": None}
    )
    assert resp.json()["standingDirection"] == []


def test_cancelling_an_id_that_is_already_gone_is_not_an_error(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")
    psid = _session_id(client, scid)

    resp = client.post(
        f"/api/play/{scid}/sessions/{psid}/standing-direction", json={"itemIds": ["nope"]}
    )
    assert resp.status_code == 200
    assert len(resp.json()["standingDirection"]) == 1


def test_a_turn_with_no_direction_at_all_owes_nothing(client, storyline_id, monkeypatch):
    """The column stays NULL for an ordinary conversational turn.

    Worth pinning because the carry-over write runs on every turn: a scene the player never
    directs must not accumulate a debt, and `standingDirection` must not become a field that
    is always populated and therefore always ignored.
    """
    _configure_llm(client)
    _route(monkeypatch, requirements=[], narrator="Quiet.")
    scid = _scenario(client, storyline_id)
    # A plain spoken turn — no guidance box, so no direction and nothing to owe. (A
    # *guidance* turn always owes at least one thing: `parse` falls back to making the whole
    # guidance a single narrator-owned requirement.)
    with client.stream(
        "POST", f"/api/play/{scid}/turn", json={"text": "I say nothing much."}
    ) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_lines():
            pass
    psid = _session_id(client, scid)
    assert _standing(client, scid, psid) == []


def test_the_export_records_what_the_direction_did(client, storyline_id, monkeypatch):
    """A reader can see the direction and the prose; the export must also carry the engine's
    own verdict on whether the two met, and what was owed from before."""
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")
    psid = _session_id(client, scid)
    _turn(client, scid, "Carry on.", session_id=psid)

    md = client.get(f"/api/play/{scid}/sessions/{psid}/export?format=md").text
    assert "_Not confirmed delivered:_ the lamp goes over" in md
    assert "_Carried over from an earlier turn:_ the lamp goes over" in md

    data = client.get(f"/api/play/{scid}/sessions/{psid}/export?format=json").json()
    second = data["turns"][1]["direction"]
    assert "the lamp goes over" in second["carried"]



# ---- ids have to be unique, because dismissal is by id ----------------------
#
# Reported from the browser as three React "two children with the same key" warnings
# (`req1`, `req2`, `req3`). The console warning is the harmless half. The other half is that
# `clear_standing_direction` drops EVERY row whose id is in `itemIds`, so a duplicate id made
# the dismiss control remove requirements the player never pointed at.


def test_a_carried_debt_and_a_fresh_direction_do_not_share_an_id(
    client, storyline_id, monkeypatch
):
    """`direction_agent` numbers every fresh parse from `req1`, and a standing row keeps the
    `reqN` it was given on the turn that raised it. Merging the two id spaces collided."""
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")
    psid = _session_id(client, scid)

    # A second turn asking for something DIFFERENT, so it cannot collapse onto the standing
    # entry by text and must instead be given an id of its own.
    _route(monkeypatch, requirements=[{"actor": None, "must": "the door slams"}],
           narrator=OFF_TOPIC)
    _turn(client, scid, "The door slams.", session_id=psid)

    standing = _standing(client, scid, psid)
    ids = [s["id"] for s in standing]
    assert len(standing) == 2, standing
    assert len(set(ids)) == len(ids), ids


def test_dismissing_one_requirement_leaves_the_other(client, storyline_id, monkeypatch):
    """The functional half of the same bug: with a shared id, cancelling one debt cancelled
    its namesake too — silently, and with no way for the player to tell."""
    _configure_llm(client)
    _route(monkeypatch, requirements=LAMP, narrator=OFF_TOPIC)
    scid = _scenario(client, storyline_id)
    _turn(client, scid, "The lamp goes over.")
    psid = _session_id(client, scid)
    _route(monkeypatch, requirements=[{"actor": None, "must": "the door slams"}],
           narrator=OFF_TOPIC)
    _turn(client, scid, "The door slams.", session_id=psid)

    standing = _standing(client, scid, psid)
    assert len(standing) == 2
    resp = client.post(
        f"/api/play/{scid}/sessions/{psid}/standing-direction",
        json={"itemIds": [standing[0]["id"]]},
    )

    assert resp.status_code == 200
    remaining = resp.json()["standingDirection"]
    assert len(remaining) == 1
    assert remaining[0]["text"] == standing[1]["text"]


def test_a_row_written_with_a_duplicate_id_is_healed_on_read(db_session, client, storyline_id):
    """No migration: the column already holds duplicates in dev. `load_standing` is the one
    function that tolerates a malformed row, so it is where the repair belongs — the
    play-through is correct from its next read, and correct on disk from its next write."""
    from app.models import PlaySession
    from app.services import direction_runtime, events_store

    scid = _scenario(client, storyline_id)
    session = events_store.create_session(db_session, scid)
    row = db_session.get(PlaySession, session.id)
    row.standing_direction = [
        {"id": "req1", "text": "the lamp goes over", "fromTurn": 0},
        {"id": "req1", "text": "the door slams", "fromTurn": 2},
        {"id": "req1", "text": "the tide turns", "fromTurn": 4},
    ]
    db_session.add(row)
    db_session.commit()

    loaded = direction_runtime.load_standing(row)

    assert [r.text for r in loaded] == ["the lamp goes over", "the door slams", "the tide turns"]
    assert len({r.id for r in loaded}) == 3
    # The first keeps the id a client may already be holding; only the newcomers move.
    assert loaded[0].id == "req1"


def test_uniquify_is_a_no_op_when_the_ids_are_already_distinct():
    from app.agents.direction_agent import DirectionRequirement
    from app.services import direction_runtime

    reqs = [DirectionRequirement(id=f"req{i}", text=f"t{i}") for i in (1, 2, 3)]
    assert direction_runtime.uniquify_ids(reqs) == 0
    assert [r.id for r in reqs] == ["req1", "req2", "req3"]
