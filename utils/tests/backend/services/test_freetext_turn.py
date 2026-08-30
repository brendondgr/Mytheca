"""The free-text engine, end to end through the turn route.

A free-text turn is one HTTP request that makes four to six model calls and returns ONE
story event. What is pinned here is the shape of that: one `scene_prose` event and no
attributed beats, the checklist on the wire, the review loop's stopping conditions, and the
one asymmetry that defines the mode — the checklist is withheld from the writer under
Playwright and sent under POV.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services import llm

_PASSAGE = (
    "The rain has found the gap in the shutters again, and Mei watches it darken the wood "
    "rather than look at him.\n\n"
    '"You are asking me the wrong thing," she says.\n\n'
    "Valdar does not move."
)


class Endpoint:
    """A scripted model. Routes by the instruction in the user message's last block."""

    def __init__(self, *, terms=None, tasks=None, verdicts=None, passages=None):
        self.terms = terms if terms is not None else []
        self.tasks = tasks if tasks is not None else []
        self.verdicts = verdicts if verdicts is not None else []
        self.passages = list(passages) if passages else [_PASSAGE]
        self.calls: list[dict] = []
        # `llm.chat_complete_stream` attempts a real stream first and falls back to the
        # blocking path when the response is not an event-stream — which a MockTransport
        # never is. So every prose call arrives here TWICE, back to back, with identical
        # bytes. Only the MOST RECENT ask is remembered, so that immediate retry gets the
        # same answer while a genuinely later ask — a second continuation pass, whose
        # prompt is identical because the outstanding list has not changed — still advances
        # to the next passage.
        self._last: tuple[str, str] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404)
        body = json.loads(request.content.decode())
        user = body["messages"][-1]["content"]
        self.calls.append({"user": user, "system": body["messages"][0]["content"]})
        # Any call that is not a prose ask ends the previous ask's retry window, so a later
        # continuation with a byte-identical prompt still advances to the next passage.
        # Placed before every route, because the review is exactly the call that separates
        # two identical continuation asks.
        if "continuous passage" not in user and "stopped before it finished" not in user:
            self._last = None

        if "what would you look up" in user or "look things up" in user.lower():
            return _resp(json.dumps({"terms": self.terms}))
        if "STRUCTURE ONLY" in user and "has to accomplish" in user:
            return _resp(json.dumps({"tasks": self.tasks}))
        if "reading back a passage" in user:
            return _resp(json.dumps({"verdicts": self.verdicts}))
        system = body["messages"][0]["content"]
        if "SITUATION-BASED follow-up" in system:
            return _resp(json.dumps({"choices": []}))
        if "private inner voice" in system:
            return _resp("{}")
        if "You interpret" in system:
            # The structured engine's intent classifier. A free-text turn must never reach
            # it — `test_free_text_makes_no_structural_calls` asserts exactly that — but a
            # structured scene in this module still does, and it must not be answered with
            # a passage.
            return _resp(json.dumps({"kind": "freeform", "directive": "go"}))
        if "continuous passage" not in user and "stopped before it finished" not in user:
            return _resp("{}")
        if self._last is None or self._last[0] != user:
            self._last = (user, self.passages.pop(0) if self.passages else "")
        return _resp(self._last[1])

    @property
    def prose_calls(self) -> list[dict]:
        """Prose asks, with the stream-then-blocking retry collapsed.

        Only *immediately consecutive* duplicates are folded, because that is exactly what
        the retry is. Two continuation passes carry byte-identical prompts — the outstanding
        list has not changed — and deduping globally would count them as one.
        """
        asks: list[dict] = []
        previous: str | None = None
        for call in self.calls:
            user = call["user"]
            prose = "continuous passage" in user or "stopped before it finished" in user
            if prose and user != previous:
                asks.append(call)
            previous = user if prose else None
        return asks


def _resp(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _install(monkeypatch, endpoint: Endpoint):
    monkeypatch.setattr(
        llm, "get_http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(endpoint)),
    )


def _configure(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "m", "apiKey": "sk-test"},
    )


def _scene(client, storyline_id, **scenario):
    ids = [
        client.post(
            f"/api/storylines/{storyline_id}/characters", json={"name": n}
        ).json()["id"]
        for n in ("Mei", "Valdar")
    ]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Drowned Lamp"}
    ).json()["id"]
    body = {
        "title": "A Debt Comes Due",
        "castIds": ids,
        "settingId": sid,
        "sceneMode": "freetext",
        **scenario,
    }
    return client.post(f"/api/storylines/{storyline_id}/scenarios", json=body).json()["id"], ids


def _turn(client, scid, **payload) -> list[dict]:
    body = {"text": "I put the ledger on the table.", "trace": True, **payload}
    resp = client.post(f"/api/play/{scid}/turn", json=body)
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def _of(events, type_):
    return [e for e in events if e.get("type") == type_]


def _text(events) -> str:
    """Accumulate a delta-streamed body the way the client does — by event id."""
    body = ""
    for event in _of(events, "scene_prose"):
        body += event["data"]["text"]
    return body


