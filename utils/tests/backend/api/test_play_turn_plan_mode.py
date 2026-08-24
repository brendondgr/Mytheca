"""POST /api/play/{scenarioId}/turn — Plan mode: show the plan, wait, then run what was approved.

Three properties, and the middle one is the whole feature:

1. **Under `plan`, nothing is written.** The turn plans, streams a `plan` frame marked
   `awaitingApproval`, and stops. No prose events, no suggestions.
2. **An approved plan is EXECUTED, never re-planned.** Asserted on the planner's *call count*
   rather than on wall clock or on the output looking similar — a second planner call would
   produce a different turn from the one the player agreed to, and that is exactly the failure
   this feature exists to prevent.
3. **A plan is never a story event.** It states what a turn intends, which may not happen;
   persisting one would put something in the transcript no reader saw and no rewind could
   account for.

LLM is offline-mocked and routed by system prompt, mirroring the sibling turn tests.
"""

from __future__ import annotations

import json

import httpx

from app.events.envelope import story_event_adapter
from app.services import llm


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _route(monkeypatch, decisions, counter: dict):
    """Route the mock by system prompt, counting planner calls."""
    plan = iter(decisions)
    counter.setdefault("planner", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "step-by-step loop" in system:
            counter["planner"] += 1
            try:
                return _resp(json.dumps(next(plan)))
            except StopIteration:
                return _resp(json.dumps({"action": "end"}))
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "SITUATION-BASED follow-up" in system or "role-playing AS a specific" in system:
            return _resp(json.dumps({"choices": []}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp("The lamp gutters.")
        return _resp('"I hear you," I say, and I do not move.')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _scene(client, storyline_id, name="Ana"):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": name}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hall"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Plan", "castIds": [cid], "settingId": sid, "suggestionsCount": 0},
    ).json()["id"]
    return scid, cid


PROSE = ("narration", "character_prose", "character_dialogue", "character_action")


def test_plan_mode_streams_a_plan_and_writes_nothing(client, storyline_id, monkeypatch):
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, [{"beats": [{"action": "speak", "actor": 1}, {"action": "end"}]}], counter)
    scid, cid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Say something.", "directedAt": cid, "overrides": {"planner": "plan"}},
        )
    )
    plans = [e for e in events if e.get("type") == "plan"]
    assert len(plans) == 1
    assert plans[0]["awaitingApproval"] is True
    assert plans[0]["beats"], "a plan with no beats is nothing to approve"
    # Nothing was written. That is the promise the panel makes.
    assert not [e for e in events if e.get("type") in PROSE]


def test_the_plan_names_who_acts_rather_than_making_the_client_join_on_ids(
    client, storyline_id, monkeypatch
):
    """A panel that has to look ids up renders "unknown" the first time presence changes."""
    _configure_llm(client)
    counter: dict = {}
    _route(
        monkeypatch,
        [{"beats": [{"action": "speak", "actor": 1, "register": "tense", "reason": "she bites"}]}],
        counter,
    )
    scid, cid = _scene(client, storyline_id, name="Mei")

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Go on.", "directedAt": cid, "overrides": {"planner": "plan"}},
        )
    )
    beat = next(e for e in events if e.get("type") == "plan")["beats"][0]
    assert beat["actorName"] == "Mei"
    assert beat["actorId"] == cid
    assert beat["register"] == "tense"  # the wire name, despite the aliased attribute
    assert beat["reason"] == "she bites"


def test_an_approved_plan_runs_without_a_second_planner_call(client, storyline_id, monkeypatch):
    """The core promise: what you approved is what runs.

    Asserted on the planner's call count. A turn that re-planned would still produce prose
    and still look fine — it would simply be a different turn from the one the player agreed
    to, which no assertion about the output could catch.
    """
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, [], counter)
    scid, cid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={
                "text": "Do it.",
                "directedAt": cid,
                "approvedPlan": [
                    {"action": "speak", "actorId": cid, "register": "grave", "reason": "owed"},
                    {"action": "end"},
                ],
            },
        )
    )
    assert counter["planner"] == 0, "an approved plan must not be re-planned"
    assert [e for e in events if e.get("type") in PROSE], "the approved beat should have run"


