"""The write path: reflection's proposal → a verified, subject-tagged row in Postgres.

Covers the part of ``services.reflection`` that turns an optional ``memory`` object into a
``character_memories`` row — subject derivation, quote verification, speaker resolution,
its own database session, and the best-effort graph mirror.
"""

from __future__ import annotations

import pytest

from app.models import CharacterMemory
from app.services import events_store, memory_store, reflection
from app.services.reflection import MemoryContext


@pytest.fixture
def world(client, storyline_id):
    dell = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Dell"}).json()["id"]
    mara = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mara"}).json()["id"]
    setting = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "The Flooded Tunnel"}
    ).json()["id"]
    scenario = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Escape", "castIds": [dell, mara], "settingId": setting},
    ).json()["id"]
    return {
        "storyline_id": storyline_id, "dell": dell, "mara": mara,
        "setting": setting, "scenario": scenario,
    }


THE_LINE = "I'm not dying for your conscience."
BEAT = f'Mara turned back toward the cargo. "{THE_LINE}"'


def _ctx(world, session_id, **kw) -> MemoryContext:
    return MemoryContext(
        storyline_id=world["storyline_id"],
        scenario_id=world["scenario"],
        turn_seq=kw.pop("turn_seq", 4),
        participants=kw.pop("participants", [world["dell"], world["mara"]]),
        verify_texts=kw.pop("verify_texts", [BEAT]),
        known_entities=kw.pop("known_entities", [
            ("dell", "dell"), ("mara", "mara"), ("the flooded tunnel", "flooded-tunnel"),
        ]),
        setting_tag=kw.pop("setting_tag", "flooded-tunnel"),
    )


def _proposal(**kw) -> dict:
    base = {
        "gloss": "she went back for the cargo and left me under the water",
        "quote": THE_LINE,
        "quoteSpeaker": "Mara",
        "salience": 0.9,
        "valence": "wound",
        "subjects": ["drowning"],
    }
    base.update(kw)
    return base


# ---- subject derivation ------------------------------------------------------


def test_subjects_union_the_model_the_setting_and_who_was_named(world):
    """The deterministic half means a memory is findable even with no model tags at all."""
    tags = reflection.derive_subjects(["drowning"], _ctx(world, "ps1"))
    assert "drowning" in tags           # proposed
    assert "flooded-tunnel" in tags  # the setting, always
    assert "mara" in tags               # named in the prose


def test_a_character_not_named_in_the_prose_is_not_a_subject(world):
    tags = reflection.derive_subjects([], _ctx(world, "ps1"))
    assert "dell" not in tags


def test_subjects_survive_a_model_that_proposes_none(world):
    assert reflection.derive_subjects([], _ctx(world, "ps1")) == ["flooded-tunnel", "mara"]


def test_a_name_inside_a_longer_word_does_not_count_as_a_mention(world):
    ctx = _ctx(world, "ps1", verify_texts=["The maratime charter was signed."],
               known_entities=[("mara", "mara")], setting_tag="")
    assert reflection.derive_subjects([], ctx) == []


# ---- memory follows presence -------------------------------------------------


class _Member:
    def __init__(self, cid, name, present=True):
        self.id, self.name, self._present = cid, name, present

    @property
    def is_present(self):
        return self._present


class _Setting:
    name = "The Flooded Tunnel"


class _Scenario:
    def __init__(self, sid):
        self.id = sid


class _Ctx:
    def __init__(self, world, cast):
        self.storyline_id = world["storyline_id"]
        self.scenario = _Scenario(world["scenario"])
        self.cast = cast
        self.setting = _Setting()


def test_a_character_who_was_not_in_the_room_is_not_a_participant(db_session, world):
    """Memory follows presence.

    The rule that stops a character knowing something they were never told: a memory
    records who was actually there, and everything downstream — the participant cue, the
    quotable/shared/private class — is a set comparison against that list. Being *told*
    later is a different event with its own, weaker memory.
    """
    cast = [
        _Member(world["dell"], "Dell"),
        _Member(world["mara"], "Mara"),
        _Member("ch_absent", "Sera", present=False),
    ]
    mem_ctx = reflection.build_memory_context(db_session, _Ctx(world, cast), [{"text": BEAT}], 4)
    assert mem_ctx.participants == [world["dell"], world["mara"]]
    assert "ch_absent" not in mem_ctx.participants


def test_the_memory_context_reads_the_storyline_s_names_for_subject_matching(db_session, world):
    mem_ctx = reflection.build_memory_context(db_session, _Ctx(world, []), [{"text": BEAT}], 4)
    names = {name for name, _tag in mem_ctx.known_entities}
    assert {"dell", "mara", "the flooded tunnel"} <= names
    assert mem_ctx.setting_tag == "flooded-tunnel"


# ---- the write ---------------------------------------------------------------


