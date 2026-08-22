"""The Ghostwriter's prompt — what it is told, and what it is told not to do.

The agent writes ONE line for the player from a note about what they want it to do. The
tests below are about the prompt rather than the prose, because the prose is the model's:
what is checkable is that the drafted line is asked for in the right voice, with the scene
in front of it, and under a contract that forbids the things that would make a draft
unusable (a speaker label, tags, deciding what happens next).
"""

from __future__ import annotations

import pytest

from app.agents import ghostwriter_agent, prompt_registry
from app.core.errors import APIError
from app.services.assembler import CastMember, TurnContext


def _ctx(**over) -> TurnContext:
    mei = CastMember(
        id="mei",
        name="Mei",
        role="Harbor master",
        traits="Guarded, exact",
        speech="Clipped. Never uses two words where one will do.",
        color="#8e2b1c",
        stats={},
    )
    base = dict(
        scenario=None,
        session_id="ps",
        storyline_id="sl",
        directed_at=None,
        cast=[mei],
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=[
            {"role": "player", "text": "Who paid for the fire?", "characterId": None},
            {"role": "character", "text": "Nobody at this table.", "characterId": "mei"},
        ],
        subgraph={},
        world_primer=None,
        stable_prefix="",
    )
    base.update(over)
    return TurnContext(**base)


def test_the_prompt_carries_the_pov_characters_voice():
    _system, user = ghostwriter_agent.build_prompt(
        _ctx(), intent="Refuse, but stay civil.", pov_id="mei", mode="character"
    )
    assert "Mei" in user
    assert "Clipped." in user  # their voice profile, not just their name


def test_the_prompt_carries_the_players_intent_verbatim():
    _system, user = ghostwriter_agent.build_prompt(
        _ctx(), intent="Refuse, but stay civil.", pov_id="mei", mode="character"
    )
    assert "Refuse, but stay civil." in user


def test_the_prompt_carries_the_scene_so_the_line_answers_what_was_said():
    _system, user = ghostwriter_agent.build_prompt(
        _ctx(), intent="Push back.", pov_id="mei", mode="character"
    )
    assert "Who paid for the fire?" in user
    assert "Nobody at this table." in user


def test_narrator_mode_does_not_write_as_a_character():
    _system, user = ghostwriter_agent.build_prompt(
        _ctx(), intent="Set the room.", pov_id=None, mode="narrator"
    )
    assert "not as any one character" in user
    assert "Clipped." not in user


def test_an_unknown_pov_falls_back_to_the_narrator_framing():
    """A POV character who has left the cast must not produce a prompt claiming to be them."""
    _system, user = ghostwriter_agent.build_prompt(
        _ctx(), intent="Say something.", pov_id="ghost", mode="character"
    )
    assert "not as any one character" in user


def test_the_output_contract_forbids_what_would_make_a_draft_unusable():
    system = prompt_registry.default(prompt_registry.GHOSTWRITER_LINE)
    lowered = system.lower()
    assert "no speaker label" in lowered
    assert "no tags" in lowered
    # It writes a line, not the rest of the scene.
    assert "do not decide what happens next" in lowered
    assert "do not answer for anyone else" in lowered


def test_the_contract_says_the_note_is_intent_not_text_to_paraphrase():
    """The failure mode this guards against is a draft that restates the note back —
    "I tell him I do not believe him" instead of what the character would actually say."""
    system = prompt_registry.default(prompt_registry.GHOSTWRITER_LINE)
    assert "not text to paraphrase" in system.lower()


def test_the_prompt_key_is_overridable_like_every_other():
    assert prompt_registry.GHOSTWRITER_LINE in {s.key for s in prompt_registry.PROMPT_REGISTRY}
    spec = next(
        s for s in prompt_registry.PROMPT_REGISTRY if s.key == prompt_registry.GHOSTWRITER_LINE
    )
    assert spec.agent == "Ghostwriter"


def test_a_storyline_override_wins_over_the_default():
    ctx = _ctx(prompts={prompt_registry.GHOSTWRITER_LINE: "OVERRIDDEN CONTRACT"})
    system, _user = ghostwriter_agent.build_prompt(
        ctx, intent="x", pov_id="mei", mode="character"
    )
    assert system == "OVERRIDDEN CONTRACT"


def test_an_unconfigured_model_raises_rather_than_returning_junk(db_session):
    """Unlike the turn agents, which degrade to skipping a beat: here the player pressed a
    button and is waiting for a sentence, so silence would read as the button being broken."""
    gen = ghostwriter_agent.stream_line(db_session, _ctx(), intent="x", pov_id="mei")
    with pytest.raises(APIError):
        next(gen)
