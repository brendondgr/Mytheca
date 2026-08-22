"""POST /api/play/{scenarioId}/turn — the per-turn ``overrides`` envelope.

Scene settings a turn may change **for itself alone**. The proof this needs is not that
the override is read — the resolver's own tests cover that — but that it reaches every one
of its three destinations (the beat loop's cap, the assembler's beat length, the tail's
suggestion count) and that the ``Scenario`` row is **untouched** afterwards. A per-turn
control that quietly writes itself to the scene is the exact surprise this feature exists
to remove.

LLM is offline-mocked and routed by system prompt, mirroring ``test_play_turn.py``.
"""

from __future__ import annotations

import json
import re

import httpx

from app.agents import character_turn_agent
from app.services import llm


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _route(monkeypatch, decisions, *, branches=None, prompts=None):
    """Route by system prompt: planner → scripted decisions, branch → options, character →
    an emission echoing the prompt's speaker. ``prompts`` collects every user prompt sent,
    which is how the beat-length directive is observed without reaching into the assembler."""
    plan = iter(decisions)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if prompts is not None:
            prompts.append(user)
        if "You interpret" in system:
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "SITUATION-BASED follow-up" in system:
            return _resp(json.dumps({"choices": branches or []}))
        if "step-by-step loop" in system:
            try:
                return _resp(json.dumps(next(plan)))
            except StopIteration:
                return _resp(json.dumps({"action": "end"}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            return _resp("A hush falls over the room.")
        m = re.search(r"You are \[(\d+)\] (\w+)", user)
        num, name = (m.group(1), m.group(2)) if m else ("1", "Someone")
        return _resp(f'<speaker:{num}>\n"{name} speaks now."')

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _prose_count(events: list[dict]) -> int:
    """Distinct character beats, collapsing the delta chunks that share an id."""
    return len({e["id"] for e in events if e["type"] == "character_prose"})


def _scene(client, storyline_id, names=("Ana", "Bo", "Cy", "Di"), **scenario):
    ids = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in names
    ]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hall"}
    ).json()["id"]
    body = {"title": "Cap", "castIds": ids, "settingId": sid, **scenario}
    return client.post(f"/api/storylines/{storyline_id}/scenarios", json=body).json()["id"], ids


_FOUR_SPEAKERS = [
    {"action": "speak", "actor": 1},
    {"action": "speak", "actor": 2},
    {"action": "speak", "actor": 3},
    {"action": "speak", "actor": 4},
    {"action": "end"},
]


def test_max_turns_override_caps_the_turn_and_leaves_the_scene_alone(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _route(monkeypatch, _FOUR_SPEAKERS)
    scid, ids = _scene(client, storyline_id, maxTurns=5)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={
                "text": "I address the room.",
                "directedAt": ids[0],
                "overrides": {"maxTurns": 2},
            },
        )
    )

    assert _prose_count(events) == 2
    # The whole point: the scene is what it was before the turn.
    assert client.get(f"/api/scenarios/{scid}").json()["maxTurns"] == 5


def test_a_later_turn_without_the_override_is_back_to_the_scene(
    client, storyline_id, monkeypatch
):
    """The spring-back, proved from the server side: the override is spent, not sticky."""
    _configure_llm(client)
    _route(monkeypatch, _FOUR_SPEAKERS)
    scid, ids = _scene(client, storyline_id, maxTurns=4)

    first = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "One.", "directedAt": ids[0], "overrides": {"maxTurns": 1}},
        )
    )
    session_id = next(e["sessionId"] for e in first if e.get("sessionId"))
    # A fresh plan for the second turn. The scripted decisions are an iterator shared by
    # every planner call, and a capped turn does not consume all of them — reusing it would
    # make this assertion a test of how many the FIRST turn happened to take.
    _route(monkeypatch, _FOUR_SPEAKERS)
    second = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Two.", "directedAt": ids[0], "sessionId": session_id},
        )
    )

    assert _prose_count(first) == 1
    assert _prose_count(second) == 4


def test_beat_length_override_reaches_the_character_prompt(client, storyline_id, monkeypatch):
    """`ctx.beat_length` has two readers; the prompt directive is the one that is visible.

    Asserted against the tier's own directive text rather than "the prompts differ" — two
    turns differ anyway, in their history and their player line, so a difference proves
    nothing about the override.
    """
    _configure_llm(client)
    short_directive = character_turn_agent._BEAT_LENGTH_DIRECTIVES["short"]
    long_directive = character_turn_agent._BEAT_LENGTH_DIRECTIVES["long"]

    default_prompts: list[str] = []
    _route(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}], prompts=default_prompts)
    scid, ids = _scene(client, storyline_id, names=("Ana",), beatLength="short")

    client.post(f"/api/play/{scid}/turn", json={"text": "Hi.", "directedAt": ids[0]})
    assert any(short_directive in p for p in default_prompts)

    overridden: list[str] = []
    _route(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}], prompts=overridden)
    client.post(
        f"/api/play/{scid}/turn",
        json={"text": "Hi again.", "directedAt": ids[0], "overrides": {"beatLength": "long"}},
    )

    assert any(long_directive in p for p in overridden)
    assert not any(short_directive in p for p in overridden)
    assert client.get(f"/api/scenarios/{scid}").json()["beatLength"] == "short"


