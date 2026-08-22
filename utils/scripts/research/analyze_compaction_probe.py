"""Read back what each arm of EXP-2026-08-011 actually said at the probe.

`run_context_compaction.py` records a *score*. A score of 0.333 does not say whether the
scene forgot the fact or paraphrased it, and those are different findings — so this reads
the two sessions back out of the running backend and records the prose, the fact tokens
that survived, and (arm B only) the summary the cast was reading at that moment.

It writes `data/probe.json`. Nothing here recomputes a metric that `metrics.json` already
holds; the scores are re-derived with the same `direction_check.coverage` call the runner
used purely as a check that the read-back lines up with the recorded row, and a mismatch is
written into the file rather than silently reconciled.

Run it while the backend that hosted the run is still up::

    uv run python -m utils.scripts.research.analyze_compaction_probe \\
        --api http://127.0.0.1:3355/api \\
        --experiment docs/research/experiments/EXP-2026-08-011-context-compaction
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.request
from typing import Any

from . import REPO_ROOT
from .run_context_compaction import PROBE_FACT

sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.services import direction_check  # noqa: E402

#: The runner scores the tail of the transcript, not a single event. Kept identical here so
#: the read-back is checking the recorded number rather than inventing a kinder one.
TAIL_CHARS = 2000


def _get(api: str, path: str) -> dict[str, Any]:
    req = urllib.request.Request(f"{api}{path}")
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode())


def _prose(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") in ("narration", "character_prose")]


def read_arm(api: str, row: dict) -> dict[str, Any]:
    """One arm's probe answer, the fact tokens it reached, and what it was reading."""
    scenario, session = row.get("scenario"), row.get("session")
    history = _get(api, f"/play/{scenario}/sessions/{session}")
    knowledge = _get(api, f"/play/{scenario}/sessions/{session}/context")
    events = history.get("events") or []

    # Everything after the last player line is the answer to the probe.
    turns = [i for i, e in enumerate(events) if e.get("type") == "user_turn"]
    answer_events = _prose(events[turns[-1] + 1 :]) if turns else []
    answer = "\n\n".join(str((e.get("data") or {}).get("text") or "") for e in answer_events)

    transcript = " ".join(str((e.get("data") or {}).get("text") or "") for e in _prose(events))
    scored_text = transcript[-TAIL_CHARS:]

    wanted = direction_check.content_words(PROBE_FACT) - direction_check.content_words("Rensal Vey")
    hit = wanted & direction_check.content_words(scored_text)
    score = round(direction_check.coverage(PROBE_FACT, scored_text, ignore_names=["Rensal Vey"]), 3)

    summary = knowledge.get("summary") or {}
    return {
        "arm": row.get("arm"),
        "scenario": scenario,
        "session": session,
        "probe_answer": answer,
        "fact_tokens_wanted": sorted(wanted),
        "fact_tokens_hit": sorted(hit),
        "fact_tokens_missed": sorted(wanted - hit),
        "score_recomputed": score,
        "score_recorded": row.get("probe_score"),
        "score_matches_recorded": score == row.get("probe_score"),
        "window_beats": knowledge.get("windowBeats"),
        "window_source": knowledge.get("windowSource"),
        "dropped_beats": knowledge.get("droppedBeats"),
        "budget_tokens": knowledge.get("budgetTokens"),
        "prompt_tokens": knowledge.get("promptTokens"),
        "summary_text": summary.get("text") or "",
        "summary_through_seq": summary.get("throughSeq"),
        "compaction_folds": [
            (t.get("data") or {}) for t in history.get("traces") or []
            if t.get("step") == "compaction"
        ],
    }


COLUMNS = [
    ("arm", "Arm"),
    ("probe_score", "Probe score"),
    ("__tokens__", "Fact tokens"),
    ("probe_hit", "Answered"),
    ("prompt_tokens_mean", "Prompt tokens (mean)"),
    ("reusable_prefix_share", "Reusable prefix"),
    ("recap_calls", "Summary rewrites"),
    ("turn_seconds_mean", "s / turn"),
]


def write_table(exp: pathlib.Path, rows: list[dict], arms: list[dict]) -> pathlib.Path:
    """The RESULTS table, generated so it cannot drift from the rows it describes.

    One line per run and no aggregate row: n = 1 per arm, and a mean of one number
    dressed as a statistic is the mistake EXP-2026-08-001 exists to warn about.
    """
    by_arm = {a["arm"]: a for a in arms}
    out = ["| " + " | ".join(label for _, label in COLUMNS) + " |",
           "| " + " | ".join("---" for _ in COLUMNS) + " |"]
    for r in rows:
        p = by_arm.get(r.get("arm")) or {}
        cells = []
        for key, _ in COLUMNS:
            if key == "__tokens__":
                cells.append(f"{len(p.get('fact_tokens_hit') or [])}/{len(p.get('fact_tokens_wanted') or [])}")
            elif key == "probe_hit":
                cells.append("yes" if r.get(key) else "**no**")
            elif key == "reusable_prefix_share":
                v = r.get(key)
                cells.append(f"{v:.1%}" if isinstance(v, (int, float)) else "—")
            else:
                v = r.get(key)
                cells.append(f"{v:,}" if isinstance(v, (int, float)) else str(v))
        out.append("| " + " | ".join(cells) + " |")
    path = exp / "tables" / "arms.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://127.0.0.1:3355/api")
    ap.add_argument("--experiment", required=True, help="path to the experiment folder")
    args = ap.parse_args()

    exp = pathlib.Path(args.experiment)
    metrics = json.loads((exp / "data" / "metrics.json").read_text(encoding="utf-8"))
    rows = [r for r in (metrics.get("per_run") or []) if r.get("status") == "ok"]
    if not rows:
        raise SystemExit("no completed rows in data/metrics.json — nothing to read back")

    out = {
        "probe_fact": PROBE_FACT,
        "tail_chars": TAIL_CHARS,
        # The block compaction is *supposed* to wait for, read from config rather than typed.
        # It is a definition, not a measurement: the bound H2 predicted is derived from it.
        "anchor_block": get_settings().turn_transcript_anchor_block,
        "arms": [read_arm(args.api, r) for r in rows],
    }
    path = exp / "data" / "probe.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {write_table(exp, rows, out['arms'])}")
    for arm in out["arms"]:
        flag = "" if arm["score_matches_recorded"] else "  ** DOES NOT MATCH THE RECORDED ROW **"
        print(f"{arm['arm']}: {arm['score_recomputed']} "
              f"({len(arm['fact_tokens_hit'])}/{len(arm['fact_tokens_wanted'])} tokens){flag}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
