"""Storyline apply service — diff guard, transactional writes, stale reconcile.

Exercises ``storyline_apply.apply_plan`` directly against the in-memory DB.
"""

from __future__ import annotations

import pytest

from app.core.errors import APIError
from app.schemas.stat import StatDefinitionCreate
from app.schemas.storyline import StorylineCreate
from app.schemas.storyline_edit import (
    FIELD_CATALOG,
    FieldChange,
    FieldScope,
    StatChange,
    StatDefinitionDraft,
    StoryPlan,
)
from app.services import crud, stats, storyline_apply


def _scope(writable: set[str]):
    return {s.key: FieldScope(writable=s.key in writable, readable=True) for s in FIELD_CATALOG}


def _storyline(db):
    return crud.create_storyline(
        db,
        StorylineCreate(
            id="w1",
            title="Old Title",
            genre="Old Genre",
            tagline="Old tag",
            premise="Old premise",
            world_primer="Old primer",
        ),
    )


# ---- text/primer -------------------------------------------------------------


def test_single_field_edit_leaves_the_others_byte_identical(db_session):
    sl = _storyline(db_session)
    plan = StoryPlan(changes=[FieldChange(field="tagline", after="Every secret has a price.")])
    result, applied = storyline_apply.apply_plan(db_session, sl.id, _scope({"tagline"}), plan, None)
    assert result.tagline == "Every secret has a price."
    assert result.title == "Old Title"
    assert result.genre == "Old Genre"
    assert result.premise == "Old premise"
    assert result.world_primer == "Old primer"
    assert applied == ["Updated tagline"]


def test_apply_rejects_out_of_scope_even_when_handcrafted(db_session):
    sl = _storyline(db_session)
    # The schema layer is bypassed — a hand-crafted plan touches an unscoped field.
    plan = StoryPlan(changes=[FieldChange(field="premise", after="sneaky")])
    with pytest.raises(APIError) as exc:
        storyline_apply.apply_plan(db_session, sl.id, _scope({"tagline"}), plan, None)
    assert exc.value.code == "scope_violation"
    db_session.refresh(sl)
    assert sl.premise == "Old premise"  # nothing written


# ---- statistics (via the clamped stat services) -----------------------------


def test_stat_add(db_session):
    sl = _storyline(db_session)
    plan = StoryPlan(
        stat_changes=[
            StatChange(
                key="resolve",
                change_type="add",
                after=StatDefinitionDraft(key="resolve", display_name="Resolve", min=0, max=80, default=10),
            )
        ]
    )
    _result, applied = storyline_apply.apply_plan(db_session, sl.id, _scope({"statistics"}), plan, None)
    defs = stats.list_stat_definitions(db_session, sl.id)
    assert [d.key for d in defs] == ["resolve"]
    assert defs[0].max == 80
    assert "Added stat resolve" in applied


def test_stat_update_range_clamps_default(db_session):
    sl = _storyline(db_session)
    stats.create_stat_definition(
        db_session,
        sl.id,
        StatDefinitionCreate(key="trust", display_name="Trust", min=0, max=100, default=90),
    )
    plan = StoryPlan(
        stat_changes=[
            StatChange(
                key="trust",
                change_type="update",
                after=StatDefinitionDraft(key="trust", display_name="Trust", min=0, max=50, default=90),
            )
        ]
    )
    storyline_apply.apply_plan(db_session, sl.id, _scope({"statistics"}), plan, None)
    d = stats.list_stat_definitions(db_session, sl.id)[0]
    assert d.max == 50
    assert d.default == 50  # clamped into the new range, not written raw


def test_stat_remove(db_session):
    sl = _storyline(db_session)
    stats.create_stat_definition(
        db_session, sl.id, StatDefinitionCreate(key="trust", display_name="Trust", min=0, max=100, default=50)
    )
    plan = StoryPlan(stat_changes=[StatChange(key="trust", change_type="remove")])
    _result, applied = storyline_apply.apply_plan(db_session, sl.id, _scope({"statistics"}), plan, None)
    assert stats.list_stat_definitions(db_session, sl.id) == []
    assert "Removed stat trust" in applied


def test_invalid_stat_rolls_back_the_whole_plan(db_session):
    sl = _storyline(db_session)
    plan = StoryPlan(
        changes=[FieldChange(field="tagline", after="New tag")],  # valid text change
        stat_changes=[
            StatChange(
                key="good",
                change_type="add",
                after=StatDefinitionDraft(key="good", display_name="Good", min=0, max=10, default=5),
            ),
            StatChange(  # invalid: min >= max → rejected by StatDefinitionCreate
                key="bad",
                change_type="add",
                after=StatDefinitionDraft(key="bad", display_name="Bad", min=50, max=10, default=0),
            ),
        ],
    )
    with pytest.raises(APIError) as exc:
        storyline_apply.apply_plan(db_session, sl.id, _scope({"tagline", "statistics"}), plan, None)
    assert exc.value.code == "invalid_stat"
    db_session.refresh(sl)
    assert sl.tagline == "Old tag"  # text change rolled back
    assert stats.list_stat_definitions(db_session, sl.id) == []  # valid stat rolled back too


# ---- stale-read reconcile ----------------------------------------------------


def test_stale_base_version_is_rejected_then_correct_one_applies(db_session):
    sl = _storyline(db_session)
    plan = StoryPlan(changes=[FieldChange(field="tagline", after="New")])
    with pytest.raises(APIError) as exc:
        storyline_apply.apply_plan(db_session, sl.id, _scope({"tagline"}), plan, base_version="deadbeef")
    assert exc.value.code == "stale_storyline"
    db_session.refresh(sl)
    assert sl.tagline == "Old tag"  # nothing overwritten

    good = storyline_apply.storyline_version(db_session, sl, {"tagline"})
    result, _applied = storyline_apply.apply_plan(db_session, sl.id, _scope({"tagline"}), plan, base_version=good)
    assert result.tagline == "New"


def test_version_narrows_to_writable_fields(db_session):
    sl = _storyline(db_session)
    v_tagline = storyline_apply.storyline_version(db_session, sl, {"tagline"})
    # Changing the premise does not move the tagline-only version.
    sl.premise = "changed"
    db_session.commit()
    assert storyline_apply.storyline_version(db_session, sl, {"tagline"}) == v_tagline
