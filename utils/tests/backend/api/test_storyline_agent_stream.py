"""Agentic storyline editor/creator — the converse/plan NDJSON streams.

Route-level: the LLM upstream is a path-aware ``httpx.MockTransport`` (chat
completions return a canned reply; engine probes 404 → UNKNOWN, so no ``guided_json``
is sent). Covers the plan phase only — no writes happen here.
"""

from __future__ import annotations

import json

import httpx

from app.schemas.storyline_edit import FIELD_CATALOG
from app.services import llm


def _patch_upstream(monkeypatch, content: str, capture: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            if capture is not None:
                capture["body"] = request.content.decode()
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        return httpx.Response(404)  # /version + /props probes → UNKNOWN backend

    monkeypatch.setattr(llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _scope_body(writable: set[str]) -> dict:
    return {s.key: {"writable": s.key in writable, "readable": True} for s in FIELD_CATALOG}


def _frames(res) -> list[dict]:
    return [json.loads(line) for line in res.text.splitlines() if line.strip()]


def _message_text(frames) -> str:
    return "".join(f.get("delta", "") for f in frames if f["type"] == "message")


# ---- edit stream: plan + discussion -----------------------------------------


def test_edit_stream_returns_a_scoped_plan_for_a_change(client, monkeypatch, storyline_id):
    _configure_llm(client)
    content = (
        '{"message": "Here is a tighter line.", "plan": '
        '{"tagline": {"after": "Every secret has a price.", "rationale": "punchier"}}}'
    )
    _patch_upstream(monkeypatch, content)
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/edit/stream",
        json={
            "scope": _scope_body({"tagline"}),
            "messages": [{"role": "user", "content": "tighten the tagline"}],
            "fields": {"tagline": "Old tagline."},
        },
    )
    assert res.status_code == 200
    frames = _frames(res)
    assert "tighter line" in _message_text(frames)
    assert any(f["type"] == "message" and f["done"] for f in frames)
    plans = [f for f in frames if f["type"] == "plan"]
    assert len(plans) == 1
    change = plans[0]["plan"]["changes"][0]
    assert change["field"] == "tagline"
    assert change["after"] == "Every secret has a price."
    assert change["before"] == "Old tagline."


def test_edit_stream_discussion_has_no_plan(client, monkeypatch, storyline_id):
    _configure_llm(client)
    _patch_upstream(monkeypatch, '{"message": "It already reads strongly to me."}')
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/edit/stream",
        json={
            "scope": _scope_body({"tagline"}),
            "messages": [{"role": "user", "content": "what do you think of the tagline?"}],
        },
    )
    frames = _frames(res)
    assert "reads strongly" in _message_text(frames)
    assert not [f for f in frames if f["type"] == "plan"]


def test_edit_stream_drops_out_of_scope_change(client, monkeypatch, storyline_id):
    _configure_llm(client)
    content = '{"message": "ok", "plan": {"tagline": {"after": "A"}, "premise": {"after": "B"}}}'
    _patch_upstream(monkeypatch, content)
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/edit/stream",
        json={
            "scope": _scope_body({"tagline"}),  # premise NOT writable
            "messages": [{"role": "user", "content": "rewrite both"}],
        },
    )
    plan = next(f for f in _frames(res) if f["type"] == "plan")["plan"]
    assert [c["field"] for c in plan["changes"]] == ["tagline"]


def test_in_chat_memory_and_no_guided_json_on_unknown_backend(client, monkeypatch, storyline_id):
    _configure_llm(client)
    capture: dict = {}
    _patch_upstream(monkeypatch, '{"message": "noted."}', capture)
    client.post(
        f"/api/storylines/{storyline_id}/agent/edit/stream",
        json={
            "scope": _scope_body({"tagline"}),
            "messages": [
                {"role": "user", "content": "MEMORY_MARKER_ONE"},
                {"role": "assistant", "content": "understood"},
                {"role": "user", "content": "now continue"},
            ],
        },
    )
    body = capture["body"]
    assert "MEMORY_MARKER_ONE" in body  # the whole conversation is replayed
    assert "guided_json" not in body  # unknown backend → prompt-instructed only


def test_edit_stream_reports_mid_stream_failure_as_error_frame(client, monkeypatch, storyline_id):
    _configure_llm(client)
    _patch_upstream(monkeypatch, "   ")  # empty completion → 502 during generation
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/edit/stream",
        json={
            "scope": _scope_body({"tagline"}),
            "messages": [{"role": "user", "content": "tighten it"}],
        },
    )
    assert res.status_code == 200  # the stream had already opened
    assert _frames(res)[-1]["type"] == "error"


# ---- pre-flight guards ------------------------------------------------------


def test_edit_stream_404_for_missing_storyline(client, monkeypatch):
    _configure_llm(client)
    res = client.post(
        "/api/storylines/nope/agent/edit/stream",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 404


def test_edit_stream_400_when_llm_unconfigured(client, storyline_id):
    client.patch("/api/options/llm", json={"baseUrl": "", "model": ""})
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/edit/stream",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 400


def test_edit_stream_400_when_no_user_message(client, storyline_id):
    _configure_llm(client)
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/edit/stream",
        json={"messages": []},
    )
    assert res.status_code == 400


