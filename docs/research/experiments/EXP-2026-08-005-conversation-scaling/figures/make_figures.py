"""Regenerate this experiment's figures from the recorded run logs.

Contract §1.4: figures are generated from recorded results, never hand-placed, and carry
no number that is not read back out of the record. Reads ``logs/conversation.log`` and
``logs/layout.log`` — both written by
``utils/scripts/research/run_conversation_scaling.py`` — and skips any panel whose data is
absent rather than inventing a series.

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


def load(name: str) -> list[dict]:
    path = EXP / "logs" / f"{name}.log"
    if not path.exists():
        return []
    return (json.loads(path.read_text(encoding="utf-8")) or {}).get("rows") or []


def _ok(rows: list[dict]) -> list[dict]:
    return [r for r in rows if not r.get("error")]


def panel_conversation(ax_time, ax_ctx, rows: list[dict]) -> None:
    rows = sorted(_ok(rows), key=lambda r: r["turn"])
    if not rows:
        for ax in (ax_time, ax_ctx):
            ax.text(0.5, 0.5, "no conversation data", ha="center", va="center",
                    transform=ax.transAxes, color="#888", fontsize=9)
            ax.set_axis_off()
        return
    turns = [r["turn"] for r in rows]

    ax_time.plot(turns, [r.get("total_s") for r in rows], "o-", color="#b4483c",
                 label="whole turn")
    ax_time.plot(turns, [r.get("first_visible_s") for r in rows], "o-", color="#4a7c59",
                 label="first visible prose")
    ax_time.set_xlabel("player turn")
    ax_time.set_ylabel("seconds")
    ax_time.set_title("Latency across a conversation", fontsize=10)
    ax_time.legend(fontsize=8)
    ax_time.set_ylim(bottom=0)

    ax_ctx.plot(turns, [r.get("prompt_tokens_max") for r in rows], "o-", color="#c08b3e",
                label="prompt tokens")
    cached = [r.get("cached_tokens_max") for r in rows]
    if any(c is not None for c in cached):
        ax_ctx.plot(turns, cached, "o-", color="#4a7c59", label="of which cached")
    ax_ctx.set_xlabel("player turn")
    ax_ctx.set_ylabel("tokens")
    ax_ctx.set_title("Context sent per turn", fontsize=10)
    ax_ctx.legend(fontsize=8)
    ax_ctx.set_ylim(bottom=0)


def panel_layout(ax, rows: list[dict]) -> None:
    rows = _ok(rows)
    if not rows:
        ax.text(0.5, 0.5, "no layout data", ha="center", va="center",
                transform=ax.transAxes, color="#888", fontsize=9)
        ax.set_axis_off()
        return
    colors = {"volatile-first": "#b4483c", "volatile-last": "#4a7c59"}
    for layout, color in colors.items():
        by_turn: dict[int, list[float]] = {}
        for r in rows:
            if r.get("layout") != layout or r.get("ttft_s") is None:
                continue
            by_turn.setdefault(r["turn"], []).append(float(r["ttft_s"]))
        if not by_turn:
            continue
        turns = sorted(by_turn)
        means = [sum(by_turn[t]) / len(by_turn[t]) for t in turns]
        ax.plot(turns, means, "o-", color=color, label=layout)
    ax.set_xlabel("transcript length (turns of history)")
    ax.set_ylabel("time to first token (s)")
    ax.set_title("Prefill vs. prompt layout", fontsize=10)
    ax.legend(fontsize=8)
    ax.set_ylim(bottom=0)


def main() -> None:
    conversation = load("conversation")
    layout = load("layout")
    if not conversation and not layout:
        raise SystemExit("no run logs recorded yet")

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    panel_conversation(axes[0], axes[1], conversation)
    panel_layout(axes[2], layout)
    fig.suptitle(
        "EXP-2026-08-005 — how a scene slows down, and what the prompt cache is doing",
        fontsize=11,
    )
    fig.tight_layout()
    for suffix in ("png", "svg", "pdf"):
        out = HERE / f"scaling.{suffix}"
        fig.savefig(out, dpi=150)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
