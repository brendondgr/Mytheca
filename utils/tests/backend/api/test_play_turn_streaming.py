"""POST /api/play/{scenarioId}/turn — live token streaming from the model.

The other play-turn tests mock the endpoint with an ordinary JSON completion, which
exercises the blocking fallback. These mock a real ``text/event-stream`` so the *live*
path runs: the emission is parsed as it arrives and each segment reaches the wire the
moment the parser recognises it, rather than being sliced up after the fact.

What this is protecting is a property the player feels directly — a character's private
thought completes while their spoken line is still being written — so the assertions are
about frame ORDER, not just frame content.
"""

from __future__ import annotations

import json
from collections import defaultdict

import httpx

from app.services import llm, llm_backend

_EMISSION = (
    "<speaker:1>"
    "<thinking>The coin is a test. He wants to see if I take it.</thinking>"
    "<type:character_action>Mei leaves the pouch where it lies.</type:character_action>"
    '<type:character_dialogue>"Coin\'s easy. It\'s after the coin I don\'t trust."'
    "</type:character_dialogue>"
)


def _sse_from(text: str, *, chunk: int = 12) -> str:
    """Serialise ``text`` as an OpenAI-style token stream."""
    lines = []
    for i in range(0, len(text), chunk):
        payload = {"choices": [{"index": 0, "delta": {"content": text[i : i + chunk]}}]}
        lines.append(f"data: {json.dumps(payload)}\n\n")
    lines.append(
        f"data: {json.dumps({'choices': [], 'usage': {'prompt_tokens': 321}})}\n\n"
    )
    lines.append("data: [DONE]\n\n")
    return "".join(lines)


