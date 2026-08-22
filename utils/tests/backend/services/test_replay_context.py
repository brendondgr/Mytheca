"""The context a re-rolled beat is generated against.

``turn_setup.context_for_replay`` exists to rebuild what a beat *originally* saw, and its
``turn_beats`` half is careful about it — it walks the persisted rows rather than the
Redis buffer, precisely so the re-run cannot see past the target. The window half was not:
``recent_beats`` came from a plain ``assemble_context``, which reads the live buffer, and
the buffer still holds the beat being replaced and everything after it.

The visible symptom is a re-roll that continues the line it was asked to replace instead
of writing another one. These tests pin the window to the same boundary the beats already
respect.
"""

from __future__ import annotations

import json

import pytest

from app.memory import buffer
from app.models import Event, Scenario
from app.services import assembler, events_store, session_state, turn_setup


class _FakeRedis:
    """The list ops the recent-turn buffer uses, in memory (mirrors test_buffer.py)."""

    def __init__(self) -> None:
        self.store: dict[str, list[str]] = {}

    def lpush(self, key: str, *vals: str) -> int:
        lst = self.store.setdefault(key, [])
        for v in vals:
            lst.insert(0, v)
        return len(lst)

    def ltrim(self, key: str, start: int, end: int) -> None:
        lst = self.store.get(key, [])
        self.store[key] = lst[start:] if end == -1 else lst[start : end + 1]

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        lst = self.store.get(key, [])
        return lst[start:] if end == -1 else lst[start : end + 1]

    def expire(self, key: str, ttl: int) -> None:
        pass

    def llen(self, key: str) -> int:
        return len(self.store.get(key, []))

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.fixture
def scene(client, storyline_id, db_session, monkeypatch):
    """A three-turn play-through with its Redis buffer populated from the rows."""
    # ONE fake, not one per call — `lambda: _FakeRedis()` hands every helper a fresh empty
    # store, so the buffer reads back as though Redis were off and the trim has nothing to
    # trim. (Cost: the first version of this fixture, and five confusing failures.)
    fake = _FakeRedis()
    monkeypatch.setattr(buffer, "_redis", lambda: fake)

    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    setting = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "Hearth"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid], "settingId": setting},
    ).json()["id"]
    session = events_store.create_session(db_session, scid)

    rows: list[Event] = []
    plan = [
        (0, "user_turn", {"text": "First line.", "pov": None}),
        (1, "character_prose", {"characterId": cid, "text": "ALPHA the first beat.", "done": True}),
        (2, "user_turn", {"text": "Second line.", "pov": None}),
        (3, "character_prose", {"characterId": cid, "text": "BRAVO the second beat.", "done": True}),
        (4, "narration", {"text": "CHARLIE the lamp gutters.", "done": True}),
    ]
    for seq, type_, data in plan:
        row = Event(type=type_, seq=seq, scenario_id=scid, session_id=session.id,
                    visibility="public", data=data)
        db_session.add(row)
        rows.append(row)
    db_session.commit()
    for row in rows:
        db_session.refresh(row)

    session_state.rebuild_buffer(db_session, session.id)
    scenario = db_session.get(Scenario, scid)
    return {
        "scenario": scenario, "session_id": session.id, "character_id": cid,
        "rows": {r.seq: r for r in rows},
    }


def _texts(ctx) -> list[str]:
    return [str(b.get("text") or "") for b in ctx.recent_beats]


def test_the_buffer_holds_every_beat_when_nothing_is_trimmed(scene, db_session):
    """The control. Without a boundary the window is the whole scene — which is right for
    an ordinary turn and wrong for a re-roll."""
    ctx = assembler.assemble_context(
        db_session, scene["scenario"], scene["session_id"], player_text=""
    )
    assert any("CHARLIE" in t for t in _texts(ctx))


def test_a_replay_window_excludes_the_beat_being_replaced(scene, db_session):
    """Re-rolling the narration at seq 4 must not show the model the narration at seq 4.
    Shown its own previous wording, a model continues from it rather than replacing it."""
    ctx = assembler.assemble_context(
        db_session, scene["scenario"], scene["session_id"], player_text="", through_seq=3
    )
    texts = _texts(ctx)
    assert not any("CHARLIE" in t for t in texts)
    assert any("BRAVO" in t for t in texts)


def test_a_replay_window_excludes_everything_after_the_boundary_too(scene, db_session):
    """Re-rolling a beat from the middle of the scene cannot be allowed to read the beats
    that followed it — they are the future from that beat's point of view."""
    ctx = assembler.assemble_context(
        db_session, scene["scenario"], scene["session_id"], player_text="", through_seq=1
    )
    texts = _texts(ctx)
    assert any("ALPHA" in t for t in texts)
    assert not any("BRAVO" in t for t in texts)
    assert not any("CHARLIE" in t for t in texts)


def test_a_boundary_above_the_scene_trims_nothing(scene, db_session):
    ctx = assembler.assemble_context(
        db_session, scene["scenario"], scene["session_id"], player_text="", through_seq=99
    )
    assert any("CHARLIE" in t for t in _texts(ctx))


def test_a_boundary_below_the_scene_empties_the_window_rather_than_wrapping(scene, db_session):
    """A negative slice index would silently return the WHOLE window — the exact opposite
    of what was asked for, and the failure would look like the fix never landed."""
    ctx = assembler.assemble_context(
        db_session, scene["scenario"], scene["session_id"], player_text="", through_seq=-1
    )
    assert _texts(ctx) == []


def test_the_trim_reaches_the_cast_s_voice_anchors_too(scene, db_session):
    """`_build_cast` pulls each speaker's recent lines out of the same list. Trimming the
    window after the cast was built would leave the character's own prompt still quoting
    the beat being replaced back at them."""
    ctx = assembler.assemble_context(
        db_session, scene["scenario"], scene["session_id"], player_text="", through_seq=1
    )
    member = ctx.cast_by_id(scene["character_id"])
    assert member is not None
    assert any("ALPHA" in line for line in member.recent_lines)
    assert not any("BRAVO" in line for line in member.recent_lines)


def test_context_for_replay_stops_at_the_beat_before_the_target(scene, db_session):
    """The whole point, end to end: the seam a re-roll actually calls."""
    target = scene["rows"][4]
    ctx, turn_beats = turn_setup.context_for_replay(
        db_session, scene["scenario"], scene["session_id"], through_seq=target.seq - 1
    )
    assert not any("CHARLIE" in t for t in _texts(ctx))
    # The `turn_beats` half already respected the boundary; it must still.
    assert not any("CHARLIE" in str(b.get("text") or "") for b in turn_beats)


def test_the_ordinary_turn_path_is_untouched(scene, db_session):
    """`through_seq=None` must produce byte-identical context to not passing it at all —
    otherwise this fix quietly changes every turn in the app."""
    a = assembler.assemble_context(
        db_session, scene["scenario"], scene["session_id"], player_text=""
    )
    b = assembler.assemble_context(
        db_session, scene["scenario"], scene["session_id"], player_text="", through_seq=None
    )
    assert json.dumps(a.recent_beats, sort_keys=True) == json.dumps(b.recent_beats, sort_keys=True)
