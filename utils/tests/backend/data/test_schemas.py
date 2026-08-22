"""camelCase aliasing, snake-case input, branch tags, and stat range validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.character import CharacterRead
from app.schemas.scenario import Branch, ScenarioCreate
from app.schemas.stat import StatBand, StatDefinitionCreate


def test_scenario_serializes_camel_case():
    s = ScenarioCreate(title="T", castIds=["a"], settingId="x", branches=[{"label": "l", "tag": "narration"}])
    assert s.cast_ids == ["a"] and s.setting_id == "x"
    dumped = s.model_dump(by_alias=True)
    assert "castIds" in dumped and "settingId" in dumped
    assert "cast_ids" not in dumped


def test_populate_by_name_accepts_snake_case():
    s = ScenarioCreate(title="T", cast_ids=["a"], setting_id="x")
    assert s.cast_ids == ["a"] and s.setting_id == "x"


def test_branch_tag_accepts_check_request():
    # check_request is a BranchTag but NOT an EventType — must be accepted here.
    assert Branch(label="l", tag="check_request").tag == "check_request"
    with pytest.raises(ValidationError):
        Branch(label="l", tag="character_dialogue")  # an EventType, not a BranchTag


def test_stat_definition_camel_and_range_rules():
    sd = StatDefinitionCreate(key="health", displayName="Health", min=0, max=100, default=100)
    dumped = sd.model_dump(by_alias=True)
    assert dumped["displayName"] == "Health" and dumped["appliesTo"] == ["character"]
    with pytest.raises(ValidationError):
        StatDefinitionCreate(key="x", displayName="X", min=10, max=5, default=7)
    with pytest.raises(ValidationError):
        StatDefinitionCreate(key="x", displayName="X", min=0, max=10, default=99)


def test_stat_band_carries_optional_description():
    # description is optional (defaults to "") and round-trips when provided.
    plain = StatBand(min=0, max=20, label="Exhausted")
    assert plain.description == ""
    described = StatBand(min=0, max=20, label="Exhausted", description="{Character} is spent.")
    assert described.description == "{Character} is spent."
    dumped = described.model_dump(by_alias=True)
    assert dumped["description"] == "{Character} is spent."
    # label stays required.
    with pytest.raises(ValidationError):
        StatBand(min=0, max=20, label="   ", description="x")


def test_character_read_matches_frontend_shape():
    class Obj:
        id, name, role, color, mono = "maerin", "Maerin Voss", "Antagonist", "#8E2B1C", "MV"
        traits = speech = goal = secret = "—"
        appearance = background = personality = portrait = None
        portrait_positive = portrait_negative = None
        voice_samples = None  # NULL column reads back as an empty list
        looseness = None  # neutral, and the overwhelming majority state

    dumped = CharacterRead.model_validate(Obj()).model_dump(by_alias=True)
    assert set(dumped) == {
        "id", "name", "role", "color", "mono", "traits", "speech", "goal", "secret",
        # Base-identity prose + portrait (nullable node properties).
        "appearance", "background", "personality", "portrait",
        # Persisted ComfyUI prompts that produced the portrait.
        "portraitPositive", "portraitNegative",
        # Voice & tone profile (situation → sample-response pairs).
        "voiceSamples",
        # The character's own word-choice bias on top of the beat's register.
        "looseness",
    }
    assert dumped["voiceSamples"] == []  # None coerced to []
    assert dumped["looseness"] is None  # neutral is a real state, not an empty one