def _patch_streaming_llm(monkeypatch, emission: str = _EMISSION):
    """Answer engine probes with 404s and every completion with an event stream."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        body = json.loads(request.content)
        if not body.get("stream"):
            return httpx.Response(200, json={"choices": [{"message": {"content": emission}}]})
        return httpx.Response(
            200, text=_sse_from(emission), headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    llm_backend.clear_cache()
    llm._NO_STREAM.clear()


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _scene(client, storyline_id, names=("Mei",)):
    cast = [
        client.post(f"/api/storylines/{storyline_id}/characters", json={"name": n}).json()["id"]
        for n in names
    ]
    setting = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Smoldering Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": cast, "settingId": setting},
    ).json()["id"]
    return cast, scid


def _stream(resp) -> list[dict]:
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _of_type(events, type_):
    return [e for e in events if e.get("type") == type_]


def test_dialogue_arrives_as_many_deltas_not_one_block(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_streaming_llm(monkeypatch)
    cast, scid = _scene(client, storyline_id)

    resp = client.post(
        f"/api/play/{scid}/turn", json={"text": "I slide the pouch over.", "directedAt": cast[0]}
    )
    assert resp.status_code == 200
    dialogue = _of_type(_stream(resp), "character_dialogue")

    # More than one frame, exactly one terminal frame, and the pieces reassemble.
    assert len(dialogue) > 2
    assert sum(1 for d in dialogue if d["data"]["done"]) == 1
    by_id: dict[str, list[dict]] = defaultdict(list)
    for d in dialogue:
        by_id[d["id"]].append(d)
    assert len(by_id) == 1  # one event id, streamed
    joined = "".join(d["data"]["text"] for d in dialogue)
    assert "after the coin I don't trust" in joined


def test_the_thought_finishes_before_the_dialogue_begins(client, storyline_id, monkeypatch):
    """The headline behaviour: interiority is visible while speech is still forming."""
    _configure_llm(client)
    _patch_streaming_llm(monkeypatch)
    cast, scid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "I slide the pouch over.", "directedAt": cast[0]},
        )
    )

    thought_done = next(
        i
        for i, e in enumerate(events)
        if e.get("type") == "internal_thought" and e["data"]["done"]
    )
    first_dialogue = next(
        i for i, e in enumerate(events) if e.get("type") == "character_dialogue"
    )
    assert thought_done < first_dialogue


def test_the_thought_itself_streams(client, storyline_id, monkeypatch):
    _configure_llm(client)
    _patch_streaming_llm(monkeypatch)
    cast, scid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "I slide the pouch over.", "directedAt": cast[0]},
        )
    )
    thoughts = _of_type(events, "internal_thought")

    assert len(thoughts) > 1
    assert "".join(t["data"]["text"] for t in thoughts).startswith("The coin is a test")


def test_the_persisted_row_holds_the_whole_line_not_a_fragment(
    client, storyline_id, monkeypatch
):
    """Deltas are transport; the DB must still hold one complete beat."""
    _configure_llm(client)
    _patch_streaming_llm(monkeypatch)
    cast, scid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "I slide the pouch over.", "directedAt": cast[0]},
        )
    )
    session_id = next(e["sessionId"] for e in events if "sessionId" in e)

    history = client.get(f"/api/play/{scid}/sessions/{session_id}").json()
    dialogue = [e for e in history["events"] if e["type"] == "character_dialogue"]
    assert len(dialogue) == 1
    assert dialogue[0]["data"]["text"].startswith('"Coin')
    assert dialogue[0]["data"]["done"] is True


def test_an_action_is_still_delivered_whole(client, storyline_id, monkeypatch):
    """`character_action` is one short beat the client folds into the open bubble —
    splitting it would break that fold, so it is held even on the live path."""
    _configure_llm(client)
    _patch_streaming_llm(monkeypatch)
    cast, scid = _scene(client, storyline_id)

    events = _stream(
        client.post(
            f"/api/play/{scid}/turn",
            json={"text": "I slide the pouch over.", "directedAt": cast[0]},
        )
    )
    actions = _of_type(events, "character_action")

    assert len(actions) == 1
    assert actions[0]["data"]["text"] == "Mei leaves the pouch where it lies."


def test_streaming_and_blocking_produce_the_same_transcript(
    client, storyline_id, monkeypatch
):
    """The transport must change WHEN text appears, never WHAT appears."""
    _configure_llm(client)
    cast, scid = _scene(client, storyline_id)
    body = {"text": "I slide the pouch over.", "directedAt": cast[0]}

    _patch_streaming_llm(monkeypatch)
    streamed = _stream(client.post(f"/api/play/{scid}/turn", json=body))

    # Same endpoint, refusing to stream — the fallback path.
    def blocking(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404, json={"detail": "Not Found"})
        if json.loads(request.content).get("stream"):
            return httpx.Response(400, json={"error": "no streaming"})
        return httpx.Response(200, json={"choices": [{"message": {"content": _EMISSION}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(blocking))
    )
    llm_backend.clear_cache()
    llm._NO_STREAM.clear()
    blocked = _stream(client.post(f"/api/play/{scid}/turn", json=body))

    def transcript(events):
        out = []
        for kind in ("internal_thought", "character_action", "character_dialogue"):
            joined = "".join(e["data"]["text"] for e in _of_type(events, kind))
            if joined:
                out.append((kind, joined))
        return out

    assert transcript(streamed) == transcript(blocked)


def test_the_scene_opening_narration_streams(client, storyline_id, monkeypatch):
    """A scene's first message is narrator-led — the beat most in need of arriving early."""
    _configure_llm(client)
    _patch_streaming_llm(monkeypatch, "The hearth spits. Rain runs off the eaves in sheets.")
    _, scid = _scene(client, storyline_id)

    # No directed character on a cold open → the narrator sets the moment first.
    events = _stream(client.post(f"/api/play/{scid}/turn", json={"text": "I step inside."}))
    narration = _of_type(events, "narration")

    assert len(narration) > 1
    assert sum(1 for n in narration if n["data"]["done"]) == 1
    assert len({n["id"] for n in narration}) == 1
    assert "The hearth spits." in "".join(n["data"]["text"] for n in narration)


def test_a_guarded_later_beat_holds_its_prose_for_the_verdict(
    client, storyline_id, monkeypatch
):
    """The continuity guard judges a COMPLETE line, so a beat it will judge cannot also
    stream — it would have to un-write itself on rejection. Later speakers therefore
    emit their prose once, after the verdict, while the first speaker streams."""
    _configure_llm(client)
    _patch_streaming_llm(monkeypatch)
    cast, scid = _scene(client, storyline_id, names=("Mei", "Kira"))

    events = _stream(
        client.post(f"/api/play/{scid}/turn", json={"text": "Everyone introduces themselves."})
    )

    per_id: dict[str, int] = defaultdict(int)
    for e in _of_type(events, "character_dialogue"):
        per_id[e["id"]] += 1
    # At least one beat streamed (many frames) — the turn is not uniformly blocking.
    assert per_id, "expected at least one dialogue beat"
    assert max(per_id.values()) > 1
