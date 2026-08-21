"""Regenerate this experiment's figure from its recorded per-run rows.

Contract §1.4: figures are generated from recorded results, never hand-placed, and carry
no number that is not read back out of the record. Everything here comes from
``data/metrics.json`` — the same rows the manifest aggregates — so the figure cannot drift
from the numbers in ``RESULTS.md``. A panel whose data is missing is skipped with a note
rather than invented.

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

ARMS = ["shipped", "half", "off"]
COLOR = {"shipped": "#b4483c", "half": "#c08b3e", "off": "#4a7c59"}
LABEL = {
    "shipped": "shipped\n0.40 / 0.30",
    "half": "half\n0.20 / 0.15",
    "off": "off\n0.00 / 0.00",
}


def rows() -> list[dict]:
    path = EXP / "data" / "metrics.json"
    if not path.exists():
        return []
    return (json.loads(path.read_text(encoding="utf-8")) or {}).get("per_run") or []


def _ok(data: list[dict], arm: str) -> list[dict]:
    return [r for r in data if r.get("arm") == arm and not r.get("error")]


def _blank(ax, message: str) -> None:
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes,
            color="#888", fontsize=9)
    ax.set_axis_off()


def panel_scatter(ax, data: list[dict], key: str, title: str, ylabel: str) -> None:
    """Every run as a point, with the arm mean as a bar behind it.

    Points rather than error bars alone: with n=10 per arm the spread is the finding as
    much as the mean is, and a bar chart would hide a bimodal arm entirely.
    """
    any_data = False
    for i, arm in enumerate(ARMS):
        vals = [r[key] for r in _ok(data, arm) if r.get(key) is not None]
        if not vals:
            continue
        any_data = True
        mean = sum(vals) / len(vals)
        ax.bar(i, mean, width=0.62, color=COLOR[arm], alpha=0.28, zorder=1)
        ax.scatter(
            [i + (j - len(vals) / 2) * 0.035 for j in range(len(vals))],
            vals, s=18, color=COLOR[arm], zorder=3,
        )
        ax.plot([i - 0.31, i + 0.31], [mean, mean], color=COLOR[arm], lw=2, zorder=4)
    if not any_data:
        return _blank(ax, "no run data")
    ax.set_xticks(range(len(ARMS)))
    ax.set_xticklabels([LABEL[a] for a in ARMS], fontsize=8)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)


def panel_share(ax, data: list[dict], key: str, title: str) -> None:
    """A 0/1 metric, drawn as the share of runs at 1."""
    any_data = False
    for i, arm in enumerate(ARMS):
        vals = [r[key] for r in _ok(data, arm) if r.get(key) is not None]
        if not vals:
            continue
        any_data = True
        share = 100 * sum(vals) / len(vals)
        ax.bar(i, share, width=0.62, color=COLOR[arm], alpha=0.85)
        ax.text(i, share + 2, f"{share:.0f}%", ha="center", fontsize=9, color="#333")
    if not any_data:
        return _blank(ax, "no run data")
    ax.set_ylim(0, 112)
    ax.set_xticks(range(len(ARMS)))
    ax.set_xticklabels([LABEL[a] for a in ARMS], fontsize=8)
    ax.set_ylabel("% of passages", fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)


def main() -> int:
    data = rows()
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.9))
    panel_scatter(
        axes[0], data, "sentences_per_100_words",
        "Sentences per 100 words", "terminators / 100 words",
    )
    panel_share(axes[1], data, "has_speech", "Passages containing speech")
    panel_scatter(axes[2], data, "paragraph_breaks", "Paragraph breaks", "blank lines")
    fig.suptitle(
        "EXP-2026-08-007 — in-voice frequency/presence penalties vs. the shape of the prose",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    for ext in ("png", "svg", "pdf"):
        fig.savefig(HERE / f"penalties.{ext}", dpi=200)
    plt.close(fig)
    print(f"wrote {HERE / 'penalties.png'} (+ svg, pdf)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
