"""Episodic memory persistence: the four rules that live in ``services.memory_store``.

Fully offline — the suite's in-memory SQLite is the whole story, which is the point of
memory being canonical in Postgres rather than in the best-effort graph.
"""

from __future__ import annotations

import pytest

from app.models import CharacterMemory, PlaySession
from app.services import events_store, memory_store
from app.services.memory_store import MemoryDraft


@pytest.fixture
def world(client, storyline_id):
    dell = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Dell"}).json()["id"]
    mara = client.post(f"/api/storylines/{storyline_id}/characters", json={"name": "Mara"}).json()["id"]
    setting = client.post(f"/api/storylines/{storyline_id}/settings", json={"name": "Tunnel"}).json()["id"]
    tunnel = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "The Flooded Tunnel", "castIds": [dell, mara], "settingId": setting},
    ).json()["id"]
    market = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "The Harbour Market", "castIds": [dell, mara], "settingId": setting},
    ).json()["id"]
    return {
        "storyline_id": storyline_id, "dell": dell, "mara": mara,
        "tunnel": tunnel, "market": market,
    }


def _draft(world, *, session_id, scenario_id=None, character_id=None, **kw) -> MemoryDraft:
    base = dict(
        storyline_id=world["storyline_id"],
        character_id=character_id or world["dell"],
        session_id=session_id,
        scenario_id=scenario_id or world["tunnel"],
        turn_seq=kw.pop("turn_seq", 4),
        gloss=kw.pop("gloss", "she went back for the cargo and left me under the water"),
        salience=kw.pop("salience", 0.9),
    )
    base.update(kw)
    return MemoryDraft(**base)


THE_LINE = "I'm not dying for your conscience."
TRANSCRIPT = [f'Mara: "{THE_LINE}" She turned back toward the cargo.']


# ---- subject normalization ---------------------------------------------------


def test_subjects_fold_to_one_spelling():
    """A tag nobody can spell twice is a tag that never fires in the cue scan.

    The leading article matters more than it looks: a live run returned one place as
    ``tunnel``, ``the-tunnel``, ``flooded-tunnel`` and ``the-flooded-tunnel`` across eight
    memories, and the setting's own name goes through this same function — so folding the
    article is what makes the deterministic tag and the model's tag agree.
    """
    assert memory_store.normalize_subject("the Flooded Tunnel") == "flooded-tunnel"
    assert memory_store.normalize_subject("flooded tunnel!") == "flooded-tunnel"
    assert memory_store.normalize_subjects(["Ogres", "ogres", "  ", "Ogres!"]) == ["ogres"]


def test_folding_the_article_does_not_eat_a_word_that_starts_with_it():
    assert memory_store.normalize_subject("theatre") == "theatre"
    assert memory_store.normalize_subject("Theodore") == "theodore"


# ---- rule 1: a quote must be real --------------------------------------------


def test_a_verified_quote_is_kept(db_session, world):
    s = events_store.create_session(db_session, world["tunnel"])
    row = memory_store.write(
        db_session,
        _draft(world, session_id=s.id, quote=THE_LINE, quote_speaker_id=world["mara"]),
        verify_texts=TRANSCRIPT,
    )
    assert row is not None and row.quote == THE_LINE
    assert row.quote_speaker_id == world["mara"]


def test_an_invented_quote_is_dropped_but_the_memory_is_kept(db_session, world):
    """A character quoting a line nobody said reads as the engine losing track.

    The gloss is still this character's own reading of the moment and is worth keeping;
    only the claim to have heard specific words is unsupported.
    """
    row = memory_store.write(
        db_session,
        _draft(
            world,
            session_id=events_store.create_session(db_session, world["tunnel"]).id,
            quote="I never wanted you here in the first place.",
            quote_speaker_id=world["mara"],
        ),
        verify_texts=TRANSCRIPT,
    )
    assert row is not None
    assert row.quote is None and row.quote_speaker_id is None
    assert row.gloss.startswith("she went back for the cargo")


