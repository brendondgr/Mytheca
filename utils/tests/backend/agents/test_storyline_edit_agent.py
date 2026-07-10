"""Storyline editor agent — plan-building logic (pure; no LLM, no DB).

Exercises ``core._parse`` / ``core._plan_from_raw`` directly: the translation from
the model's keyed reply into a canonical, scope-filtered :class:`StoryPlan`.
"""

from __future__ import annotations

from app.agents.storyline_edit import core
from app.schemas.storyline_edit import (
    FIELD_CATALOG,
    FieldScope,
    StatDefinitionDraft,
    StorylineFieldsSnapshot,
)


def _scope(writable: set[str]):
    return {
        s.key: FieldScope(writable=s.key in writable, readable=True) for s in FIELD_CATALOG
    }


# ---- _parse -----------------------------------------------------------------


def test_parse_message_only_has_no_plan():
    msg, plan = core._parse('{"message": "It reads well already."}', _scope(set()), StorylineFieldsSnapshot())
    assert msg == "It reads well already."
    assert plan is None


def test_parse_non_json_degrades_to_plain_message():
    msg, plan = core._parse("just prose, no object here", _scope({"title"}), StorylineFieldsSnapshot())
    assert msg == "just prose, no object here"
    assert plan is None


# ---- text/primer field changes ----------------------------------------------


def test_text_change_carries_before_from_snapshot():
    snap = StorylineFieldsSnapshot(tagline="Old tagline.")
    raw = {"tagline": {"after": "Every secret has a price.", "rationale": "punchier"}}
    plan = core._plan_from_raw(raw, _scope({"tagline"}), snap)
    assert plan is not None
    change = plan.changes[0]
    assert change.field == "tagline"
    assert change.before == "Old tagline."
    assert change.after == "Every secret has a price."
    assert change.rationale == "punchier"


def test_out_of_scope_text_field_is_dropped_from_the_plan():
    raw = {"tagline": {"after": "A"}, "premise": {"after": "B"}}
    plan = core._plan_from_raw(raw, _scope({"tagline"}), StorylineFieldsSnapshot())
    assert plan is not None
    assert [c.field for c in plan.changes] == ["tagline"]


# ---- stat schema changes ----------------------------------------------------


def test_stat_add_is_schema_altering_and_carries_the_draft():
    raw = {
        "statChanges": [
            {
                "key": "resolve",
                "changeType": "add",
                "after": {"displayName": "Resolve", "min": 0, "max": 80, "default": 10},
                "rationale": "grit under pressure",
            }
        ]
    }
    plan = core._plan_from_raw(raw, _scope({"statistics"}), StorylineFieldsSnapshot())
    assert plan is not None
    change = plan.stat_changes[0]
    assert change.change_type == "add"
    assert change.schema_altering is True
    assert change.after.display_name == "Resolve"
    assert change.after.max == 80


def test_stat_update_range_is_flagged_and_merges_onto_existing():
    existing = StatDefinitionDraft(
        key="trust", display_name="Trust", min=0, max=100, default=50, description="baseline"
    )
    snap = StorylineFieldsSnapshot(stats=[existing])
    raw = {"statChanges": [{"key": "trust", "changeType": "update", "after": {"max": 80}}]}
    plan = core._plan_from_raw(raw, _scope({"statistics"}), snap)
    change = plan.stat_changes[0]
    assert change.schema_altering is True  # range moved
    # unspecified fields are preserved from the existing definition.
    assert change.after.max == 80
    assert change.after.display_name == "Trust"
    assert change.after.description == "baseline"


def test_stat_description_only_update_is_not_schema_altering():
    existing = StatDefinitionDraft(key="trust", display_name="Trust", description="old")
    snap = StorylineFieldsSnapshot(stats=[existing])
    raw = {"statChanges": [{"key": "trust", "changeType": "update", "after": {"description": "new"}}]}
    plan = core._plan_from_raw(raw, _scope({"statistics"}), snap)
    assert plan.stat_changes[0].schema_altering is False


def test_stat_noop_update_is_dropped():
    existing = StatDefinitionDraft(key="trust", display_name="Trust", description="same")
    snap = StorylineFieldsSnapshot(stats=[existing])
    raw = {"statChanges": [{"key": "trust", "changeType": "update", "after": {"description": "same"}}]}
    assert core._plan_from_raw(raw, _scope({"statistics"}), snap) is None


def test_stat_remove_is_schema_altering():
    snap = StorylineFieldsSnapshot(stats=[StatDefinitionDraft(key="trust", display_name="Trust")])
    raw = {"statChanges": [{"key": "trust", "changeType": "remove", "rationale": "unused"}]}
    plan = core._plan_from_raw(raw, _scope({"statistics"}), snap)
    change = plan.stat_changes[0]
    assert change.change_type == "remove"
    assert change.schema_altering is True


def test_stat_changes_dropped_when_statistics_not_writable():
    raw = {"statChanges": [{"key": "x", "changeType": "remove"}]}
    assert core._plan_from_raw(raw, _scope({"title"}), StorylineFieldsSnapshot()) is None
