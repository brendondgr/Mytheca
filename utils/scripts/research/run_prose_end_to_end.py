"""EXP-2026-08-008 — does the prose read like a scene through the real turn engine?

EXP-2026-08-007 measured the sampler by calling the relay directly, with the shipped
contract as the only system message. That isolates the sampler, and it deliberately leaves
out everything the turn engine does: the planner's beat and register, the assembled
context, the voice samples, the emission parser, and the four guards that can discard a
passage before a reader sees it. This runner measures the thing the owner actually looks
at — the beats a live session emits — end to end.

It drives N player turns through ``POST /api/play/{id}/turn`` against a running backend,
building its own throwaway world so a run does not depend on the dev database, then reads
back **every emitted beat** and measures the same prose-form metrics EXP-2026-08-007 used,
plus the two failures that only exist end to end: a beat byte-identical to another beat in
the same session, and a beat the engine had to discard or skip (counted from the trace).

Read ``docs/research/experiments/EXP-2026-08-008-prose-end-to-end/PROTOCOL.md`` first.

    uv run python -m utils.scripts.research.run_prose_end_to_end \
      --experiment docs/research/experiments/EXP-2026-08-008-prose-end-to-end --turns 6
"""

from __future__ import annotations

import argparse
import json
import sys
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
from .run_conversation_scaling import API, PLAYER_LINES, build_world
from .run_prose_form import SPOKEN, TERMINATORS

sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.agents import prompt_registry  # noqa: E402
from app.services import emission  # noqa: E402

#: Beat types that carry a character's own passage. ``narration`` is measured separately —
#: the narrator is third person and is not asked for dialogue, so holding it to the same
#: speech metric would score the contract against a prompt that forbids it.
CHARACTER_KINDS = {"character_prose", "character_dialogue", "character_action"}

#: Trace flags the engine sets when it throws a passage away. Each one is a beat the
#: reader never saw, and a run that scores well only because half its beats were discarded
#: is not a run that scores well.
DISCARD_FLAGS = ("scratchpad", "dropped", "degenerate", "skipped")

METRIC_KEYS = [
    "sentences_per_100_words",
    "has_speech",
    "paragraph_breaks",
    "is_scratchpad",
    "starts_mid_sentence",
    "names_the_player",
    "is_distinct",
    "chars",
]


def measure(passage: str) -> dict[str, Any]:
    """The countable shadows of "reads like a scene", per beat.

    Same definitions as ``run_prose_form.measure`` so the two experiments are comparable,
    plus ``starts_mid_sentence`` — the guard that caught a live fragment the vocabulary
    test missed, which is worth counting once it is load-bearing.
    """
    words = len(passage.split())
    return {
        "chars": len(passage),
        "words": words,
        "sentences_per_100_words": (
            round(100 * len(TERMINATORS.findall(passage)) / words, 3) if words else 0.0
        ),
        "has_speech": 1 if SPOKEN.search(passage) else 0,
        "paragraph_breaks": passage.count("\n\n"),
        "is_scratchpad": 1 if emission.looks_like_scratchpad(passage) else 0,
        "starts_mid_sentence": 1 if emission.starts_mid_sentence(passage) else 0,
        # Whole passage, not the opening: the engine's gate can only judge an opening,
        # and 12 of the 13 leaks in the first recorded run were mid-passage. Measuring
        # only what the gate sees would have reported the defect as one beat in
        # eighteen.
        "names_the_player": 1 if emission.names_the_player(passage) else 0,
    }


