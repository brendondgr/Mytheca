"""Scene direction — requirement parsing, roster binding, rebinding, and the budget packer."""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import direction_agent, intent_agent
from app.agents.direction_agent import DirectionRequirement, SceneDirection
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


def _reqs(*specs: tuple[str, str | None]) -> list[DirectionRequirement]:
    return [
        DirectionRequirement(id=f"req{i + 1}", text=t, actor_id=a)
        for i, (t, a) in enumerate(specs)
    ]


# ---- parse -----------------------------------------------------------------


def test_parse_binds_requirements_to_the_roster(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps(
            {
                "requirements": [
                    {"actor": 2, "must": "Mei storms out"},
                    {"actor": None, "must": "the lamp goes over"},
                ]
            }
        ),
    )
    direction = direction_agent.parse(
        db_session, _ctx(_cast("beth", "mei")), "Mei storms out and the lamp goes over"
    )
    assert direction.active
    assert [(r.text, r.actor_id) for r in direction.requirements] == [
        ("Mei storms out", "mei"),
        ("the lamp goes over", None),
    ]
    assert direction.text == "Mei storms out and the lamp goes over"


def test_parse_drops_out_of_roster_actor_to_the_narrator(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"requirements": [{"actor": 9, "must": "the door slams"}]}))
    direction = direction_agent.parse(db_session, _ctx(_cast("beth")), "the door slams")
    assert direction.requirements[0].actor_id is None


def test_parse_caps_the_requirement_count(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps({"requirements": [{"actor": None, "must": f"thing {i}"} for i in range(20)]}),
    )
    direction = direction_agent.parse(db_session, _ctx(_cast("beth")), "lots happens")
    assert len(direction.requirements) == direction_agent.MAX_REQUIREMENTS


def test_malformed_reply_keeps_the_whole_guidance(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, "not json at all")
    direction = direction_agent.parse(db_session, _ctx(_cast("beth")), "things get worse")
    assert [(r.text, r.actor_id) for r in direction.requirements] == [("things get worse", None)]


def test_empty_requirement_list_keeps_the_whole_guidance(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"requirements": []}))
    direction = direction_agent.parse(db_session, _ctx(_cast("beth")), "things get worse")
    assert [r.text for r in direction.requirements] == ["things get worse"]


def test_unconfigured_llm_keeps_the_whole_guidance(db_session):
    direction = direction_agent.parse(db_session, _ctx(_cast("beth")), "things get worse")
    assert [r.text for r in direction.requirements] == ["things get worse"]


def test_blank_guidance_is_no_direction(db_session):
    direction = direction_agent.parse(db_session, _ctx(_cast("beth")), "   ")
    assert not direction.active and direction.requirements == []


# ---- the intent agent extracts the same shape ------------------------------


def test_intent_carries_requirements_from_the_same_call(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(
        monkeypatch,
        json.dumps(
            {
                "kind": "narration",
                "directive": "the argument boils over",
                "requirements": [{"actor": 1, "must": "Beth raises her voice"}],
            }
        ),
    )
    intent = intent_agent.interpret(
        db_session, _ctx(_cast("beth", "mei")), "the argument boils over"
    )
    assert [(r.text, r.actor_id) for r in intent.requirements] == [
        ("Beth raises her voice", "beth")
    ]


def test_intent_without_requirements_is_unchanged(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch(monkeypatch, json.dumps({"kind": "freeform", "directive": "hello"}))
    intent = intent_agent.interpret(db_session, _ctx(_cast("beth")), "hello")
    assert intent.requirements == []


# ---- SceneDirection bookkeeping --------------------------------------------


def test_rebind_moves_absent_and_pov_owners_to_the_narrator():
    direction = SceneDirection(
        text="x", requirements=_reqs(("a acts", "a"), ("b acts", "b"), ("c acts", "c"))
    )
    direction.rebind(present_ids={"a", "b"}, locked_id="b")
    assert [r.actor_id for r in direction.requirements] == ["a", None, None]


def test_outstanding_and_satisfy():
    direction = SceneDirection(text="x", requirements=_reqs(("one", "a"), ("two", None)))
    direction.satisfy(direction.for_actor("a"))
    assert [r.text for r in direction.outstanding()] == ["two"]
    assert direction.summary() == ["✓ one", "• two"]


# ---- schedule --------------------------------------------------------------


def test_schedule_returns_none_when_nothing_is_owed():
    assert direction_agent.schedule([], remaining=3) is None


def test_schedule_drives_one_requirement_per_beat_when_the_budget_fits():
    outstanding = _reqs(("one", "a"), ("two", "b"))
    beat = direction_agent.schedule(outstanding, remaining=2)
    assert beat is not None and beat.actor_id == "a"
    assert [r.text for r in beat.requirements] == ["one"]


def test_schedule_bundles_same_owner_requirements_when_the_budget_is_short():
    outstanding = _reqs(("one", "a"), ("two", "a"), ("three", "b"))
    beat = direction_agent.schedule(outstanding, remaining=2)
    assert beat is not None and beat.actor_id == "a"
    assert [r.text for r in beat.requirements] == ["one", "two"]


def test_schedule_never_bundles_across_owners():
    outstanding = _reqs(("one", "a"), ("two", "b"), ("three", "c"))
    beat = direction_agent.schedule(outstanding, remaining=2)
    # Two beats left, three owed by three different people — only "a"'s can ride together,
    # so the beat carries just theirs and the last beat collapses to narration (below).
    assert beat is not None and beat.actor_id == "a"
    assert [r.text for r in beat.requirements] == ["one"]


def test_last_beat_with_several_owed_collapses_to_narration():
    outstanding = _reqs(("one", "a"), ("two", "b"))
    beat = direction_agent.schedule(outstanding, remaining=1)
    assert beat is not None and beat.actor_id is None
    assert [r.text for r in beat.requirements] == ["one", "two"]


def test_last_beat_with_one_owed_still_goes_to_its_owner():
    beat = direction_agent.schedule(_reqs(("one", "a")), remaining=1)
    assert beat is not None and beat.actor_id == "a"


def test_schedule_survives_an_exhausted_budget():
    beat = direction_agent.schedule(_reqs(("one", "a"), ("two", "b")), remaining=0)
    assert beat is not None and beat.actor_id is None and len(beat.requirements) == 2
