#!/usr/bin/env python3
"""Compute beats-per-turn from the recovered event log.

Provenance, stated because it is unusual and it limits what these numbers support:
this run happened on 2026-08-24 but was never written up. The event log was
recovered from the development Postgres on 2026-08-31, before the throwaway
storyline it lived in (`47525d8b`, "EXP-016 Scene Flow") was deleted. The raw
export is `data/events.json`.

What that means: the beat counts below are exactly what the engine emitted and
persisted, because they are counted from the persisted events themselves. Nothing
else the protocol asked for survived — no per-call latency, no token accounting,
no cache rates, no arm labels. Those were never captured, and no amount of
post-hoc reconstruction can produce them.

Run:  python3 make_metrics.py   ->  writes data/metrics.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
#: Everything except the player's own input is a beat the engine produced.
PLAYER = "user_turn"

#: Which session ran which arm. The recovered event log does not label them, but
#: ISSUES.md (2026-08-25) does, in passing: "voiced turn 3 produced 18 beats and
#: continuous turn 3 produced 3". Those two counts identify both sessions in the log
#: unambiguously — no other session/turn pair matches. Recorded here rather than
#: hand-written into metrics.json so the mapping is auditable.
ARM = {"ps_c8d97156cc": "voiced", "ps_b59a06795e": "continuous"}
ARM_SOURCE = (
    "ISSUES.md 2026-08-25: 'voiced turn 3 produced 18 beats and continuous turn 3 "
    "produced 3'. Those counts identify both sessions in the recovered log."
)


def main() -> None:
    events = json.loads((HERE / "data" / "events.json").read_text())

    sessions: dict[str, list[dict]] = {}
    for e in events:
        sessions.setdefault(e["session_id"], []).append(e)

    per_turn: list[dict] = []
    for sid, evs in sessions.items():
        evs.sort(key=lambda e: e["seq"])
        turn = 0
        counts: dict[int, int] = {}
        types: dict[int, dict[str, int]] = {}
        for e in evs:
            if e["type"] == PLAYER:
                turn += 1
                counts.setdefault(turn, 0)
                types.setdefault(turn, {})
                continue
            if turn == 0:
                continue  # scene-opening narration, emitted before any player turn
            counts[turn] = counts.get(turn, 0) + 1
            types[turn][e["type"]] = types[turn].get(e["type"], 0) + 1
        for t in sorted(counts):
            per_turn.append(
                {
                    "session": sid,
                    "arm": ARM.get(sid, "unknown"),
                    "turn": t,
                    "beats": counts[t],
                    "by_type": types[t],
                }
            )

    beats = [r["beats"] for r in per_turn]
    by_arm = {}
    for arm in sorted({r["arm"] for r in per_turn}):
        b = [r["beats"] for r in per_turn if r["arm"] == arm]
        by_arm[arm] = {"turns": len(b), "beats": b, "max": max(b)}

    # No cross-arm mean is emitted. The two arms are different conditions, so averaging
    # them describes nothing that was run. n = 5 and 6 per arm is far too small for a
    # per-arm mean to carry meaning either, so only the raw sequences and maxima ship.
    metrics = {
        "provenance": "recovered from the dev database 2026-08-31; see module docstring",
        "arm_source": ARM_SOURCE,
        "sessions": len(sessions),
        "player_turns": len(per_turn),
        "beats_per_turn": per_turn,
        "by_arm": by_arm,
        "beats_max": max(beats),
        "turns_over_15_beats": sorted(b for b in beats if b > 15),
        "not_recovered": [
            "per-call latency",
            "token accounting",
            "prefix-cache rate",
            "cross_speaker_rate",
            "voice_distinctness",
            "misattribution_rate",
        ],
    }
    out = HERE / "data" / "metrics.json"
    out.write_text(json.dumps(metrics, indent=1) + "\n")
    print(f"wrote {out}")
    print(f"  max beats in one turn: {metrics['beats_max']}")
    print(f"  turns over 15 beats:   {metrics['turns_over_15_beats']}")


if __name__ == "__main__":
    main()
