"""Regenerate this experiment's figure from its recorded rows.

Contract §1.4: a figure is generated from recorded results and carries no number that is not
read back out of the record. Everything below comes from ``data/metrics-baseline.json`` and
``data/metrics-fixed.json``. The only drawn constants are the *definitions* — which metrics
are "0 is correct", which are "1 is correct", and which are merely observed — and all three
are stated in ``PROTOCOL.md``.

Three panels, one per question the run can answer with a number:

* **What survived the cut.** Counts of things a rewind was supposed to remove. Counts rather
  than a pass/fail tick, because "3 interior keys" and "1 interior key" are different
  failures and a tick would hide the difference.
* **What the cast still knew.** The recall floor (asked before the fact was ever planted)
  beside the score after the rewind. The two arms are different scenes with different floors,
  so each arm is readable against **its own** floor and not against the other.
* **Where the boundaries held.** The 0/1 conformance checks, inverted where the raw metric
  counts a leak so that every bar in the panel reads the same way.

The graph-edge count is drawn **hatched**, because it is the one channel this plan measured
and deliberately left open (`docs/checklist.md`). Hatching rather than recolouring: colour
carries which arm a bar belongs to, and spending it on "not fixed" would trade one piece of
information for another instead of adding it.

A metric a run does not have is drawn as **"n/r"**, never as a zero. A bar at zero is a
result here, and imputing one would invent exactly the thing this figure exists to report.

n = 1 scene per probe per arm. Every panel says so, because a bar chart of two numbers
invites being read as a rate and it is not one.

Run via ``make figures`` (or directly).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent

ARMS = ["baseline", "fixed"]
COLOR = {"baseline": "#b4483c", "fixed": "#4a6d8c"}
#: Suffix marking a metric that is reported and NOT expected to reach the correct value.
OPEN = "*"


def load(arm: str) -> dict[str, dict]:
    path = EXP / "data" / f"metrics-{arm}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r.get("probe"): r for r in data.get("rows", [])}


def window_read(rows: dict[str, dict], key: str):
    """A replay-window read, from the probe row or from the standalone re-read row.

    The baseline measured these with ``--replay-window`` after the fact (`ISSUES.md` A-3);
    later arms measure them inline. Same function, same code, different row.
    """
    for probe in ("reroll_beat", "reroll_replay_window"):
        value = (rows.get(probe) or {}).get(key)
        if value is not None:
            return value
    return None


def invert(value):
    """A leak count (1 = the beat was visible) read as conformance (1 = correct)."""
    return None if value is None else 1 - int(value)


def both(row, a: str, b: str):
    if not row or row.get(a) is None or row.get(b) is None:
        return None
    return int(bool(row[a]) and bool(row[b]))


def bars(ax, groups: list[tuple[str, dict[str, float | None]]]) -> None:
    width = 0.36
    for i, (name, by_arm) in enumerate(groups):
        for j, arm in enumerate(ARMS):
            value = by_arm.get(arm)
            x = i + (j - 0.5) * width
            if value is None:
                ax.text(x, 0.04, "n/r", ha="center", va="bottom", fontsize=6.5,
                        color="#8a8175", rotation=90)
                continue
            ax.bar(x, value, width=width, color=COLOR[arm], edgecolor="white",
                   linewidth=0.6, zorder=3, hatch="//" if name.endswith(OPEN) else None)
            ax.text(x, value, f"{value:g}", ha="center", va="bottom", fontsize=7,
                    color="#3a352e", zorder=4)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([n.rstrip(OPEN) for n, _ in groups], fontsize=7,
                       rotation=24, ha="right", rotation_mode="anchor")
    ax.grid(axis="y", color="#e6e0d4", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def main() -> None:
    data = {arm: load(arm) for arm in ARMS}
    if not data["baseline"]:
        raise SystemExit("no baseline metrics recorded — run the harness first")

    rw = {arm: data[arm].get("rewind") or {} for arm in ARMS}
    br = {arm: data[arm].get("branch") or {} for arm in ARMS}

    fig, axes = plt.subplots(1, 3, figsize=(13.0, 4.6))
    fig.patch.set_facecolor("white")

    axes[0].set_title("What survived a rewind\n(0 is correct)", fontsize=9.5, loc="left")
    bars(axes[0], [
        ("interior state", {a: rw[a].get("interior_keys_after") for a in ARMS}),
        ("standing (cut turns)", {a: rw[a].get("standing_after_from_cut_turns") for a in ARMS}),
        ("buffer leak", {a: rw[a].get("buffer_leak_beats") for a in ARMS}),
        ("rows above cut", {a: rw[a].get("events_above_cut") for a in ARMS}),
        ("graph edges" + OPEN, {a: rw[a].get("graph_edges_after") for a in ARMS}),
    ])
    axes[0].set_ylabel("count", fontsize=8)

    axes[1].set_title(
        "What the cast still knew after the rewind\n(a fact no longer in the transcript)",
        fontsize=9.5, loc="left",
    )
    bars(axes[1], [
        ("floor (pre-plant)", {a: rw[a].get("recall_floor") for a in ARMS}),
        ("after rewind", {a: rw[a].get("recall_coverage") for a in ARMS}),
        ("after (discounted)", {a: rw[a].get("recall_coverage_discounted") for a in ARMS}),
    ])
    axes[1].set_ylabel("fraction of the fact's content tokens", fontsize=8)
    axes[1].set_ylim(0, 0.5)

    axes[2].set_title("Where the boundaries held\n(1 is correct)", fontsize=9.5, loc="left")
    bars(axes[2], [
        ("re-roll: window clean",
         {a: invert(window_read(data[a], "target_in_replay_window")) for a in ARMS}),
        ("re-roll: anchors clean",
         {a: invert(window_read(data[a], "target_in_voice_anchors")) for a in ARMS}),
        ("re-roll: id + seq held",
         {a: both(data[a].get("reroll_beat"), "id_stable", "seq_stable") for a in ARMS}),
        ("branch: debt kept", {a: br[a].get("standing_inherited") for a in ARMS}),
    ])
    axes[2].set_ylim(0, 1.25)
    axes[2].set_yticks([0, 1])

    fig.suptitle(
        "EXP-2026-08-014 — what the record operations forget, before and after",
        fontsize=11, x=0.008, ha="left",
    )
    fig.legend(
        handles=[
            Patch(facecolor=COLOR["baseline"], label="baseline (before the fixes)"),
            Patch(facecolor=COLOR["fixed"], label="fixed (after)"),
            Patch(facecolor="white", edgecolor="#6b645a", hatch="//",
                  label="measured, deliberately not fixed"),
        ],
        loc="upper right", frameon=False, fontsize=8, ncol=3, bbox_to_anchor=(0.995, 1.0),
    )
    fig.tight_layout(rect=(0, 0.17, 1, 0.92))

    # Footnotes in FIGURE coordinates. In axes coordinates `tight_layout` counts them as part
    # of the axes and shrinks the plot to a sliver to make room for them.
    notes = [
        ("Hatched = reported, NOT fixed: relationship edges written by cut turns have no\n"
         "per-turn provenance to delete by (docs/checklist.md).    n = 1 scene."),
        ("The two arms are DIFFERENT scenes with different floors — read each against its own.\n"
         "Lexical coverage is a FLOOR on recall, not a measure of it. \"n/r\" = the discounted\n"
         "metric postdates that run and is not imputed (ISSUES.md A-1, A-2).    n = 1."),
        ("\"clean\" inverts a raw metric that counts a leak, so every bar reads the same way.\n"
         "n = 1 scene per probe per arm."),
    ]
    for ax, text in zip(axes, notes):
        fig.text(ax.get_position().x0, 0.115, text, fontsize=6.6, color="#6b645a",
                 va="top", linespacing=1.55)

    for ext in ("svg", "pdf"):
        fig.savefig(HERE / f"record_controls.{ext}", bbox_inches="tight")
    print(f"wrote {HERE / 'record_controls.svg'} and .pdf")


if __name__ == "__main__":
    main()
