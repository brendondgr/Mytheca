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
