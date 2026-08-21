"""Regenerate this experiment's figure from the two runs it compares.

Contract §1.4: figures are generated from recorded results, never hand-placed, and carry no
number that is not read back out of the record. The "after" cells come from this folder's
`data/metrics.json`; the "before" cells are read out of **EXP-2026-08-008's own recorded
files** (`manifest.yaml` for the form metrics, `data/leak.json` for the leak) rather than
retyped here, so the baseline cannot drift from the experiment it belongs to.

A panel whose data is missing is skipped with a note rather than invented.

Run via ``make figures`` (or directly).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
BEFORE_EXP = EXP.parent / "EXP-2026-08-008-prose-end-to-end"

BEFORE_C = "#b4483c"
AFTER_C = "#4a7c59"

#: The form metrics that must not regress, with the label the panel shows.
FORM = [
    ("has_speech", "contains\nspoken dialogue"),
    ("is_distinct", "distinct from\nevery other beat"),
]


def after_rows() -> list[dict]:
    path = EXP / "data" / "metrics.json"
    if not path.exists():
        return []
    data = (json.loads(path.read_text(encoding="utf-8")) or {}).get("per_run") or []
    return [r for r in data if not r.get("error")]


def before_cells() -> dict[str, dict]:
    """EXP-2026-08-008's `metrics.values`, parsed out of its manifest.

    A tiny reader rather than a YAML dependency: the block is flat `key: {mean,std,n}` and
    the alternative is retyping the baseline into this file, which is the thing the contract
    forbids.
    """
    path = BEFORE_EXP / "manifest.yaml"
    if not path.exists():
        return {}
    cells: dict[str, dict] = {}
    key: str | None = None
    in_values = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^  values:\s*$", line):
            in_values = True
            continue
        if in_values and line and not line.startswith("    "):
            break
        if not in_values:
            continue
        if m := re.match(r"^    ([A-Za-z_][\w.]*):\s*$", line):
            key = m.group(1)
            cells[key] = {}
        elif key and (m := re.match(r"^      (mean|std|n):\s*([-\d.]+)$", line)):
            cells[key][m.group(1)] = float(m.group(2))
    return cells


def before_leak() -> dict:
    path = BEFORE_EXP / "data" / "leak.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")) or {}


def after_leak() -> dict:
    """This run's leak counts, from ``analyze_run.py``.

    Narration is not in the runner's aggregate — it is third person and excluded from the
    form metrics — so its after-figure has to come from here. Reading it rather than
    printing "see tables/" matters: narration is the half with no regeneration seam, so its
    bar is the one a reader most needs to see next to the before.
    """
    path = EXP / "data" / "leak.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")) or {}


def _blank(ax, message: str) -> None:
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes,
            color="#888", fontsize=9)
    ax.set_axis_off()


def panel_leak(ax, before: dict, after: dict) -> None:
    """The primary metric, before and after, for both beat kinds."""
    if not before.get("character") or not after.get("character"):
        return _blank(ax, "missing before/after leak data")

    def share(block: dict) -> float | None:
        if not block or not block.get("total"):
            return None
        return 100 * block["leaking"] / block["total"]

    pairs = [
        ("character\nbeats", share(before.get("character")), share(after.get("character"))),
        ("narration", share(before.get("narration")), share(after.get("narration"))),
    ]
    xs = list(range(len(pairs)))
    for i, (_, was, now) in enumerate(pairs):
        for offset, value, color, label in (
            (-0.19, was, BEFORE_C, "EXP-008 (label `Player:`)"),
            (0.19, now, AFTER_C, "EXP-009 (label `You:`)"),
        ):
            if value is None:
                continue
            ax.bar(i + offset, value, width=0.36, color=color, label=label if not i else None)
            ax.text(i + offset, value + 2, f"{value:.0f}%", ha="center", fontsize=8,
                    color="#333")
    ax.set_ylim(0, 112)
    ax.set_xticks(xs)
    ax.set_xticklabels([p[0] for p in pairs], fontsize=8)
    ax.set_ylabel('% of beats saying "the player"', fontsize=9)
    ax.set_title("The leak (primary)", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)


def panel_form(ax, rows: list[dict], cells: dict) -> None:
    """The metrics that must NOT regress. A fix that costs the form is not a fix."""
    if not rows or not cells:
        return _blank(ax, "missing before/after form data")
    xs = list(range(len(FORM)))
    for i, (key, _) in enumerate(FORM):
        before = 100 * (cells.get(key, {}).get("mean") or 0.0)
        after = 100 * sum(r.get(key, 0) for r in rows) / len(rows)
        ax.bar(i - 0.19, before, width=0.36, color=BEFORE_C,
               label="EXP-008" if not i else None)
        ax.bar(i + 0.19, after, width=0.36, color=AFTER_C,
               label="EXP-009" if not i else None)
        for x, v in ((i - 0.19, before), (i + 0.19, after)):
            ax.text(x, v + 2, f"{v:.0f}%", ha="center", fontsize=8, color="#333")
    ax.set_ylim(0, 112)
    ax.set_xticks(xs)
    ax.set_xticklabels([label for _, label in FORM], fontsize=8)
    ax.set_ylabel("% of character beats", fontsize=9)
    ax.set_title("The form, which must not regress", fontsize=10)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)


def panel_sentences(ax, rows: list[dict], cells: dict) -> None:
    """Sentences per 100 words: every after-beat as a point, before as a band."""
    if not rows:
        return _blank(ax, "no run data")
    vals = [r.get("sentences_per_100_words") or 0.0 for r in rows]
    before = cells.get("sentences_per_100_words") or {}
    if before.get("mean") is not None:
        mean, std = before["mean"], before.get("std") or 0.0
        ax.axhspan(mean - std, mean + std, color=BEFORE_C, alpha=0.16, zorder=1)
        ax.axhline(mean, color=BEFORE_C, lw=1.2, ls="--", zorder=2,
                   label=f"EXP-008 {mean:.1f} ± {std:.1f}")
    ax.scatter(range(len(vals)), vals, s=24, color=AFTER_C, zorder=3)
    after_mean = sum(vals) / len(vals)
    ax.axhline(after_mean, color=AFTER_C, lw=1.6, zorder=4,
               label=f"EXP-009 {after_mean:.1f}")
    ax.margins(y=0.14)
    ax.set_xlabel("character beat, in session order", fontsize=9)
    ax.set_ylabel("terminators / 100 words", fontsize=9)
    ax.set_title("Sentences per 100 words", fontsize=10)
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)


def main() -> int:
    rows, cells = after_rows(), before_cells()
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.0))
    panel_leak(axes[0], before_leak(), after_leak())
    panel_form(axes[1], rows, cells)
    panel_sentences(axes[2], rows, cells)
    fig.suptitle(
        "EXP-2026-08-009 — labelling the player's line `You:` instead of `Player:`",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    for ext in ("png", "svg", "pdf"):
        fig.savefig(HERE / f"second_person.{ext}", dpi=200)
    plt.close(fig)
    print(f"wrote {HERE / 'second_person.png'} (+ svg, pdf)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
