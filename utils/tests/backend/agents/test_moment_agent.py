"""Moment-prompt agent — the scene → an appearance-first ComfyUI prompt.

The LLM is stubbed (``services.llm.chat_complete`` patched) and the connection is
passed in pre-resolved, so nothing here touches the network or the settings row.
The point of these tests is the feature's central rule: the prompt describes
people, it never names them.
"""

from __future__ import annotations

import json

import pytest

from app.agents import moment_agent
from app.agents.moment_agent import FramedCharacter, strip_names, visual_tag
from app.core.errors import APIError
from app.schemas.settings import LlmParams

CONN = ("http://localhost:7070/v1", "sk-test", "test-model", LlmParams())

MAERIN = FramedCharacter(
    id="maerin",
    name="Maerin Voss",
    role="Harbor-mistress",
    appearance="Weathered and sharp-eyed, silver streak through dark hair.",
    portrait_positive="middle-aged human woman, salt-stained oilskin coat, silver-streaked dark hair, watercolor portrait",
    doing="closing a brass-cornered ledger",
)
WREN = FramedCharacter(
    id="wren",
    name="Wren",
    role="Informant",
    appearance="Wiry, quick, freckled.",
    portrait_positive="wiry young human, freckled face, patched grey cloak, watercolor portrait",
)


def _stub_llm(monkeypatch, payload: dict, seen: dict | None = None):
    def fake_chat_complete(base_url, api_key, model, messages, params=None, **kwargs):
        if seen is not None:
            seen["messages"] = messages
        return json.dumps(payload)

    monkeypatch.setattr(moment_agent.llm, "chat_complete", fake_chat_complete)


def test_visual_tag_prefers_the_established_portrait_look():
    assert visual_tag(MAERIN) == "middle-aged human woman, salt-stained oilskin coat"
    # No portrait prompt → the first clause of the appearance prose.
    bare = FramedCharacter(id="x", name="X", appearance="Tall and stooped. Grey robes.")
    assert visual_tag(bare) == "Tall and stooped"
    # Nothing but a role → the role.
    assert visual_tag(FramedCharacter(id="y", name="Y", role="Dockhand")) == "dockhand"
    assert visual_tag(FramedCharacter(id="z", name="Z")) == "a figure"


def test_strip_names_rewrites_leaked_names_as_appearance():
    text = "Maerin Voss closing a ledger, Wren leaning in beside her, lamplit tavern"
    out = strip_names(text, [MAERIN, WREN])

    assert "Maerin" not in out and "Voss" not in out and "Wren" not in out
    assert "middle-aged human woman, salt-stained oilskin coat" in out
    assert "wiry young human" in out
    assert "lamplit tavern" in out


def test_strip_names_catches_a_bare_first_name_and_a_possessive():
    out = strip_names("Maerin's hands on the ledger", [MAERIN])
    assert "Maerin" not in out
    assert out.startswith("middle-aged human woman")


def test_strip_names_leaves_ordinary_words_alone():
    """A character called Hope must not turn every 'hopeful' phrase into a person."""
    hope = FramedCharacter(id="h", name="Sister Hope", portrait_positive="young nun, plain habit")
    out = strip_names("a hopeful expression, warm hope in the room", [hope])
    assert out == "a hopeful expression, warm hope in the room"
    # The full name still goes.
    assert "Sister Hope" not in strip_names("Sister Hope kneeling", [hope])


def test_strip_names_never_reintroduces_a_name_through_its_own_tag():
    selfnamed = FramedCharacter(
        id="s", name="Rowan", portrait_positive="Rowan, tall elf archer, green cloak"
    )
    out = strip_names("Rowan drawing a bow", [selfnamed])
    assert "Rowan" not in out
    assert "tall elf archer" in out


def test_write_moment_prompt_scrubs_names_and_pins_the_landscape_frame(monkeypatch):
    seen: dict = {}
    _stub_llm(
        monkeypatch,
        {
            "positive": "Maerin Voss facing Wren across a lamplit table, rain on the shutters",
            "negative": "text, watermark",
            "caption": "Maerin closes her ledger as Wren leans in.",
        },
        seen,
    )

    out = moment_agent.write_moment_prompt(
        None,
        beats=["Narrator: Rain ticks against the shutters.", "Maerin: You're late."],
        cast=[MAERIN, WREN],
        world="World: Embergate (Maritime).",
        place="Place:\nThe Saltworn, a smoke-dark tavern",
        conn=CONN,
    )

    assert "Maerin" not in out.positive and "Wren" not in out.positive
    assert "salt-stained oilskin coat" in out.positive
    assert moment_agent.LANDSCAPE_TAG in out.positive  # appended when the model omits it
    assert out.negative == "text, watermark"
    # The caption is for people, not the image model — names are welcome there.
    assert out.caption == "Maerin closes her ledger as Wren leans in."
    # The cast block reaches the model with the look, and the beats with the moment.
    user = seen["messages"][1]["content"]
    assert "salt-stained oilskin coat" in user
    assert "You're late." in user


def test_write_moment_prompt_keeps_a_landscape_tag_the_model_supplied(monkeypatch):
    _stub_llm(monkeypatch, {"positive": "a wide landscape composition of an empty pier"})
    out = moment_agent.write_moment_prompt(None, beats=["Narrator: The pier is empty."], conn=CONN)
    assert out.positive.count("landscape") == 1
    assert out.negative == moment_agent.DEFAULT_NEGATIVE  # filled in when the model gives none


def test_write_moment_prompt_requires_a_beat_to_depict():
    with pytest.raises(APIError) as exc:
        moment_agent.write_moment_prompt(None, beats=[" "], conn=CONN)
    assert exc.value.status_code == 400


def test_write_moment_prompt_rejects_an_empty_prompt(monkeypatch):
    _stub_llm(monkeypatch, {"positive": "   ", "caption": "nothing"})
    with pytest.raises(APIError) as exc:
        moment_agent.write_moment_prompt(None, beats=["Narrator: Something happens."], conn=CONN)
    assert exc.value.status_code == 502
