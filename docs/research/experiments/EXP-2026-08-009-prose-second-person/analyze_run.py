"""Score the narration beats of this run for the leak, and tabulate the before/after.

The runner aggregates **character** beats only — narration is third person and forbidden
dialogue, so scoring it on `has_speech` would score the contract against a prompt that
forbids the thing counted. But narration leaked in `EXP-2026-08-008` too (6 of 10 beats),
and it is the half with **no regeneration seam**: narration delta-streams from its first
token by design, so the prompt is its only defence and it is the half most likely to have
survived the fix. It therefore has to be scored explicitly rather than left out.

Everything is read out of recorded files — this run's `logs/transcript.json` and
`data/metrics.json`, and EXP-2026-08-008's `manifest.yaml` and `data/leak.json` — through
the same `emission.names_the_player` the engine uses. Nothing is counted or retyped by hand.

    uv run python docs/research/experiments/EXP-2026-08-009-prose-second-person/analyze_run.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
# web/backend only — the repo root holds an `app.py` that shadows the `app` package.
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.services import emission  # noqa: E402

BEFORE_EXP = HERE.parent / "EXP-2026-08-008-prose-end-to-end"
CHARACTER_KINDS = {"character_prose", "character_dialogue", "character_action"}


def before_cells() -> dict[str, dict]:
    """EXP-2026-08-008's `metrics.values`, parsed out of its manifest (see figures/)."""
    cells: dict[str, dict] = {}
    key: str | None = None
    in_values = False
    for line in (BEFORE_EXP / "manifest.yaml").read_text(encoding="utf-8").splitlines():
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
    transcript = HERE / "logs" / "transcript.json"
    if not transcript.exists():
        print(f"missing {transcript}", file=sys.stderr)
        return 1
    beats = (json.loads(transcript.read_text(encoding="utf-8")) or {}).get("beats") or []
    if not beats:
        print("no beats in logs/transcript.json", file=sys.stderr)
        return 1

    groups = {
        "character": [b for b in beats if b.get("type") in CHARACTER_KINDS],
        "narration": [b for b in beats if b.get("type") == "narration"],
    }
    leak: dict[str, object] = {
        "source": "logs/transcript.json",
        "detector": "app.services.emission.names_the_player (whole passage, no window)",
    }
    after: dict[str, tuple[int, int]] = {}
    for name, group in groups.items():
        leaking = [b for b in group if emission.names_the_player(b.get("text") or "")]
        leak[name] = {"total": len(group), "leaking": len(leaking)}
        after[name] = (len(leaking), len(group))
        leak[f"{name}_beats"] = [
            {"turn": b.get("turn"), "beat": b.get("beat"), "text": b.get("text")}
            for b in leaking
        ]
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "leak.json").write_text(json.dumps(leak, indent=2), encoding="utf-8")

    before = json.loads((BEFORE_EXP / "data" / "leak.json").read_text(encoding="utf-8"))
    table = [
        "| Beat kind | EXP-008 (`Player:`) | EXP-009 (`You:`) |",
        "| --- | --- | --- |",
    ]
    for name in ("character", "narration"):
        b = before.get(name) or {}
        a_leak, a_total = after[name]
        b_share = f"{100 * b['leaking'] / b['total']:.0f} %" if b.get("total") else "—"
        a_share = f"{100 * a_leak / a_total:.0f} %" if a_total else "—"
        table.append(
            f"| {name} | {b.get('leaking', '?')} / {b.get('total', '?')} ({b_share}) "
            f"| {a_leak} / {a_total} ({a_share}) |"
        )
    (HERE / "tables").mkdir(exist_ok=True)
    (HERE / "tables" / "leak.md").write_text("\n".join(table) + "\n", encoding="utf-8")

    # The form metrics side by side, so a regression cannot hide in a folder nobody opens.
    cells = before_cells()
    metrics = json.loads((HERE / "data" / "metrics.json").read_text(encoding="utf-8"))
    now = metrics.get("aggregate") or {}
    form = ["| Metric | EXP-008 | EXP-009 |", "| --- | --- | --- |"]
    for key in ("has_speech", "paragraph_breaks", "is_distinct", "sentences_per_100_words",
                "is_scratchpad", "starts_mid_sentence", "names_the_player", "chars"):
        b, a = cells.get(key), now.get(key)
        fmt = lambda c: (  # noqa: E731 - a two-line helper reads worse here
            f"{c['mean']:.2f} ± {c.get('std', 0):.2f} (n={int(c['n'])})" if c else "—"
        )
        form.append(f"| `{key}` | {fmt(b)} | {fmt(a)} |")
    (HERE / "tables" / "form.md").write_text("\n".join(form) + "\n", encoding="utf-8")

    for name, (leaking, total) in after.items():
        print(f"{name}: naming the player {leaking}/{total}")
    print(f"wrote data/leak.json, tables/leak.md, tables/form.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