# ---- create stream ----------------------------------------------------------


def test_create_stream_returns_a_plan(client, monkeypatch):
    _configure_llm(client)
    content = '{"message": "Here is a draft title.", "plan": {"title": {"after": "Embergate"}}}'
    _patch_upstream(monkeypatch, content)
    res = client.post(
        "/api/storylines/agent/create/stream",
        json={
            "scope": _scope_body({"title"}),
            "messages": [{"role": "user", "content": "draft a title for a drowned port"}],
            "fields": {},
        },
    )
    assert res.status_code == 200
    plan = next(f for f in _frames(res) if f["type"] == "plan")["plan"]
    assert plan["changes"][0]["field"] == "title"
    assert plan["changes"][0]["after"] == "Embergate"


# ---- context-file grounding (docsOverview) ----------------------------------
# The New Storyline page sends the inline text of the files the author kept selected
# for Draft. Without this the assistant never saw uploaded documents at all.


def test_create_stream_grounds_the_prompt_with_selected_context_files(client, monkeypatch):
    _configure_llm(client)
    capture: dict = {}
    _patch_upstream(monkeypatch, '{"message": "Understood."}', capture)
    res = client.post(
        "/api/storylines/agent/create/stream",
        json={
            "scope": _scope_body({"title"}),
            "messages": [{"role": "user", "content": "draft a title"}],
            "fields": {},
            "docsOverview": "### tide-charts.md\nThe harbour drowns at every ninth bell.",
        },
    )
    assert res.status_code == 200
    system = json.loads(capture["body"])["messages"][0]
    assert system["role"] == "system"
    assert "ninth bell" in system["content"]
    assert "tide-charts.md" in system["content"]


def test_edit_stream_grounds_the_prompt_with_selected_context_files(
    client, monkeypatch, storyline_id
):
    _configure_llm(client)
    capture: dict = {}
    _patch_upstream(monkeypatch, '{"message": "Understood."}', capture)
    res = client.post(
        f"/api/storylines/{storyline_id}/agent/edit/stream",
        json={
            "scope": _scope_body({"premise"}),
            "messages": [{"role": "user", "content": "expand the premise"}],
            "fields": {},
            "docsOverview": "### lore.md\nThe Ashen Concord signs no treaty twice.",
        },
    )
    assert res.status_code == 200
    system = json.loads(capture["body"])["messages"][0]["content"]
    assert "Ashen Concord" in system


def test_streams_still_work_without_any_context_files(client, monkeypatch):
    """The field is optional — omitting it leaves the prompt ungrounded, not broken."""
    _configure_llm(client)
    capture: dict = {}
    _patch_upstream(monkeypatch, '{"message": "Understood."}', capture)
    res = client.post(
        "/api/storylines/agent/create/stream",
        json={
            "scope": _scope_body({"title"}),
            "messages": [{"role": "user", "content": "draft a title"}],
            "fields": {},
        },
    )
    assert res.status_code == 200
    assert "Reference notes from dropped files" not in json.loads(capture["body"])["messages"][0]["content"]


# ---- keep-alive frames on a slow turn ---------------------------------------
# The agent produces nothing until the LLM returns, so without keep-alives the
# response is a silent socket for the whole generation and an idle-connection reap
# kills it mid-thought.


def test_a_slow_turn_emits_status_keepalives_before_the_reply(client, monkeypatch):
    import time

    from app.events import stream as stream_mod
    from app.routes import storylines as routes

    _configure_llm(client)

    def slow_chat(*args, **kwargs):
        time.sleep(0.25)
        return '{"message": "Worth the wait."}'

    monkeypatch.setattr("app.services.llm.chat_complete", slow_chat)
    # Poll far faster than the 10s production interval so the test stays quick.
    monkeypatch.setattr(
        routes, "with_keepalive", lambda src, ka: stream_mod.with_keepalive(src, ka, interval=0.05)
    )

    res = client.post(
        "/api/storylines/agent/create/stream",
        json={
            "scope": _scope_body(set()),
            "messages": [{"role": "user", "content": "think hard"}],
            "fields": {},
        },
    )
    assert res.status_code == 200
    frames = _frames(res)
    statuses = [f for f in frames if f["type"] == "status"]
    assert statuses, "a slow turn must keep the socket warm"
    # Keep-alives precede the reply and never displace it.
    assert frames.index(statuses[-1]) < next(i for i, f in enumerate(frames) if f["type"] == "message")
    assert "Worth the wait." in _message_text(frames)


def test_a_fast_turn_sends_no_keepalives(client, monkeypatch):
    """The frames are padding, not chatter — a prompt reply adds none."""
    _configure_llm(client)
    _patch_upstream(monkeypatch, '{"message": "Instant."}')
    res = client.post(
        "/api/storylines/agent/create/stream",
        json={
            "scope": _scope_body(set()),
            "messages": [{"role": "user", "content": "hi"}],
            "fields": {},
        },
    )
    assert [f for f in _frames(res) if f["type"] == "status"] == []
