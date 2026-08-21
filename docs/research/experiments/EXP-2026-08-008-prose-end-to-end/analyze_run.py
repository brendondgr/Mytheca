"""Recompute this run's two post-hoc metrics from its recorded transcript.

Two metrics this experiment reports did not exist when the runner wrote `manifest.yaml`:

* `names_the_player` — the defect the run *exposed*. `emission.names_the_player` was written
  afterwards, in response to it, so the runner could not have recorded it.
* `is_distinct` — recorded per row as `duplicate_of`, but merged into the manifest as a bare
  count, which `manifest_schema.MetricValue` rejects (a count hides the n it was taken over,
  and it is right to reject it).

Both are recomputed here from `logs/transcript.json` — the run's raw recorded output —
through the same `emission` functions the engine uses, and written back as proper
`{mean, std, n}` cells. **Nothing here is counted by hand, and nothing is invented:** if the
transcript is missing, this fails rather than guessing.

    uv run python docs/research/experiments/EXP-2026-08-008-prose-end-to-end/analyze_run.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
# web/backend only — the repo root holds an `app.py` that shadows the `app` package.
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.services import emission  # noqa: E402

CHARACTER_KINDS = {"character_prose", "character_dialogue", "character_action"}


def cell(values: list[int]) -> dict[str, float | int]:
    """A distribution over beats: mean, population std, and the n it was taken over."""
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    return {"mean": round(mean, 6), "std": round(var**0.5, 6), "n": n}


def main() -> int:
    transcript_path = HERE / "logs" / "transcript.json"
    if not transcript_path.exists():
        print(f"missing {transcript_path}", file=sys.stderr)
        return 1
    beats = (json.loads(transcript_path.read_text(encoding="utf-8")) or {}).get("beats") or []
    if not beats:
        print("no beats in logs/transcript.json", file=sys.stderr)
        return 1

    groups = {
        "character": [b for b in beats if b.get("type") in CHARACTER_KINDS],
        "narration": [b for b in beats if b.get("type") == "narration"],
    }

    # --- the leak, per beat kind ------------------------------------------------------
    leak: dict[str, object] = {
        "source": "logs/transcript.json",
        "detector": "app.services.emission.names_the_player (whole passage, no window)",
    }
    rows = []
    for name, group in groups.items():
        leaking = [b for b in group if emission.names_the_player(b.get("text") or "")]
        leak[name] = {"total": len(group), "leaking": len(leaking)}
        rows.append((name, len(leaking), len(group)))
        # Every offending beat, so a reader can check the count rather than trust it.
        leak[f"{name}_beats"] = [
            {"turn": b.get("turn"), "beat": b.get("beat"), "text": b.get("text")}
            for b in leaking
        ]
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "leak.json").write_text(json.dumps(leak, indent=2), encoding="utf-8")

    (HERE / "tables").mkdir(exist_ok=True)
    table = ["| Beat kind | Naming the player | Total | Share |", "| --- | --- | --- | --- |"]
    for name, leaking, total in rows:
        share = f"{100 * leaking / total:.0f} %" if total else "—"
        table.append(f"| {name} | {leaking} | {total} | {share} |")
    (HERE / "tables" / "leak.md").write_text("\n".join(table) + "\n", encoding="utf-8")

    # --- write both cells back into the manifest --------------------------------------
    # Character beats only, matching every other cell in `metrics.values` (narration is
    # third person and is scored separately, in tables/leak.md).
    chars = groups["character"]
    seen: set[str] = set()
    distinct: list[int] = []
    for beat in chars:
        body = (beat.get("text") or "").strip()
        distinct.append(0 if body in seen else 1)
        seen.add(body)
    cells = {
        "names_the_player": cell(
            [1 if emission.names_the_player(b.get("text") or "") else 0 for b in chars]
        ),
        "is_distinct": cell(distinct),
    }

    manifest = HERE / "manifest.yaml"
    text = manifest.read_text(encoding="utf-8")
    lines = text.splitlines()
    # Bare-count cells the runner wrote before the schema rejected them. Every claim they
    # made survives in a distribution cell (18 of 18 with speech == has_speech mean 1.0,
    # n 18), so they are dropped rather than converted into a fake distribution.
    stale = ("beats.total", "beats.distinct", "beats.with_speech",
             "beats.with_paragraph_breaks", "beats.naming_the_player")
    kept = [ln for ln in lines if not any(f"    {key}:" == ln[:len(key) + 5] for key in stale)]
    if kept == lines and not any(k in text for k in cells):
        print("manifest already clean; adding cells", file=sys.stderr)

    out: list[str] = []
    for line in kept:
        out.append(line)
        if line.strip() == "values:":
            for name, value in sorted(cells.items()):
                out.append(f"    {name}:")
                out.append(f"      mean: {value['mean']}")
                out.append(f"      std: {value['std']}")
                out.append(f"      n: {value['n']}")
    manifest.write_text("\n".join(out) + "\n", encoding="utf-8")

    for name, leaking, total in rows:
        print(f"{name}: naming the player {leaking}/{total}")
    for name, value in sorted(cells.items()):
        print(f"{name}: {value}")
    print(f"wrote data/leak.json, tables/leak.md, and merged 2 cells into manifest.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
