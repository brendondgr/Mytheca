"""ReAct planner — next-beat parse (speak/narrate/end), roster-constrained, fallback."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import planner_agent
from app.agents.direction_agent import DirectionRequirement, SceneDirection
from app.agents.intent_agent import TurnIntent
from app.models import Scenario
from app.services import assembler, llm, llm_backend


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _patch(monkeypatch, content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _cast(*ids: str) -> list[assembler.CastMember]:
    return [
        assembler.CastMember(id=i, name=i.title(), role="X", traits="", speech="", color="#000", stats={})
        for i in ids
    ]


def _ctx(cast) -> assembler.TurnContext:
    return assembler.TurnContext(
        scenario=Scenario(storyline_id="e", title="S", cast_ids=[c.id for c in cast], setting_id=""),
        session_id="ps1",
        storyline_id="e",
        directed_at=None,
        cast=cast,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[],
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer=None,
        stable_prefix="",
    )


def test_speak_resolves_actor_and_addressing(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "speak", "actor": 2, "addressing": 1, "reason": "provoked"}))
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [])
    assert d.action == "speak" and d.actor_id == "kira" and d.addressing_id == "mei"
    assert d.reason == "provoked"


def test_narrate_action(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "narrate", "reason": "set the scene"}))
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei")), TurnIntent(), [], [])
    assert d.action == "narrate"


def test_end_carries_needs_branch(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "end", "needsBranch": True}))
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [])
    assert d.action == "end" and d.needs_branch is True


def test_out_of_roster_actor_falls_back(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "speak", "actor": 9}))
    # freeform intent, nothing acted → the fallback opens with the first cast member.
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [])
    assert d.action == "speak" and d.actor_id == "mei"


def test_broadcast_fallback_walks_the_cast(db_session):
    # No LLM configured → the fallback honors scope=all, picking the next un-acted member.
    ctx = _ctx(_cast("a", "b", "c"))
    intent = TurnIntent(kind="broadcast", scope="all")
    assert planner_agent.next_beat(db_session, ctx, intent, [], []).actor_id == "a"
    assert planner_agent.next_beat(db_session, ctx, intent, [], ["a"]).actor_id == "b"
    assert planner_agent.next_beat(db_session, ctx, intent, [], ["a", "b"]).actor_id == "c"
    assert planner_agent.next_beat(db_session, ctx, intent, [], ["a", "b", "c"]).action == "end"


def test_addressed_fallback_reacts_then_ends(db_session):
    ctx = _ctx(_cast("mei", "kira"))
    intent = TurnIntent(kind="direct", addressed=["kira"])
    assert planner_agent.next_beat(db_session, ctx, intent, [], []).actor_id == "kira"
    # once the addressed character has acted, the direction is satisfied.
    assert planner_agent.next_beat(db_session, ctx, intent, [], ["kira"]).action == "end"


def test_scene_opening_freeform_does_not_force_a_speaker(db_session):
    # Cold open + freeform (no LLM → fallback): the narrator opens the scene (engine), so
    # the planner does NOT force a character. Mid-scene freeform still gets a responder.
    ctx = _ctx(_cast("mei", "kira"))
    intent = TurnIntent()  # freeform
    assert planner_agent.next_beat(db_session, ctx, intent, [], [], scene_opening=True).action == "end"
    assert (
        planner_agent.next_beat(db_session, ctx, intent, [], [], scene_opening=False).actor_id == "mei"
    )


def test_scene_opening_still_honors_a_directed_character(db_session):
    # Even at a cold open, an explicitly addressed character reacts (the player directed them).
    ctx = _ctx(_cast("mei", "kira"))
    intent = TurnIntent(kind="direct", addressed=["kira"])
    assert (
        planner_agent.next_beat(db_session, ctx, intent, [], [], scene_opening=True).actor_id == "kira"
    )


def test_no_cast_ends(db_session):
    assert planner_agent.next_beat(db_session, _ctx([]), TurnIntent(), [], []).action == "end"


def test_malformed_reply_falls_back(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, "not json at all")
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei")), TurnIntent(), [], [])
    assert d.action == "speak" and d.actor_id == "mei"  # opening fallback


def test_system_biases_narration_to_progress(client, db_session, monkeypatch):
    # The planner leans on narration to PROGRESS the scene; a character speaks only after
    # the scene has moved and has a real POV reaction — not every beat (fix for over-talking).
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        seen["system"] = json.loads(request.content.decode())["messages"][0]["content"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"action": "end"})}}]}
        )

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    _configure_llm(client)
    planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [])
    system = seen["system"]
    assert "DEFAULT for carrying the scene" in system  # narrate-to-progress is the default
    assert "PROGRESS the story to the next beat" in system
    assert "over-talking" in system  # dialogue only after movement, not every beat


def _present(*ids: str, absent: dict[str, str] | None = None) -> list[assembler.CastMember]:
    """Cast members, optionally with a non-``present`` status (id → status)."""
    absent = absent or {}
    return [
        assembler.CastMember(
            id=i, name=i.title(), role="X", traits="", speech="", color="#000",
            stats={}, presence=absent.get(i, "present"),
        )
        for i in ids
    ]


def test_exit_resolves_actor_and_status(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "exit", "actor": 1, "status": "dead", "reason": "cut down"}))
    d = planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [])
    assert d.action == "exit" and d.actor_id == "mei" and d.status == "dead"


def test_exit_with_bad_status_falls_back(client, db_session, monkeypatch):
    # "exit" without a valid status must not guess a removal — it falls back instead.
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "exit", "actor": 1, "status": "vaporized"}))
    d = planner_agent.next_beat(
        db_session, _ctx(_cast("mei")), TurnIntent(kind="direct", addressed=["mei"]), [], []
    )
    assert d.action != "exit"


def test_non_present_member_never_selected(client, db_session, monkeypatch):
    # Mei is dead → roster lists only Kira as [1]; the planner can't pick Mei.
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "speak", "actor": 1, "reason": "reacts"}))
    ctx = _ctx(_present("mei", "kira", absent={"mei": "dead"}))
    d = planner_agent.next_beat(db_session, ctx, TurnIntent(), [], [])
    assert d.action == "speak" and d.actor_id == "kira"


def test_present_only_roster_in_prompt(client, db_session, monkeypatch):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        seen["user"] = json.loads(request.content.decode())["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"action": "end"})}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    _configure_llm(client)
    ctx = _ctx(_present("mei", "kira", absent={"mei": "left"}))
    planner_agent.next_beat(db_session, ctx, TurnIntent(), [], [])
    assert "Kira" in seen["user"] and "Mei" not in seen["user"]  # departed member off the roster


def test_all_absent_ends(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"action": "speak", "actor": 1}))
    ctx = _ctx(_present("mei", "kira", absent={"mei": "dead", "kira": "left"}))
    d = planner_agent.next_beat(db_session, ctx, TurnIntent(scope="all"), [], [])
    assert d.action == "end"


def test_fallback_skips_non_present(db_session):
    # No LLM configured → fallback path; a whole-group direction walks only present members.
    ctx = _ctx(_present("mei", "kira", absent={"mei": "unconscious"}))
    d = planner_agent.next_beat(db_session, ctx, TurnIntent(scope="all"), [], [])
    assert d.action == "speak" and d.actor_id == "kira"


# ---- The scene direction (Narrator-Guided Scenes) --------------------------


def _direction(*specs):
    return SceneDirection(
        text="something happens",
        requirements=[
            DirectionRequirement(id=f"req{i + 1}", text=t, actor_id=a)
            for i, (t, a) in enumerate(specs)
        ],
    )


def test_outstanding_direction_reaches_the_prompt_with_the_budget(client, db_session, monkeypatch):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        seen["user"] = json.loads(request.content.decode())["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"action": "end"})}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    _configure_llm(client)
    direction = _direction(("Kira laughs", "kira"), ("the door slams", None))
    planner_agent.next_beat(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [],
        direction=direction, remaining_beats=3,
    )
    assert "Still to deliver" in seen["user"]
    assert "[2]: Kira laughs" in seen["user"] and "narrator: the door slams" in seen["user"]
    assert "3 beat(s) left in this turn" in seen["user"]


def test_a_delivered_direction_says_so(client, db_session, monkeypatch):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        seen["user"] = json.loads(request.content.decode())["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"action": "end"})}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    _configure_llm(client)
    direction = _direction(("Kira laughs", "kira"))
    direction.satisfy(direction.requirements)
    planner_agent.next_beat(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [], direction=direction
    )
    assert "fully delivered" in seen["user"] and "Still to deliver" not in seen["user"]


def test_no_direction_leaves_the_prompt_untouched(client, db_session, monkeypatch):
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        seen["user"] = json.loads(request.content.decode())["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"action": "end"})}}]})

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    _configure_llm(client)
    planner_agent.next_beat(db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [])
    assert "Still to deliver" not in seen["user"] and "delivered" not in seen["user"]


def test_offline_fallback_still_honors_the_direction(db_session):
    # No LLM configured → the fallback path. What the player is owed outranks the heuristics.
    d = planner_agent.next_beat(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [],
        direction=_direction(("Kira laughs", "kira")),
    )
    assert d.action == "speak" and d.actor_id == "kira"


def test_offline_fallback_narrates_a_narrator_owned_requirement(db_session):
    d = planner_agent.next_beat(
        db_session, _ctx(_cast("mei", "kira")), TurnIntent(), [], [],
        direction=_direction(("the door slams", None)),
    )
    assert d.action == "narrate"


def test_offline_fallback_skips_a_requirement_whose_owner_left(db_session):
    ctx = _ctx(_present("mei", "kira", absent={"kira": "left"}))
    d = planner_agent.next_beat(
        db_session, ctx, TurnIntent(), [], [],
        direction=_direction(("Kira laughs", "kira"), ("Mei flinches", "mei")),
    )
    assert d.action == "speak" and d.actor_id == "mei"
