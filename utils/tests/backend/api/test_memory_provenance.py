"""The per-beat "where did this come from?" read.

Player-facing by design: the moment, the words, where to find it, and whether anyone
remembers it differently. Engine internals (scores, fade, cue hits) stay in the Inspector.
"""

from __future__ import annotations

import pytest

from app.models import Event
from app.services import events_store, memory_store
from app.services.memory_store import MemoryDraft


@pytest.fixture
def scene(client, db_session, storyline_id):
    dell = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Dell"}).json()["id"]
    mara = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mara"}).json()["id"]
    setting = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Tunnel"}).json()["id"]
    scenario = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "The Flooded Tunnel", "castIds": [dell, mara], "settingId": setting},
    ).json()["id"]
    session = events_store.create_session(db_session, scenario)
    return {
        "storyline_id": storyline_id, "dell": dell, "mara": mara,
        "scenario": scenario, "session": session,
    }


def _memory(db, scene, *, character_id, gloss, quote=None, speaker=None, turn_seq=0):
    row = memory_store.write(
        db,
        MemoryDraft(
            storyline_id=scene["storyline_id"], character_id=character_id,
            session_id=scene["session"].id, scenario_id=scene["scenario"],
            turn_seq=turn_seq, gloss=gloss, quote=quote, quote_speaker_id=speaker,
            salience=0.9, participants=[scene["dell"], scene["mara"]],
        ),
        verify_texts=['Mara turned away. "I am not dying for your conscience."'],
    )
    db.commit()
    return row


def _beat(db, scene, *, seq, recalled):
    row = Event(
        type="character_prose", seq=seq, scenario_id=scene["scenario"],
        session_id=scene["session"].id, visibility="public",
        data={"characterId": scene["dell"], "text": "He said nothing.", "done": True,
              "recalled": recalled},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _get(client, scene, event_id):
    return client.get(
        f"/api/play/{scene['scenario']}/sessions/{scene['session'].id}/beats/{event_id}/memory"
    )


def test_a_beat_reports_the_memory_it_was_written_with(client, db_session, scene):
    memory = _memory(
        db_session, scene, character_id=scene["dell"],
        gloss="she went back for the cargo", quote="I am not dying for your conscience.",
        speaker=scene["mara"],
    )
    beat = _beat(db_session, scene, seq=5, recalled=[memory.id])

    body = _get(client, scene, beat.id).json()
    assert body["eventId"] == beat.id
    row = body["memories"][0]
    assert row["characterName"] == "Dell"
    assert row["gloss"] == "she went back for the cargo"
    assert row["quote"] == "I am not dying for your conscience."
    assert row["quoteSpeakerName"] == "Mara"
    assert row["scenarioTitle"] == "The Flooded Tunnel"
    assert row["inThisSession"] is True


def test_a_beat_with_no_memory_behind_it_is_not_an_error(client, db_session, scene):
    """"This line came from nowhere in particular" is a real and common answer."""
    beat = _beat(db_session, scene, seq=5, recalled=[])
    resp = _get(client, scene, beat.id)
    assert resp.status_code == 200
    assert resp.json()["memories"] == []


def test_a_contradicting_memory_of_the_same_moment_is_reported(client, db_session, scene):
    """Without this, two characters disagreeing reads as the app losing track."""
    dell = _memory(
        db_session, scene, character_id=scene["dell"], turn_seq=2,
        gloss="she walked away and left me under the water",
    )
    _memory(
        db_session, scene, character_id=scene["mara"], turn_seq=2,
        gloss="he was frozen and he shouted at me to go",
    )
    beat = _beat(db_session, scene, seq=6, recalled=[dell.id])

    row = _get(client, scene, beat.id).json()["memories"][0]
    assert [c["characterName"] for c in row["contradictedBy"]] == ["Mara"]
    assert row["contradictedBy"][0]["gloss"].startswith("he was frozen")


def test_agreement_is_not_reported_as_contradiction(client, db_session, scene):
    dell = _memory(
        db_session, scene, character_id=scene["dell"], turn_seq=2,
        gloss="she went back for the cargo and left me under the water",
    )
    _memory(
        db_session, scene, character_id=scene["mara"], turn_seq=2,
        gloss="she left me under the water and went back for the cargo",
    )
    beat = _beat(db_session, scene, seq=6, recalled=[dell.id])
    assert _get(client, scene, beat.id).json()["memories"][0]["contradictedBy"] == []


def test_a_beat_from_another_play_through_is_a_404(client, db_session, scene):
    other = events_store.create_session(db_session, scene["scenario"])
    row = Event(
        type="character_prose", seq=0, scenario_id=scene["scenario"],
        session_id=other.id, visibility="public", data={"text": "x", "recalled": []},
    )
    db_session.add(row)
    db_session.commit()
    assert _get(client, scene, row.id).status_code == 404


def test_an_unknown_beat_is_a_404(client, scene):
    assert _get(client, scene, "ev_nope").status_code == 404


def test_a_dropped_memory_id_does_not_break_the_read(client, db_session, scene):
    """A rewind deletes memories; a beat that survived it must still answer."""
    memory = _memory(db_session, scene, character_id=scene["dell"], gloss="kept")
    beat = _beat(db_session, scene, seq=5, recalled=[memory.id, "cm_deleted"])
    body = _get(client, scene, beat.id).json()
    assert [m["id"] for m in body["memories"]] == [memory.id]
