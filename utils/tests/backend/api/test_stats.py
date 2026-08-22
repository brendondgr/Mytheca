"""Stat definitions + clamped character values over the API."""

from __future__ import annotations


def _define_health(client, storyline_id, **over):
    body = {"key": "health", "displayName": "Health", "min": 0, "max": 100, "default": 100}
    body.update(over)
    return client.post(f"/api/storylines/{storyline_id}/stats", json=body)


def test_define_list_and_clamp(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Maerin"}).json()["id"]

    created = _define_health(client, storyline_id)
    assert created.status_code == 201
    assert created.json()["displayName"] == "Health" and created.json()["appliesTo"] == ["character"]

    assert [s["key"] for s in client.get(f"/api/storylines/{storyline_id}/stats").json()] == ["health"]

    # Values are clamped to [min, max] at both ends.
    assert client.put(f"/api/characters/{cid}/stats", json={"health": 250}).json() == {"health": 100}
    assert client.put(f"/api/characters/{cid}/stats", json={"health": -40}).json() == {"health": 0}
    assert client.get(f"/api/characters/{cid}/stats").json() == {"health": 0}


def test_reject_unknown_stat_key(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "X"}).json()["id"]
    r = client.put(f"/api/characters/{cid}/stats", json={"ghost": 5})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_stat"


def test_duplicate_stat_key_conflicts(client, storyline_id):
    _define_health(client, storyline_id)
    assert _define_health(client, storyline_id, displayName="Dup").status_code == 409


def test_range_freely_editable_and_reclamps(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "R"}).json()["id"]
    _define_health(client, storyline_id)
    client.put(f"/api/characters/{cid}/stats", json={"health": 90})

    # Range is now freely editable — narrowing it re-clamps existing values.
    patched = client.patch(
        f"/api/storylines/{storyline_id}/stats/health",
        json={"displayName": "Vitality", "min": 50, "max": 60},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["displayName"] == "Vitality" and body["min"] == 50 and body["max"] == 60
    # The character's 90 was pulled back into the new [50, 60] range.
    assert client.get(f"/api/characters/{cid}/stats").json() == {"health": 60}


def test_invalid_range_rejected_on_create(client, storyline_id):
    r = _define_health(client, storyline_id, key="bad", min=10, max=5, default=7)
    assert r.status_code == 422


def test_invalid_range_rejected_on_patch(client, storyline_id):
    _define_health(client, storyline_id)
    r = client.patch(
        f"/api/storylines/{storyline_id}/stats/health", json={"min": 80, "max": 50}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_range"


def test_bands_roundtrip_and_validate(client, storyline_id):
    bands = [
        {"min": 0, "max": 20, "label": "Nearly dead", "description": "{Character} can barely stand."},
        {"min": 81, "max": 100, "label": "Very healthy"},
    ]
    created = _define_health(client, storyline_id, bands=bands)
    assert created.status_code == 201
    # The read always carries an explicit per-band description (default "" when omitted).
    assert created.json()["bands"] == [
        {"min": 0, "max": 20, "label": "Nearly dead", "description": "{Character} can barely stand."},
        {"min": 81, "max": 100, "label": "Very healthy", "description": ""},
    ]

    # Bands (incl. their descriptions) are editable via PATCH.
    new_bands = [{"min": 0, "max": 100, "label": "Alive", "description": "{Character} lives."}]
    patched = client.patch(
        f"/api/storylines/{storyline_id}/stats/health", json={"bands": new_bands}
    )
    assert patched.status_code == 200 and patched.json()["bands"] == new_bands

    # A band with min > max or a blank label is rejected.
    bad = _define_health(client, storyline_id, key="b2", bands=[{"min": 50, "max": 10, "label": "x"}])
    assert bad.status_code == 422
    blank = _define_health(client, storyline_id, key="b3", bands=[{"min": 0, "max": 5, "label": " "}])
    assert blank.status_code == 422


def test_delete_stat_prunes_character_values(client, storyline_id):
    cid = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "D"}).json()["id"]
    _define_health(client, storyline_id)
    client.put(f"/api/characters/{cid}/stats", json={"health": 50})
    assert client.get(f"/api/characters/{cid}/stats").json() == {"health": 50}

    assert client.delete(f"/api/storylines/{storyline_id}/stats/health").status_code == 204
    # Definition gone, and the character's value for it was pruned.
    assert [s["key"] for s in client.get(f"/api/storylines/{storyline_id}/stats").json()] == []
    assert client.get(f"/api/characters/{cid}/stats").json() == {}
    # Deleting a missing stat is a 404.
    assert client.delete(f"/api/storylines/{storyline_id}/stats/health").status_code == 404