def drive_turn(scenario: str, session: str | None, text: str) -> dict[str, Any]:
    """Drive one player turn, collecting completed beats and the engine's discard flags.

    A delta-streamed beat re-emits the same ``id`` with an **incremental** chunk, and its
    final frame carries ``done: true`` with an *empty* string (``TurnEmitter.close`` sends
    ``_frame("", done=True)``). So a beat is accumulated by ``id`` across every frame and
    marked finished when ``done`` arrives — reading the text off the ``done`` frame alone
    yields "" for every streamed beat, and scored a first draft of this runner at 0 % speech.
    Non-streamed beats send their whole text on a single ``done`` frame; accumulating covers
    both.
    """
    payload: dict[str, Any] = {"text": text, "trace": True}
    if session:
        payload["sessionId"] = session
    req = urllib.request.Request(
        f"{API}/play/{scenario}/turn", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    beats: dict[str, dict[str, Any]] = {}
    discards: dict[str, int] = {flag: 0 for flag in DISCARD_FLAGS}
    session_id, error = session, None
    started = time.monotonic()

    with urllib.request.urlopen(req, timeout=1800) as res:
        for raw in res:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            try:
                frame = json.loads(line)
            except ValueError:
                continue
            kind = frame.get("type")
            session_id = frame.get("sessionId") or session_id
            data = frame.get("data") or {}
            if kind == "trace":
                for flag in DISCARD_FLAGS:
                    if data.get(flag):
                        discards[flag] += 1
            elif kind == "error":
                error = frame.get("message")
            elif kind in CHARACTER_KINDS or kind == "narration":
                beat = beats.setdefault(
                    frame.get("id") or f"anon{len(beats)}",
                    {"type": kind, "speaker": None, "text": "", "done": False},
                )
                beat["text"] += data.get("text") or ""
                beat["speaker"] = (
                    data.get("characterName") or data.get("characterId") or beat["speaker"]
                )
                beat["done"] = beat["done"] or bool(data.get("done"))
    return {
        "session_id": session_id,
        "error": error,
        "elapsed_s": round(time.monotonic() - started, 3),
        # An unfinished beat is a beat the stream cut off; it is not a measurable passage
        # and counting it would score the run on a fragment.
        "beats": [b for b in beats.values() if b["done"]],
        "unfinished": sum(1 for b in beats.values() if not b["done"]),
        "discards": discards,
    }


def served_model(base_url: str, model: str) -> str:
    """Which upstream is actually answering, read off a one-token completion.

    The relay's ``/v1/models`` reports ``upstream_model: auto`` for a hot-swapping alias, so
    it cannot be trusted to name what served a run — and the alias has already been observed
    pointing at two different models across a restart. A completion's ``model`` field is the
    only answer that comes from the thing that did the work. The turn engine does not put it
    on the wire, so this is a separate call; it is cheap and it is the difference between a
    reproducible record and one that says "relay/skynet" for two different models.
    """
    body = {"model": model, "messages": [{"role": "user", "content": "."}], "max_tokens": 1}
    req = urllib.request.Request(
        f"{base_url}/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            return (json.load(res) or {}).get("model") or "unknown"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return f"unknown ({exc.__class__.__name__})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--max-turns", type=int, default=5)
    parser.add_argument("--suggestions", type=int, default=0)
    parser.add_argument("--context-beats", type=int, default=100)
    parser.add_argument("--llm-base-url", default="http://localhost:4000/v1",
                        help="only used to record WHICH upstream served the run")
    parser.add_argument("--llm-model", default="skynet")
    args = parser.parse_args()

    exp = args.experiment if args.experiment.is_absolute() else REPO_ROOT / args.experiment
    entrypoint = (
        "uv run python -m utils.scripts.research.run_prose_end_to_end "
        f"--experiment {args.experiment} --turns {args.turns}"
    )
    record = RunRecord(entrypoint=entrypoint)

    upstream = served_model(args.llm_base_url, args.llm_model)
    record.note(f"served upstream model: {upstream} (alias {args.llm_model})")
    print(f"served upstream: {upstream}", flush=True)

    scenario, storyline = build_world(args.max_turns, args.suggestions, args.context_beats)
    record.note(f"scenario={scenario} storyline={storyline} turns={args.turns} "
                f"maxTurns={args.max_turns} suggestions={args.suggestions} "
                f"contextBeats={args.context_beats}")

    session: str | None = None
    transcript: list[dict[str, Any]] = []
    # Keyed on the whole passage, across the WHOLE session: the duplicate this catches is
    # two characters returning the same beat, which showed up three times in a five-turn
    # run and is invisible if each turn is deduped on its own.
    seen: dict[str, str] = {}
    started_all = time.monotonic()

    for turn in range(1, args.turns + 1):
        text = PLAYER_LINES[(turn - 1) % len(PLAYER_LINES)]
        try:
            got = drive_turn(scenario, session, text)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            record.note(f"turn {turn} FAILED: {exc.__class__.__name__}: {exc}")
            record.add_run({"turn": turn, "error": f"{exc.__class__.__name__}: {exc}"})
            print(f"turn {turn:>2}: FAILED {exc}", flush=True)
            continue
        session = got["session_id"] or session
        if got["error"]:
            record.note(f"turn {turn} returned an error frame: {got['error']}")

        for index, beat in enumerate(got["beats"]):
            body = beat["text"].strip()
            row = {
                "turn": turn,
                "beat": index,
                "type": beat["type"],
                "speaker": beat["speaker"],
                "duplicate_of": seen.get(body),
                "is_distinct": 0 if seen.get(body) else 1,
                **measure(beat["text"]),
            }
            seen.setdefault(body, f"t{turn}b{index}")
            # The aggregate is over CHARACTER beats: narration is third-person and is not
            # asked to contain speech, so mixing it in would move every metric for a
            # reason that has nothing to do with the contract under test.
            if beat["type"] in CHARACTER_KINDS:
                record.add_run(row)
            transcript.append({**row, "text": beat["text"]})

        record.llm_calls += len(got["beats"])
        if got["unfinished"]:
            record.note(f"turn {turn}: {got['unfinished']} beat(s) never sent a done frame")
        chars = [b for b in got["beats"] if b["type"] in CHARACTER_KINDS]
        print(
            f"turn {turn:>2}: beats={len(got['beats'])} character={len(chars)} "
            f"speech={sum(1 for b in chars if SPOKEN.search(b['text']))}/{len(chars)} "
            f"breaks={sum(1 for b in chars if chr(10) * 2 in b['text'])}/{len(chars)} "
            f"discards={ {k: v for k, v in got['discards'].items() if v} } "
            f"unfinished={got['unfinished']} {got['elapsed_s']}s {got['error'] or ''}",
            flush=True,
        )
    record.wall_clock_seconds = time.monotonic() - started_all

    rows = [r for r in record.per_run if not r.get("error")]
    failed = [r for r in record.per_run if r.get("error")]
    values: dict[str, Any] = {}
    if failed:
        # Survivors of a partially-failed run are not a random subsample (the
        # EXP-2026-08-001 rule): per-turn rows are the result and no aggregate is written.
        record.note(f"{len(failed)}/{args.turns} turn(s) failed — NO aggregate computed. "
                    "Per-beat rows are the result; see ISSUES.md.")
    elif rows:
        # Every cell is a mean +/- std over n beats. Bare counts are deliberately NOT
        # added: manifest_schema.MetricValue rejects them, on the grounds that a count
        # hides the n it was taken over. "18 of 18 carried speech" is has_speech
        # mean 1.0 at n 18, which says the same thing and cannot lose its denominator.
        values = dict(aggregate(rows, METRIC_KEYS))

    write_environment(exp, record)
    write_metrics(exp, record, values)
    update_manifest(exp, {
        "code": git_block(entrypoint),
        "status": "failed" if failed else "complete",
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
        json.dumps({"notes": record.notes, "session": session, "beats": transcript}, indent=2),
        encoding="utf-8",
    )
    print(f"\n{'FAILED' if failed else 'complete'} — session={session} — wrote {log}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
