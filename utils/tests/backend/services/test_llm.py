"""`services.llm.chat_complete` — the shared generation choke point.

Its central reasoning/channel sanitization keeps chain-of-thought + harmony tokens out
of every agent's text (narrator, character emission, authoring JSON). LLM is offline via
httpx.MockTransport.
"""

from __future__ import annotations

import httpx

from app.services import llm


def _patch(monkeypatch, content: str):
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(
        llm, "get_http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def _call() -> str:
    return llm.chat_complete(
        "http://localhost:7070/v1", "sk-test", "m", [{"role": "user", "content": "hi"}]
    )


def test_chat_complete_strips_channel_leak(monkeypatch):
    _patch(
        monkeypatch,
        "reasoning noise here\n<channel|>\nThe lamps gutter out as the door slams.",
    )
    assert _call() == "The lamps gutter out as the door slams."


def test_chat_complete_strips_harmony_final_channel(monkeypatch):
    _patch(
        monkeypatch,
        "<|channel|>analysis<|message|>plan the beat<|end|>"
        "<|start|>assistant<|channel|>final<|message|>Rain hammers the roof.",
    )
    assert _call() == "Rain hammers the roof."


def test_chat_complete_passes_clean_text_through(monkeypatch):
    _patch(monkeypatch, "  A clean, marker-free reply.  ")
    assert _call() == "A clean, marker-free reply."


def test_chat_complete_preserves_app_emission_markers(monkeypatch):
    # The app's own emission markers must survive the scrub (character path parses them).
    emission = '<speaker:1>\n<thinking>plot</thinking>\n<type:character_dialogue>\n"Fine."'
    _patch(monkeypatch, emission)
    assert _call() == emission
