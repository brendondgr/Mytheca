"""Regenerate this experiment's figures from ``data/metrics.json``.

Contract §1.4: figures are generated, never hand-placed, and never carry a number that
is not read out of the recorded metrics. Nothing here is hardcoded — if the run is
re-executed with different results, the figure changes with it, and if a metric is
missing the figure says so rather than inventing a bar.

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
ARMS = ["blocking-uncapped", "blocking-capped", "streaming-capped"]
ARM_LABELS = {
    "blocking-uncapped": "blocking\n(no budget)",
    "blocking-capped": "blocking\n(capped)",
    "streaming-capped": "streaming\n(capped)",
}


def load() -> dict:
    path = EXP / "data" / "metrics.json"
    if not path.exists():
        raise SystemExit(f"no metrics recorded yet: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def series(metrics: dict, metric: str) -> tuple[list[str], list[float], list[float]]:
    """Per-arm (labels, means, stds) for one metric, skipping arms with no value.

    Falls back to the per-run rows when no aggregate exists — which is the normal state
    for a partially-failed experiment, where the contract forbids aggregating over the
    surviving runs. In that case the bar shows the per-run mean of THAT arm only if the
    arm itself is complete; an arm with any failed run is skipped entirely.
    """
    agg = metrics.get("aggregate") or {}
    rows = metrics.get("per_run") or []
    labels: list[str] = []
    means: list[float] = []
    stds: list[float] = []
    for arm in ARMS:
        key = f"{arm}.{metric}"
        if key in agg:
            labels.append(ARM_LABELS[arm])
            means.append(float(agg[key]["mean"]))
            stds.append(float(agg[key].get("std") or 0.0))
            continue
        arm_rows = [r for r in rows if r.get("arm") == arm]
        if not arm_rows or any(r.get("error") for r in arm_rows):
            continue
        values = [float(r[metric]) for r in arm_rows if r.get(metric) is not None]
        if not values:
            continue
        mean = sum(values) / len(values)
        labels.append(ARM_LABELS[arm])
        means.append(mean)
        stds.append((sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5)
    return labels, means, stds


def bar(ax, metrics: dict, metric: str, title: str, ylabel: str) -> None:
    labels, means, stds = series(metrics, metric)
    if not labels:
        ax.text(0.5, 0.5, f"no data for\n{metric}", ha="center", va="center",
                transform=ax.transAxes, fontsize=9, color="#888")
        ax.set_axis_off()
        return
    bars = ax.bar(labels, means, yerr=stds if any(stds) else None, capsize=4,
                  color=["#b4483c", "#c08b3e", "#4a7c59"][: len(labels)])
    ax.set_title(title, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.tick_params(labelsize=8)
    for rect, value in zip(bars, means):
        ax.annotate(f"{value:.1f}", (rect.get_x() + rect.get_width() / 2, value),
                    textcoords="offset points", xytext=(0, 3), ha="center", fontsize=8)


def main() -> None:
    metrics = load()
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.6))
    bar(axes[0], metrics, "ttft_s", "Time to first visible token", "seconds")
    bar(axes[1], metrics, "wall_clock_s", "Total generation", "seconds")
    bar(axes[2], metrics, "completion_tokens", "Tokens produced", "tokens")
    fig.suptitle(
        "EXP-2026-08-003 — capping the reasoning vs. streaming the transport", fontsize=11
    )
    fig.tight_layout()
    # Raster for reading, vector for the paper — the validator requires all three.
    for suffix in ("png", "svg", "pdf"):
        out = HERE / f"latency_by_arm.{suffix}"
        fig.savefig(out, dpi=150)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
