"""The prompt's reusable prefix must GROW with the scene, not stay pinned at the system message.

This is the invariant the whole Phase-4 reordering exists for, tested at the level that
actually matters: two consecutive character prompts from a scene that gained a beat
between them. EXP-2026-08-005 measured the old layout — cached tokens pinned at exactly
800 (the system message) across ten turns while the prompt grew 1830 → 4678 — because the
speaker's live stat values sat ahead of the transcript, and a prefix cache stops at the
first byte that differs.
"""

from __future__ import annotations

import json

import httpx

from app.agents import character_turn_agent
from app.models import Scenario
from app.services import assembler, llm


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch(monkeypatch, capture: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        capture.append("\n".join(m["content"] for m in body["messages"]))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '<speaker:1>\n<type:character_dialogue>\n"Ok."'}}]},
        )

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _ctx(beats: list[dict], stats: dict) -> assembler.TurnContext:
    mei = assembler.CastMember(
        id="c_mei", name="Mei", role="Cautious smuggler", traits="cautious",
        speech="short, clipped lines", color="#3A5A78", stats=stats,
    )
    return assembler.TurnContext(
        scenario=Scenario(storyline_id="e", title="S", cast_ids=["c_mei"], setting_id=""),
        session_id="ps-cache",
        storyline_id="e",
        directed_at=None,
        cast=[mei],
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=beats,
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer="Embergate is a rain-soaked harbor city.",
        stable_prefix="WORLD PRIMER\nEmbergate is a rain-soaked harbor city.",
        context_beats=100,
    )


def _beats(n: int) -> list[dict]:
    return [
        {"role": "player", "text": f"The {i}th thing the player said, at some length.", "characterId": None}
        for i in range(n)
    ]


def _shared(a: str, b: str) -> int:
    limit = min(len(a), len(b))
    i = 0
    while i < limit and a[i] == b[i]:
        i += 1
    return i


def test_the_reusable_prefix_covers_the_whole_transcript(client, db_session, monkeypatch):
    """Turn N+1 must match turn N through every beat they have in common."""
    _configure_llm(client)
    prompts: list[str] = []
    _patch(monkeypatch, prompts)

    # Turn N, then turn N+1: one more beat, and the speaker's stats have moved — which is
    # precisely what used to invalidate everything.
    character_turn_agent.generate_line(
        db_session, _ctx(_beats(20), {"trust": 38}), _ctx(_beats(20), {"trust": 38}).cast[0],
        turn_beats=[],
    )
    character_turn_agent.generate_line(
        db_session, _ctx(_beats(21), {"trust": 41}), _ctx(_beats(21), {"trust": 41}).cast[0],
        turn_beats=[],
    )

    shared = _shared(prompts[0], prompts[1])
    # The 19th beat is common to both and must fall inside the shared region.
    marker = "The 19th thing the player said"
    assert prompts[0].index(marker) < shared, (
        "the transcript is no longer inside the reusable prefix — the prompt-cache "
        "ordering has regressed; see _build_user_prompt"
    )
    # And the shared region is most of the prompt, not just the system message.
    assert shared > 0.5 * len(prompts[0])


def test_a_stat_change_alone_no_longer_invalidates_the_transcript(client, db_session, monkeypatch):
    """The exact failure EXP-2026-08-005 measured, as a regression test."""
    _configure_llm(client)
    prompts: list[str] = []
    _patch(monkeypatch, prompts)

    beats = _beats(20)
    for trust in (38, 39):
        ctx = _ctx(beats, {"trust": trust})
        character_turn_agent.generate_line(db_session, ctx, ctx.cast[0], turn_beats=[])

    shared = _shared(prompts[0], prompts[1])
    # Nothing but a stat moved, so everything up to the volatile region must still match.
    assert prompts[0].index("The 19th thing the player said") < shared
    # The match ends inside the stat value itself — "trust=3" is common, the digit is not.
    stat_at = prompts[0].index("trust=38")
    assert stat_at <= shared <= stat_at + len("trust=38")


def test_shared_prefix_chars_is_zero_for_a_new_scope():
    assert llm.shared_prefix_chars("scope-never-seen", "hello world") == 0


def test_shared_prefix_chars_measures_the_common_head():
    llm.shared_prefix_chars("scope-x", "abcdef")
    assert llm.shared_prefix_chars("scope-x", "abcXYZ") == 3
    # And it advances: the previous prompt is replaced, not accumulated.
    assert llm.shared_prefix_chars("scope-x", "abcXYZ!") == 6
