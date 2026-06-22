"""ORM models: relations, JSON round-trip, uniqueness, and cascade delete."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Character,
    CharacterStat,
    Scenario,
    Setting,
    StatDefinition,
    Storyline,
)


def _embergate() -> Storyline:
    sl = Storyline(id="embergate", title="Embergate", genre="Maritime Intrigue")
    sl.characters.append(Character(id="maerin", name="Maerin Voss", mono="MV", position=0))
    sl.settings.append(
        Setting(id="saltworn", name="The Saltworn Tavern", type="Social Hub", desc="Lamplit.")
    )
    sl.scenarios.append(
        Scenario(
            id="embergate-sc",
            title="The Embergate Conspiracy",
            cast_ids=["maerin"],
            setting_id="saltworn",
            branches=[{"label": "Confront", "check": "Insight", "outcome": "x", "tag": "check_request"}],
        )
    )
    sl.stat_definitions.append(
        StatDefinition(key="health", display_name="Health", min=0, max=100, default=100)
    )
    return sl


def test_children_and_json_round_trip(db_session):
    db_session.add(_embergate())
    db_session.commit()

    sl = db_session.get(Storyline, "embergate")
    assert [c.name for c in sl.characters] == ["Maerin Voss"]
    sc = sl.scenarios[0]
    assert sc.cast_ids == ["maerin"]
    assert sc.setting_id == "saltworn"
    assert sc.branches[0]["tag"] == "check_request"  # JSON survived the round trip
    assert sl.stat_definitions[0].applies_to == ["character"]  # default callable


def test_stat_definition_unique_per_storyline(db_session):
    db_session.add(_embergate())
    db_session.commit()
    db_session.add(StatDefinition(storyline_id="embergate", key="health", display_name="Dup"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_character_stat_unique_per_character(db_session):
    db_session.add(_embergate())
    db_session.commit()
    db_session.add_all(
        [
            CharacterStat(character_id="maerin", key="health", value=80),
            CharacterStat(character_id="maerin", key="health", value=20),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_delete_storyline_cascades(db_session):
    db_session.add(_embergate())
    db_session.commit()
    db_session.add(CharacterStat(character_id="maerin", key="health", value=80))
    db_session.commit()

    db_session.delete(db_session.get(Storyline, "embergate"))
    db_session.commit()

    assert db_session.query(Character).count() == 0
    assert db_session.query(Setting).count() == 0
    assert db_session.query(Scenario).count() == 0
    assert db_session.query(StatDefinition).count() == 0
    assert db_session.query(CharacterStat).count() == 0  # via character cascade
