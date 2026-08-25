"""A structural call gets its own, much shorter read window than prose generation.

EXP-2026-08-005 measured the beat planner at 4.9 s and intent at 3.6 s, both sharing
prose generation's 300 s patience. A stalled one therefore cost the player five minutes
of silence. These tests pin the two halves of the fix: the transport honours a per-call
override, and the prose-free agents actually pass one.
"""

from __future__ import annotations

import httpx
import pytest

from app.agents import direction_agent, intent_agent, planner_agent, triage_agent
from app.agents._common import decision_timeout
from app.core.config import get_settings
from app.services import llm


def test_gen_timeout_defaults_to_the_generation_window():
    assert llm._gen_timeout().read == float(get_settings().llm_gen_timeout_seconds)


def test_gen_timeout_override_replaces_the_read_window():
    window = llm._gen_timeout(25)
    assert window.read == 25.0
    # The connect budget is a separate concern and must not move with it.
    assert window.connect == 5.0


def test_decision_timeout_reads_the_setting():
    assert decision_timeout() == float(get_settings().llm_decision_timeout_seconds)


def test_decision_timeout_is_far_below_the_prose_window():
    """The whole point: a decision must not be able to burn the prose budget."""
    settings = get_settings()
    assert settings.llm_decision_timeout_seconds < settings.llm_gen_timeout_seconds / 4


@pytest.mark.parametrize("streaming", [False, True])
def test_transport_forwards_the_override(monkeypatch, streaming):
    seen: dict = {}

    def fake_send(method, url, *, headers, json=None, timeout=None):
        seen["timeout"] = timeout
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(llm, "_send", fake_send)
    args = ("http://localhost:7070/v1", "sk", "m", [{"role": "user", "content": "hi"}])
    if streaming:
        # Force the blocking fallback, which is the path that must still carry it.
        monkeypatch.setattr(llm, "_NO_STREAM", {("http://localhost:7070/v1", "m")})
        gen = llm.chat_complete_stream(*args, timeout_s=7)
        with pytest.raises(StopIteration):
            while True:
                next(gen)
    else:
        llm.chat_complete(*args, timeout_s=7)
    assert seen["timeout"].read == 7.0


def _capture(monkeypatch) -> dict:
    seen: dict = {}

    def fake_chat_complete(*_a, **kw):
        seen.update(kw)
        raise RuntimeError("stop after capturing the kwargs")

    monkeypatch.setattr(llm, "chat_complete", fake_chat_complete)
    return seen


#: The planner is the one structural agent that does NOT use the decision window. It runs
#: once per turn at a full thinking budget rather than many times as a snap judgement, so it
#: carries its own bounded window (`plan_timeout`, 180 s). The invariant this file protects is
#: unchanged — a prose-free agent must never silently inherit the 300 s *prose* window — so
#: the assertion is on "opted into a bounded window of its own", not on one constant.
_WINDOW = {
    "app.agents.planner_agent": "timeout_s=plan_timeout()",
}


@pytest.mark.parametrize(
    "module", [intent_agent, planner_agent, direction_agent, triage_agent]
)
def test_structural_agents_pass_a_decision_timeout(module):
    """Every prose-free agent must opt into a short window, not inherit the long one."""
    source = module.__file__
    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    expected = _WINDOW.get(module.__name__, "timeout_s=decision_timeout()")
    assert expected in text, f"{module.__name__} still uses the prose window"
    # Guard against a future call site being added without the override.
    assert text.count("llm.chat_complete(") == text.count(expected)
