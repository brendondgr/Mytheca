"""Regenerate this experiment's figure from its recorded per-beat rows.

Contract §1.4: figures are generated from recorded results, never hand-placed, and carry no
number that is not read back out of the record. Everything comes from `data/metrics.json` —
the same rows the manifest aggregates — so the figure cannot drift from `RESULTS.md`. The
target bands are the only drawn constants, and they are the *definition* of the tiers rather
than a measurement.

The left panel draws every beat as a point against its tier's target band, because the mean
alone cannot distinguish a working control ("every beat at 3") from a broken one ("half at 1,
half at 5") — and that distinction is the finding either way.

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

ARMS = ["short", "medium", "long"]
COLOR = {"short": "#4a7c59", "medium": "#c08b3e", "long": "#b4483c"}
#: What each tier ASKS for — the definition of the control, drawn as the band a beat should
#: land in. Not a measurement.
TARGET = {"short": (1, 2), "medium": (2, 4), "long": (5, 6)}
LABEL = {arm: f"{arm}\n{TARGET[arm][0]}–{TARGET[arm][1]} ¶" for arm in ARMS}


def rows() -> list[dict]:
    path = EXP / "data" / "metrics.json"
    if not path.exists():
        return []
    data = (json.loads(path.read_text(encoding="utf-8")) or {}).get("per_run") or []
    return [r for r in data if not r.get("error")]


def paragraphs(row: dict) -> int:
    """A beat's paragraph count: blank-line separators plus one."""
    return int(row.get("paragraph_breaks") or 0) + 1


def _blank(ax, message: str) -> None:
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes,
            color="#888", fontsize=9)
    ax.set_axis_off()


def panel_paragraphs(ax, data: list[dict]) -> None:
    """Every beat as a point, against the band its tier asked for."""
    if not data:
        return _blank(ax, "no beat data")
    for i, arm in enumerate(ARMS):
        vals = [paragraphs(r) for r in data if r.get("arm") == arm]
        lo, hi = TARGET[arm]
        # The target band, drawn behind the points: "did it land where it was told to".
        ax.add_patch(
            plt.Rectangle((i - 0.34, lo), 0.68, hi - lo, color=COLOR[arm], alpha=0.16, zorder=1)
        )
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        ax.scatter(
            [i + (j - len(vals) / 2) * 0.035 for j in range(len(vals))],
            vals, s=26, color=COLOR[arm], zorder=3,
        )
        ax.plot([i - 0.34, i + 0.34], [mean, mean], color=COLOR[arm], lw=2, zorder=4)
        inside = sum(1 for v in vals if lo <= v <= hi)
        ax.text(i, 0.4, f"{100 * inside / len(vals):.0f}% in band",
                ha="center", fontsize=8, color="#555")
    ax.set_xticks(range(len(ARMS)))
    ax.set_xticklabels([LABEL[a] for a in ARMS], fontsize=8)
    ax.set_ylabel("paragraphs in the beat", fontsize=9)
    ax.set_title("Paragraphs per beat (primary) — shaded = the tier's target", fontsize=10)
    ax.set_ylim(0, None)
    ax.spines[["top", "right"]].set_visible(False)


def panel_chars(ax, data: list[dict]) -> None:
    """Length in characters — expected to follow the ordering, but not the target."""
    if not data:
        return _blank(ax, "no beat data")
    for i, arm in enumerate(ARMS):
        vals = [r.get("chars") or 0 for r in data if r.get("arm") == arm]
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        ax.bar(i, mean, width=0.62, color=COLOR[arm], alpha=0.28, zorder=1)
        ax.scatter(
            [i + (j - len(vals) / 2) * 0.035 for j in range(len(vals))],
            vals, s=20, color=COLOR[arm], zorder=3,
        )
        ax.plot([i - 0.31, i + 0.31], [mean, mean], color=COLOR[arm], lw=2, zorder=4)
    ax.set_xticks(range(len(ARMS)))
    ax.set_xticklabels([LABEL[a] for a in ARMS], fontsize=8)
    ax.set_ylabel("characters", fontsize=9)
    ax.set_title("Beat length in characters", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)


def panel_form(ax, data: list[dict]) -> None:
    """The metrics that must NOT regress. A shorter beat that is worse is not a win."""
    if not data:
        return _blank(ax, "no beat data")
    # `is_distinct` is NOT drawn: the runner does not compute it (see ARM_METRIC_KEYS), and
    # a bar reading 0 for a metric that was never measured is worse than no bar. Duplicates
    # were checked post-hoc over the transcript by `analyze_run.py` — none, in any arm.
    # "clean" is the share of beats no guard flagged, which is the property that matters:
    # a shorter beat that trips a guard is not a shorter beat, it is a broken one.
    keys = [("has_speech", "contains\nspeech"), ("__clean__", "no guard\nflagged it")]
    width = 0.26
    for k, (key, _) in enumerate(keys):
        for i, arm in enumerate(ARMS):
            group = [r for r in data if r.get("arm") == arm]
            if key == "__clean__":
                vals = [
                    0 if (r.get("is_scratchpad") or r.get("starts_mid_sentence")
                          or r.get("names_the_player")) else 1
                    for r in group
                ]
            else:
                vals = [r.get(key, 0) for r in group]
            if not vals:
                continue
            share = 100 * sum(vals) / len(vals)
            ax.bar(k + (i - 1) * width, share, width=width, color=COLOR[arm],
                   label=arm if k == 0 else None)
            ax.text(k + (i - 1) * width, share + 2, f"{share:.0f}", ha="center", fontsize=7,
                    color="#333")
    ax.set_ylim(0, 118)
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([label for _, label in keys], fontsize=8)
    ax.set_ylabel("% of character beats", fontsize=9)
    ax.set_title("The form, which must not regress", fontsize=10)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)


def main() -> int:
    data = rows()
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.0))
    panel_paragraphs(axes[0], data)
    panel_chars(axes[1], data)
    panel_form(axes[2], data)
    fig.suptitle(
        "EXP-2026-08-010 — do the Short / Medium / Long beat-length tiers separate?",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    for ext in ("png", "svg", "pdf"):
        fig.savefig(HERE / f"beat_length.{ext}", dpi=200)
    plt.close(fig)
    print(f"wrote {HERE / 'beat_length.png'} (+ svg, pdf)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
