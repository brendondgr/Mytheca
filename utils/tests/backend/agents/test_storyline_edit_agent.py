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


def test_band_description_merge_keeps_min_max_and_is_not_dropped():
    # Regression: adding band descriptions while sending only label+description per band
    # must NOT drop the whole change (previously bands were wholesale-replaced, so the
    # missing min/max failed StatBand validation and the stat change vanished).
    existing = StatDefinitionDraft(
        key="syth",
        display_name="Syth",
        min=0,
        max=100,
        default=50,
        bands=[
            {"min": 0, "max": 30, "label": "Faint"},
            {"min": 31, "max": 70, "label": "Present"},
            {"min": 71, "max": 100, "label": "Overwhelming"},
        ],
    )
    snap = StorylineFieldsSnapshot(stats=[existing])
    raw = {
        "statChanges": [
            {
                "key": "syth",
                "changeType": "update",
                "after": {
                    "bands": [
                        {"label": "Faint", "description": "{Character} barely senses it."},
                        {"label": "Present", "description": "{Character} feels it clearly."},
                        {"label": "Overwhelming", "description": "{Character} is consumed by it."},
                    ]
                },
            }
        ]
    }
    plan = core._plan_from_raw(raw, _scope({"statistics"}), snap)
    assert plan is not None  # not silently dropped
    bands = plan.stat_changes[0].after.bands
    assert [b.label for b in bands] == ["Faint", "Present", "Overwhelming"]
    assert (bands[0].min, bands[0].max) == (0, 30)  # preserved from the existing band
    assert bands[0].description == "{Character} barely senses it."
    assert plan.stat_changes[0].schema_altering is False  # range unchanged


def test_band_merge_by_index_when_labels_absent():
    existing = StatDefinitionDraft(
        key="hp",
        display_name="HP",
        bands=[{"min": 0, "max": 50, "label": "Low"}, {"min": 51, "max": 100, "label": "High"}],
    )
    snap = StorylineFieldsSnapshot(stats=[existing])
    raw = {
        "statChanges": [
            {"key": "hp", "changeType": "update", "after": {"bands": [{"description": "d1"}, {"description": "d2"}]}}
        ]
    }
    plan = core._plan_from_raw(raw, _scope({"statistics"}), snap)
    bands = plan.stat_changes[0].after.bands
    assert bands[0].label == "Low" and bands[0].description == "d1"
    assert bands[1].label == "High" and bands[1].description == "d2"


def test_stat_changes_accepts_snake_case_key():
    snap = StorylineFieldsSnapshot(stats=[StatDefinitionDraft(key="trust", display_name="Trust")])
    raw = {"stat_changes": [{"key": "trust", "changeType": "remove"}]}
    plan = core._plan_from_raw(raw, _scope({"statistics"}), snap)
    assert plan is not None and plan.stat_changes[0].change_type == "remove"


# ---- context-file grounding in the system prompt ----------------------------


def test_build_system_folds_in_the_selected_context_files():
    from app.agents._common import docs_block

    grounding = docs_block("### tide-charts.md\nThe harbour drowns at every ninth bell.")
    system = core._build_system("persona", _scope({"title"}), StorylineFieldsSnapshot(), grounding)
    assert "ninth bell" in system
    assert "tide-charts.md" in system


def test_build_system_omits_the_grounding_block_when_no_files_are_selected():
    from app.agents._common import docs_block

    system = core._build_system("persona", _scope({"title"}), StorylineFieldsSnapshot(), docs_block(""))
    assert "Reference notes from dropped files" not in system
