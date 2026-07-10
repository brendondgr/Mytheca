"""Scope enforcement for the storyline editor — schema builder + diff guard.

These are the two load-bearing safety tests from the feature's validation gate:
the dynamic schema must omit non-scoped keys for *every* subset of the field set,
and the diff guard must reject a plan touching an out-of-scope field.
"""

from __future__ import annotations

from itertools import chain, combinations

import pytest

from app.agents.storyline_edit import scope as sc
from app.core.errors import APIError
from app.schemas.storyline_edit import (
    FIELD_CATALOG,
    FIELD_KEYS,
    FieldChange,
    FieldScope,
    ScopeState,
    StatChange,
    StatDefinitionDraft,
    StoryPlan,
)

TEXT_PRIMER_KEYS = {s.key for s in FIELD_CATALOG if s.kind in ("text", "primer")}
STAT_KEY = next(s.key for s in FIELD_CATALOG if s.kind == "stats")


def _scope(writable: set[str], readable: set[str] | None = None) -> ScopeState:
    read = readable if readable is not None else set(FIELD_KEYS)
    return {
        spec.key: FieldScope(writable=spec.key in writable, readable=spec.key in read)
        for spec in FIELD_CATALOG
    }


def _powerset(keys):
    ks = list(keys)
    return chain.from_iterable(combinations(ks, r) for r in range(len(ks) + 1))


# ---- writable / readable / changed ------------------------------------------


def test_writable_and_readable_keys_intersect_the_catalogue():
    scope = _scope({"title", "statistics"}, readable={"title", "premise"})
    # An unknown key in the scope object is ignored (never grants write).
    scope["bogus"] = FieldScope(writable=True, readable=True)
    assert sc.writable_keys(scope) == {"title", "statistics"}
    assert sc.readable_keys(scope) == {"title", "premise"}


def test_changed_fields_folds_stat_changes_to_statistics():
    plan = StoryPlan(
        changes=[FieldChange(field="title", after="New")],
        stat_changes=[StatChange(key="resolve", change_type="update")],
    )
    assert sc.changed_fields(plan) == {"title", "statistics"}


def test_changed_fields_ignores_unknown_field_keys():
    plan = StoryPlan(changes=[FieldChange(field="not_a_field", after="x")])
    assert sc.changed_fields(plan) == set()


# ---- diff guard (layer 3, load-bearing) -------------------------------------


def test_diff_guard_allows_in_scope_plan():
    scope = _scope({"tagline"})
    plan = StoryPlan(changes=[FieldChange(field="tagline", after="Tighter.")])
    sc.diff_guard(plan, scope)  # no raise


def test_diff_guard_rejects_out_of_scope_text_field():
    # Only statistics is writable, but the plan touches the premise.
    scope = _scope({"statistics"})
    plan = StoryPlan(changes=[FieldChange(field="premise", after="sneaky")])
    with pytest.raises(APIError) as exc:
        sc.diff_guard(plan, scope)
    assert exc.value.status_code == 422
    assert exc.value.code == "scope_violation"
    assert "premise" in exc.value.details["outside"]


def test_diff_guard_rejects_out_of_scope_statistics():
    scope = _scope({"title"})
    plan = StoryPlan(stat_changes=[StatChange(key="trust", change_type="add")])
    with pytest.raises(APIError):
        sc.diff_guard(plan, scope)


# ---- dynamic response schema (layer 1) --------------------------------------


def test_schema_always_has_message_and_optional_plan():
    schema = sc.response_schema_for(_scope(set()))
    assert schema["properties"]["message"] == {"type": "string"}
    assert schema["required"] == ["message"]
    assert schema["additionalProperties"] is False
    # No writable field → the plan object has only its "notes" escape hatch.
    assert set(schema["properties"]["plan"]["properties"]) == {"notes"}


@pytest.mark.parametrize("writable", list(_powerset(FIELD_KEYS)))
def test_schema_omits_non_scoped_keys_for_every_subset(writable):
    writable = set(writable)
    schema = sc.response_schema_for(_scope(writable))
    plan_props = set(schema["properties"]["plan"]["properties"])
    plan_props.discard("notes")

    expected = {k for k in writable & TEXT_PRIMER_KEYS}
    if STAT_KEY in writable:
        expected.add(sc.STAT_CHANGES_KEY)
    assert plan_props == expected
    # A non-writable field key is unrepresentable in the plan.
    for spec in FIELD_CATALOG:
        if spec.key not in writable:
            assert spec.key not in schema["properties"]["plan"]["properties"]


def test_plan_property_keys_maps_stats_to_stat_changes():
    keys = sc.plan_property_keys(_scope({"statistics", "title"}))
    assert keys == {"title", sc.STAT_CHANGES_KEY}


def test_stat_definition_draft_round_trips_bands():
    draft = StatDefinitionDraft(
        key="resolve",
        display_name="Resolve",
        min=0,
        max=80,
        default=40,
        bands=[{"min": 0, "max": 20, "label": "Broken"}],
    )
    assert draft.max == 80
    assert draft.bands[0].label == "Broken"
