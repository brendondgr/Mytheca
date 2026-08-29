"""Storyline-edit schema shapes — catalogue, plan, and stat-change artifacts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.storyline_edit import (
    FIELD_CATALOG,
    FIELD_KEYS,
    AgentMessage,
    FieldChange,
    StatChange,
    StatDefinitionDraft,
    StoryPlan,
)


def test_catalogue_covers_the_scoped_storyline_fields():
    assert {s.key for s in FIELD_CATALOG} == {
        "title",
        "genre",
        "tagline",
        "premise",
        "worldPrimer",
        "statistics",
        "styleBlocks",
    }
    assert FIELD_KEYS == {s.key for s in FIELD_CATALOG}
    # Exactly one stats field and one style field; the rest are text/primer. Both of those
    # kinds stand for a whole sub-structure the author scopes as ONE decision.
    assert sum(1 for s in FIELD_CATALOG if s.kind == "stats") == 1
    assert sum(1 for s in FIELD_CATALOG if s.kind == "style") == 1
    for spec in FIELD_CATALOG:
        assert spec.label and spec.kind in ("text", "primer", "stats", "style")


def test_story_plan_defaults_empty():
    plan = StoryPlan()
    assert plan.is_empty()
    assert plan.changes == [] and plan.stat_changes == [] and plan.style_changes == []


def test_story_plan_not_empty_with_a_change():
    assert not StoryPlan(changes=[FieldChange(field="title", after="X")]).is_empty()
    assert not StoryPlan(
        stat_changes=[StatChange(key="trust", change_type="remove")]
    ).is_empty()


def test_field_change_serializes_camel():
    dumped = FieldChange(field="worldPrimer", before="a", after="b").model_dump(by_alias=True)
    assert dumped == {"field": "worldPrimer", "before": "a", "after": "b", "rationale": ""}


def test_stat_change_carries_flag_and_draft():
    change = StatChange(
        key="resolve",
        change_type="add",
        schema_altering=True,
        after=StatDefinitionDraft(key="resolve", display_name="Resolve", min=0, max=80, default=10),
    )
    dumped = change.model_dump(by_alias=True)
    assert dumped["changeType"] == "add"
    assert dumped["schemaAltering"] is True
    assert dumped["after"]["displayName"] == "Resolve"


def test_stat_definition_draft_rejects_bad_band():
    with pytest.raises(ValidationError):
        StatDefinitionDraft(
            key="x",
            bands=[{"min": 30, "max": 10, "label": "bad"}],  # min > max
        )


def test_agent_message_roles():
    assert AgentMessage(role="user", content="hi").role == "user"
    with pytest.raises(ValidationError):
        AgentMessage(role="system", content="nope")
