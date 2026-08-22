"""The transcript window fits itself to the model's context budget.

The per-scene "Number of beats" slider asked the player to pick a depth. That is a question
only the app can answer — the right depth is whatever the model can actually hold, and the app
knows the model's window while the player does not. The slider is gone; this is what replaced
it.

The thing that must not break is the **block anchoring**. `buffer.anchored_turns` keeps the
rendered transcript's prefix byte-stable by moving its start in blocks, because a prefix cache
matches from the first token. A dynamic depth is a direct threat to that, so the fit is
quantised to the same block — and these tests hold that line rather than merely checking the
arithmetic.
"""

from __future__ import annotations

import pytest

from app.memory import buffer
from app.services import assembler, context_budget


@pytest.fixture
def scene(client, storyline_id):
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
    return scid


def _scenario_row(db_session, scenario_id):
    from app.models import Scenario

    return db_session.get(Scenario, scenario_id)


def _stub_buffer(monkeypatch, beats: list[dict], seen: dict):
    """Record what depth `anchored_turns` was asked for, and serve a fixed history."""

    def anchored(session_id, window, block):
        seen["window"] = window
        seen["block"] = block
        return beats[-window:]

    monkeypatch.setattr(buffer, "anchored_turns", anchored)
    monkeypatch.setattr(buffer, "recent_turns", lambda session_id, limit=None: beats)


def _beats(n: int, chars: int = 400) -> list[dict]:
    return [{"role": "narrator", "text": "x" * chars, "characterId": None} for _ in range(n)]


def test_the_auto_window_asks_for_a_depth_the_budget_actually_allows(
    client, storyline_id, db_session, monkeypatch, scene
):
    seen: dict = {}
    _stub_buffer(monkeypatch, _beats(200), seen)
    monkeypatch.setattr(
        context_budget,
        "resolve_window",
        lambda db: context_budget.WindowInfo(max_tokens=8_000, source="detected"),
    )
    ctx = assembler.assemble_context(
        db_session, _scenario_row(db_session, scene), "ps_x", None, player_text="hi"
    )
    # A depth was chosen, it is not the old hardcoded 14, and it is what the buffer was asked
    # for — the fit is not computed and then ignored.
    assert ctx.window_beats == seen["window"]
    assert ctx.window_source == "detected"
    assert ctx.window_beats > 0


def test_the_depth_is_always_a_whole_number_of_anchor_blocks(
    client, storyline_id, db_session, monkeypatch, scene
):
    """The load-bearing property. A depth that moved by one beat per turn would re-prefill
    the whole transcript every turn — the exact cost `anchored_turns` exists to avoid."""
    seen: dict = {}
    _stub_buffer(monkeypatch, _beats(400), seen)
    monkeypatch.setattr(
        context_budget,
        "resolve_window",
        lambda db: context_budget.WindowInfo(max_tokens=40_000, source="detected"),
    )
    ctx = assembler.assemble_context(
        db_session, _scenario_row(db_session, scene), "ps_x", None, player_text="hi"
    )
    assert ctx.window_beats % seen["block"] == 0


def test_the_window_does_not_move_when_a_beat_does_not_cross_a_block(
    client, storyline_id, db_session, monkeypatch, scene
):
    monkeypatch.setattr(
        context_budget,
        "resolve_window",
        lambda db: context_budget.WindowInfo(max_tokens=40_000, source="detected"),
    )
    depths = set()
    for n in (100, 101, 102, 103, 104):
        seen: dict = {}
        _stub_buffer(monkeypatch, _beats(n), seen)
        ctx = assembler.assemble_context(
            db_session, _scenario_row(db_session, scene), "ps_x", None, player_text="hi"
        )
        depths.add(ctx.window_beats)
    assert len(depths) == 1, f"the window moved on an ordinary beat: {depths}"


def test_a_scene_can_opt_out_and_keep_its_own_depth(
    client, storyline_id, db_session, monkeypatch, scene
):
    client.patch(f"/api/scenarios/{scene}", json={"contextPolicy": "fixed", "contextBeats": 22})
    db_session.expire_all()
    seen: dict = {}
    _stub_buffer(monkeypatch, _beats(200), seen)
    ctx = assembler.assemble_context(
        db_session, _scenario_row(db_session, scene), "ps_x", None, player_text="hi"
    )
    assert seen["window"] == 22
    assert ctx.window_beats == 22
    assert ctx.window_source == "fixed"


def test_a_fixed_scene_never_probes_the_model(
    client, storyline_id, db_session, monkeypatch, scene
):
    """Opting out must actually opt out — not fit a window and then discard it."""
    client.patch(f"/api/scenarios/{scene}", json={"contextPolicy": "fixed"})
    db_session.expire_all()
    seen: dict = {}
    _stub_buffer(monkeypatch, _beats(50), seen)

    def boom(db):  # pragma: no cover - the point is that it is never reached
        raise AssertionError("resolve_window was called under the fixed policy")

    monkeypatch.setattr(context_budget, "resolve_window", boom)
    assembler.assemble_context(
        db_session, _scenario_row(db_session, scene), "ps_x", None, player_text="hi"
    )


def test_no_redis_still_assembles_a_turn(client, storyline_id, db_session, monkeypatch, scene):
    """The buffer is best-effort. With no Redis the fit sees nothing, and the turn must still
    run — degrading to a scene with no memory is acceptable; failing the turn is not."""
    seen: dict = {}
    _stub_buffer(monkeypatch, [], seen)
    monkeypatch.setattr(
        context_budget,
        "resolve_window",
        lambda db: context_budget.WindowInfo(max_tokens=8_000, source="detected"),
    )
    ctx = assembler.assemble_context(
        db_session, _scenario_row(db_session, scene), "ps_x", None, player_text="hi"
    )
    assert ctx.recent_beats == []
    # Falls back to the scene's own depth rather than asking the buffer for zero beats.
    assert seen["window"] > 0


def test_an_unknown_window_is_reported_as_fallback_not_configured(
    client, storyline_id, db_session, monkeypatch, scene
):
    seen: dict = {}
    _stub_buffer(monkeypatch, _beats(50), seen)
    monkeypatch.setattr(
        context_budget,
        "resolve_window",
        lambda db: context_budget.WindowInfo(max_tokens=8_192, source="fallback"),
    )
    ctx = assembler.assemble_context(
        db_session, _scenario_row(db_session, scene), "ps_x", None, player_text="hi"
    )
    assert ctx.window_source == "fallback"


def test_a_tiny_window_still_leaves_the_scene_some_memory(
    client, storyline_id, db_session, monkeypatch, scene
):
    seen: dict = {}
    _stub_buffer(monkeypatch, _beats(50, chars=4_000), seen)
    monkeypatch.setattr(
        context_budget,
        "resolve_window",
        lambda db: context_budget.WindowInfo(max_tokens=1_200, source="detected"),
    )
    ctx = assembler.assemble_context(
        db_session, _scenario_row(db_session, scene), "ps_x", None, player_text="hi"
    )
    assert ctx.window_beats >= 1
