"""Interleaved two-arm compaction runner for EXP-2026-08-011.

The question, from `PROTOCOL.md`: when a scene outgrows the model's context window, does
folding the dropped beats into a rolling summary preserve continuity that dropping them
outright loses — and does it cost anything?

**Arms are interleaved scene-by-scene inside one process run.** `docs/checklist.md` states
plainly that day-to-day comparison on this endpoint is worthless: the served model has changed
under this project between experiments before. Alternating within one session is the only way
the comparison is between two configurations rather than two afternoons.

The continuity probe is the point. Each scene plants a specific, checkable fact early, plays
enough turns to push it out of the verbatim window, then asks about it. Scoring reuses
`services.direction_check.coverage` — the same lexical check the direction system uses, with
the same known crudeness — so it is a **floor** on continuity rather than a measurement of it,
and it errs the same way in both arms.

Usage::

    uv run python -m utils.scripts.research.run_context_compaction \\
        --scenes 2 --turns 14 \\
        --experiment docs/research/experiments/EXP-2026-08-011-context-compaction
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from . import REPO_ROOT
from . import run_conversation_scaling as scaling
from .record import RunRecord, update_manifest, write_environment, write_metrics
from .run_conversation_scaling import API, _patch, _post, run_turn

# The planted fact, and the line that asks about it. Deliberately concrete: a fact scored by
# word overlap has to be made of words that cannot arrive by accident.
PLANT = (
    "I tell them my name is Rensal Vey, that I owe the harbourmaster four hundred crowns, "
    "and that I keep a brass key sewn into my collar."
)
PROBE = "I ask them to repeat back what I told them about my debt and my collar."
#: The content the probe's answer must reach for the fact to count as remembered.
PROBE_FACT = "Rensal Vey owes the harbourmaster four hundred crowns and keeps a brass key sewn into his collar"

#: Filler turns between the plant and the probe — enough to push the plant out of a fitted
#: window. Fixed before the run (the protocol's stopping rule); never extended after seeing a
#: result.
FILLER = [
    "I ask about the tide tables.",
    "I ask who runs the night market now.",
    "I ask what the watch is being paid to ignore.",
    "I ask about the fire on the east pier.",
    "I ask whether the ferrymen still take coin.",
    "I ask what the salt tax did to the fishers.",
    "I ask who last came asking questions.",
    "I ask about the sealed warehouse.",
    "I ask what the oracle said about the tide.",
    "I ask whether anyone has seen the captain.",
    "I ask what they would do in my place.",
    "I ask what it would take to leave this city.",
    "I ask who profits when the tide comes in early.",
    "I ask about the debt ledgers the watch keeps.",
    "I ask what happened to the last person who asked.",
    "I ask whether the truce is worth keeping.",
    "I ask what the harbourmaster wants from me.",
    "I ask about the boats that never came back.",
    "I ask who I should be afraid of here.",
    "I ask what they would trade for silence.",
    "I ask about the sealed room upstairs.",
    "I ask whether anyone here can be bought.",
    "I ask what the priest knows that he will not say.",
    "I ask how long this arrangement can hold.",
    "I ask what happens at first light.",
    "I ask whether there is another way out of this room.",
    "I ask what the salt does to a body left in it.",
    "I ask who keeps the keys to the undercroft.",
    "I ask what they think I am really here for.",
]

#: Compaction waits for a WHOLE anchor block (20 beats) to fall out of the window before it
#: fires — deliberately, so it costs one call per block rather than one per turn. Run 1 of this
#: experiment used 10 turns, which at `maxTurns: 2` produces about 20 beats *in total*, so 20
#: beats could never *drop* and the treatment was never exercised. Any run of this experiment
#: must be long enough to exceed the window by a full block. See ISSUES.md §2.
MIN_TURNS_FOR_COMPACTION = 24


def _build_scene(arm: str, index: int) -> tuple[str, str]:
    """A throwaway world + scenario configured for one arm."""
    sl = _post("/storylines", {
        "title": f"Compaction Probe {arm}{index}",
        "genre": "noir",
        "premise": "A harbour city where a truce between smugglers and the watch is fraying.",
    })["id"]
    cast = [
        _post(f"/storylines/{sl}/characters", {"name": name, "role": role})["id"]
        for name, role in (("Mei", "fence"), ("Kira", "harbour watch"))
    ]
    setting = _post(f"/storylines/{sl}/settings", {
        "name": "The Smoldering Hearth",
        "desc": "A back room behind a dockside tavern, rain on the shutters.",
    })["id"]
    body: dict[str, Any] = {
        "title": f"Salt and Ledgers ({arm})",
        "castIds": cast,
        "settingId": setting,
        "maxTurns": 2,
        "suggestionsCount": 0,
    }
    if arm == "A":
        # The control: today's behaviour, a fixed deep window and no compaction.
        body["contextPolicy"] = "fixed"
        body["contextBeats"] = 100
    else:
        body["contextPolicy"] = "auto"
    scenario = _post(f"/storylines/{sl}/scenarios", body)["id"]

    got = _patch(f"/scenarios/{scenario}", {})
    want = "fixed" if arm == "A" else "auto"
    if (got.get("contextPolicy") or "auto") != want:
        raise SystemExit(f"arm {arm}: contextPolicy did not apply ({got.get('contextPolicy')})")
    return scenario, sl


def _scored(text: str) -> float:
    """How much of the planted fact the answer reached. Same check the engine uses."""
    sys.path.insert(0, str(_backend_path()))
    from app.services import direction_check  # noqa: PLC0415 — path set above

    return direction_check.coverage(PROBE_FACT, text, ignore_names=["Rensal Vey"])


def _backend_path():
    return REPO_ROOT / "web" / "backend"


def _history(scenario: str, session: str) -> dict[str, Any]:
    req = urllib.request.Request(f"{API}/play/{scenario}/sessions/{session}")
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read().decode())


def _compaction_calls(scenario: str, session: str) -> int:
    """How many times compaction actually ran — the cost side of H2."""
    if not session:
        return 0
    return sum(
        1 for t in _history(scenario, session).get("traces", []) if t.get("step") == "compaction"
    )


def _session_transcript(scenario: str, session: str) -> str:
    history = _history(scenario, session)
    return " ".join(
        str((e.get("data") or {}).get("text") or "")
        for e in history.get("events", [])
        if e.get("type") in ("narration", "character_prose")
    )


def run_scene(arm: str, index: int, turns: int) -> dict[str, Any]:
    """Plant, fill, probe. Returns one row — never an aggregate."""
    scenario, storyline = _build_scene(arm, index)
    # The scene's throwaway world is torn down however this returns — including the
    # early return on a failed turn, which is the path that used to leak one world per
    # failure. Nothing in `main` reads the storyline back off the row.
    try:
        session: str | None = None
        prompt_tokens: list[int] = []
        reuse: list[float] = []
        seconds: list[float] = []
        started = time.monotonic()

        lines = [PLANT, *FILLER[: max(0, turns - 2)], PROBE]
        for i, line in enumerate(lines):
            row = run_turn(scenario, session, line)
            session = row["session_id"]
            if row.get("error"):
                return {
                    "arm": arm, "scene": index, "status": "failed",
                    "failed_at_turn": i, "error": row["error"],
                }
            seconds.append(row["total_s"])
            if isinstance(row.get("prompt_tokens_max"), int):
                prompt_tokens.append(row["prompt_tokens_max"])
            if isinstance(row.get("reuse_ratio_mean"), (int, float)):
                reuse.append(float(row["reuse_ratio_mean"]))

        # Counted from the session's own trace rows rather than threaded through the shared
        # `run_turn` (which EXP-2026-08-005 also uses): a runner two experiments depend on is the
        # wrong place to add a field only one of them reads.
        recap_calls = _compaction_calls(scenario, session or "")

        # The probe's answer is the last turn's prose.
        transcript = _session_transcript(scenario, session or "")
        answer = transcript[-2000:]
        score = _scored(answer)

        return {
            "arm": arm,
            "scene": index,
            "status": "ok",
            "scenario": scenario,
            "storyline": storyline,
            "session": session,
            "turns": len(lines),
            "probe_score": round(score, 3),
            "probe_hit": score >= 0.34,
            "prompt_tokens_mean": round(statistics.fmean(prompt_tokens), 1) if prompt_tokens else None,
            "reusable_prefix_share": round(statistics.fmean(reuse), 4) if reuse else None,
            "recap_calls": recap_calls,
            "turn_seconds_mean": round(statistics.fmean(seconds), 2) if seconds else None,
            "wall_seconds": round(time.monotonic() - started, 1),
        }
    finally:
        scaling.delete_world(storyline)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenes", type=int, default=2, help="scenes per arm")
    ap.add_argument("--turns", type=int, default=14, help="turns per scene, plant+filler+probe")
    ap.add_argument("--experiment", required=True)
    ap.add_argument(
        "--api",
        default=API,
        help=(
            "Backend API root. Arm B needs a backend started with "
            "TURN_CONTEXT_COMPACTION=true (the setting is process-level and ships off), so "
            "this run usually points at a second instance rather than disturbing the dev one."
        ),
    )
    args = ap.parse_args()

    if args.turns < MIN_TURNS_FOR_COMPACTION:
        # A guard rather than a note, because the failure it prevents is silent: the run
        # completes cleanly, reports zero recap calls, and looks like a result about
        # compaction when it is a result about the scene being too short. See ISSUES.md §2.
        raise SystemExit(
            f"--turns {args.turns} cannot exercise compaction: it waits for a whole anchor "
            f"block (20 beats) to fall out of the window, and a scene this short never "
            f"produces that many beats to drop. Use at least {MIN_TURNS_FOR_COMPACTION}."
        )

    # Both this module and the shared `run_turn` read the API root from
    # `run_conversation_scaling`, so redirecting it there redirects everything.
    if args.api != API:
        scaling.API = args.api
        globals()["API"] = args.api

    record = RunRecord(entrypoint=" ".join(sys.argv))
    started_all = time.monotonic()
    record.note(f"arms interleaved scene-by-scene; scenes={args.scenes} turns={args.turns}")

    rows: list[dict[str, Any]] = []
    # Interleaved: A1, B1, A2, B2 … so endpoint drift hits both arms equally.
    for index in range(args.scenes):
        for arm in ("A", "B"):
            print(f"scene {arm}{index}…", flush=True)
            row = run_scene(arm, index, args.turns)
            rows.append(row)
            record.add_run(row)
            record.note(f"{arm}{index}: {json.dumps(row)}")
            print(f"  {json.dumps(row)}", flush=True)

    failed = [r for r in rows if r["status"] != "ok"]
    payload: dict[str, Any] = {"rows": rows, "failed": len(failed)}

    if failed:
        # Survivors of a partially-failed run are not a random subsample. Per-run rows only.
        # `EXP-2026-08-001` is this repository's worked example of getting that wrong.
        payload["aggregate"] = None
        payload["aggregate_withheld_reason"] = (
            f"{len(failed)} of {len(rows)} runs failed; an aggregate over the survivors would "
            "not be an aggregate over a random subsample."
        )
    else:
        def mean(arm: str, key: str) -> float | None:
            vals = [r[key] for r in rows if r["arm"] == arm and r.get(key) is not None]
            return round(statistics.fmean(vals), 4) if vals else None

        payload["aggregate"] = {
            arm: {
                "probe_total": sum(1 for r in rows if r["arm"] == arm),
                "continuity_hits": sum(1 for r in rows if r["arm"] == arm and r["probe_hit"]),
                "probe_score_mean": mean(arm, "probe_score"),
                "prompt_tokens_mean": mean(arm, "prompt_tokens_mean"),
                "reusable_prefix_share": mean(arm, "reusable_prefix_share"),
                "recap_calls_total": sum(r["recap_calls"] for r in rows if r["arm"] == arm),
                "turn_seconds_mean": mean(arm, "turn_seconds_mean"),
            }
            for arm in ("A", "B")
        }

    record.wall_clock_seconds = time.monotonic() - started_all
    record.llm_calls = sum(r.get("recap_calls", 0) for r in rows)
    exp = pathlib.Path(args.experiment)
    write_metrics(exp, record, payload)
    write_environment(exp, record)
    update_manifest(exp, {"status": "failed" if failed else "complete"})
    print(json.dumps(payload, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
