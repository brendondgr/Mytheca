"""EXP-2026-08-010 — do the Short/Medium/Long tiers actually separate?

`beat_length` is a per-scenario control over how much a character says in one beat: short
1–2 paragraphs, medium 2–4, long 5–6. It works by putting a paragraph count in the character
prompt's recency TAIL, with a per-tier token allowance behind it as a backstop.

Whether a prompt directive about length binds at all is **not** known in advance. A countable
length target has already failed on this codebase once — EXP-2026-08-007 measured a "usually
80–200 words" instruction moving the average passage *up*. The bet here is that a paragraph
count is different in kind, because it names an axis the model already controls deliberately.
If the arms overlap, the directive does not work and the tier is enforced by the token
allowance alone, which is a worse feature and is reported as such.

**This is a real interleaved arm test, not a before/after.** Because the tier is per-scenario,
one world can hold three scenarios that differ ONLY in `beat_length`, and the runner walks
them turn by turn — arm A turn 1, arm B turn 1, arm C turn 1, arm A turn 2… — so a drift in
endpoint state spreads across the arms instead of landing on whichever ran last. Every earlier
prompt comparison in this record had to be a before/after for want of exactly this seam
(OPEN_QUESTIONS, from EXP-2026-08-009).

Read `docs/research/experiments/EXP-2026-08-010-beat-length/PROTOCOL.md` first.

    uv run python -m utils.scripts.research.run_beat_length \
      --experiment docs/research/experiments/EXP-2026-08-010-beat-length --turns 6
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import REPO_ROOT
from .record import (
    RunRecord,
    aggregate,
    git_block,
    hardware,
    hash_text,
    update_manifest,
    write_environment,
    write_metrics,
)
from .run_conversation_scaling import API, PLAYER_LINES, _patch, _post
from .run_prose_end_to_end import (
    CHARACTER_KINDS,
    METRIC_KEYS,
    drive_turn,
    measure,
    served_model,
)

#: ``METRIC_KEYS`` includes ``is_distinct``, which ``measure()`` does NOT compute — the
#: sibling runner adds it in its own loop from a cross-beat ``seen`` set. Claiming it here
#: would put an empty column in the aggregate, so it is dropped and duplicates are counted
#: post-hoc by ``analyze_run.py`` over the recorded transcript instead.
ARM_METRIC_KEYS = [k for k in METRIC_KEYS if k != "is_distinct"]

import sys  # noqa: E402 - after the package imports, which set up the path

sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.agents import prompt_registry  # noqa: E402

#: The arms. Order is fixed so the interleave is deterministic and a rerun walks the same
#: sequence; it is NOT the order they are reported in.
ARMS = ("short", "medium", "long")

#: What each tier asks for, used only to report "did it land in range" — never fed to the
#: model, which gets the directive from the prompt registry like any real turn.
TARGET_PARAGRAPHS = {"short": (1, 2), "medium": (2, 4), "long": (5, 6)}


def build_world(max_turns: int, suggestions: int, context_beats: int) -> tuple[str, list[str]]:
    """One storyline, one cast, one setting — and one scenario per arm.

    Sharing the world is the point: the arms differ in `beat_length` and in nothing else, so
    cast, setting, premise and settings are all identical by construction rather than by
    being written out three times.
    """
    storyline = _post("/storylines", {
        "title": "Beat Length Probe",
        "genre": "noir",
        "premise": "A harbour city where a truce between smugglers and the watch is fraying.",
    })["id"]
    cast = [
        _post(f"/storylines/{storyline}/characters", {"name": name, "role": role})["id"]
        for name, role in (("Mei", "fence"), ("Kira", "harbour watch"), ("Aldous", "archivist"))
    ]
    setting = _post(f"/storylines/{storyline}/settings", {
        "name": "The Smoldering Hearth",
        "desc": "A back room behind a dockside tavern, rain on the shutters.",
    })["id"]

    scenarios: list[str] = []
    for arm in ARMS:
        scenario = _post(f"/storylines/{storyline}/scenarios", {
            "title": f"Salt and Ledgers ({arm})",
            "castIds": cast,
            "settingId": setting,
            "maxTurns": max_turns,
            "suggestionsCount": suggestions,
            "contextBeats": context_beats,
            "beatLength": arm,
        })["id"]
        # Confirm every setting actually landed. The schema clamps `context_beats` and
        # rejects an unknown tier, and a silently-different arm would invalidate the run
        # without leaving a trace anywhere.
        got = _patch(f"/scenarios/{scenario}", {})
        applied = {
            "maxTurns": got.get("maxTurns"),
            "suggestionsCount": got.get("suggestionsCount"),
            "contextBeats": got.get("contextBeats"),
            "beatLength": got.get("beatLength"),
        }
        expected = {
            "maxTurns": max_turns,
            "suggestionsCount": suggestions,
            "contextBeats": context_beats,
            "beatLength": arm,
        }
        if applied != expected:
            raise SystemExit(f"{arm}: settings not applied as requested: {applied} != {expected}")
        scenarios.append(scenario)
    return storyline, scenarios


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--max-turns", type=int, default=5)
    parser.add_argument("--suggestions", type=int, default=0)
    parser.add_argument("--context-beats", type=int, default=100)
    parser.add_argument("--llm-base-url", default="http://localhost:4000/v1")
    parser.add_argument("--llm-model", default="skynet")
    args = parser.parse_args()

    exp = args.experiment if args.experiment.is_absolute() else REPO_ROOT / args.experiment
    entrypoint = (
        "uv run python -m utils.scripts.research.run_beat_length "
        f"--experiment {args.experiment} --turns {args.turns}"
    )
    record = RunRecord(entrypoint=entrypoint)

    upstream = served_model(args.llm_base_url, args.llm_model)
    record.note(f"served upstream model: {upstream} (alias {args.llm_model})")
    print(f"served upstream: {upstream}", flush=True)

    storyline, scenarios = build_world(args.max_turns, args.suggestions, args.context_beats)
    record.note(
        f"storyline={storyline} arms="
        + ", ".join(f"{arm}:{sid}" for arm, sid in zip(ARMS, scenarios, strict=True))
    )

    sessions: dict[str, str | None] = {arm: None for arm in ARMS}
    transcript: list[dict[str, Any]] = []
    failed_turns = 0
    started_all = time.monotonic()

    # Interleaved BY TURN: every arm plays turn N before any arm plays turn N+1, so a drift
    # in endpoint state spreads across the arms instead of landing on whichever ran last.
    for turn in range(1, args.turns + 1):
        text = PLAYER_LINES[(turn - 1) % len(PLAYER_LINES)]
        for arm, scenario in zip(ARMS, scenarios, strict=True):
            try:
                got = drive_turn(scenario, sessions[arm], text)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                failed_turns += 1
                record.note(f"{arm} turn {turn} FAILED: {exc.__class__.__name__}: {exc}")
                record.add_run({"arm": arm, "turn": turn, "error": f"{exc.__class__.__name__}"})
                print(f"{arm:<7} turn {turn:>2}: FAILED {exc}", flush=True)
                continue
            sessions[arm] = got["session_id"] or sessions[arm]
            if got["error"]:
                record.note(f"{arm} turn {turn} returned an error frame: {got['error']}")

            for index, beat in enumerate(got["beats"]):
                row = {
                    "arm": arm,
                    "turn": turn,
                    "beat": index,
                    "type": beat["type"],
                    **measure(beat["text"]),
                }
                # Narration is recorded but excluded from the aggregate: it is third person,
                # forbidden dialogue, and NOT governed by `beat_length` at all — mixing it in
                # would dilute the very effect under test.
                if beat["type"] in CHARACTER_KINDS:
                    record.add_run(row)
                transcript.append({**row, "text": beat["text"]})

            record.llm_calls += len(got["beats"])
            chars = [b for b in got["beats"] if b["type"] in CHARACTER_KINDS]
            paragraphs = [b["text"].count("\n\n") + 1 for b in chars]
            lo, hi = TARGET_PARAGRAPHS[arm]
            in_range = sum(1 for p in paragraphs if lo <= p <= hi)
            print(
                f"{arm:<7} turn {turn:>2}: beats={len(chars)} "
                f"paras={paragraphs} in_range={in_range}/{len(chars)} "
                f"chars={[len(b['text']) for b in chars]} "
                f"discards={ {k: v for k, v in got['discards'].items() if v} } "
                f"{got['elapsed_s']}s {got['error'] or ''}",
                flush=True,
            )
    record.wall_clock_seconds = time.monotonic() - started_all

    values: dict[str, Any] = {}
    if failed_turns:
        # Survivors of a partially-failed run are not a random subsample (the
        # EXP-2026-08-001 rule): per-beat rows are the result and no aggregate is written.
        record.note(
            f"{failed_turns} turn(s) failed — NO aggregate computed. Per-beat rows are the "
            "result; see ISSUES.md."
        )
    else:
        for arm in ARMS:
            rows = [r for r in record.per_run if r.get("arm") == arm and not r.get("error")]
            if not rows:
                record.note(f"arm {arm}: no beats — no aggregate")
                continue
            for key, cell in aggregate(rows, ARM_METRIC_KEYS).items():
                values[f"{arm}.{key}"] = cell

    write_environment(exp, record)
    write_metrics(exp, record, values)
    update_manifest(exp, {
        "code": git_block(entrypoint),
        "status": "failed" if failed_turns else "complete",
        "n_runs": len(record.per_run),
        "compute": {
            "hardware": hardware(),
            "wall_clock_hours": round(record.wall_clock_seconds / 3600, 4),
            "estimated_cost_usd": 0.0,
        },
        "metrics": {"values": values},
        "llm": {
            "model": f"relay/{args.llm_model} -> {upstream}",
            "prompt_hash": hash_text(
                prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT)
            ),
        },
    })
    log = exp / "logs" / "transcript.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps(
            {"notes": record.notes, "sessions": sessions, "beats": transcript}, indent=2
        ),
        encoding="utf-8",
    )
    print(f"\n{'FAILED' if failed_turns else 'complete'} — wrote {log}")
    return 1 if failed_turns else 0


if __name__ == "__main__":
    raise SystemExit(main())
