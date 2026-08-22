"""Regenerate this experiment's figure from its recorded rows.

Contract §1.4: figures are generated from recorded results and carry no number that is not
read back out of the record. Everything here comes from `data/metrics.json` (the rows the
manifest aggregates) and `data/probe.json` (the read-back written by
`utils/scripts/research/analyze_compaction_probe.py`). The only drawn constants are the
probe's hit threshold and the anchor block — both *definitions*, and the anchor block is
read from `probe.json` rather than typed.

Three panels, one per hypothesis that has a number:

* **H1** — which tokens of the planted fact each arm's answer reached. A bar of the score
  alone cannot distinguish "forgot the fact" from "paraphrased it", and that distinction is
  the whole finding: both arms lose the *verbs* to paraphrase, only arm B loses the *nouns*.
* **H2 cost, reading** — mean prompt tokens against the share of each prompt byte-identical
  to the previous one. The second is what a cache is; drawing it beside the saving is the
  only way the trade is visible.
* **H2 cost, calls** — how many times the summary was rewritten, against the bound H2
  predicted (one per anchor block that fell out).

n = 1 scene per arm. Every panel is annotated with that, because a bar chart of two numbers
invites being read as a rate and it is not one.

Run via ``make figures`` (or directly).
"""

from __future__ import annotations

import json
import math
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
EXP = HERE.parent

ARMS = ["A", "B"]
COLOR = {"A": "#4a6d8c", "B": "#b4483c"}
LABEL = {"A": "A — fixed 100 beats\n(control, no compaction)", "B": "B — fitted window\n+ compaction"}
#: The score at which the runner calls the probe answered. A definition of the metric.
HIT_THRESHOLD = 0.34


def _load(name: str) -> dict:
    path = EXP / "data" / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")) or {}


def rows() -> dict[str, dict]:
    data = (_load("metrics.json").get("per_run") or [])
    return {r["arm"]: r for r in data if r.get("status") == "ok" and r.get("arm") in ARMS}


def probes() -> dict[str, dict]:
    data = _load("probe.json")
    return {a["arm"]: a for a in (data.get("arms") or []) if a.get("arm") in ARMS}


def _blank(ax, message: str) -> None:
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes,
            color="#888", fontsize=9)
    ax.set_axis_off()


def panel_probe(ax, run: dict[str, dict], probe: dict[str, dict]) -> None:
    """H1 — of the planted fact's content tokens, which the answer reached."""
    if not probe:
        return _blank(ax, "no probe read-back (data/probe.json)")
    for i, arm in enumerate(ARMS):
        p = probe.get(arm)
        if not p:
            continue
        wanted = p.get("fact_tokens_wanted") or []
        hit = p.get("fact_tokens_hit") or []
        total = len(wanted) or 1
        ax.bar(i, len(hit) / total, width=0.5, color=COLOR[arm], zorder=2)
        ax.bar(i, 1 - len(hit) / total, width=0.5, bottom=len(hit) / total,
               color=COLOR[arm], alpha=0.14, zorder=2)
        ax.text(i, len(hit) / total - 0.05, f"{len(hit)}/{total}", ha="center", va="top",
                color="white", fontsize=10, fontweight="bold", zorder=3)
        missed = ", ".join(p.get("fact_tokens_missed") or []) or "none"
        ax.text(i, 1.02, "missed: " + textwrap.fill(missed, 26), ha="center", va="bottom",
                fontsize=7, color="#555", linespacing=1.3)
    ax.axhline(HIT_THRESHOLD, color="#333", lw=1, ls="--", zorder=4)
    ax.text(len(ARMS) - 0.52, HIT_THRESHOLD + 0.015, f"answered at ≥ {HIT_THRESHOLD}",
            fontsize=7, color="#333")
    ax.set_xticks(range(len(ARMS)))
    ax.set_xticklabels([LABEL[a] for a in ARMS], fontsize=8)
    ax.set_ylim(0, 1.24)
    ax.set_ylabel("share of the fact's content tokens", fontsize=9)
    ax.set_title("H1 — what the probe answer recovered", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)