def test_quote_verification_tolerates_reflowed_whitespace_and_wrapping_quotes():
    assert memory_store.quote_is_real('"I\'m not dying\n  for your conscience."', TRANSCRIPT)
    assert not memory_store.quote_is_real("I am not dying for your conscience.", TRANSCRIPT)
    assert not memory_store.quote_is_real("", TRANSCRIPT)
    assert not memory_store.quote_is_real(None, TRANSCRIPT)


def test_narration_is_not_quotable_however_real_its_words_are():
    """Found in a live run, not reasoned about.

    A character came back "quoting" *"The current grabs my ankle, cold and slick, and pulls
    me sideways"* — every word of it in the turn's prose, and none of it said by anyone. A
    substring check over the whole passage accepts that; requiring the match to land inside
    a span of quoted speech does not.
    """
    passage = ["The current grabs Dell's ankle, cold and slick, and pulls him sideways."]
    assert not memory_store.quote_is_real("The current grabs Dell's ankle", passage)
    assert memory_store.quote_is_real(
        "Hold on to me.", ['He got a hand under the beam. "Hold on to me."']
    )


def test_curly_quotes_count_as_speech():
    assert memory_store.quote_is_real("Leave the ledger.", ["She said \u201cLeave the ledger.\u201d"])


# ---- rule 2: reinforce, don't duplicate --------------------------------------


def test_a_recurring_moment_reinforces_instead_of_inserting(db_session, world):
    s = events_store.create_session(db_session, world["tunnel"])
    first = memory_store.write(db_session, _draft(world, session_id=s.id), verify_texts=TRANSCRIPT)
    db_session.commit()
    again = memory_store.write(
        db_session,
        _draft(
            world, session_id=s.id, turn_seq=9,
            gloss="she left me under the water and went back for the cargo",
            subjects=["mara"],
        ),
        verify_texts=TRANSCRIPT,
    )
    db_session.commit()
    assert again is not None and again.id == first.id
    assert again.reinforcements == 1 and again.turn_seq == 9
    assert db_session.query(CharacterMemory).count() == 1


def test_the_same_moment_with_its_clauses_swapped_still_matches():
    """Character-sequence similarity alone scores this pair 0.49 — plainly wrong."""
    assert memory_store._same_moment(
        "she went back for the cargo and left me under the water",
        "she left me under the water and went back for the cargo",
    )


def test_a_small_rewording_of_the_same_moment_matches():
    assert memory_store._same_moment(
        "she left me under the water", "she left me in the water"
    )


def test_two_similar_but_distinct_moments_stay_apart():
    """Two different lies must not collapse into one memory."""
    assert not memory_store._same_moment(
        "he lied to me about the gate", "he lied to me about the coin"
    )
    assert not memory_store._same_moment("she saved my life", "she nearly took my life")
    assert not memory_store._same_moment("", "he lied to me")


def test_an_unresolvable_pair_is_left_as_two_rows_not_merged():
    """Pins the deliberate bias, so nobody "fixes" it by loosening the thresholds.

    "chose"/"picked the cargo" (0.873) is the same moment reworded and *should* merge;
    "gate"/"coin" (0.857) is two moments and should not. No threshold separates them, so
    the tie breaks toward keeping both: a duplicate costs a redundant row that cooldown
    suppresses, a wrong merge destroys a memory.
    """
    assert not memory_store._same_moment(
        "she chose the cargo over me", "she picked the cargo over me"
    )


def test_a_different_moment_is_its_own_row(db_session, world):
    s = events_store.create_session(db_session, world["tunnel"])
    memory_store.write(db_session, _draft(world, session_id=s.id), verify_texts=TRANSCRIPT)
    memory_store.write(
        db_session,
        _draft(world, session_id=s.id, gloss="she shared her last ration with me", salience=0.4),
        verify_texts=TRANSCRIPT,
    )
    db_session.commit()
    assert db_session.query(CharacterMemory).count() == 2