# ---- the shape of a turn ---------------------------------------------------


def test_a_free_text_turn_is_one_unattributed_body(client, storyline_id, monkeypatch):
    _configure(client)
    _install(monkeypatch, Endpoint())
    scid, _ = _scene(client, storyline_id)

    events = _turn(client, scid)

    prose = _of(events, "scene_prose")
    assert prose, "the turn produced no passage"
    assert len({e["id"] for e in prose}) == 1, "one turn, one event"
    assert "characterId" not in prose[0]["data"]
    assert _text(events).strip() == _PASSAGE
    # The structured engine's beat types must not appear at all.
    assert not _of(events, "character_prose")
    assert not _of(events, "narration")


def test_nothing_schedules_a_speaker(client, storyline_id, monkeypatch):
    """The planner is barred: a free-text turn that reaches it has rebuilt the thing the
    mode exists to remove."""
    from app.agents import planner_agent

    def explode(*_a, **_k):
        raise AssertionError("the planner ran on a free-text turn")

    monkeypatch.setattr(planner_agent, "plan_beats", explode)
    _configure(client)
    _install(monkeypatch, Endpoint())
    scid, _ = _scene(client, storyline_id)

    assert _of(_turn(client, scid), "scene_prose")


def test_a_structured_scene_is_untouched(client, storyline_id, monkeypatch):
    """Every phase of this is additive. A scene that did not ask for the new engine keeps
    producing attributed beats."""
    _configure(client)
    _install(monkeypatch, Endpoint(passages=['<speaker:1>\n"Someone speaks."'] * 8))
    scid, _ = _scene(client, storyline_id, sceneMode="structured")

    events = _turn(client, scid)
    assert not _of(events, "scene_prose")


def test_a_turn_can_pick_the_engine_without_editing_the_scene(client, storyline_id, monkeypatch):
    _configure(client)
    _install(monkeypatch, Endpoint())
    scid, _ = _scene(client, storyline_id, sceneMode="structured")

    events = _turn(client, scid, overrides={"sceneMode": "freetext"})
    assert _of(events, "scene_prose")


# ---- the checklist ---------------------------------------------------------


def test_the_checklist_reaches_the_wire_before_any_prose(client, storyline_id, monkeypatch):
    _configure(client)
    _install(monkeypatch, Endpoint(tasks=[{"must": "Valdar refuses to name the buyer"}]))
    scid, _ = _scene(client, storyline_id)

    events = _turn(client, scid)
    frames = _of(events, "tasks")
    assert frames, "no checklist frame"
    assert frames[0]["tasks"][0]["must"] == "Valdar refuses to name the buyer"
    assert frames[0]["pass"] == 0
    assert events.index(frames[0]) < events.index(_of(events, "scene_prose")[0])


def test_the_verdicts_come_back_on_the_same_task_numbers(client, storyline_id, monkeypatch):
    _configure(client)
    _install(
        monkeypatch,
        Endpoint(
            tasks=[{"must": "Valdar refuses"}],
            verdicts=[{"task": 1, "state": "yes", "note": "he refuses"}],
        ),
    )
    scid, _ = _scene(client, storyline_id)

    graded = _of(_turn(client, scid), "tasks")[-1]
    assert graded["tasks"][0]["n"] == 1
    assert graded["tasks"][0]["state"] == "yes"
    assert graded["complete"] is True


# ---- the withheld list -----------------------------------------------------


def test_playwright_withholds_the_checklist_from_the_writer(client, storyline_id, monkeypatch):
    """The sharpest decision in the mode. A model handed a checklist writes to it, and prose
    that visibly works through a list reads like the minutes of a meeting."""
    endpoint = Endpoint(tasks=[{"must": "Valdar refuses to name the buyer"}])
    _configure(client)
    _install(monkeypatch, endpoint)
    scid, _ = _scene(client, storyline_id)

    _turn(client, scid)

    first_pass = endpoint.prose_calls[0]["user"]
    assert "Valdar refuses to name the buyer" not in first_pass
    # …but the grader does see it.
    review = [c for c in endpoint.calls if "reading back a passage" in c["user"]]
    assert review and "Valdar refuses to name the buyer" in review[0]["user"]


def test_pov_with_instructions_sends_the_checklist_along(client, storyline_id, monkeypatch):
    """The deliberate opposite: the player wrote those as direction to their scene partners,
    so there is nothing to gain by hiding them."""
    endpoint = Endpoint(tasks=[{"must": "Valdar refuses to name the buyer"}])
    _configure(client)
    _install(monkeypatch, endpoint)
    scid, ids = _scene(client, storyline_id)

    _turn(client, scid, povCharacterId=ids[0], guidance="Make him stonewall me.")

    assert "Valdar refuses to name the buyer" in endpoint.prose_calls[0]["user"]


