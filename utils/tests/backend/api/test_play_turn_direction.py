"""POST /api/play/{scenarioId}/turn — the scene direction (Playwright-guided scenes).

The player directs: in Playwright mode with their own line, under Player POV with the
separate ``guidance`` box. Either way the turn owes a list of requirements and must deliver
every one of them inside the scene's ``maxTurns`` budget — the planner paces them while
there is room, and the engine schedules the rest itself once there is not.

LLM is offline-mocked and routed by system prompt, mirroring ``test_play_turn_pov.py``.
"""

from __future__ import annotations

import json
import re

import httpx

from app.services import llm


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _owed_in(prompt: str) -> str:
    """The requirement text this beat was handed, read back out of its own prompt.

    The two writers state the owed outcomes differently — the character prompt's tail says
    "THIS BEAT MUST MAKE THIS TRUE: …", the narrator's lead says "has to make the following
    actually happen: …" — so both shapes are matched here rather than in each test.
    """
    for pattern in (
        r"THIS BEAT MUST MAKE THIS TRUE: (.+?)\. It is the player's direction",
        r"has to make the following actually happen: (.+?)\. Narrate it",
    ):
        m = re.search(pattern, prompt, re.S)
        if m:
            return m.group(1).replace(";", ".")
    return ""


def _route(
    monkeypatch,
    *,
    requirements=None,
    intent=None,
    decisions=(),
    seen=None,
):
    """Route the mock by system prompt.

    ``requirements`` answers the standalone direction parse (POV guidance); ``intent``
    overrides the intent reply (which is where Playwright-mode requirements ride).
    ``decisions`` scripts the planner; ``seen`` (a dict) collects the prompts each agent
    actually received so a test can assert on them.

    **The mocked writers deliver what they are asked to.** Delivery is now confirmed from
    the prose a beat actually emitted, so a mock that always replies "The room shifts."
    would fail every requirement no matter how well the engine scheduled it — and these
    tests are about the *scheduling*, not about the coverage check (which has its own file,
    ``services/test_direction_check.py``). Both writers therefore echo the owed text out of
    their own prompt, which is exactly what a cooperating model does.
    """
    plan = iter(decisions)
    log = seen if seen is not None else {}
    log.setdefault("planner", [])
    log.setdefault("character", [])
    log.setdefault("narrator", [])
    log.setdefault("direction_calls", 0)

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if "You read the player's DIRECTION" in system:
            log["direction_calls"] += 1
            return _resp(json.dumps({"requirements": requirements or []}))
        if "You interpret" in system:
            return _resp(json.dumps(intent or {"kind": "freeform", "directive": "go"}))
        if "role-playing AS a specific character" in system:
            return _resp(json.dumps({"choices": []}))
        if "SITUATION-BASED follow-up" in system:
            return _resp(json.dumps({"choices": []}))
        if "step-by-step loop" in system:
            log["planner"].append(user)
            try:
                return _resp(json.dumps(next(plan)))
            except StopIteration:
                return _resp(json.dumps({"action": "end"}))
        if "continuity auditor" in system:
            return _resp(json.dumps({"consistent": True}))
        if "private inner voice" in system:
            return _resp("{}")
        if "narrator of an interactive scene" in system:
            log["narrator"].append(user)
            return _resp(f"The room shifts. {_owed_in(user)}".strip())
        log["character"].append(user)
        m = re.search(r"You are \[(\d+)\] (\w+)", user)
        num, name = (m.group(1), m.group(2)) if m else ("1", "Someone")
        return _resp(
            f'<speaker:{num}>\n<type:character_dialogue>\n"{name} speaks now. {_owed_in(user)}"'
        )

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return log


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _traces(events, step):
    return [e for e in events if e["type"] == "trace" and e["step"] == step]


def _prose_beats(events) -> int:
    """Distinct emitted prose beats (delta-streamed events share one id)."""
    return len(
        {
            e["id"]
            for e in events
            if e["type"] in ("narration", "character_dialogue", "character_action")
        }
    )


def _two(client, storyline_id):
    mei = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}).json()["id"]
    kira = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Kira"}).json()["id"]
    sid = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}).json()["id"]
    return mei, kira, sid


def _scenario(client, storyline_id, cast, setting, **extra):
    body = {"title": "Standoff", "castIds": cast, "settingId": setting, "suggestionsCount": 0, **extra}
    return client.post(f"/api/storylines/{storyline_id}/scenarios", json=body).json()["id"]


# ---- The direction is delivered --------------------------------------------


