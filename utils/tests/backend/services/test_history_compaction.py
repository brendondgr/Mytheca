"""History compaction — the scene's memory of what fell out of the window.

Two things must hold, and they pull in opposite directions.

**It must fire rarely.** Bounded to whole anchor blocks, so a long session costs one cheap
call roughly every twenty beats rather than a growing re-summarisation every turn — and so the
summary line moves on the same turn the anchored window re-anchors, breaking the prompt-cache
prefix once instead of twice.

**It must never lie.** A rewind, an edit or a re-roll at or below the summarised seq makes the
summary describe a scene that did not happen. Clearing it is not tidiness: a stale summary is
*worse* than none, because the cast would confidently remember the very beats the player
removed.
"""

from __future__ import annotations

import pytest

from app.agents import recap_agent
from app.core.config import get_settings
from app.memory import buffer
from app.models import Event, PlaySession, Scenario
from app.services import context_budget, history_compaction


@pytest.fixture(autouse=True)
def _compaction_on(monkeypatch):
    """The feature ships OFF (owner decision D-2). These tests turn it on explicitly."""
    settings = get_settings()
    monkeypatch.setattr(settings, "turn_context_compaction", True, raising=False)
    yield


@pytest.fixture
def scene(client, storyline_id, db_session):
    cid = client.post(
        f"/api/storylines/{storyline_id}/characters", json={"name": "Mei"}
    ).json()["id"]
    scid = client.post(
        f"/api/storylines/{storyline_id}/scenarios",
        json={"title": "Standoff", "castIds": [cid]},
    ).json()["id"]
    session = PlaySession(id="ps_comp", scenario_id=scid)
    db_session.add(session)
    db_session.commit()
    return db_session.get(Scenario, scid), session


def _events(db_session, session_id: str, n: int, *, start: int = 0):
    for i in range(n):
        db_session.add(
            Event(
                id=f"ev{start + i}",
                type="narration",
                seq=start + i,
                scenario_id="x",
                session_id=session_id,
                visibility="public",
                data={"text": f"Beat {start + i} happened.", "done": True},
            )
        )
    db_session.commit()


def _drop(monkeypatch, dropped: int, retained: int = 200):
    """Force the window fit to report `dropped` beats falling out."""
    monkeypatch.setattr(
        buffer, "recent_turns", lambda sid, limit=None: [{"text": "x"} for _ in range(retained)]
    )
    monkeypatch.setattr(
        context_budget,
        "fit_window",
        lambda beats, budget, block, current=None: context_budget.FitResult(
            window_beats=max(0, len(beats) - dropped), dropped_beats=dropped, used_tokens=0
        ),
    )


def _agent(monkeypatch, text: str | None, seen: dict | None = None):
    def fake(conn, **kw):
        if seen is not None:
            seen.update(kw)
        return text

    monkeypatch.setattr(recap_agent, "summarize_history", fake)


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


# ---- when it fires ----------------------------------------------------------


def test_it_does_not_fire_while_everything_still_fits(
    client, db_session, monkeypatch, scene
):
    _configure_llm(client)
    scenario, session = scene
    _events(db_session, session.id, 40)
    _drop(monkeypatch, dropped=0)
    _agent(monkeypatch, "should not be called")

    result = history_compaction.maybe_compact(db_session, session, scenario)
    assert result.ran is False
    assert result.reason == "nothing-dropped"
    assert session.summary_text is None


def test_it_does_not_fire_for_less_than_a_whole_block(
    client, db_session, monkeypatch, scene
):
    """Compacting every turn a single beat falls off would cost a call per turn AND move the
    summary line on a turn the window did not re-anchor — breaking the cache prefix twice."""
    _configure_llm(client)
    scenario, session = scene
    _events(db_session, session.id, 40)
    block = get_settings().turn_transcript_anchor_block
    _drop(monkeypatch, dropped=block - 1)
    _agent(monkeypatch, "should not be called")

    assert history_compaction.maybe_compact(db_session, session, scenario).ran is False


def test_it_fires_once_a_whole_block_has_dropped(client, db_session, monkeypatch, scene):
    _configure_llm(client)
    scenario, session = scene
    _events(db_session, session.id, 60)
    block = get_settings().turn_transcript_anchor_block
    _drop(monkeypatch, dropped=block)
    _agent(monkeypatch, "Mei confessed; the lamp went over.")

    result = history_compaction.maybe_compact(db_session, session, scenario)
    assert result.ran is True
    assert result.beats_folded == block
    assert session.summary_text == "Mei confessed; the lamp went over."
    assert session.summary_through_seq == block - 1
    assert session.summary_updated_at is not None


