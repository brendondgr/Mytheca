"""Figures for EXP-2026-08-017. Every number is read from data/metrics.json.

No value is written into this file. If a figure and the record disagree, the figure is wrong
by construction, which is the point.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
METRICS = json.loads((HERE.parent / "data" / "metrics.json").read_text())
ROWS = METRICS["per_run"]
ARMS = ["voiced", "continuous"]
COLOURS = {"voiced": "#4C72B0", "continuous": "#DD8452"}


def _rows(arm: str) -> list[dict]:
    return sorted((r for r in ROWS if r["arm"] == arm), key=lambda r: r["turn"])


def plan_adherence(ax) -> None:
    """Per turn, because the pre-registered rule is a per-turn pass/fail, not a mean."""
    width = 0.35
    for i, arm in enumerate(ARMS):
        rows = _rows(arm)
        xs = [r["turn"] + (i - 0.5) * width for r in rows]
        ys = [r["plan_adherence"] for r in rows]
        ax.bar(xs, ys, width, label=arm, color=COLOURS[arm])
    ax.axhline(1.0, color="#333", linestyle="--", linewidth=1)
    ax.annotate("the plan, run as written", xy=(0.02, 1.0), xycoords=("axes fraction", "data"),
                va="bottom", fontsize=8, color="#333")
    ax.set_xticks([r["turn"] for r in _rows("voiced")])
    ax.set_xlabel("player turn")
    ax.set_ylabel("beats run ÷ beats planned")
    ax.set_title("Plan adherence")
    ax.legend(fontsize=8)


def planner_calls(ax) -> None:
    width = 0.35
    for i, arm in enumerate(ARMS):
        rows = _rows(arm)
        xs = [r["turn"] + (i - 0.5) * width for r in rows]
        ax.bar(xs, [r["planner_calls"] for r in rows], width, label=arm, color=COLOURS[arm])
    ax.axhline(1.0, color="#333", linestyle="--", linewidth=1)
    ax.set_xticks([r["turn"] for r in _rows("voiced")])
    ax.set_xlabel("player turn")
    ax.set_ylabel("planning calls")
    ax.set_title("Planner calls per turn (target: 1)")
    ax.legend(fontsize=8)


def cache_rate(ax) -> None:
    width = 0.35
    for i, arm in enumerate(ARMS):
        rows = _rows(arm)
        xs = [r["turn"] + (i - 0.5) * width for r in rows]
        ys = [(r["cached_token_rate"] or 0.0) for r in rows]
        ax.bar(xs, ys, width, label=arm, color=COLOURS[arm])
    ax.set_xticks([r["turn"] for r in _rows("voiced")])
    ax.set_xlabel("player turn")
    ax.set_ylabel("cached ÷ prompt tokens")
    ax.set_title("Prefix-cache hit rate")
    ax.legend(fontsize=8)


def main() -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    plan_adherence(axes[0])
    planner_calls(axes[1])
    cache_rate(axes[2])
    fig.suptitle(
        "EXP-2026-08-017 — bound plan, two execution arms (n = 2 turns per arm, one run)",
        fontsize=10,
    )
    fig.tight_layout()
    for ext in ("svg", "pdf"):
        fig.savefig(HERE / f"bound_plan_execution.{ext}", bbox_inches="tight")
    print(f"wrote {HERE}/bound_plan_execution.svg and .pdf")


if __name__ == "__main__":
    main()
