"""Recall: which memories reach a beat, and why.

Every assertion here is about **arithmetic**. The point of scoring being a pure function is
that an odd line in a live scene can be reproduced, so these tests hold the scorer to
behaviour a reader could predict rather than to whatever it happens to do.
"""

from __future__ import annotations

import pytest

from app.models import CharacterMemory
from app.services import memory_recall
from app.services.memory_recall import Recalled


def _mem(**kw) -> CharacterMemory:
    base = dict(
        id=kw.pop("id", "cm_1"),
        storyline_id="w1",
        character_id=kw.pop("character_id", "ch_dell"),
        session_id=kw.pop("session_id", "ps1"),
        scenario_id="sc1",
        turn_seq=kw.pop("turn_seq", 4),
        gloss=kw.pop("gloss", "she left me under the water"),
        quote=kw.pop("quote", None),
        salience=kw.pop("salience", 0.8),
        participants=kw.pop("participants", []),
        subjects=kw.pop("subjects", []),
        reinforcements=kw.pop("reinforcements", 0),
        last_recalled_seq=kw.pop("last_recalled_seq", None),
        last_recalled_session_id=kw.pop("last_recalled_session_id", None),
    )
    base.update(kw)
    return CharacterMemory(**base)


def _score(memory, *, now=10, session="ps1", present=(), cues=()) -> float:
    value, _ = memory_recall.score(
        memory, session_id=session, now_seq=now, present_ids=set(present), cues=set(cues)
    )
    return value


# ---- fade, reinforcement, presence -------------------------------------------


def test_a_memory_cools_as_the_scene_moves_on():
    fresh = _score(_mem(turn_seq=10), now=10)
    old = _score(_mem(turn_seq=10), now=90)
    assert old < fresh


def test_fade_never_reaches_zero():
    """A faded memory lingers rather than being forgotten — the registry's stated intent."""
    assert _score(_mem(turn_seq=0, salience=1.0), now=100_000) > 0


def test_reinforcement_keeps_a_grudge_hot_against_the_fade():
    picked_at = _mem(turn_seq=10, reinforcements=3)
    left_alone = _mem(turn_seq=10, reinforcements=0)
    assert _score(picked_at, now=60) > _score(left_alone, now=60)


def test_the_reinforcement_bonus_is_capped():
    """So one much-relived memory cannot monopolise every slot forever."""
    a = _score(_mem(reinforcements=3))
    b = _score(_mem(reinforcements=50))
    assert b == pytest.approx(a)


def test_someone_from_the_memory_being_in_the_room_lifts_it():
    with_mara = _score(_mem(participants=["ch_mara"]), present=["ch_mara"])
    alone = _score(_mem(participants=["ch_mara"]), present=[])
    assert with_mara - alone == pytest.approx(memory_recall.PARTICIPANT_BONUS)


def test_a_memory_from_another_scenario_is_only_gently_attenuated():
    """Recalling scene one during scene four is the feature, not an edge case to decay away.

    A per-turn decay curve cannot be applied across a session boundary anyway: seq numbers
    are per-session, so "how many turns ago" is undefined there.
    """
    other_scene = _score(_mem(session_id="ps_earlier"), now=500)
    assert other_scene == pytest.approx(0.8 * memory_recall.CROSS_SESSION_FADE)


# ---- cooldown ----------------------------------------------------------------


def test_a_memory_just_surfaced_is_pushed_down():
    """Without this the same memory wins every beat and the character says one thing."""
    just_used = _mem(last_recalled_seq=9, last_recalled_session_id="ps1")
    assert _score(just_used, now=10) < _score(_mem(), now=10)


def test_cooldown_expires():
    cooled = _mem(last_recalled_seq=1, last_recalled_session_id="ps1")
    assert _score(cooled, now=1 + memory_recall.COOLDOWN_TURNS) == pytest.approx(
        _score(_mem(turn_seq=4), now=1 + memory_recall.COOLDOWN_TURNS)
    )


def test_cooldown_does_not_leak_across_play_throughs():
    """A branch must not inherit the parent's idea of what was said recently."""
    used_elsewhere = _mem(last_recalled_seq=9, last_recalled_session_id="ps_other")
    assert _score(used_elsewhere, now=10) == pytest.approx(_score(_mem(), now=10))


# ---- ranking -----------------------------------------------------------------


