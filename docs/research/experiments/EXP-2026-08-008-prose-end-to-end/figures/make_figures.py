"""Regenerate this experiment's figure from its recorded per-beat rows.

Contract §1.4: figures are generated from recorded results, never hand-placed, and carry no
number that is not read back out of the record. Everything here comes from
``data/metrics.json`` — the same rows the manifest aggregates — so the figure cannot drift
from the numbers in ``RESULTS.md``. A panel whose data is missing is skipped with a note
rather than invented.

The left panel is per-beat and ordered by turn: the threat this experiment actually has is
that the form **degrades as the session grows**, and a mean would hide exactly that. The
right panel is the owner's complaint as a count, against the pre-change baseline recorded in
``docs/plans/prose-that-reads-like-a-scene.md`` § 1 — a different model and session, drawn
hollow because it is a *before* picture, not a controlled arm.

Run via ``make figures`` (or directly).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent

INK = "#4a7c59"
MISS = "#b4483c"
#: Pre-change, from the plan's § 1 table. 12 beats: 3 with speech, 4 with a paragraph break.
BASELINE = {"n": 12, "speech": 3, "breaks": 4}


def rows() -> list[dict]:
    path = EXP / "data" / "metrics.json"
    if not path.exists():
        return []
    data = (json.loads(path.read_text(encoding="utf-8")) or {}).get("per_run") or []
    return [r for r in data if not r.get("error")]


def _blank(ax, message: str) -> None:
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes,
            color="#888", fontsize=9)
    ax.set_axis_off()


def panel_per_beat(ax, data: list[dict]) -> None:
    """Every beat in session order, coloured by whether it carried spoken dialogue."""
    if not data:
        return _blank(ax, "no beat data")
    xs = list(range(len(data)))
    vals = [r.get("sentences_per_100_words") or 0.0 for r in data]
    colors = [INK if r.get("has_speech") else MISS for r in data]
    misses = sum(1 for r in data if not r.get("has_speech"))
    ax.scatter(xs, vals, s=26, color=colors, zorder=3,
               label="no spoken line" if misses else None)
    mean = sum(vals) / len(vals)
    ax.axhline(mean, color=INK, lw=1.2, ls="--", zorder=2,
               label=f"mean {mean:.1f}")
    # Turn boundaries, so "does it degrade as the transcript grows" is readable off the plot.
    # The labels sit at the BOTTOM: at the top they collided with the subplot title, and the
    # trend this panel exists to show runs downward, so the floor is the empty half.
    lo, hi = min(vals), max(vals)
    label_y = lo - (hi - lo) * 0.06 if hi > lo else lo
    seen = None
    for i, r in enumerate(data):
        if r.get("turn") != seen:
            seen = r.get("turn")
            if i:
                ax.axvline(i - 0.5, color="#ccc", lw=0.8, zorder=1)
            ax.text(i, label_y, f"t{seen}", fontsize=7, color="#888",
                    va="top", ha="left")
    ax.margins(y=0.14)
    ax.set_xlabel("character beat, in session order (t = turn)", fontsize=9)
    ax.set_ylabel("terminators / 100 words", fontsize=9)
    ax.set_title(
        "Sentences per 100 words, per beat"
        + ("" if misses else " — every beat carried speech"),
        fontsize=10,
    )
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)


def panel_counts(ax, data: list[dict]) -> None:
    """The owner's complaint as a share, against the pre-change baseline."""
    if not data:
        return _blank(ax, "no beat data")
    n = len(data)
    now = [100 * sum(1 for r in data if r.get("has_speech")) / n,
           100 * sum(1 for r in data if r.get("paragraph_breaks")) / n]
    before = [100 * BASELINE["speech"] / BASELINE["n"],
              100 * BASELINE["breaks"] / BASELINE["n"]]
    xs = [0, 1]
    ax.bar([x - 0.19 for x in xs], before, width=0.36, facecolor="none",
           edgecolor="#999", lw=1.2, ls="--", label=f"before (n={BASELINE['n']})")
    ax.bar([x + 0.19 for x in xs], now, width=0.36, color=INK, label=f"now (n={n})")
    for x, v in zip(xs, before):
        ax.text(x - 0.19, v + 2, f"{v:.0f}%", ha="center", fontsize=8, color="#777")
    for x, v in zip(xs, now):
        ax.text(x + 0.19, v + 2, f"{v:.0f}%", ha="center", fontsize=8, color="#333")
    ax.set_ylim(0, 118)
    ax.set_xticks(xs)
    ax.set_xticklabels(["contains\nspoken dialogue", "contains a\nparagraph break"],
                       fontsize=8)
    ax.set_ylabel("% of character beats", fontsize=9)
    ax.set_title("The complaint, counted", fontsize=10)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)


def main() -> int:
    data = rows()
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0))
    panel_per_beat(axes[0], data)
    panel_counts(axes[1], data)
    fig.suptitle(
        "EXP-2026-08-008 — the prose form through the live turn engine",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    for ext in ("png", "svg", "pdf"):
        fig.savefig(HERE / f"prose_end_to_end.{ext}", dpi=200)
    plt.close(fig)
    print(f"wrote {HERE / 'prose_end_to_end.png'} (+ svg, pdf)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
