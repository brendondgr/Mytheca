"""Regenerate this experiment's figures from the recorded run logs.

Contract §1.4: figures are generated from recorded results, never hand-placed, and carry
no number that is not read back out of the record. Reads this experiment's
``logs/conversation.log`` **and** EXP-2026-08-005's, so the before/after panels are drawn
from both records rather than from numbers retyped out of a results table. Any panel whose
data is missing is skipped with a note rather than invented.

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
BASELINE = EXP.parent / "EXP-2026-08-005-conversation-scaling"

AFTER = "#4a7c59"
BEFORE = "#b4483c"
ACCENT = "#c08b3e"


def load(experiment: Path, name: str) -> list[dict]:
    path = experiment / "logs" / f"{name}.log"
    if not path.exists():
        return []
    return (json.loads(path.read_text(encoding="utf-8")) or {}).get("rows") or []


def _ok(rows: list[dict]) -> list[dict]:
    return sorted((r for r in rows if not r.get("error")), key=lambda r: r.get("turn", 0))


def _blank(ax, message: str) -> None:
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes,
            color="#888", fontsize=9)
    ax.set_axis_off()


def panel_total(ax, before: list[dict], after: list[dict]) -> None:
    """Whole-turn wall clock, before and after, per turn."""
    if not after:
        return _blank(ax, "no run data")
    if before:
        ax.plot([r["turn"] for r in before], [r.get("total_s") for r in before],
                "o--", color=BEFORE, label="before (EXP-005)")
    ax.plot([r["turn"] for r in after], [r.get("total_s") for r in after],
            "o-", color=AFTER, label="after")
    ax.set_xlabel("player turn")
    ax.set_ylabel("seconds")
    ax.set_title("Whole turn", fontsize=10)
    ax.legend(fontsize=8)
    ax.set_ylim(bottom=0)


def panel_reuse(ax, before: list[dict], after: list[dict]) -> None:
    """The prompt-cache question: how much of each prompt is reusable, per turn.

    The two series measure different things and are labelled as such — the baseline could
    only report the server's cache-hit ratio, this run reports the locally-computed
    reusable prefix. Both answer "what share of the prompt did not have to be re-read".
    """
    drew = False
    if before:
        hits = [(r["turn"], r.get("cache_hit_ratio")) for r in before]
        hits = [(t, v) for t, v in hits if isinstance(v, (int, float))]
        if hits:
            ax.plot([t for t, _ in hits], [100 * v for _, v in hits], "o--", color=BEFORE,
                    label="before — server cache hit")
            drew = True
    if after:
        reuse = [(r["turn"], r.get("reuse_ratio_mean")) for r in after]
        reuse = [(t, v) for t, v in reuse if isinstance(v, (int, float))]
        if reuse:
            ax.plot([t for t, _ in reuse], [100 * v for _, v in reuse], "o-", color=AFTER,
                    label="after — reusable prefix")
            drew = True
    if not drew:
        return _blank(ax, "no reuse data")
    ax.set_xlabel("player turn")
    ax.set_ylabel("% of prompt not re-read")
    ax.set_title("Prompt reuse across a scene", fontsize=10)
    ax.legend(fontsize=8)
    ax.set_ylim(0, 100)


def _planner_calls(rows: list[dict]) -> list[tuple[int, int]]:
    """Planner calls per turn, counted from whatever the row records.

    This run stores ``planner_calls`` directly. The baseline predates that field, so it is
    recovered from its ``step_marks`` — the same source the step tables were built from —
    rather than being retyped from the results table.
    """
    out: list[tuple[int, int]] = []
    for row in rows:
        direct = row.get("planner_calls")
        if isinstance(direct, int):
            out.append((row["turn"], direct))
            continue
        marks = row.get("step_marks") or {}
        n = sum(1 for k in marks if k == "step:planning" or k.startswith("step:planning#"))
        if n:
            out.append((row["turn"], n))
    return out


def panel_planner(ax, before: list[dict], after: list[dict]) -> None:
    b, a = _planner_calls(before), _planner_calls(after)
    if not a and not b:
        return _blank(ax, "no planner data")
    width = 0.38
    if b:
        ax.bar([t - width / 2 for t, _ in b], [n for _, n in b], width,
               color=BEFORE, label="before (EXP-005)")
    if a:
        ax.bar([t + width / 2 for t, _ in a], [n for _, n in a], width,
               color=AFTER, label="after")
    ax.set_xlabel("player turn")
    ax.set_ylabel("planner calls")
    ax.set_title("Planner calls per turn", fontsize=10)
    ax.legend(fontsize=8)


def panel_first_signal(ax, after: list[dict]) -> None:
    """What the player waits for: the first thing on screen vs. the first prose."""
    if not after:
        return _blank(ax, "no run data")
    turns = [r["turn"] for r in after]
    ax.plot(turns, [r.get("first_visible_s") for r in after], "o-", color=ACCENT,
            label="first prose")
    reason = [r.get("first_reasoning_s") for r in after]
    if any(isinstance(v, (int, float)) for v in reason):
        ax.plot(turns, reason, "o-", color=AFTER, label="first live thinking")
    ax.set_xlabel("player turn")
    ax.set_ylabel("seconds")
    ax.set_title("Time to something on screen", fontsize=10)
    ax.legend(fontsize=8)
    ax.set_ylim(bottom=0)


def main() -> None:
    after = _ok(load(EXP, "conversation"))
    before = _ok(load(BASELINE, "conversation"))
    if not after:
        raise SystemExit("no run log recorded yet for EXP-2026-08-006")
    if not before:
        print("note: EXP-2026-08-005 log not readable — before/after panels will be partial")

    fig, axes = plt.subplots(1, 4, figsize=(16, 3.8))
    panel_total(axes[0], before, after)
    panel_planner(axes[1], before, after)
    panel_reuse(axes[2], before, after)
    panel_first_signal(axes[3], after)
    fig.suptitle(
        "EXP-2026-08-006 — turn latency before and after the overhaul (same endpoint, same scene config)",
        fontsize=11,
    )
    fig.tight_layout()
    for suffix in ("png", "svg", "pdf"):
        out = HERE / f"overhaul.{suffix}"
        fig.savefig(out, dpi=150)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