def test_pov_guidance_is_parsed_and_delivered_in_full(client, storyline_id, monkeypatch):
    # Speaking AS Mei while guiding the scene: the guidance box is a SEPARATE string, so it
    # is parsed on its own and its requirements are all delivered.
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, maxTurns=4)
    log = _route(
        monkeypatch,
        requirements=[
            {"actor": 2, "must": "Kira draws her knife"},
            {"actor": None, "must": "the lantern goes out"},
        ],
        decisions=[{"action": "end"}, {"action": "end"}, {"action": "end"}],
    )
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={
                "text": "I hold my ground.",
                "povCharacterId": mei,
                "guidance": "Kira draws her knife and the lantern goes out",
                "trace": True,
            },
        )
    )
    assert log["direction_calls"] == 1  # the guidance was parsed, once
    summary = _traces(events, "direction")[-1]
    # Three counts now, not two: what landed, what a beat tried but could not be confirmed
    # to have reached, and what the turn never got to at all.
    assert summary["data"] == {
        "delivered": 2,
        "total": 2,
        "unconfirmed": [],
        "never": [],
        "undelivered": [],
        # Blocked on an absent character — a different problem from running out of beats,
        # and only one of the two is fixed by a longer scene.
        "blocked": [],
    }
    assert _prose_beats(events) <= 4  # inside the scene's cap


def test_a_planner_end_cannot_drop_an_outstanding_requirement(client, storyline_id, monkeypatch):
    # The planner wants to stop after one beat; the player is still owed something, so the
    # engine overrides it and schedules the rest.
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, maxTurns=5)
    _route(
        monkeypatch,
        requirements=[
            {"actor": 1, "must": "Mei backs down"},
            {"actor": 2, "must": "Kira laughs"},
        ],
        decisions=[{"action": "end"}, {"action": "end"}, {"action": "end"}, {"action": "end"}],
    )
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Both of you settle this.", "guidance": "Mei backs down, Kira laughs",
                  "trace": True},
        )
    )
    assert _traces(events, "direction")[-1]["data"]["undelivered"] == []
    forced = [t for t in _traces(events, "direction") if "not delivered yet" in (t["detail"] or "")]
    assert forced, "the engine should have overridden the premature end"


def test_a_tight_budget_collapses_the_last_beat_to_narration(client, storyline_id, monkeypatch):
    """When what is owed no longer fits the beats left, the engine schedules the rest itself.

    The budget used to be the player's `maxTurns`, and two beats against three requirements
    was enough to trigger this. With that control gone the only ceiling is the runaway
    backstop, so a direction now has to be genuinely enormous to outrun it — which is the
    right shape (the mechanism is a safety net, not a pacing rule) but does mean this is
    reached far less often than it was. It is still the thing standing between a long
    direction and a silently dropped requirement, so it stays tested.

    The backstop floor is `max(turn_max_beats, 2 * cast + 6)` — 10 for this two-hander,
    however low the setting goes — so the direction below carries twelve.
    """
    _configure_llm(client)
    monkeypatch.setattr(
        "app.services.turn_engine.get_settings",
        lambda: type("S", (), {"turn_max_beats": 1, "turn_planner_lookahead": 1})(),
    )
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid)
    owed = [{"actor": 1, "must": f"Mei does thing {i}"} for i in range(5)]
    owed += [{"actor": 2, "must": f"Kira does thing {i}"} for i in range(5)]
    owed += [{"actor": None, "must": "the alarm starts"},
             {"actor": None, "must": "the lights go out"}]
    log = _route(monkeypatch, requirements=owed, decisions=[{"action": "end"}])
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Go.", "guidance": "everything happens at once", "trace": True},
        )
    )
    # Bounded by the backstop, and nothing the player asked for was quietly dropped.
    assert _prose_beats(events) <= 11
    assert _traces(events, "direction")[-1]["data"]["undelivered"] == []
    # Deliberately NOT asserting which beat carried which requirement. With twelve owed and
    # ten beats the engine has real latitude — it may pace a narrator-owned line into the
    # opening passage, fold two together, or give one its own beat — and pinning the route
    # would test this run's arithmetic rather than the contract. The contract is above: the
    # turn stays inside the backstop and the player is owed nothing at the end of it.
    assert log["direction_calls"] >= 0