def test_a_recurrence_can_upgrade_a_missing_quote_but_never_blank_one(db_session, world):
    s = events_store.create_session(db_session, world["tunnel"])
    first = memory_store.write(db_session, _draft(world, session_id=s.id), verify_texts=TRANSCRIPT)
    db_session.commit()
    assert first.quote is None

    memory_store.write(
        db_session,
        _draft(world, session_id=s.id, quote=THE_LINE, quote_speaker_id=world["mara"]),
        verify_texts=TRANSCRIPT,
    )
    db_session.commit()
    assert first.quote == THE_LINE

    memory_store.write(db_session, _draft(world, session_id=s.id), verify_texts=TRANSCRIPT)
    db_session.commit()
    assert first.quote == THE_LINE  # a quote already earned is never lost


def test_the_salience_floor_rejects_a_shrug(db_session, world):
    s = events_store.create_session(db_session, world["tunnel"])
    assert memory_store.write(
        db_session, _draft(world, session_id=s.id, salience=0.1), verify_texts=TRANSCRIPT
    ) is None
    assert memory_store.write(
        db_session, _draft(world, session_id=s.id, gloss="   "), verify_texts=TRANSCRIPT
    ) is None
    db_session.commit()
    assert db_session.query(CharacterMemory).count() == 0


# ---- rule 3: recall is lineage-scoped ----------------------------------------


def _fork(db, parent: PlaySession, scenario_id: str, at_seq: int) -> PlaySession:
    child = PlaySession(scenario_id=scenario_id, parent_session_id=parent.id, fork_seq=at_seq)
    db.add(child)
    db.commit()
    db.refresh(child)
    return child


def test_a_branch_inherits_its_parent_only_up_to_the_fork(db_session, world):
    """The road not taken must not be remembered.

    Without the cap a fork recalls memories from a timeline the player deliberately
    walked away from — the same class of leak the rewind path had to close.
    """
    parent = events_store.create_session(db_session, world["tunnel"])
    memory_store.write(
        db_session, _draft(world, session_id=parent.id, turn_seq=2, gloss="before the fork"),
        verify_texts=TRANSCRIPT,
    )
    memory_store.write(
        db_session, _draft(world, session_id=parent.id, turn_seq=8, gloss="after the fork"),
        verify_texts=TRANSCRIPT,
    )
    db_session.commit()
    child = _fork(db_session, parent, world["tunnel"], at_seq=5)

    glosses = [
        m.gloss for m in memory_store.visible_for(
            db_session, storyline_id=world["storyline_id"], session=child,
            character_ids=[world["dell"]],
        )
    ]
    assert glosses == ["before the fork"]


def test_lineage_caps_compound_across_nested_forks(db_session, world):
    grand = events_store.create_session(db_session, world["tunnel"])
    child = _fork(db_session, grand, world["tunnel"], at_seq=3)
    grandchild = _fork(db_session, child, world["tunnel"], at_seq=10)
    caps = memory_store.lineage_caps(db_session, grandchild)
    assert caps == [(grandchild.id, None), (child.id, 10), (grand.id, 3)]


def test_lineage_walk_survives_a_cycle(db_session, world):
    a = events_store.create_session(db_session, world["tunnel"])
    b = _fork(db_session, a, world["tunnel"], at_seq=2)
    a.parent_session_id = b.id  # not reachable in the app; the guard must hold anyway
    a.fork_seq = 1
    db_session.add(a)
    db_session.commit()
    assert [sid for sid, _ in memory_store.lineage_caps(db_session, b)] == [b.id, a.id]


def test_a_prior_scenario_is_remembered_whole(db_session, world):
    """The premise of the feature: scene one is still there in scene four."""
    tunnel_session = events_store.create_session(db_session, world["tunnel"])
    memory_store.write(
        db_session,
        _draft(world, session_id=tunnel_session.id, turn_seq=6, gloss="the tunnel"),
        verify_texts=TRANSCRIPT,
    )
    db_session.commit()
    market_session = events_store.create_session(db_session, world["market"])

    glosses = [
        m.gloss for m in memory_store.visible_for(
            db_session, storyline_id=world["storyline_id"], session=market_session,
            character_ids=[world["dell"]],
        )
    ]
    assert glosses == ["the tunnel"]