def test_ranking_is_capped_and_ordered_by_score():
    rows = [
        _mem(id="cm_low", salience=0.4),
        _mem(id="cm_high", salience=0.95),
        _mem(id="cm_mid", salience=0.7),
    ]
    picked = memory_recall.rank(
        rows, session_id="ps1", now_seq=5, present_ids=set(), cues=set(), limit=2
    )
    assert [r.memory.id for r in picked] == ["cm_high", "cm_mid"]


def test_ties_break_deterministically_not_on_row_order():
    """The same scene replayed must not read differently for no findable reason."""
    a, b = _mem(id="cm_b"), _mem(id="cm_a")
    forward = memory_recall.rank([a, b], session_id="ps1", now_seq=5, present_ids=set(), cues=set())
    backward = memory_recall.rank([b, a], session_id="ps1", now_seq=5, present_ids=set(), cues=set())
    assert [r.memory.id for r in forward] == [r.memory.id for r in backward] == ["cm_a", "cm_b"]


def test_a_memory_below_the_bar_is_not_offered_at_all():
    faded = _mem(salience=0.36, turn_seq=0, last_recalled_seq=0, last_recalled_session_id="ps1")
    assert memory_recall.rank(
        [faded], session_id="ps1", now_seq=1, present_ids=set(), cues=set()
    ) == []


def test_cues_lift_a_memory_and_are_reported():
    """Phase 5 supplies the cues; the scorer already accounts for them."""
    value, hits = memory_recall.score(
        _mem(subjects=["ogres", "drowning"]),
        session_id="ps1", now_seq=5, present_ids=set(), cues={"ogres"},
    )
    assert hits == ["ogres"] and value > _score(_mem(subjects=["ogres"]))


# ---- the note that reaches the prompt ----------------------------------------


class _Ctx:
    def __init__(self, recalled):
        self.recalled = recalled
        self.cast = []


def _note(items):
    from app.services import beat_runner

    return beat_runner.memory_note(_Ctx({"ch_dell": items}), "ch_dell")


def test_no_memories_means_no_prompt_change_at_all():
    """The kill switch and an empty store must be indistinguishable from no feature."""
    from app.services import beat_runner

    assert _note([]) == ""
    assert beat_runner.memory_note(_Ctx({}), "ch_dell") == ""


def test_a_quote_reaches_the_prompt_verbatim_with_permission_to_use_it():
    note = _note([Recalled(memory=_mem(quote="I'm not dying for your conscience."), score=1.0)])
    assert '"I\'m not dying for your conscience."' in note
    assert "you may quote this back" in note


def test_only_one_verbatim_quote_reaches_a_beat():
    """Two callbacks and the character becomes someone who only speaks in flashback."""
    note = _note([
        Recalled(memory=_mem(id="cm_1", quote="First line."), score=2.0),
        Recalled(memory=_mem(id="cm_2", gloss="another thing", quote="Second line."), score=1.0),
    ])
    assert note.count("you may quote this back") == 1
    assert "First line." in note and "Second line." not in note
    assert "another thing" in note  # the second memory still lands, just without its quote


def test_the_note_is_capped():
    items = [Recalled(memory=_mem(id=f"cm_{i}", gloss=f"thing {i}"), score=1.0) for i in range(5)]
    bullets = [ln for ln in _note(items).splitlines() if ln.startswith("- ")]
    assert len(bullets) == memory_recall.PER_SPEAKER_LIMIT


def test_the_note_marks_the_memories_private_and_not_for_recap():
    """A model handed context without a job will summarise it back at the reader."""
    note = _note([Recalled(memory=_mem(), score=1.0)])
    assert "yours alone" in note and "not narration" in note


# ---- the semantic channel, and its gate --------------------------------------


class _Session:
    id = "ps1"
    scenario_id = "sc1"
    parent_session_id = None
    fork_seq = None
    updated_at = None


def _rows(monkeypatch, rows):
    from app.services import memory_store

    monkeypatch.setattr(memory_store, "visible_for", lambda *a, **k: rows)


