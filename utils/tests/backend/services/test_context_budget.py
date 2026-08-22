"""How much of the scene fits in the model's context.

The per-scene "Number of beats" slider asked the player a question only the app can answer.
This module answers it — and the thing that has to be right is not the arithmetic but the
**stability**: `buffer.anchored_turns` keeps the rendered transcript's prefix byte-stable by
moving its start in blocks, because a prefix cache matches from the first token. A depth that
changed by one beat per turn would defeat that completely, so the depth is quantised to the
same block and only moves when the change is worth a cold prefill.
"""

from __future__ import annotations

import pytest

from app.services import context_budget as cb
from app.services.context_budget import WindowInfo

BLOCK = 20


def beats(n: int, chars: int = 400) -> list[str]:
    """``n`` beats of ``chars`` characters — 100 tokens each at 4 chars/token."""
    return ["x" * chars for _ in range(n)]


# ---- reserve_for ------------------------------------------------------------


def test_reserve_measures_the_parts_rather_than_assuming_a_constant():
    """The non-transcript prompt varies by an order of magnitude between a bare scenario and
    a fully-authored world; a fixed reserve would strand context in one case and overflow in
    the other."""
    small = cb.reserve_for("short")
    large = cb.reserve_for("x" * 40_000)
    assert large > small
    # Both carry the answer allowance on top.
    assert small > 0


def test_reserve_with_no_parts_is_just_the_answer_allowance():
    assert cb.reserve_for() == cb.get_settings().turn_context_reserve_tokens


# ---- transcript_budget ------------------------------------------------------


def test_the_transcript_is_capped_at_a_fraction_of_the_window():
    """Filling a context window with transcript is not using it well — the character
    prompt's tail is the act-now region."""
    window = WindowInfo(max_tokens=100_000, source="detected")
    assert cb.transcript_budget(window, reserve=10, fraction=0.5) == 50_000


def test_a_large_reserve_wins_over_the_fraction():
    window = WindowInfo(max_tokens=10_000, source="detected")
    assert cb.transcript_budget(window, reserve=9_000, fraction=0.5) == 1_000


def test_the_budget_is_never_negative():
    window = WindowInfo(max_tokens=1_000, source="fallback")
    assert cb.transcript_budget(window, reserve=99_999) == 0


# ---- fit_window: the quantisation that protects the prompt cache ------------


def test_the_depth_is_quantised_down_to_a_whole_block():
    # 47 beats fit by tokens; the window must be 40, not 47.
    fit = cb.fit_window(beats(200), budget_tokens=4_700, block=BLOCK)
    assert fit.window_beats % BLOCK == 0
    assert fit.window_beats == 40


def test_a_growing_transcript_does_not_move_the_window_every_beat():
    """The whole point. A window that slid by one beat per turn would re-prefill the entire
    transcript every turn — exactly what `anchored_turns` exists to prevent."""
    budget = 10_000
    depths = {
        cb.fit_window(beats(n), budget_tokens=budget, block=BLOCK).window_beats
        for n in range(60, 75)
    }
    # Fifteen consecutive transcript lengths, all comfortably inside the budget, must not
    # produce fifteen different window depths.
    assert len(depths) <= 2


def test_hysteresis_keeps_a_window_that_is_over_by_less_than_a_block():
    """Without it, a transcript hovering on the boundary grows and shrinks every turn, and
    every change costs a cold prefill."""
    # Budget fits 39 beats → quantises to 20 with no history…
    fresh = cb.fit_window(beats(100), budget_tokens=3_900, block=BLOCK)
    # …but a window already at 40 is only 1 beat over, so it is kept.
    kept = cb.fit_window(beats(100), budget_tokens=3_900, block=BLOCK, current=40)
    assert fresh.window_beats == 20
    assert kept.window_beats == 40


def test_a_window_does_shrink_once_it_is_over_by_a_whole_block():
    # Budget now fits only 15 beats — 40 is over by more than a block, so it must give.
    fit = cb.fit_window(beats(100), budget_tokens=1_500, block=BLOCK, current=40)
    assert fit.window_beats < 40


def test_a_window_grows_only_in_block_steps():
    small = cb.fit_window(beats(200), budget_tokens=20_000, block=BLOCK, current=20)
    assert small.window_beats % BLOCK == 0
    assert small.window_beats > 20


# ---- degenerate inputs ------------------------------------------------------


def test_no_beats_is_an_empty_window_not_a_crash():
    fit = cb.fit_window([], budget_tokens=10_000, block=BLOCK)
    assert (fit.window_beats, fit.dropped_beats, fit.used_tokens) == (0, 0, 0)


def test_a_zero_budget_drops_everything():
    fit = cb.fit_window(beats(10), budget_tokens=0, block=BLOCK)
    assert fit.window_beats == 0
    assert fit.dropped_beats == 10


def test_one_enormous_beat_still_gets_a_window():
    """A single beat larger than the whole budget must not leave the scene with no memory at
    all — a window of zero is worse than one block of overage."""
    fit = cb.fit_window(["x" * 400_000], budget_tokens=100, block=BLOCK)
    assert fit.window_beats == 1


def test_a_block_of_zero_or_one_is_tolerated():
    assert cb.fit_window(beats(10), budget_tokens=10_000, block=0).window_beats == 10
    assert cb.fit_window(beats(10), budget_tokens=10_000, block=1).window_beats == 10


def test_dropped_and_window_always_account_for_every_beat():
    for n, budget in ((100, 3_000), (7, 10_000), (0, 10_000)):
        fit = cb.fit_window(beats(n), budget_tokens=budget, block=BLOCK)
        assert fit.window_beats + fit.dropped_beats == n


# ---- resolve_window ---------------------------------------------------------


def test_resolve_window_prefers_the_engine_then_the_setting_then_a_fallback(
    db_session, monkeypatch
):
    """"We asked the model" and "we guessed" are different claims, and only one of them
    should be trusted with a full window — so the source is reported, never flattened."""
    from app.services import llm_backend, settings_store

    monkeypatch.setattr(
        settings_store, "resolve_llm_credentials", lambda *a, **k: ("http://x/v1", "k")
    )
    monkeypatch.setattr(llm_backend, "get_context_window", lambda *a, **k: 131_072)
    assert cb.resolve_window(db_session) == WindowInfo(131_072, "detected")

    monkeypatch.setattr(llm_backend, "get_context_window", lambda *a, **k: None)
    got = cb.resolve_window(db_session)
    assert got.source in ("configured", "fallback")
    assert got.max_tokens > 0


def test_an_unconfigured_endpoint_never_reports_detected(db_session, monkeypatch):
    from app.services import settings_store

    monkeypatch.setattr(settings_store, "resolve_llm_credentials", lambda *a, **k: ("", ""))
    assert cb.resolve_window(db_session).source != "detected"


@pytest.mark.parametrize("bogus", [0, -1])
def test_a_nonsense_detected_window_falls_through(db_session, monkeypatch, bogus):
    from app.services import llm_backend, settings_store

    monkeypatch.setattr(
        settings_store, "resolve_llm_credentials", lambda *a, **k: ("http://x/v1", "k")
    )
    monkeypatch.setattr(llm_backend, "get_context_window", lambda *a, **k: bogus)
    assert cb.resolve_window(db_session).source != "detected"
