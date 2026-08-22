"""Regenerate EXP-2026-08-012's figure from the recorded metrics.

Every number is read from ``data/metrics.json``. Nothing is hardcoded except the
pre-registered thresholds, which are themselves read from the same file.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE.parent / "data" / "metrics.json").read_text())

ROUTES = [("library", "Library  /"), ("story-player", "Story player  /{world}/{scene}")]
METRICS = [("CLS", "CLS", "", 1.0), ("INP", "INP", "ms", 1.0), ("LCP", "LCP", "ms", 1.0)]


def main() -> None:
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.6))
    fig.suptitle(
        "EXP-2026-08-012 — Core Web Vitals, 4× CPU throttle, "
        f"n={DATA['loads_per_route']} cold loads per route",
        fontsize=11,
    )

    for ax, (key, label, unit, scale) in zip(axes, METRICS):
        means = [DATA["routes"][r][key]["mean"] * scale for r, _ in ROUTES]
        stds = [DATA["routes"][r][key]["std"] * scale for r, _ in ROUTES]
        threshold = DATA["thresholds"][key] * scale
        # Colour by the pre-registered threshold, not by eye.
        colours = ["#1F8A5B" if m < threshold else "#9A3520" for m in means]

        bars = ax.bar([n for _, n in ROUTES], means, yerr=stds, capsize=4, color=colours)
        ax.axhline(threshold, ls="--", lw=1.2, color="#8E2B1C")
        ax.annotate(
            f"threshold {threshold:g}{unit}",
            xy=(0.98, threshold),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="bottom",
            fontsize=8,
            color="#8E2B1C",
        )
        top = max([*means, threshold]) * 1.45
        ax.set_ylim(0, top)
        ax.set_title(f"{label}{f'  ({unit})' if unit else ''}", fontsize=10)
        ax.tick_params(axis="x", labelsize=8)
        for bar, mean in zip(bars, means):
            ax.annotate(
                f"{mean:.4g}",
                xy=(bar.get_x() + bar.get_width() / 2, mean),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                fontsize=8,
            )

    fig.tight_layout(rect=(0, 0, 1, 0.92))
    for ext in ("svg", "pdf"):
        fig.savefig(HERE / f"core_web_vitals.{ext}")
    print("wrote figures/core_web_vitals.{svg,pdf}")


if __name__ == "__main__":
    main()
