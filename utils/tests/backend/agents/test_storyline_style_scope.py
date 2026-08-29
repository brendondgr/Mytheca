"""The storyline assistant editing the NARRATIVE STYLE GUIDE.

Style is its own field kind rather than six text fields, and it travels as `styleChanges`
the way statistics travel as `statChanges`. What matters here is the same thing that matters
for stats: an approved change to one block must not silently take the other five with it,
and nothing outside the author's approved scope may be written at all.
"""

from __future__ import annotations

from app.agents.storyline_edit import core, scope as sc
from app.core.errors import APIError
from app.models.storyline import Storyline
from app.schemas.storyline_edit import (
    FieldScope,
    StorylineFieldsSnapshot,
    StoryPlan,
    StyleChange,
)
from app.services import storyline_apply

import pytest

STYLE = "styleBlocks"


def _scope(**writable) -> dict:
    return {k: FieldScope(writable=v, readable=True) for k, v in writable.items()}


def _fields(**blocks) -> StorylineFieldsSnapshot:
    return StorylineFieldsSnapshot(title="W", style_blocks=dict(blocks))


def _parse(raw: dict, scope: dict, fields: StorylineFieldsSnapshot) -> StoryPlan | None:
    return core._plan_from_raw(raw, scope, fields)


# ---- parsing -----------------------------------------------------------------------


def test_a_style_change_is_parsed_with_its_before_value():
    plan = _parse(
        {"styleChanges": [{"block": "voice", "after": "Clipped.", "rationale": "colder"}]},
        _scope(styleBlocks=True),
        _fields(voice="Plain."),
    )
    assert [(c.block, c.before, c.after) for c in plan.style_changes] == [
        ("voice", "Plain.", "Clipped.")
    ]


def test_a_null_after_is_a_removal_not_a_no_op():
    plan = _parse(
        {"styleChanges": [{"block": "never", "after": None}]},
        _scope(styleBlocks=True),
        _fields(never="No recaps."),
    )
    assert [(c.block, c.before, c.after) for c in plan.style_changes] == [
        ("never", "No recaps.", None)
    ]


def test_setting_a_block_to_what_it_already_says_is_not_a_change():
    """Otherwise the author is asked to approve a diff that does nothing."""
    plan = _parse(
        {"styleChanges": [{"block": "voice", "after": "Plain."}]},
        _scope(styleBlocks=True),
        _fields(voice="Plain."),
    )
    assert plan is None or not plan.style_changes


def test_an_unknown_block_id_is_dropped_rather_than_fatal():
    plan = _parse(
        {"styleChanges": [{"block": "cadence", "after": "x"}, {"block": "voice", "after": "y"}]},
        _scope(styleBlocks=True),
        _fields(),
    )
    assert [c.block for c in plan.style_changes] == ["voice"]


def test_style_changes_are_dropped_when_style_is_not_writable():
    plan = _parse(
        {"styleChanges": [{"block": "voice", "after": "Clipped."}]},
        _scope(styleBlocks=False, title=True),
        _fields(voice="Plain."),
    )
    assert plan is None or not plan.style_changes


# ---- the diff guard ----------------------------------------------------------------


def test_the_diff_guard_rejects_a_style_change_outside_scope():
    plan = StoryPlan(style_changes=[StyleChange(block="voice", after="Clipped.")])
    with pytest.raises(APIError) as err:
        sc.diff_guard(plan, _scope(title=True))
    assert err.value.status_code == 422


def test_the_diff_guard_allows_it_in_scope():
    plan = StoryPlan(style_changes=[StyleChange(block="voice", after="Clipped.")])
    sc.diff_guard(plan, _scope(styleBlocks=True))  # no raise


# ---- read context ------------------------------------------------------------------


def test_the_agent_sees_the_guide_block_by_block():
    text = core._current_values(_scope(styleBlocks=True), _fields(voice="Plain.", never="No."))
    assert "Narrative style / voice: Plain." in text
    assert "Narrative style / never: No." in text


def test_an_empty_guide_says_so_rather_than_going_missing():
    assert "(no guide yet)" in core._current_values(_scope(styleBlocks=True), _fields())


# ---- apply -------------------------------------------------------------------------


def test_applying_one_block_leaves_the_others_alone(db_session):
    sl = Storyline(id="s1", title="W", style_blocks={"voice": "Plain.", "never": "No recaps."})
    db_session.add(sl)
    db_session.commit()

    plan = StoryPlan(style_changes=[StyleChange(block="voice", after="Clipped.")])
    fresh, applied = storyline_apply.apply_plan(db_session, "s1", _scope(styleBlocks=True), plan, None)
    assert fresh.style_blocks == {"voice": "Clipped.", "never": "No recaps."}
    assert applied == ["Updated narrative style / voice"]


def test_applying_a_removal_drops_only_that_block(db_session):
    sl = Storyline(id="s2", title="W", style_blocks={"voice": "Plain.", "never": "No recaps."})
    db_session.add(sl)
    db_session.commit()

    plan = StoryPlan(style_changes=[StyleChange(block="never", after=None)])
    fresh, applied = storyline_apply.apply_plan(db_session, "s2", _scope(styleBlocks=True), plan, None)
    assert fresh.style_blocks == {"voice": "Plain."}
    assert applied == ["Removed narrative style / never"]


def test_removing_the_last_block_leaves_no_guide(db_session):
    sl = Storyline(id="s3", title="W", style_blocks={"voice": "Plain."})
    db_session.add(sl)
    db_session.commit()

    plan = StoryPlan(style_changes=[StyleChange(block="voice", after=None)])
    fresh, _ = storyline_apply.apply_plan(db_session, "s3", _scope(styleBlocks=True), plan, None)
    assert not fresh.style_blocks


def test_the_version_token_covers_the_guide(db_session):
    """Without this, two assistants editing the guide would both pass the staleness check."""
    sl = Storyline(id="s4", title="W", style_blocks={"voice": "Plain."})
    db_session.add(sl)
    db_session.commit()

    before = storyline_apply.storyline_version(db_session, sl, {STYLE})
    sl.style_blocks = {"voice": "Clipped."}
    db_session.commit()
    assert storyline_apply.storyline_version(db_session, sl, {STYLE}) != before