def test_only_the_latest_play_through_of_a_prior_scenario_counts(db_session, world):
    """Interim rule for plan gap G2 — see ``_other_scenario_sessions``."""
    old = events_store.create_session(db_session, world["tunnel"])
    memory_store.write(
        db_session, _draft(world, session_id=old.id, gloss="the first time we played it"),
        verify_texts=TRANSCRIPT,
    )
    db_session.commit()
    replay = events_store.create_session(db_session, world["tunnel"])
    memory_store.write(
        db_session, _draft(world, session_id=replay.id, gloss="the way it went the second time"),
        verify_texts=TRANSCRIPT,
    )
    db_session.commit()

    market_session = events_store.create_session(db_session, world["market"])
    glosses = [
        m.gloss for m in memory_store.visible_for(
            db_session, storyline_id=world["storyline_id"], session=market_session,
            character_ids=[world["dell"]],
        )
    ]
    assert glosses == ["the way it went the second time"]


def test_recall_never_reaches_another_character(db_session, world):
    s = events_store.create_session(db_session, world["tunnel"])
    memory_store.write(
        db_session, _draft(world, session_id=s.id, character_id=world["mara"], gloss="mara's own"),
        verify_texts=TRANSCRIPT,
    )
    db_session.commit()
    assert memory_store.visible_for(
        db_session, storyline_id=world["storyline_id"], session=s,
        character_ids=[world["dell"]],
    ) == []


def test_visible_for_is_a_single_query(db_session, world):
    """Recall runs once per turn for every planned speaker — not once per beat."""
    from sqlalchemy import event as sa_event

    s = events_store.create_session(db_session, world["tunnel"])
    memory_store.write(db_session, _draft(world, session_id=s.id), verify_texts=TRANSCRIPT)
    db_session.commit()

    selects: list[str] = []

    def _count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "character_memories" in statement:
            selects.append(statement)

    sa_event.listen(db_session.bind, "before_cursor_execute", _count)
    try:
        memory_store.visible_for(
            db_session, storyline_id=world["storyline_id"], session=s,
            character_ids=[world["dell"], world["mara"]],
        )
    finally:
        sa_event.remove(db_session.bind, "before_cursor_execute", _count)
    assert len(selects) == 1


def test_visible_for_with_no_characters_asks_nothing(db_session, world):
    s = events_store.create_session(db_session, world["tunnel"])
    assert memory_store.visible_for(
        db_session, storyline_id=world["storyline_id"], session=s, character_ids=[]
    ) == []


# ---- rule 4: a rewind forgets transactionally --------------------------------


def test_delete_after_forgets_only_the_cut_turns(db_session, world):
    s = events_store.create_session(db_session, world["tunnel"])
    memory_store.write(
        db_session, _draft(world, session_id=s.id, turn_seq=2, gloss="kept"), verify_texts=TRANSCRIPT
    )
    memory_store.write(
        db_session, _draft(world, session_id=s.id, turn_seq=7, gloss="cut away"), verify_texts=TRANSCRIPT
    )
    db_session.commit()

    assert memory_store.delete_after(db_session, s.id, after_seq=4) == 1
    db_session.commit()
    assert [m.gloss for m in db_session.query(CharacterMemory).all()] == ["kept"]


def test_mark_recalled_stamps_the_clock_cooldown_and_fade_read(db_session, world):
    s = events_store.create_session(db_session, world["tunnel"])
    row = memory_store.write(db_session, _draft(world, session_id=s.id), verify_texts=TRANSCRIPT)
    db_session.commit()
    memory_store.mark_recalled(db_session, [row.id], session_id=s.id, seq=11)
    db_session.commit()
    assert row.last_recalled_seq == 11 and row.last_recalled_session_id == s.id