def test_an_approved_beat_naming_someone_who_left_is_dropped(client, storyline_id, monkeypatch):
    """Presence can change between a plan being shown and it coming back."""
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, [], counter)
    scid, cid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={
                "text": "Do it.",
                "directedAt": cid,
                # A cast id that is not in this scene at all — the same shape as a character
                # written out between the plan and the approval.
                "approvedPlan": [{"action": "speak", "actorId": "c_ghost"}],
                "trace": True,
            },
        )
    )
    # Nothing the player approved could run, so the turn plans afresh rather than answering
    # them with silence — and says so, because that is a substitution, not their plan.
    stale = [
        e for e in events
        if e.get("type") == "trace" and e.get("data", {}).get("planner") == "stale"
    ]
    assert stale, "a plan that could not be run must say so"
    assert "out of date" in stale[0]["title"].lower()


def test_the_plan_frame_carries_the_session_so_the_approval_can_come_back(
    client, storyline_id, monkeypatch
):
    """Under `plan` the turn stops before any story event, and story events are the only
    other frames carrying a session id. Without this the client would have nothing to send
    the approval on, and every approved plan would open a SECOND session."""
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, [{"beats": [{"action": "speak", "actor": 1}]}], counter)
    scid, cid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Hi.", "directedAt": cid, "overrides": {"planner": "plan"}},
        )
    )
    plan = next(e for e in events if e.get("type") == "plan")
    assert plan["sessionId"], "the plan frame must name its session"
    # And it is a real session the approval can actually be sent on.
    assert client.get(f"/api/play/{scid}/sessions/{plan['sessionId']}").status_code == 200


def test_a_plan_is_not_a_story_event(client, storyline_id, monkeypatch):
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, [{"beats": [{"action": "speak", "actor": 1}]}], counter)
    scid, cid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Hi.", "directedAt": cid, "overrides": {"planner": "plan"}},
        )
    )
    plan = next(e for e in events if e.get("type") == "plan")
    assert "seq" not in plan and "id" not in plan
    # And it is genuinely outside the story-event union, not merely missing fields.
    try:
        story_event_adapter.validate_python(plan)
    except Exception:
        pass
    else:  # pragma: no cover - only reached if someone adds `plan` to the union
        raise AssertionError("a plan must not validate as a story event")

    # It is also not persisted: a reload must not find it in the session's history.
    history = client.get(f"/api/play/{scid}/sessions/{plan['sessionId']}").json()
    assert not [e for e in history["events"] if e["type"] == "plan"]


def test_auto_keeps_the_default_stream_unchanged(client, storyline_id, monkeypatch):
    """The plan frame is diagnostics under `auto`, so it is opt-in like `trace`.

    Emitting it unconditionally would insert a frame ahead of the first story event on EVERY
    turn, quietly changing the shape of the stream `docs/api-contract.md` documents and that
    every existing consumer indexes into.
    """
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}], counter)
    scid, cid = _scene(client, storyline_id)

    plain = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "Hi.", "directedAt": cid})
    )
    assert not [e for e in plain if e.get("type") == "plan"]

    counter["planner"] = 0
    _route(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}], counter)
    traced = _stream(
        client.post(
            f"/api/play/{scid}/turn", json={"text": "Again.", "directedAt": cid, "trace": True}
        )
    )
    assert [e for e in traced if e.get("type") == "plan"]


def test_the_legacy_planner_value_still_means_auto(client, storyline_id, monkeypatch):
    """`"planner"` is on scenario rows and in saved clients; it must not become `plan`."""
    _configure_llm(client)
    counter: dict = {}
    _route(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}], counter)
    scid, cid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Hi.", "directedAt": cid, "overrides": {"planner": "planner"}},
        )
    )
    # It played out rather than stopping for an approval nobody asked for.
    assert [e for e in events if e.get("type") in PROSE]
    assert not [e for e in events if e.get("type") == "plan"]