# ---- the authored baseline, and getting back to it --------------------------


def _world_with_stat(client, storyline_id, *, carry: bool):
    client.post(
        f"/api/storylines/{storyline_id}/stats",
        json={
            "key": "trust",
            "displayName": "Trust",
            "min": 0,
            "max": 100,
            "default": 50,
            "carryOver": carry,
        },
    )
    return client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]


def test_an_authoring_write_sets_the_baseline_too(client, storyline_id, db_session):
    from app.models import CharacterStat

    cid = _world_with_stat(client, storyline_id, carry=False)
    client.put(f"/api/characters/{cid}/stats", json={"trust": 70})

    row = db_session.query(CharacterStat).filter_by(character_id=cid, key="trust").one()
    assert (row.value, row.baseline) == (70, 70)


def test_carry_forward_captures_the_baseline_once_and_never_again(
    client, storyline_id, db_session
):
    """A second capture would overwrite the baseline with the first carry's result, and
    "back to how they were written" would drift a scene at a time until it meant nothing."""
    from app.models import CharacterStat
    from app.services import session_stats

    cid = _world_with_stat(client, storyline_id, carry=True)
    client.put(f"/api/characters/{cid}/stats", json={"trust": 70})
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "S", "castIds": [cid], "settingId": sid},
    ).json()["id"]

    first = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]
    session_stats.apply(db_session, first, cid, {"trust": 20})
    session_stats.carry_forward(db_session, first)

    row = db_session.query(CharacterStat).filter_by(character_id=cid, key="trust").one()
    assert (row.value, row.baseline) == (20, 70)

    second = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]
    session_stats.apply(db_session, second, cid, {"trust": 5})
    session_stats.carry_forward(db_session, second)

    db_session.refresh(row)
    assert (row.value, row.baseline) == (5, 70)  # still the AUTHORED value


def test_reset_restores_the_authored_value(client, storyline_id, db_session):
    from app.services import session_stats

    cid = _world_with_stat(client, storyline_id, carry=True)
    client.put(f"/api/characters/{cid}/stats", json={"trust": 70})
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "S", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    ps = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]
    session_stats.apply(db_session, ps, cid, {"trust": 20})
    session_stats.carry_forward(db_session, ps)
    assert client.get(f"/api/characters/{cid}/stats").json()["trust"] == 20

    assert client.post(f"/api/characters/{cid}/stats/reset").json()["trust"] == 70
    assert client.get(f"/api/characters/{cid}/stats").json()["trust"] == 70


def test_resetting_a_never_played_character_is_a_no_op(client, storyline_id):
    """Safe to call on a whole cast without knowing what any of them have been through."""
    cid = _world_with_stat(client, storyline_id, carry=False)
    client.put(f"/api/characters/{cid}/stats", json={"trust": 70})

    assert client.post(f"/api/characters/{cid}/stats/reset").json()["trust"] == 70


def test_reset_404s_for_an_unknown_character(client):
    assert client.post("/api/characters/nope/stats/reset").status_code == 404


def test_re_authoring_moves_the_baseline_with_the_value(client, storyline_id, db_session):
    """The author redefining what a character starts with makes the old baseline describe a
    value nobody chose any more."""
    from app.models import CharacterStat
    from app.services import session_stats

    cid = _world_with_stat(client, storyline_id, carry=True)
    client.put(f"/api/characters/{cid}/stats", json={"trust": 70})
    sid = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "S", "castIds": [cid], "settingId": sid},
    ).json()["id"]
    ps = client.post(f"/api/play/{scid}/sessions", json={}).json()["id"]
    session_stats.apply(db_session, ps, cid, {"trust": 20})
    session_stats.carry_forward(db_session, ps)

    client.put(f"/api/characters/{cid}/stats", json={"trust": 35})

    row = db_session.query(CharacterStat).filter_by(character_id=cid, key="trust").one()
    assert (row.value, row.baseline) == (35, 35)
