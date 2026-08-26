"""`stop` sequences and constrained decoding — the two ways to bound a model mechanically.

Neither existed before. Every bound in the turn loop was a sentence in a prompt, which is why
the planner could be told "END IT NOW" and keep going: `_pressure()` escalates at 8 beats and
EXP-2026-08-016 still measured 18-, 22- and 24-beat turns.

The `stop` half carries a hazard worth stating twice, because it is invisible until it costs
a whole generation: **a stop sequence matches the reasoning channel too.** Measured on the
deployed route, `stop: ["<END_SCENARIO>"]` killed the generation mid-thought and returned
empty content, while the same prompt without `stop` returned the text intact.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import planner_agent
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams
from app.services import llm


def _capture(monkeypatch) -> dict:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return seen


@pytest.mark.parametrize(
    ("effort", "expected"),
    [
        (ReasoningEffort.NONE, True),
        (ReasoningEffort.QUICK, False),
        (ReasoningEffort.HIGH, False),
        # `None` sends no budget key at all, so the SERVER's default applies — unlimited on
        # the local endpoint. "Unspecified" is not "off".
        (None, False),
    ],
)
def test_stop_is_only_safe_with_the_thinking_channel_off(effort, expected):
    assert llm.stop_is_safe(effort) is expected


def test_a_stop_sequence_reaches_the_wire_when_it_is_safe(monkeypatch):
    seen = _capture(monkeypatch)
    llm.chat_complete(
        "http://x/v1", "k", "m", [{"role": "user", "content": "hi"}], LlmParams(),
        reasoning=ReasoningEffort.NONE, stop=["<END_SCENARIO>"],
    )
    assert seen["body"]["stop"] == ["<END_SCENARIO>"]


def test_a_stop_sequence_is_dropped_rather_than_truncating_a_thinking_model(monkeypatch):
    """Dropped, not raised.

    A caller asking for a stop sequence wants a bounded generation; refusing the call outright
    would be a worse answer than generating without one.
    """
    seen = _capture(monkeypatch)
    llm.chat_complete(
        "http://x/v1", "k", "m", [{"role": "user", "content": "hi"}], LlmParams(),
        reasoning=ReasoningEffort.HIGH, stop=["<END_SCENARIO>"],
    )
    assert "stop" not in seen["body"]


def test_no_stop_key_appears_when_none_was_asked_for(monkeypatch):
    seen = _capture(monkeypatch)
    llm.chat_complete(
        "http://x/v1", "k", "m", [{"role": "user", "content": "hi"}], LlmParams(),
        reasoning=ReasoningEffort.NONE,
    )
    assert "stop" not in seen["body"]


# ---- constrained decoding ----------------------------------------------------


def test_the_plan_schema_constrains_only_what_the_loop_dispatches_on():
    """Register, stakes and reason stay free text.

    They are prose the planner writes and the writer consumes; pinning them to an enum would
    trade a parse guarantee for a worse plan.
    """
    schema = planner_agent.plan_schema_body()["response_format"]["json_schema"]["schema"]
    beat = schema["properties"]["beats"]["items"]["properties"]

    assert beat["action"]["enum"] == sorted(planner_agent._ACTIONS)
    assert beat["register"]["type"] == ["string", "null"]
    assert "enum" not in beat["stakes"]
    assert schema["properties"]["beats"]["items"]["required"] == ["action"]


def test_an_endpoint_without_schema_support_is_retried_unconstrained(
    client, storyline_id, monkeypatch
):
    """A server with no grammar support must not become a scene with no planner.

    Driven through a real turn rather than a unit call, because the thing being protected is
    the turn's behaviour: the first attempt is rejected for carrying `response_format`, the
    second succeeds without it, and the scene plans normally.
    """
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )
    attempts: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        system = body["messages"][0]["content"]
        if "step-by-step loop" in system:
            constrained = "response_format" in body
            attempts.append(constrained)
            if constrained:
                return httpx.Response(
                    400, json={"error": {"message": "response_format is not supported"}}
                )
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
                {"beats": [{"action": "speak", "actor": 1}, {"action": "end"}]}
            )}}]})
        if "You interpret" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
                {"kind": "freeform", "directive": "go"})}}]})
        if "SITUATION-BASED follow-up" in system or "role-playing AS a specific" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
                {"choices": []})}}]})
        if "continuity auditor" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(
                {"consistent": True})}}]})
        if "private inner voice" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        if "narrator of an interactive scene" in system:
            return httpx.Response(200, json={"choices": [{"message": {"content": "The lamp gutters."}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": '"Yes," she says.'}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )

    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Lily"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hall"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Retry", "castIds": [cid], "settingId": sid, "suggestionsCount": 0},
    ).json()["id"]

    resp = client.post(
        f"/api/play/{scid}/turn",
        json={"text": "Go.", "overrides": {"sceneFlow": "voiced"}},
    )
    events = [json.loads(line) for line in resp.text.splitlines() if line.strip()]

    assert attempts[:2] == [True, False], "constrained first, then retried without the schema"
    assert any(e.get("type") == "character_prose" for e in events), "the scene still played"
