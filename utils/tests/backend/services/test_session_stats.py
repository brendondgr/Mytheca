"""Session-scoped stat values (owner decision D-1).

Before this, a stat value was global to a character: two play-throughs of one scenario
shared a health value, a branch inherited whatever the last one had done, and a rewind could
only reconcile to whichever session happened to be open.

The contract these pin down:
  * a play-through starts from the character's **authored** value (not the definition
    default, and not another play-through's state);
  * a change inside a play-through stays there;
  * `carry_over` moves a value onto the character when the play-through **closes**, and
    nothing else does.
"""

from __future__ import annotations

import pytest

from app.models import CharacterStat, SessionCharacterStat
from app.services import events_store, session_stats, stats


@pytest.fixture
def world(client, storyline_id):
    """A storyline with two stats — one that carries between scenes, one that does not."""
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={"key": "health", "displayName": "Health", "min": 0, "max": 100, "default": 100},
    )
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={"key": "trust", "displayName": "Trust", "min": 0, "max": 100, "default": 50},
    )
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    return {"storyline_id": storyline_id, "character_id": cid, "scenario_id": scid}


def _mark_carry_over(db, storyline_id, key, value=True):
    from sqlalchemy import select

    from app.models import StatDefinition

    d = db.scalars(
        select(StatDefinition).where(
            StatDefinition.storyline_id == storyline_id, StatDefinition.key == key
        )
    ).first()
    d.carry_over = value
    db.commit()


# ---- baseline -------------------------------------------------------------


def test_baseline_uses_the_definition_default_when_the_character_has_no_value(db_session, world):
    values = session_stats.baseline(db_session, world["character_id"])
    assert values["health"] == 100
    assert values["trust"] == 50


def test_baseline_prefers_the_characters_authored_value(db_session, world):
    """The authored starting value is what the author said this character begins with.
    A play-through that ignored it would open contradicting its own world."""
    stats.set_character_stats(db_session, world["character_id"], {"health": 40})
    assert session_stats.baseline(db_session, world["character_id"])["health"] == 40


def test_baseline_is_not_conditioned_on_carry_over(db_session, world):
    """`carry_over` governs the write-back, never the starting point."""
    stats.set_character_stats(db_session, world["character_id"], {"health": 40})
    _mark_carry_over(db_session, world["storyline_id"], "health", False)
    assert session_stats.baseline(db_session, world["character_id"])["health"] == 40


# ---- resolve / apply ------------------------------------------------------


def test_resolve_without_a_session_is_the_baseline(db_session, world):
    stats.set_character_stats(db_session, world["character_id"], {"health": 70})
    assert session_stats.resolve(db_session, None, world["character_id"])["health"] == 70


def test_apply_writes_into_the_play_through_only(db_session, world):
    session = events_store.create_session(db_session, world["scenario_id"])
    session_stats.apply(db_session, session.id, world["character_id"], {"health": 30})

    assert session_stats.resolve(db_session, session.id, world["character_id"])["health"] == 30
    # The character's authored baseline is untouched — this is the whole point.
    assert stats.get_character_stats(db_session, world["character_id"]).get("health") is None


def test_two_play_throughs_do_not_share_a_value(db_session, world):
    a = events_store.create_session(db_session, world["scenario_id"])
    b = events_store.create_session(db_session, world["scenario_id"])
    session_stats.apply(db_session, a.id, world["character_id"], {"health": 10})

    assert session_stats.resolve(db_session, a.id, world["character_id"])["health"] == 10
    assert session_stats.resolve(db_session, b.id, world["character_id"])["health"] == 100


def test_apply_clamps_to_the_definition_range(db_session, world):
    session = events_store.create_session(db_session, world["scenario_id"])
    session_stats.apply(db_session, session.id, world["character_id"], {"health": 9999})
    assert session_stats.resolve(db_session, session.id, world["character_id"])["health"] == 100
    session_stats.apply(db_session, session.id, world["character_id"], {"health": -50})
    assert session_stats.resolve(db_session, session.id, world["character_id"])["health"] == 0


