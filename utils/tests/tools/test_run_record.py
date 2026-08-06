"""Capture-layer behaviour that protects the record from misleading numbers."""

from __future__ import annotations

from utils.scripts.research.record import aggregate


def test_aggregate_reports_mean_std_and_n() -> None:
    rows = [{"beats": 4}, {"beats": 6}, {"beats": 5}]

    out = aggregate(rows, ["beats"])

    assert out["beats"]["mean"] == 5.0
    assert out["beats"]["n"] == 3
    assert out["beats"]["std"] > 0


def test_aggregate_omits_std_for_a_single_run() -> None:
    """0.0 would read as 'no variance observed'; the truth is 'not measurable'."""
    out = aggregate([{"beats": 4}], ["beats"])

    assert out["beats"] == {"mean": 4.0, "n": 1}
    assert "std" not in out["beats"]


def test_aggregate_skips_metrics_with_no_values() -> None:
    out = aggregate([{"beats": 4}], ["beats", "never_recorded"])

    assert "never_recorded" not in out


def test_aggregate_counts_only_rows_that_have_the_metric() -> None:
    """n must reflect the runs that actually produced the number, so an excluded seed
    shows up as a smaller n rather than silently widening the denominator."""
    rows = [{"beats": 4}, {"beats": None}, {"beats": 6}]

    out = aggregate(rows, ["beats"])

    assert out["beats"]["n"] == 2
    assert out["beats"]["mean"] == 5.0