def test_a_plain_character_turn_has_no_checklist_at_all(client, storyline_id, monkeypatch):
    """The third path: you said something, the room answers. One prose call, no deliberation."""
    endpoint = Endpoint(tasks=[{"must": "should never be asked for"}])
    _configure(client)
    _install(monkeypatch, endpoint)
    scid, ids = _scene(client, storyline_id)

    events = _turn(client, scid, povCharacterId=ids[0])

    assert not _of(events, "tasks")
    assert not [c for c in endpoint.calls if "reading back a passage" in c["user"]]
    assert len(endpoint.prose_calls) == 1


# ---- the continuation loop -------------------------------------------------


def test_an_unmet_task_continues_the_same_passage(client, storyline_id, monkeypatch):
    endpoint = Endpoint(
        tasks=[{"must": "Valdar refuses"}],
        verdicts=[{"task": 1, "state": "no"}],
        passages=["First part.", "Second part.", "Third part."],
    )
    _configure(client)
    _install(monkeypatch, endpoint)
    scid, _ = _scene(client, storyline_id)

    events = _turn(client, scid)

    # One event, extended — not a second block underneath.
    assert len({e["id"] for e in _of(events, "scene_prose")}) == 1
    # Separated by a paragraph break the ENGINE inserts: the transport strips leading
    # whitespace off a completion, so whatever spacing the model wrote never arrives, and
    # without this the passes come back glued into one sentence.
    assert _text(events).strip() == "First part.\n\nSecond part.\n\nThird part."


def test_the_continuation_is_capped(client, storyline_id, monkeypatch):
    """Three generations for one message is already a long wait, and the player can always
    send another message — they cannot un-wait."""
    from app.services import freetext_turn

    endpoint = Endpoint(
        tasks=[{"must": "never satisfied"}],
        verdicts=[{"task": 1, "state": "no"}],
        passages=[f"Part {i}." for i in range(10)],
    )
    _configure(client)
    _install(monkeypatch, endpoint)
    scid, _ = _scene(client, storyline_id)

    _turn(client, scid)
    assert len(endpoint.prose_calls) == freetext_turn.MAX_CONTINUATIONS + 1


def test_a_satisfied_checklist_stops_after_one_pass(client, storyline_id, monkeypatch):
    endpoint = Endpoint(
        tasks=[{"must": "Valdar refuses"}],
        verdicts=[{"task": 1, "state": "yes"}],
        passages=["Only part.", " should not be written"],
    )
    _configure(client)
    _install(monkeypatch, endpoint)
    scid, _ = _scene(client, storyline_id)

    _turn(client, scid)
    assert len(endpoint.prose_calls) == 1


def test_no_checklist_means_no_review_call(client, storyline_id, monkeypatch):
    endpoint = Endpoint(tasks=[])
    _configure(client)
    _install(monkeypatch, endpoint)
    scid, _ = _scene(client, storyline_id)

    _turn(client, scid)
    assert not [c for c in endpoint.calls if "reading back a passage" in c["user"]]
    assert len(endpoint.prose_calls) == 1


# ---- degradation -----------------------------------------------------------


def test_an_endpoint_that_answers_nothing_is_an_error_not_a_silent_turn(
    client, storyline_id, monkeypatch
):
    """A completion with no content is an upstream failure, and the player should be told.

    Same line the structured engine draws when every attempt fails: a scene that quietly
    says nothing looks like the story deciding something, which is worse than an error.
    """
    _configure(client)
    _install(monkeypatch, Endpoint(passages=[""]))
    scid, _ = _scene(client, storyline_id)

    assert _of(_turn(client, scid), "error")


def test_a_leaked_briefing_is_withheld_and_the_scene_still_says_something(
    client, storyline_id, monkeypatch
):
    """The gate catches the opening before the reader sees it — and free-text needs that
    more than the structured engine does, because thinking is ON by default here.

    Nothing reached the wire, so there is nothing to retract; the turn falls back to the
    same quiet holding narration the structured engine uses when a turn produced nothing.
    """
    briefing = (
        "Okay — the player wants Valdar to stonewall. Per the instruction, the cast list "
        "gives me Mei and Valdar, so the passage should open on her. Checking the voice "
        "sample for tone before writing the prompt response."
    )
    _configure(client)
    _install(monkeypatch, Endpoint(passages=[briefing]))
    scid, _ = _scene(client, storyline_id)

    events = _turn(client, scid)
    assert not _of(events, "scene_prose"), "the briefing must never reach the reader"
    assert _of(events, "narration"), "the scene must still say something"
    assert not _of(events, "error")


def test_the_cached_prefix_is_identical_across_every_call_of_the_turn(
    client, storyline_id, monkeypatch
):
    """The economic argument for the mode, asserted against real traffic rather than a unit."""
    endpoint = Endpoint(
        tasks=[{"must": "Valdar refuses"}], verdicts=[{"task": 1, "state": "yes"}]
    )
    _configure(client)
    _install(monkeypatch, endpoint)
    scid, _ = _scene(client, storyline_id)

    _turn(client, scid)

    freetext = [
        c for c in endpoint.calls
        if "THE CAST" in c["system"]  # excludes the finalize agents, which are not this mode
    ]
    assert len(freetext) >= 3
    assert len({c["system"] for c in freetext}) == 1
