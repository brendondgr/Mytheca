"""Bounded concurrent execution: order preserved, failures isolated, empty/single."""

from __future__ import annotations

from app.services import concurrency


def test_run_all_preserves_input_order():
    results = concurrency.run_all([lambda i=i: i * 10 for i in range(6)])
    assert results == [0, 10, 20, 30, 40, 50]


def test_run_all_isolates_failures_as_none():
    def boom() -> int:
        raise RuntimeError("nope")

    results = concurrency.run_all([lambda: 1, boom, lambda: 3])
    assert results == [1, None, 3]


def test_run_all_empty_is_empty():
    assert concurrency.run_all([]) == []


def test_run_all_single_unit_runs_inline():
    assert concurrency.run_all([lambda: "solo"]) == ["solo"]


def test_run_all_respects_max_workers_cap():
    # Cap of 1 forces the inline path; results are still correct + ordered.
    assert concurrency.run_all([lambda i=i: i for i in range(4)], max_workers=1) == [0, 1, 2, 3]


# ---- imap_unordered (as-completed, index-tagged, bounded) ----------------------


def test_imap_unordered_yields_every_result_with_its_index():
    out = dict(concurrency.imap_unordered([lambda i=i: i * 10 for i in range(6)], max_workers=4))
    assert out == {0: 0, 1: 10, 2: 20, 3: 30, 4: 40, 5: 50}


def test_imap_unordered_isolates_failures_as_none():
    def boom() -> int:
        raise RuntimeError("nope")

    out = dict(concurrency.imap_unordered([lambda: 1, boom, lambda: 3], max_workers=3))
    assert out == {0: 1, 1: None, 2: 3}


def test_imap_unordered_empty_yields_nothing():
    assert list(concurrency.imap_unordered([])) == []


def test_imap_unordered_cap_one_runs_inline_in_order():
    # max_workers<=1 runs inline, preserving order (deterministic dev/test path).
    got = list(concurrency.imap_unordered([lambda i=i: i for i in range(4)], max_workers=1))
    assert got == [(0, 0), (1, 1), (2, 2), (3, 3)]


def test_imap_unordered_completes_all_under_concurrency():
    # 8 units, cap 4 — every index appears exactly once regardless of completion order.
    seen = [i for i, _ in concurrency.imap_unordered([lambda: 1] * 8, max_workers=4)]
    assert sorted(seen) == list(range(8))


# ---- P11: submit_background (inline by default, async when enabled) ------------


def test_submit_background_runs_inline_by_default():
    # TURN_ASYNC_FINALIZE is off by default → the job runs before the call returns.
    ran: list[int] = []
    concurrency.submit_background(lambda: ran.append(1))
    assert ran == [1]


def test_submit_background_isolates_failures_inline():
    def boom() -> None:
        raise RuntimeError("nope")

    concurrency.submit_background(boom)  # must not raise (best-effort)


def test_submit_background_runs_on_a_thread_when_enabled(monkeypatch):
    import threading

    from app.core import config

    monkeypatch.setenv("TURN_ASYNC_FINALIZE", "true")  # default DATABASE_URL is not SQLite
    config.get_settings.cache_clear()
    try:
        done = threading.Event()
        concurrency.submit_background(done.set)
        assert done.wait(timeout=2.0)  # the daemon worker ran the job
    finally:
        config.get_settings.cache_clear()