def test_a_proposal_becomes_a_row_with_its_quote_and_speaker(db_session, world, monkeypatch):
    monkeypatch.setattr(reflection, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    s = events_store.create_session(db_session, world["scenario"])

    reflection.store_memory(s.id, world["dell"], _proposal(), _ctx(world, s.id))

    row = db_session.query(CharacterMemory).one()
    assert row.character_id == world["dell"]
    assert row.quote == THE_LINE
    assert row.quote_speaker_id == world["mara"]  # resolved from the name the model gave
    assert row.participants == [world["dell"], world["mara"]]
    assert "drowning" in row.subjects and "flooded-tunnel" in row.subjects
    assert row.valence == "wound" and row.salience == 0.9


def test_an_unverifiable_quote_is_stripped_before_it_reaches_the_row(db_session, world, monkeypatch):
    monkeypatch.setattr(reflection, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    s = events_store.create_session(db_session, world["scenario"])

    reflection.store_memory(
        s.id, world["dell"],
        _proposal(quote="You were never worth the trouble."),
        _ctx(world, s.id),
    )
    row = db_session.query(CharacterMemory).one()
    assert row.quote is None and row.quote_speaker_id is None
    assert row.gloss.startswith("she went back")


def test_a_quote_from_the_narrator_or_the_player_keeps_no_speaker_id(db_session, world, monkeypatch):
    """Not every quotable voice is a Character row, and that is not an error."""
    monkeypatch.setattr(reflection, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    s = events_store.create_session(db_session, world["scenario"])

    reflection.store_memory(
        s.id, world["dell"], _proposal(quoteSpeaker="the narrator"), _ctx(world, s.id)
    )
    row = db_session.query(CharacterMemory).one()
    assert row.quote == THE_LINE and row.quote_speaker_id is None


def test_a_shrug_is_rejected_and_writes_nothing(db_session, world, monkeypatch):
    monkeypatch.setattr(reflection, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    s = events_store.create_session(db_session, world["scenario"])

    reflection.store_memory(s.id, world["dell"], _proposal(salience=0.05), _ctx(world, s.id))
    assert db_session.query(CharacterMemory).count() == 0


def test_the_write_opens_its_own_session(world, monkeypatch):
    """The interlude runs on a background thread — there is no request Session to borrow."""
    opened = {"n": 0, "closed": 0}

    class _FakeSession:
        def __init__(self):
            opened["n"] += 1

        def query(self, *a, **k):
            raise RuntimeError("boom")

        def rollback(self):
            pass

        def close(self):
            opened["closed"] += 1

    monkeypatch.setattr(reflection, "SessionLocal", _FakeSession)
    reflection.store_memory("ps1", "ch_dell", _proposal(), _ctx(world, "ps1"))
    assert opened == {"n": 1, "closed": 1}


def test_a_failing_write_never_escapes(world, monkeypatch):
    """The turn was delivered long ago; one lost memory must not surface anywhere."""

    class _Boom:
        def query(self, *a, **k):
            raise RuntimeError("database gone")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(reflection, "SessionLocal", _Boom)
    reflection.store_memory("ps1", "ch_dell", _proposal(), _ctx(world, "ps1"))  # must not raise


def test_the_graph_mirror_is_attempted_and_is_not_load_bearing(db_session, world, monkeypatch):
    monkeypatch.setattr(reflection, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    seen: list[dict] = []
    monkeypatch.setattr(
        reflection.graph_writer, "mirror_memory_safe", lambda **kw: seen.append(kw)
    )
    s = events_store.create_session(db_session, world["scenario"])

    reflection.store_memory(s.id, world["dell"], _proposal(), _ctx(world, s.id))

    assert len(seen) == 1
    assert seen[0]["character_id"] == world["dell"]
    assert seen[0]["event_node_id"] == f"evt_{s.id}_4"
    # And the row is in Postgres regardless of what the graph did with it.
    assert db_session.query(CharacterMemory).count() == 1


def test_two_characters_may_remember_one_moment_differently(db_session, world, monkeypatch):
    """The contradiction the design is for: neither is lying, neither is a defect."""
    monkeypatch.setattr(reflection, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    s = events_store.create_session(db_session, world["scenario"])

    reflection.store_memory(s.id, world["dell"], _proposal(), _ctx(world, s.id))
    reflection.store_memory(
        s.id, world["mara"],
        _proposal(gloss="he was frozen and I had seconds; he shouted at me to go", quote=None),
        _ctx(world, s.id),
    )

    by_character = {m.character_id: m.gloss for m in db_session.query(CharacterMemory).all()}
    assert by_character[world["dell"]].startswith("she went back for the cargo")
    assert by_character[world["mara"]].startswith("he was frozen")


def test_recall_returns_only_the_asking_character_s_version(db_session, world, monkeypatch):
    """What makes the contradiction survive: the two versions never meet in one prompt."""
    monkeypatch.setattr(reflection, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    s = events_store.create_session(db_session, world["scenario"])
    reflection.store_memory(s.id, world["dell"], _proposal(), _ctx(world, s.id))
    reflection.store_memory(
        s.id, world["mara"], _proposal(gloss="he told me to go", quote=None), _ctx(world, s.id)
    )

    dell_sees = memory_store.visible_for(
        db_session, storyline_id=world["storyline_id"], session=s, character_ids=[world["dell"]]
    )
    assert [m.gloss for m in dell_sees] == ["she went back for the cargo and left me under the water"]
