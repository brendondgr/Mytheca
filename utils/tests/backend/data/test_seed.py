"""The Embergate seed matches the frontend and is idempotent."""

from __future__ import annotations

from app.core.seed import SEED_STORYLINE_ID, seed_if_empty
from app.models import Character, Scenario, Setting, StatDefinition, Storyline


def test_seed_populates_embergate(db_session):
    assert seed_if_empty(db_session) is True

    storyline = db_session.get(Storyline, SEED_STORYLINE_ID)
    assert storyline.title == "Embergate"
    assert storyline.premise and "\n\n" in storyline.premise  # multi-paragraph world
    assert db_session.query(Character).count() == 6
    assert db_session.query(Setting).count() == 5
    assert db_session.query(Scenario).count() == 3
    assert db_session.query(StatDefinition).count() == 4

    conspiracy = db_session.get(Scenario, "embergate")
    assert conspiracy.cast_ids == ["maerin", "aldous", "wren", "doran"]
    assert conspiracy.setting_id == "saltworn"
    assert conspiracy.branches[0]["tag"] == "check_request"  # tag preserved verbatim


def test_seed_is_idempotent(db_session):
    assert seed_if_empty(db_session) is True
    assert seed_if_empty(db_session) is False
    assert db_session.query(Character).count() == 6
