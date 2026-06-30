"""Turn-loop validator — stat change parse, validate, clamp, reason; unknown dropped."""

from __future__ import annotations

from app.models import Character, Storyline
from app.models.stat import CharacterStat, StatDefinition
from app.services import validator


def _world(db) -> None:
    db.add(Storyline(id="w1", title="W"))
    db.commit()
    db.add(
        StatDefinition(
            storyline_id="w1", key="suspicion", display_name="Suspicion", min=0, max=100, default=50
        )
    )
    db.add(Character(id="c_kira", storyline_id="w1", name="Kira"))
    db.commit()


def test_delta_applied_and_reason_kept(db_session):
    _world(db_session)
    db_session.add(CharacterStat(character_id="c_kira", key="suspicion", value=55))
    db_session.commit()
    patch = validator.validate_stat(
        db_session, "w1", "c_kira", '{"key":"suspicion","delta":12,"reason":"old guilt"}'
    )
    assert patch is not None
    assert patch.value == 67 and patch.delta == 12 and patch.reason == "old guilt"


def test_clamps_to_max(db_session):
    _world(db_session)
    db_session.add(CharacterStat(character_id="c_kira", key="suspicion", value=95))
    db_session.commit()
    patch = validator.validate_stat(db_session, "w1", "c_kira", '{"key":"suspicion","delta":20}')
    assert patch is not None
    assert patch.value == 100 and patch.delta == 5  # 95+20 → clamp 100; delta = 100-95


def test_explicit_value_clamped_against_default(db_session):
    _world(db_session)  # no stat row → current = the definition default (50)
    patch = validator.validate_stat(db_session, "w1", "c_kira", '{"key":"suspicion","value":200}')
    assert patch is not None
    assert patch.value == 100 and patch.delta == 50


def test_unknown_stat_is_dropped(db_session):
    _world(db_session)
    assert validator.validate_stat(db_session, "w1", "c_kira", '{"key":"mana","delta":5}') is None


def test_malformed_or_no_change_dropped(db_session):
    _world(db_session)
    assert validator.validate_stat(db_session, "w1", "c_kira", "not json at all") is None
    assert validator.validate_stat(db_session, "w1", "c_kira", '{"key":"suspicion"}') is None