def test_the_semantic_channel_stays_shut_when_the_tags_already_fired(monkeypatch):
    """The gate, and the whole cost story of this channel.

    It answers "did the dictionary miss?", and the dictionary having matched is a direct
    answer to that — so a second opinion on memories the tags already found is never bought.
    """
    _rows(monkeypatch, [_mem(subjects=["ogres"])])
    called = {"n": 0}
    monkeypatch.setattr(
        memory_recall, "semantic_boosts", lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {}
    )
    memory_recall.recall_for_turn(
        None, storyline_id="w1", session=_Session(), speaker_ids=["ch_dell"],
        present_ids=["ch_dell"], now_seq=5, scene_texts=["An ogre steps out."],
    )
    assert called["n"] == 0


def test_the_semantic_channel_fires_when_no_tag_matched(monkeypatch):
    _rows(monkeypatch, [_mem(subjects=["drowning"])])
    seen: list[str] = []

    def _boosts(db, *, storyline_id, query, candidate_ids):
        seen.append(query)
        return {"cm_1": 0.3}

    monkeypatch.setattr(memory_recall, "semantic_boosts", _boosts)
    memory_recall.recall_for_turn(
        None, storyline_id="w1", session=_Session(), speaker_ids=["ch_dell"],
        present_ids=["ch_dell"], now_seq=5, scene_texts=["The water is high tonight."],
    )
    assert seen and "water is high" in seen[0]


def test_the_semantic_channel_can_be_switched_off_entirely(monkeypatch):
    _rows(monkeypatch, [_mem(subjects=["drowning"])])
    called = {"n": 0}
    monkeypatch.setattr(
        memory_recall, "semantic_boosts", lambda *a, **k: called.__setitem__("n", 1) or {}
    )
    memory_recall.recall_for_turn(
        None, storyline_id="w1", session=_Session(), speaker_ids=["ch_dell"],
        present_ids=["ch_dell"], now_seq=5, scene_texts=["The water is high."], semantic=False,
    )
    assert called["n"] == 0


def test_a_semantic_hit_lifts_a_memory_the_tags_could_not_reach(monkeypatch):
    """The "water's high tonight" case: nobody from that night is here and no tag matches."""
    _rows(monkeypatch, [_mem(id="cm_far", salience=0.15, subjects=["drowning"], turn_seq=0)])
    monkeypatch.setattr(memory_recall, "semantic_boosts", lambda *a, **k: {"cm_far": 0.4})
    out = memory_recall.recall_for_turn(
        None, storyline_id="w1", session=_Session(), speaker_ids=["ch_dell"],
        present_ids=["ch_dell"], now_seq=5, scene_texts=["The water is high tonight."],
    )
    assert [r.memory.id for r in out["ch_dell"]] == ["cm_far"]


def test_without_the_boost_that_same_memory_is_below_the_bar(monkeypatch):
    """The other half of the pair. Both use the same faint memory on purpose: if it cleared
    MIN_SCORE on its own, the test above would pass whether the boost did anything or not."""
    _rows(monkeypatch, [_mem(id="cm_far", salience=0.15, subjects=["drowning"], turn_seq=0)])
    monkeypatch.setattr(memory_recall, "semantic_boosts", lambda *a, **k: {})
    out = memory_recall.recall_for_turn(
        None, storyline_id="w1", session=_Session(), speaker_ids=["ch_dell"],
        present_ids=["ch_dell"], now_seq=5, scene_texts=["The water is high tonight."],
    )
    assert out["ch_dell"] == []


def test_semantic_boosts_ignore_hits_outside_this_turn_s_candidates():
    """The corpus holds settings and documents too; only a candidate memory may be lifted."""

    class _Hit:
        def __init__(self, entry_id):
            self.entry_id = entry_id

    import app.rag.retriever as retriever_mod

    original = retriever_mod.retrieve
    retriever_mod.retrieve = lambda *a, **k: [_Hit("st_setting"), _Hit("cm_1")]
    try:
        boosts = memory_recall.semantic_boosts(
            None, storyline_id="w1", query="water", candidate_ids={"cm_1"}
        )
    finally:
        retriever_mod.retrieve = original
    assert set(boosts) == {"cm_1"}


def test_a_store_that_is_down_leaves_recall_exactly_as_it_was():
    import app.rag.retriever as retriever_mod

    original = retriever_mod.retrieve

    def _boom(*a, **k):
        raise RuntimeError("qdrant down")

    retriever_mod.retrieve = _boom
    try:
        assert memory_recall.semantic_boosts(
            None, storyline_id="w1", query="water", candidate_ids={"cm_1"}
        ) == {}
    finally:
        retriever_mod.retrieve = original