def panel_reading(ax, run: dict[str, dict]) -> None:
    """H2 cost — what each arm reads, against how much of it the cache could keep."""
    if not run:
        return _blank(ax, "no recorded rows")
    twin = ax.twinx()
    for i, arm in enumerate(ARMS):
        r = run.get(arm) or {}
        tokens = r.get("prompt_tokens_mean")
        share = r.get("reusable_prefix_share")
        if tokens is not None:
            ax.bar(i, tokens, width=0.5, color=COLOR[arm], alpha=0.35, zorder=1)
            ax.text(i, tokens + 90, f"{tokens:,.0f}", ha="center", fontsize=8, color="#333")
        if share is not None:
            twin.plot([i - 0.25, i + 0.25], [share, share], color=COLOR[arm], lw=2.5, zorder=3)
            twin.text(i, share + 0.03, f"{share:.0%} reusable", ha="center", fontsize=8,
                      color=COLOR[arm])
    ax.set_xticks(range(len(ARMS)))
    ax.set_xticklabels([LABEL[a] for a in ARMS], fontsize=8)
    ax.set_ylabel("mean prompt tokens (bars)", fontsize=9)
    twin.set_ylabel("reusable prefix share (lines)", fontsize=9)
    twin.set_ylim(0, 1.12)
    ax.set_title("H2 — cheaper to read, worse to cache", fontsize=10)
    ax.spines[["top"]].set_visible(False)
    twin.spines[["top"]].set_visible(False)


def panel_calls(ax, run: dict[str, dict], probe: dict[str, dict], block: int) -> None:
    """H2 cost — rewrites of the summary, against the bound the hypothesis predicted."""
    if not run:
        return _blank(ax, "no recorded rows")
    for i, arm in enumerate(ARMS):
        calls = (run.get(arm) or {}).get("recap_calls") or 0
        ax.bar(i, calls, width=0.5, color=COLOR[arm], zorder=2)
        ax.text(i, calls + 0.3, str(calls), ha="center", fontsize=9, color="#333")
        dropped = (probe.get(arm) or {}).get("dropped_beats") or 0
        if not dropped:
            # Nothing fell out of this arm's window, so the bound is not a prediction it
            # could have broken. Say that rather than draw a line at zero.
            ax.text(i, 1.5, "nothing dropped —\nno summary to write", ha="center",
                    fontsize=7.5, color="#555")
            continue
        bound = math.ceil(dropped / block)
        ax.plot([i - 0.34, i + 0.34], [bound, bound], color="#333", lw=1.6, ls="--", zorder=3)
        ax.text(i, bound + 0.35, f"H2 predicted ≤ {bound}", fontsize=7.5, color="#333",
                ha="center")
    ax.set_xticks(range(len(ARMS)))
    ax.set_xticklabels([LABEL[a] for a in ARMS], fontsize=8)
    ax.set_ylabel("times the summary was rewritten", fontsize=9)
    ax.set_title(f"H2 — predicted: one call per {block}-beat block", fontsize=10)
    ax.set_ylim(0, None)
    ax.spines[["top", "right"]].set_visible(False)


def main() -> int:
    run, probe = rows(), probes()
    block = int(_load("probe.json").get("anchor_block") or 20)
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4))
    panel_probe(axes[0], run, probe)
    panel_reading(axes[1], run)
    panel_calls(axes[2], run, probe, block)
    turns = (run.get("A") or {}).get("turns")
    fig.suptitle(
        "EXP-2026-08-011 — does compacting dropped history preserve continuity, and what does "
        f"it cost?   (n = 1 scene per arm{f', {turns} turns' if turns else ''} — not a rate)",
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    for ext in ("png", "svg", "pdf"):
        fig.savefig(HERE / f"context_compaction.{ext}", dpi=200)
    plt.close(fig)
    print(f"wrote {HERE / 'context_compaction.png'} (+ svg, pdf)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
