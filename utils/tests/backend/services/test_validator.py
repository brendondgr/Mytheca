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


# ---- relationship changes (Reactive Turn Director P5) -------------------------

_CAST = [("mei", "Mei"), ("beth", "Beth")]


def test_validate_relationship_ok():
    p = validator.validate_relationship(
        "mei", '{"target":"Beth","type":"fears","reason":"an old debt"}', cast=_CAST
    )
    assert p is not None
    assert (p.source_id, p.type, p.target_id, p.reason) == ("mei", "fears", "beth", "an old debt")


def test_validate_relationship_fuzzy_target():
    p = validator.validate_relationship("mei", '{"target":"beth the smuggler","type":"trusts"}', cast=_CAST)
    assert p is not None and p.target_id == "beth"


def test_validate_relationship_unknown_type_dropped():
    assert validator.validate_relationship("mei", '{"target":"Beth","type":"despises"}', cast=_CAST) is None


def test_validate_relationship_unknown_target_dropped():
    assert validator.validate_relationship("mei", '{"target":"Nobody","type":"fears"}', cast=_CAST) is None


def test_validate_relationship_self_directed_dropped():
    assert validator.validate_relationship("mei", '{"target":"Mei","type":"loves"}', cast=_CAST) is None


def test_validate_relationship_malformed_dropped():
    assert validator.validate_relationship("mei", "not json at all", cast=_CAST) is None


def test_validate_presence_legal_transition():
    assert validator.validate_presence('{"status": "left", "reason": "storms out"}', current="present") == (
        "left",
        "storms out",
    )
    assert validator.validate_presence('{"status": "dead"}', current="unconscious") == ("dead", "")


def test_validate_presence_drops_noop_and_terminal_and_unknown():
    # No-op (same status), leaving a terminal status, and an unknown status are all dropped.
    assert validator.validate_presence('{"status": "present"}', current="present") is None
    assert validator.validate_presence('{"status": "present"}', current="dead") is None
    assert validator.validate_presence('{"status": "left"}', current="dead") is None
    assert validator.validate_presence('{"status": "vaporized"}', current="present") is None
    assert validator.validate_presence("not json", current="present") is None