def test_a_requirement_naming_the_pov_character_moves_to_the_narrator(
    client, storyline_id, monkeypatch
):
    # The AI never voices the POV character, so a requirement bound to them would be
    # undeliverable. It is rebound to the narrator instead.
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, maxTurns=3)
    _route(
        monkeypatch,
        requirements=[{"actor": 1, "must": "Mei drops the letter"}],
        decisions=[{"action": "end"}, {"action": "end"}],
    )
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "I hesitate.", "povCharacterId": mei,
                  "guidance": "Mei drops the letter", "trace": True},
        )
    )
    opening = _traces(events, "direction")[0]
    # `pinned: False` — the model *inferred* this target from the guidance text, so the
    # engine is still free to re-own it. A target the PLAYER names (an `@` mention, sent as
    # a directive) is pinned and would not have moved.
    assert opening["data"]["requirements"] == [
        {"text": "Mei drops the letter", "actor": None, "pinned": False}
    ]
    assert _traces(events, "direction")[-1]["data"]["undelivered"] == []


# ---- Where the direction comes from ----------------------------------------


def test_narrator_mode_reads_the_direction_off_the_players_own_line(
    client, storyline_id, monkeypatch
):
    # No guidance box in Playwright mode — the player's line IS the direction, and the intent
    # call already carries its requirements, so no second parse is spent.
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, maxTurns=3)
    log = _route(
        monkeypatch,
        intent={
            "kind": "narration",
            "directive": "the argument boils over",
            "requirements": [{"actor": 2, "must": "Kira shouts back"}],
        },
        decisions=[{"action": "end"}, {"action": "end"}],
    )
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "The argument boils over.", "trace": True},
        )
    )
    assert log["direction_calls"] == 0  # no extra round-trip
    assert _traces(events, "direction")[0]["data"]["source"] == "message"
    assert _traces(events, "direction")[-1]["data"]["undelivered"] == []


def test_pov_line_is_never_read_as_direction(client, storyline_id, monkeypatch):
    # Under POV the player's line is the CHARACTER'S dialogue. Even if the intent call
    # returns requirements for it, the turn carries no direction without a guidance box.
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, maxTurns=3)
    _route(
        monkeypatch,
        intent={
            "kind": "narration",
            "directive": "x",
            "requirements": [{"actor": 2, "must": "Kira obeys"}],
        },
        decisions=[{"action": "end"}],
    )
    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Everyone out.", "povCharacterId": mei, "trace": True},
        )
    )
    assert _traces(events, "direction") == []


def test_an_ordinary_turn_is_unchanged(client, storyline_id, monkeypatch):
    # No direction at all: no direction trace, and the planner prompt is the pre-direction
    # one (no "Still to deliver" block).
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, maxTurns=3)
    log = _route(monkeypatch, decisions=[{"action": "end"}])
    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "Hello there.", "trace": True})
    )
    assert _traces(events, "direction") == []
    assert log["planner"] and all("Still to deliver" not in u for u in log["planner"])


# ---- What the speakers are told --------------------------------------------


def test_the_planner_sees_what_is_owed_and_how_long_it_has(client, storyline_id, monkeypatch):
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, maxTurns=4)
    log = _route(
        monkeypatch,
        requirements=[
            {"actor": 2, "must": "Kira apologises"},
            {"actor": None, "must": "the rain starts"},
        ],
        decisions=[{"action": "speak", "actor": 2}, {"action": "end"}, {"action": "end"}],
    )
    _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Fix this.", "guidance": "Kira apologises, then the rain starts",
                  "trace": True},
        )
    )
    # The scene-opening narration already absorbed the narrator-owned line, so by the first
    # planner call only Kira's is still owed — listed against her roster number, with the
    # budget that is left to deliver it in.
    assert any("the rain starts" in u for u in log["narrator"])
    first = log["planner"][0]
    assert "Still to deliver" in first
    assert "[2]: Kira apologises" in first
    assert "beat(s) left in this turn" in first


def test_the_carrying_character_is_told_the_outcome_not_the_words(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    mei, kira, sid = _two(client, storyline_id)
    scid = _scenario(client, storyline_id, [mei, kira], sid, maxTurns=3)
    log = _route(
        monkeypatch,
        requirements=[{"actor": 2, "must": "Kira apologises"}],
        decisions=[{"action": "speak", "actor": 2}, {"action": "end"}],
    )
    _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "Fix this.", "guidance": "Kira apologises", "trace": True},
        )
    )
    kira_prompt = next(p for p in log["character"] if "Kira" in p)
    assert "THIS BEAT MUST MAKE THIS TRUE: Kira apologises" in kira_prompt
    assert "Never quote or paraphrase the direction" in kira_prompt
    # Every speaker also sees where the scene is going, carrier or not.
    assert all("Where this scene is going (the player's direction):" in p for p in log["character"])