def test_it_is_incremental_across_calls(client, db_session, monkeypatch, scene):
    """The second call folds only the NEW beats, and is shown the previous summary."""
    _configure_llm(client)
    scenario, session = scene
    _events(db_session, session.id, 200)
    block = get_settings().turn_transcript_anchor_block

    _drop(monkeypatch, dropped=block)
    _agent(monkeypatch, "First half.")
    history_compaction.maybe_compact(db_session, session, scenario)
    first_through = session.summary_through_seq

    seen: dict = {}
    _drop(monkeypatch, dropped=block)
    _agent(monkeypatch, "Both halves.", seen)
    history_compaction.maybe_compact(db_session, session, scenario)

    assert seen["previous_summary"] == "First half."
    # Only beats after the first summary's boundary were folded.
    assert all(f"Beat {i} " not in " ".join(seen["beats"]) for i in range(first_through + 1))
    assert session.summary_through_seq > first_through


# ---- when it must not break the turn ----------------------------------------


def test_a_declining_agent_leaves_the_previous_summary_intact(
    client, db_session, monkeypatch, scene
):
    """A scene that cannot summarise forgets a little more; it does not fail."""
    _configure_llm(client)
    scenario, session = scene
    _events(db_session, session.id, 200)
    block = get_settings().turn_transcript_anchor_block

    _drop(monkeypatch, dropped=block)
    _agent(monkeypatch, "The good summary.")
    history_compaction.maybe_compact(db_session, session, scenario)

    _drop(monkeypatch, dropped=block)
    _agent(monkeypatch, None)  # the model is unreachable this turn
    result = history_compaction.maybe_compact(db_session, session, scenario)

    assert result.ran is False
    assert result.reason == "agent-declined"
    assert session.summary_text == "The good summary."


def test_no_redis_is_a_no_op_not_an_error(client, db_session, monkeypatch, scene):
    _configure_llm(client)
    scenario, session = scene
    monkeypatch.setattr(buffer, "recent_turns", lambda sid, limit=None: [])
    _agent(monkeypatch, "should not be called")
    result = history_compaction.maybe_compact(db_session, session, scenario)
    assert (result.ran, result.reason) == (False, "no-buffer")


def test_no_configured_model_is_a_no_op(db_session, monkeypatch, scene):
    scenario, session = scene
    _events(db_session, session.id, 60)
    _drop(monkeypatch, dropped=get_settings().turn_transcript_anchor_block)
    result = history_compaction.maybe_compact(db_session, session, scenario)
    assert (result.ran, result.reason) == (False, "no-model")


def test_the_setting_off_is_a_total_no_op(client, db_session, monkeypatch, scene):
    """It ships off (owner decision D-2) — nothing may claim compaction is free until it has
    been measured against the writing it summarises."""
    _configure_llm(client)
    scenario, session = scene
    monkeypatch.setattr(get_settings(), "turn_context_compaction", False, raising=False)

    def never(sid, limit=None):  # pragma: no cover
        raise AssertionError("compaction must not even read the buffer when disabled")

    monkeypatch.setattr(buffer, "recent_turns", never)
    result = history_compaction.maybe_compact(db_session, session, scenario)
    assert (result.ran, result.reason) == (False, "off")


def test_a_fixed_scene_manages_its_own_depth_and_is_left_alone(
    client, db_session, monkeypatch, scene
):
    _configure_llm(client)
    scenario, session = scene
    scenario.context_policy = "fixed"
    db_session.add(scenario)
    db_session.commit()

    def never(sid, limit=None):  # pragma: no cover
        raise AssertionError("a fixed scene did not ask the app to manage its memory")

    monkeypatch.setattr(buffer, "recent_turns", never)
    assert history_compaction.maybe_compact(db_session, session, scenario).reason == "fixed"


# ---- invalidation: the summary must never describe a scene that did not happen ----


def _summarised(db_session, session, through: int):
    session.summary_text = "Something was remembered."
    session.summary_through_seq = through
    db_session.add(session)
    db_session.commit()


def test_a_cut_at_the_summary_boundary_clears_it(db_session, scene):
    _scenario, session = scene
    _summarised(db_session, session, through=30)
    assert history_compaction.invalidate_after(db_session, session.id, 30) is True
    assert session.summary_text is None
    assert session.summary_through_seq is None


def test_a_cut_below_the_boundary_clears_it(db_session, scene):
    _scenario, session = scene
    _summarised(db_session, session, through=30)
    assert history_compaction.invalidate_after(db_session, session.id, 5) is True
    assert session.summary_text is None


def test_a_cut_above_the_boundary_leaves_it_alone(db_session, scene):
    """The beats the summary covers are still true — clearing it would throw away memory the
    player did not ask to remove, and force an unnecessary re-summarisation."""
    _scenario, session = scene
    _summarised(db_session, session, through=30)
    assert history_compaction.invalidate_after(db_session, session.id, 31) is False
    assert session.summary_text == "Something was remembered."


def test_invalidating_a_session_with_no_summary_is_harmless(db_session, scene):
    _scenario, session = scene
    assert history_compaction.invalidate_after(db_session, session.id, 0) is False


def test_invalidating_an_unknown_session_is_harmless(db_session):
    assert history_compaction.invalidate_after(db_session, "ps_nope", 0) is False
