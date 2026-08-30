"""The checklist a free-text turn writes for itself, and the grade it gives itself after.

Two properties are pinned hardest. First, that the checklist is not a plan — nothing in it
is dispatched on, and `who` resolves to names precisely so it cannot be mistaken for a
schedule. Second, that every failure biases toward *writing more*, never toward declaring a
turn finished: an extra passage costs the reader some prose, where a false "yes" costs them
the thing they asked for.
"""

from __future__ import annotations

import pytest

from app.agents import task_agent
from app.core.errors import APIError
from app.services.assembler import CastMember, TurnContext


class FakeScenario:
    title = "A Debt Comes Due"


def member(cid, name, **kwargs) -> CastMember:
    defaults = dict(role="smuggler", traits="", speech="", color="#fff", stats={})
    return CastMember(id=cid, name=name, **{**defaults, **kwargs})


def context(**kwargs) -> TurnContext:
    defaults = dict(
        scenario=FakeScenario(),
        session_id="s1",
        storyline_id="w1",
        directed_at=None,
        cast=[member("c1", "Mei"), member("c2", "Valdar")],
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[],
        subgraph={},
        world_primer="",
        stable_prefix="",
    )
    return TurnContext(**{**defaults, **kwargs})


@pytest.fixture(autouse=True)
def _llm(monkeypatch):
    monkeypatch.setattr(task_agent, "resolve_llm", lambda db: ("http://x", "k", "m", None))


def reply(monkeypatch, text):
    monkeypatch.setattr(task_agent.llm, "chat_complete", lambda *a, **k: text)


# ---- writing the checklist -------------------------------------------------


def test_it_returns_the_outcomes_the_turn_owes(monkeypatch):
    reply(monkeypatch, '{"tasks": [{"must": "Valdar refuses to name the buyer", "who": [2]}]}')
    tasks = task_agent.write_checklist(None, context(), [])
    assert [t.must for t in tasks] == ["Valdar refuses to name the buyer"]
    assert tasks[0].n == 1
    assert tasks[0].state == ""


def test_who_resolves_to_names_not_ids(monkeypatch):
    """A name cannot be dispatched on. That is the point of resolving it here.

    The checklist is not a plan: nothing in the engine reads `who`, and carrying character
    ids would make it one keystroke away from being a schedule.
    """
    reply(monkeypatch, '{"tasks": [{"must": "someone answers", "who": [1, 2]}]}')
    assert task_agent.write_checklist(None, context(), [])[0].who == ["Mei", "Valdar"]


def test_an_unknown_roster_number_is_dropped_rather_than_guessed(monkeypatch):
    reply(monkeypatch, '{"tasks": [{"must": "x", "who": [9, 1, null, "two"]}]}')
    assert task_agent.write_checklist(None, context(), [])[0].who == ["Mei"]


def test_an_absent_character_is_not_numbered_into_the_checklist(monkeypatch):
    reply(monkeypatch, '{"tasks": [{"must": "x", "who": [2]}]}')
    ctx = context(cast=[member("c1", "Mei"), member("c2", "Valdar", presence="left")])
    assert task_agent.write_checklist(None, ctx, [])[0].who == []


def test_the_list_is_capped(monkeypatch):
    rows = ", ".join(f'{{"must": "task {i}"}}' for i in range(9))
    reply(monkeypatch, '{"tasks": [' + rows + "]}")
    assert len(task_agent.write_checklist(None, context(), [])) == task_agent.MAX_TASKS


def test_tasks_are_numbered_contiguously_even_when_rows_are_dropped(monkeypatch):
    """The review references tasks by number, so a gap would silently mis-target a verdict."""
    reply(monkeypatch, '{"tasks": [{"must": "  "}, {"must": "a"}, "junk", {"must": "b"}]}')
    assert [t.n for t in task_agent.write_checklist(None, context(), [])] == [1, 2]


