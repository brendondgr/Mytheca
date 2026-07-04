"""Phase 3 — resolved writing prompts flow through TurnContext into the four agents.

Covers both ends: the assembler folds global → storyline → scenario into ``ctx.prompts``,
and each writing agent sends the resolved system message (falling back to its default).
"""

from __future__ import annotations

import httpx
import pytest

from app.agents import (
    character_turn_agent,
    director_agent,
    narrator_agent,
    planner_agent,
    prompt_registry,
)
from app.agents.intent_agent import TurnIntent
from app.models import Scenario
from app.schemas.scenario import ScenarioCreate
from app.schemas.settings import LlmConfigUpdate
from app.schemas.storyline import StorylineCreate
from app.services import assembler, crud, llm, llm_backend, settings_store


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


# ---- assembler resolution (global → storyline → scenario) ------------------


def test_assemble_context_folds_all_three_layers(db_session):
    settings_store.update_llm(db_session, LlmConfigUpdate())  # no-op, ensures store exists
    settings_store.set_prompts_overrides(
        db_session,
        {
            prompt_registry.DIRECTOR_WHO_IS_UP: "GLOBAL who's-up",
            prompt_registry.PLANNER_SYSTEM: "GLOBAL planner",
        },
    )
    crud.create_storyline(
        db_session,
        StorylineCreate(
            id="w",
            title="W",
            prompt_overrides={prompt_registry.PLANNER_SYSTEM: "STORYLINE planner"},
        ),
    )
    scenario = crud.create_scenario(
        db_session,
        "w",
        ScenarioCreate(
            title="Scene",
            prompt_overrides={prompt_registry.NARRATOR_SYSTEM: "SCENARIO narrator"},
        ),
    )

    ctx = assembler.assemble_context(db_session, scenario, "sess1")

    # scenario layer wins for its key
    assert ctx.prompts[prompt_registry.NARRATOR_SYSTEM] == "SCENARIO narrator"
    # storyline beats global for the planner key
    assert ctx.prompts[prompt_registry.PLANNER_SYSTEM] == "STORYLINE planner"
    # global beats default where neither storyline nor scenario overrides
    assert ctx.prompts[prompt_registry.DIRECTOR_WHO_IS_UP] == "GLOBAL who's-up"
    # untouched key falls through to the registry default
    assert ctx.prompts[prompt_registry.DIRECTOR_RERANK] == prompt_registry.default(
        prompt_registry.DIRECTOR_RERANK
    )


# ---- per-agent threading ----------------------------------------------------

_CAPTURED: list[list[dict]] = []


@pytest.fixture
def capture_llm(db_session, monkeypatch):
    """Configure the LLM + record every outgoing chat message list."""
    settings_store.update_llm(
        db_session,
        LlmConfigUpdate(base_url="http://localhost:7070/v1", model="m", api_key="sk-t"),
    )
    _CAPTURED.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            import json

            _CAPTURED.append(json.loads(request.content)["messages"])
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"speakers":[1]}'}}]})
        return httpx.Response(404)

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return db_session


def _cast(*ids: str) -> list[assembler.CastMember]:
    return [
        assembler.CastMember(
            id=i, name=i.title(), role="X", traits="", speech="", color="#000", stats={}, recent_lines=[]
        )
        for i in ids
    ]


def _ctx(cast, prompts):
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
        prompts=prompts,
    )


def _last_system() -> str:
    return _CAPTURED[-1][0]["content"]


def test_character_agent_uses_resolved_contract(capture_llm):
    ctx = _ctx(_cast("a"), {prompt_registry.CHARACTER_OUTPUT_CONTRACT: "CUSTOM CONTRACT"})
    character_turn_agent.generate_line(capture_llm, ctx, ctx.cast[0], turn_beats=[])
    assert _last_system().startswith("CUSTOM CONTRACT")


def test_narrator_agent_selects_short_vs_long_override(capture_llm):
    ctx = _ctx(
        _cast("a"),
        {
            prompt_registry.NARRATOR_SYSTEM: "SHORT NARR",
            prompt_registry.NARRATOR_SYSTEM_LONG: "LONG NARR",
        },
    )
    narrator_agent.interstitial(capture_llm, ctx, [], long=False)
    assert _last_system().startswith("SHORT NARR")
    narrator_agent.interstitial(capture_llm, ctx, [], long=True)
    assert _last_system().startswith("LONG NARR")


def test_director_who_is_up_uses_override(capture_llm):
    # 2+ cast, no directed_at → escalates to the reasoned (LLM) decision.
    ctx = _ctx(_cast("a", "b"), {prompt_registry.DIRECTOR_WHO_IS_UP: "CUSTOM DIRECTOR"})
    director_agent.who_is_up(capture_llm, ctx)
    assert _last_system() == "CUSTOM DIRECTOR"


def test_director_rerank_and_branch_use_overrides(capture_llm):
    ctx = _ctx(
        _cast("a", "b"),
        {
            prompt_registry.DIRECTOR_RERANK: "CUSTOM RERANK",
            prompt_registry.DIRECTOR_BRANCH: "CUSTOM BRANCH",
        },
    )
    director_agent.rerank(capture_llm, ctx, ["a", "b"], [{"role": "player", "text": "hi"}])
    assert _last_system() == "CUSTOM RERANK"
    director_agent.propose_branches(capture_llm, ctx, [{"role": "character", "text": "yo"}], count=2)
    assert _last_system() == "CUSTOM BRANCH"


def test_planner_agent_uses_override(capture_llm):
    ctx = _ctx(_cast("a"), {prompt_registry.PLANNER_SYSTEM: "CUSTOM PLANNER"})
    planner_agent.next_beat(capture_llm, ctx, TurnIntent(), [], [])
    assert _last_system() == "CUSTOM PLANNER"


def test_agents_fall_back_to_registry_default_when_prompts_empty(capture_llm):
    ctx = _ctx(_cast("a"), {})  # no prompts → registry defaults
    planner_agent.next_beat(capture_llm, ctx, TurnIntent(), [], [])
    assert _last_system() == prompt_registry.default(prompt_registry.PLANNER_SYSTEM)
