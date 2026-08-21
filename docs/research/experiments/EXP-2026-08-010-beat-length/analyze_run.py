"""Tabulate the arms, including the two numbers the runner's aggregate cannot express.

The runner writes mean ± std per arm per metric. Two things this experiment turns on are not
means:

* **in-band share** — the fraction of beats inside the tier's stated range. A mean of 3 could
  be "every beat at 3" or "half at 1 and half at 5", and only the first is a working control.
* **overlap** — whether any `short` beat is as long as any `long` beat. Non-overlapping
  ranges are what makes an ordinal claim safe at this n.

Both are computed here from `data/metrics.json` — the run's own recorded rows — and written to
`tables/`. Nothing is counted by hand, and the baseline is read out of EXP-2026-08-009's
recorded manifest rather than retyped.

    uv run python docs/research/experiments/EXP-2026-08-010-beat-length/analyze_run.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE_EXP = HERE.parent / "EXP-2026-08-009-prose-second-person"

ARMS = ["short", "medium", "long"]
TARGET = {"short": (1, 2), "medium": (2, 4), "long": (5, 6)}


def baseline_cells() -> dict[str, dict]:
    """EXP-2026-08-009's `metrics.values` — the same session shape with NO length control."""
    path = BASELINE_EXP / "manifest.yaml"
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


def main() -> int:
    path = HERE / "data" / "metrics.json"
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        return 1
    rows = [r for r in (json.loads(path.read_text(encoding="utf-8")) or {}).get("per_run") or []
            if not r.get("error")]
    if not rows:
        print("no beat rows", file=sys.stderr)
        return 1

    per_arm = {arm: [r for r in rows if r.get("arm") == arm] for arm in ARMS}
    paras = {arm: [int(r.get("paragraph_breaks") or 0) + 1 for r in group]
             for arm, group in per_arm.items()}

    out: dict[str, object] = {"source": "data/metrics.json"}
    lines = [
        "| Arm | Target | Paragraphs (mean ± std) | Range | In band | Chars (mean ± std) | n |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for arm in ARMS:
        group, values = per_arm[arm], paras[arm]
        if not values:
            lines.append(f"| {arm} | — | no beats | — | — | — | 0 |")
            continue
        lo, hi = TARGET[arm]
        n = len(values)
        mean = sum(values) / n
        std = (sum((v - mean) ** 2 for v in values) / n) ** 0.5
        chars = [r.get("chars") or 0 for r in group]
        cmean = sum(chars) / n
        cstd = (sum((c - cmean) ** 2 for c in chars) / n) ** 0.5
        inside = sum(1 for v in values if lo <= v <= hi)
        out[arm] = {
            "n": n, "target": [lo, hi],
            "paragraphs": {"mean": round(mean, 3), "std": round(std, 3),
                           "min": min(values), "max": max(values)},
            "chars": {"mean": round(cmean, 1), "std": round(cstd, 1),
                      "min": min(chars), "max": max(chars)},
            "in_band": inside, "in_band_share": round(inside / n, 4),
        }
        lines.append(
            f"| `{arm}` | {lo}–{hi} ¶ | **{mean:.2f} ± {std:.2f}** | {min(values)}–{max(values)} "
            f"| {inside}/{n} ({100 * inside / n:.0f} %) | {cmean:.0f} ± {cstd:.0f} | {n} |"
        )

    # Overlap: the claim is ordinal, so what matters is whether the ranges touch at all.
    overlaps = []
    for a, b in (("short", "medium"), ("medium", "long"), ("short", "long")):
        if paras[a] and paras[b]:
            touching = max(paras[a]) >= min(paras[b])
            overlaps.append(f"{a} max {max(paras[a])} vs {b} min {min(paras[b])}: "
                            + ("OVERLAP" if touching else "no overlap"))
    out["overlap"] = overlaps

    base = baseline_cells()
    if base.get("paragraph_breaks"):
        # EXP-009 recorded paragraph BREAKS; paragraphs is breaks + 1.
        lines.append(
            f"| _EXP-009 (no control)_ | — | _{base['paragraph_breaks']['mean'] + 1:.2f}_ | — | — "
            f"| _{base.get('chars', {}).get('mean', 0):.0f}_ | _{int(base['paragraph_breaks']['n'])}_ |"
        )

    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "arms.md").write_text(
        "\n".join(lines) + "\n\n" + "\n".join(f"- {o}" for o in overlaps) + "\n", encoding="utf-8"
    )
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "arms.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("\n".join(lines))
    print()
    for o in overlaps:
        print(o)
    print(f"\nwrote tables/arms.md and data/arms.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