@pytest.mark.parametrize("text", ["not json", '{"tasks": "one thing"}', "{}"])
def test_a_malformed_checklist_leaves_the_turn_to_simply_write(monkeypatch, text):
    reply(monkeypatch, text)
    assert task_agent.write_checklist(None, context(), []) == []


def test_an_unconfigured_endpoint_yields_no_checklist(monkeypatch):
    monkeypatch.setattr(
        task_agent, "resolve_llm",
        lambda db: (_ for _ in ()).throw(APIError(400, "bad_request", "no model")),
    )
    assert task_agent.write_checklist(None, context(), []) == []


# ---- grading it ------------------------------------------------------------


def tasks_of(*musts) -> list[task_agent.Task]:
    return [task_agent.Task(n=i + 1, must=m) for i, m in enumerate(musts)]


def test_a_verdict_fills_the_state_and_the_note(monkeypatch):
    reply(monkeypatch, '{"verdicts": [{"task": 1, "state": "yes", "note": "he refuses"}]}')
    graded = task_agent.review(None, context(), [], tasks_of("Valdar refuses"), "prose")
    assert graded[0].state == "yes"
    assert graded[0].note == "he refuses"
    assert graded[0].delivered


def test_partial_and_no_are_both_outstanding(monkeypatch):
    reply(
        monkeypatch,
        '{"verdicts": [{"task": 1, "state": "partial"}, {"task": 2, "state": "no"}]}',
    )
    graded = task_agent.review(None, context(), [], tasks_of("a", "b"), "prose")
    assert len(task_agent.outstanding(graded)) == 2


def test_an_unrecognised_grade_reads_as_partial(monkeypatch):
    """The safe direction: it costs a continuation pass, not the thing the player asked for."""
    reply(monkeypatch, '{"verdicts": [{"task": 1, "state": "sort of"}]}')
    assert task_agent.review(None, context(), [], tasks_of("a"), "prose")[0].state == "partial"


def test_a_task_the_review_never_mentioned_stays_outstanding(monkeypatch):
    """Silence is not delivery. Treating it as delivery is how a requirement vanishes."""
    reply(monkeypatch, '{"verdicts": [{"task": 1, "state": "yes"}]}')
    graded = task_agent.review(None, context(), [], tasks_of("a", "b"), "prose")
    assert [t.must for t in task_agent.outstanding(graded)] == ["b"]


def test_a_verdict_for_a_task_that_does_not_exist_is_ignored(monkeypatch):
    reply(monkeypatch, '{"verdicts": [{"task": 7, "state": "yes"}]}')
    graded = task_agent.review(None, context(), [], tasks_of("a"), "prose")
    assert graded[0].state == ""


@pytest.mark.parametrize("text", ["not json", '{"verdicts": {}}', "{}"])
def test_a_failed_review_sends_the_turn_back_rather_than_passing_it(monkeypatch, text):
    reply(monkeypatch, text)
    graded = task_agent.review(None, context(), [], tasks_of("a"), "prose")
    assert task_agent.outstanding(graded) == graded


def test_grading_nothing_is_a_no_op(monkeypatch):
    reply(monkeypatch, '{"verdicts": []}')
    assert task_agent.review(None, context(), [], [], "prose") == []
    assert task_agent.review(None, context(), [], tasks_of("a"), "   ")[0].state == ""


def test_the_review_is_shown_the_passage_and_the_list(monkeypatch):
    """Two calls exist so the grader reads finished prose rather than its own intent."""
    seen: dict = {}

    def capture(base_url, api_key, model, messages, params=None, **kwargs):
        seen["user"] = messages[1]["content"]
        return '{"verdicts": []}'

    monkeypatch.setattr(task_agent.llm, "chat_complete", capture)
    task_agent.review(None, context(), [], tasks_of("Valdar refuses"), "He said nothing.")
    assert "WHAT THIS TURN OWED" in seen["user"]
    assert "1. Valdar refuses" in seen["user"]
    assert "He said nothing." in seen["user"]