def test_zero_suggestions_override_suppresses_the_branch_event(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _route(
        monkeypatch,
        [{"action": "speak", "actor": 1}, {"action": "end"}],
        branches=[{"label": "Back off", "outcome": "de-escalate"}],
    )
    scid, ids = _scene(client, storyline_id, names=("Ana",), suggestionsCount=4)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "I press her.", "directedAt": ids[0], "overrides": {"suggestionsCount": 0}},
        )
    )

    assert all(e["type"] != "branch_choices" for e in events)
    assert client.get(f"/api/scenarios/{scid}").json()["suggestionsCount"] == 4


def test_the_user_turn_row_records_what_the_turn_ran_with(client, storyline_id, monkeypatch):
    """An override is spent when the turn ends, so the row is the only audit of it."""
    _configure_llm(client)
    _route(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}])
    scid, ids = _scene(client, storyline_id, names=("Ana",))

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={
                "text": "I press her.",
                "directedAt": ids[0],
                "overrides": {"maxTurns": 1, "suggestionsCount": 0},
            },
        )
    )
    session_id = next(e["sessionId"] for e in events if e.get("sessionId"))
    history = client.get(f"/api/play/{scid}/sessions/{session_id}").json()
    row = next(e for e in history["events"] if e["type"] == "user_turn")

    assert row["data"]["overrides"] == {"maxTurns": 1, "suggestionsCount": 0}


def test_a_turn_with_no_overrides_writes_no_key(client, storyline_id, monkeypatch):
    """Absent, not empty — an `overrides: {}` on every row is noise in the export."""
    _configure_llm(client)
    _route(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}])
    scid, ids = _scene(client, storyline_id, names=("Ana",))

    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "Hi.", "directedAt": ids[0]})
    )
    session_id = next(e["sessionId"] for e in events if e.get("sessionId"))
    history = client.get(f"/api/play/{scid}/sessions/{session_id}").json()
    row = next(e for e in history["events"] if e["type"] == "user_turn")

    assert "overrides" not in row["data"]


def test_an_out_of_range_override_is_rejected_at_the_boundary(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _route(monkeypatch, [{"action": "end"}])
    scid, ids = _scene(client, storyline_id, names=("Ana",))

    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "Hi.", "directedAt": ids[0], "overrides": {"maxTurns": 99}},
    )

    assert resp.status_code == 422


def test_a_pinned_register_is_credited_on_the_speaker_step(client, storyline_id, monkeypatch):
    """The register control invites the question "did my pin reach this beat?", and the
    Inspector answers it from this field."""
    _configure_llm(client)
    _route(monkeypatch, [{"action": "speak", "actor": 1, "register": "light"}, {"action": "end"}])
    scid, ids = _scene(client, storyline_id, names=("Ana",))

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={
                "text": "I press her.",
                "directedAt": ids[0],
                "trace": True,
                "overrides": {"register": "grave"},
            },
        )
    )
    speaker = next(e for e in events if e["type"] == "trace" and e["step"] == "speaker")

    assert speaker["data"]["register"] == "grave"
    assert speaker["data"]["registerSource"] == "player"


def test_the_register_rides_on_the_user_turn_row_like_any_override(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _route(monkeypatch, [{"action": "speak", "actor": 1}, {"action": "end"}])
    scid, ids = _scene(client, storyline_id, names=("Ana",))

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Hi.", "directedAt": ids[0], "overrides": {"register": "tense"}},
        )
    )
    session_id = next(e["sessionId"] for e in events if e.get("sessionId"))
    history = client.get(f"/api/play/{scid}/sessions/{session_id}").json()
    row = next(e for e in history["events"] if e["type"] == "user_turn")

    assert row["data"]["overrides"] == {"register": "tense"}


def test_an_unknown_register_is_rejected_at_the_boundary(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _route(monkeypatch, [{"action": "end"}])
    scid, ids = _scene(client, storyline_id, names=("Ana",))

    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "Hi.", "directedAt": ids[0], "overrides": {"register": "apocalyptic"}},
    )

    assert resp.status_code == 422