def test_apply_drops_an_unknown_key_rather_than_raising(db_session, world):
    """This runs on the turn path, where the proposer is a language model: a bad key must
    cost a dropped change, not the turn."""
    session = events_store.create_session(db_session, world["scenario_id"])
    out = session_stats.apply(db_session, session.id, world["character_id"], {"mana": 5})
    assert "mana" not in out


# ---- copy / clear ---------------------------------------------------------


def test_copy_forks_the_values(db_session, world):
    a = events_store.create_session(db_session, world["scenario_id"])
    b = events_store.create_session(db_session, world["scenario_id"])
    session_stats.apply(db_session, a.id, world["character_id"], {"health": 33})

    assert session_stats.copy(db_session, a.id, b.id) == 1
    assert session_stats.resolve(db_session, b.id, world["character_id"])["health"] == 33

    # Diverging afterwards leaves the source alone.
    session_stats.apply(db_session, b.id, world["character_id"], {"health": 5})
    assert session_stats.resolve(db_session, a.id, world["character_id"])["health"] == 33


def test_clear_returns_the_play_through_to_the_baseline(db_session, world):
    stats.set_character_stats(db_session, world["character_id"], {"health": 80})
    session = events_store.create_session(db_session, world["scenario_id"])
    session_stats.apply(db_session, session.id, world["character_id"], {"health": 12})

    assert session_stats.clear(db_session, session.id) == 1
    assert session_stats.resolve(db_session, session.id, world["character_id"])["health"] == 80


# ---- carry_forward --------------------------------------------------------


def test_carry_forward_moves_only_the_stats_marked_to_carry(db_session, world):
    _mark_carry_over(db_session, world["storyline_id"], "health", True)
    session = events_store.create_session(db_session, world["scenario_id"])
    session_stats.apply(
        db_session, session.id, world["character_id"], {"health": 25, "trust": 90}
    )

    session_stats.carry_forward(db_session, session.id)

    baseline = stats.get_character_stats(db_session, world["character_id"])
    assert baseline["health"] == 25          # carries
    assert "trust" not in baseline           # does not


def test_closing_a_play_through_carries_forward(db_session, world):
    """`carry_over` has exactly one moment: the play-through ending."""
    _mark_carry_over(db_session, world["storyline_id"], "health", True)
    session = events_store.create_session(db_session, world["scenario_id"])
    session_stats.apply(db_session, session.id, world["character_id"], {"health": 44})

    assert stats.get_character_stats(db_session, world["character_id"]).get("health") is None
    events_store.close_session(db_session, session.id)
    assert stats.get_character_stats(db_session, world["character_id"])["health"] == 44


def test_carry_forward_is_idempotent(db_session, world):
    _mark_carry_over(db_session, world["storyline_id"], "health", True)
    session = events_store.create_session(db_session, world["scenario_id"])
    session_stats.apply(db_session, session.id, world["character_id"], {"health": 44})

    session_stats.carry_forward(db_session, session.id)
    session_stats.carry_forward(db_session, session.id)

    rows = db_session.query(CharacterStat).filter(
        CharacterStat.character_id == world["character_id"], CharacterStat.key == "health"
    ).all()
    assert len(rows) == 1 and rows[0].value == 44


def test_carry_forward_on_an_untouched_play_through_does_nothing(db_session, world):
    session = events_store.create_session(db_session, world["scenario_id"])
    assert session_stats.carry_forward(db_session, session.id) == {}


def test_deleting_a_play_through_takes_its_stat_rows(db_session, world):
    session = events_store.create_session(db_session, world["scenario_id"])
    session_stats.apply(db_session, session.id, world["character_id"], {"health": 10})

    events_store.delete_session(db_session, session.id)

    remaining = db_session.query(SessionCharacterStat).filter(
        SessionCharacterStat.session_id == session.id
    ).count()
    assert remaining == 0
