"""EXP-2026-08-016 — continuous scene script against the per-speaker writer.

Read ``docs/research/experiments/EXP-2026-08-016-continuous-scene-script/PROTOCOL.md``
before this file. The design decisions that matter (interleaving, separate sessions, the
decision rule, the threats) are pre-registered there and are not restated here.

Drives 2 x N player turns through ``POST /api/play/{id}/turn`` against a running backend,
alternating ``overrides.sceneFlow`` between ``"voiced"`` and ``"continuous"`` turn by turn so
the endpoint is a shared condition rather than a variable. One world, two sessions.

Every prose metric is imported from ``app.services.prose_guards``. A harness with its own
copy of "what counts as a violation" measures its own opinion, and the point of the guards
being pure functions is that the engine, the smoke test and this file all ask the same
question.

    uv run python -m utils.scripts.research.run_scene_script \\
      --experiment docs/research/experiments/EXP-2026-08-016-continuous-scene-script --turns 6
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from . import REPO_ROOT
from .record import (
    RunRecord,
    git_block,
    hardware,
    update_manifest,
    write_environment,
    write_metrics,
)

sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.services import prose_guards  # noqa: E402

API = "http://localhost:3345/api"

ARMS = ("voiced", "continuous")

#: Three characters. Two cannot distinguish a cross-speaker leak from a hand-off, and give
#: voice distinctness a single pair to average over.
CAST = [
    ("Lily", "a street singer who talks her way out of things"),
    ("Zoe", "a harbour-watch sergeant who does not"),
    ("Aldous", "an archivist who knows what both of them owe"),
]

#: Fixed, so both arms drive the identical conversation and the only difference is the flow.
PLAYER_LINES = [
    "Lily jumps up on the table and starts singing to drown out the argument.",
    "Zoe tries to get her down before anyone outside hears.",
    "Aldous finally says what he has been holding back all evening.",
    "Someone outside starts knocking, slowly, three times.",
    "Lily decides to answer the door herself.",
    "Whatever is on the other side, it is not what any of them expected.",
]

CHARACTER_KINDS = {"character_prose", "character_dialogue", "character_action"}
#: Trace flags the engine sets when it throws a passage away. A run that scores well only
#: because half its beats were discarded is not a run that scores well — see PROTOCOL § 7.
DISCARD_FLAGS = ("scratchpad", "dropped", "degenerate", "crossSpeaker")


# ---- transport ---------------------------------------------------------------


def _req(method: str, path: str, body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=1800) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw.strip() else None


def _stream(path: str, body: dict) -> list[dict]:
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    frames: list[dict] = []
    with urllib.request.urlopen(req, timeout=3600) as resp:
        for line in resp:
            text = line.decode().strip()
            if text:
                try:
                    frames.append(json.loads(text))
                except ValueError:
                    pass
    return frames


def build_world() -> tuple[str, str, dict[str, str]]:
    storyline = _req("POST", "/storylines", {
        "title": "EXP-016 Scene Flow",
        "genre": "noir",
        "premise": "A dockside tavern the night before a debt comes due.",
    })["id"]
    cast: dict[str, str] = {}
    for name, role in CAST:
        row = _req("POST", f"/storylines/{storyline}/characters", {"name": name, "role": role})
        cast[row["id"]] = name
    setting = _req("POST", f"/storylines/{storyline}/settings", {
        "name": "The Smoldering Hearth",
        "desc": "A back room behind a dockside tavern, rain on the shutters.",
    })["id"]
    scenario = _req("POST", f"/storylines/{storyline}/scenarios", {
        "title": "Last Call",
        "castIds": list(cast),
        "settingId": setting,
        "suggestionsCount": 0,  # a director call that says nothing about prose
    })["id"]
    return storyline, scenario, cast


# ---- reading the stream ------------------------------------------------------


def beats_from(frames: list[dict]) -> list[dict]:
    """Accumulate the delta stream into finished beats, in order.

    Delta frames re-emit the same event id with an INCREMENTAL ``text`` and the final frame
    carries an empty one, so this accumulates by id. Reading the text off the done frame is
    the standard way to misread this stream and yields "" for every beat.
    """
    order: list[str] = []
    by_id: dict[str, dict] = {}
    for frame in frames:
        kind = frame.get("type")
        if kind not in CHARACTER_KINDS | {"narration"}:
            continue
        eid = frame.get("id") or ""
        data = frame.get("data") or {}
        if eid not in by_id:
            by_id[eid] = {"kind": kind, "characterId": data.get("characterId"), "text": ""}
            order.append(eid)
        by_id[eid]["text"] += data.get("text") or ""
    return [by_id[i] for i in order if by_id[i]["text"].strip()]


def discards_in(frames: list[dict]) -> int:
    n = 0
    for f in frames:
        if f.get("type") != "trace":
            continue
        data = f.get("data") or {}
        if any(data.get(flag) for flag in DISCARD_FLAGS):
            n += 1
    return n


def fell_back(frames: list[dict]) -> bool:
    return any(
        f.get("type") == "trace" and (f.get("data") or {}).get("sceneFlow") == "fallback"
        for f in frames
    )


def planned_speakers(frames: list[dict]) -> list[str | None]:
    """The plan's speaker order, from the `plan` frame (requires `trace: true`)."""
    for f in frames:
        if f.get("type") == "plan":
            return [b.get("actorId") for b in f.get("beats", [])
                    if b.get("action") in ("speak", "narrate")]
    return []


# ---- metrics -----------------------------------------------------------------

_WORD = re.compile(r"[a-z']+")
#: Function words carry grammar, not voice. Left in, a distinctness measure mostly reports
#: that everyone writes English; the signal is in what each character reaches for.
_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with",
    "is", "are", "was", "were", "be", "been", "am", "it", "its", "this", "that", "these",
    "those", "i", "my", "me", "he", "she", "him", "her", "his", "they", "them", "their",
    "as", "if", "so", "not", "no", "do", "does", "did", "have", "has", "had", "will",
    "would", "can", "could", "there", "then", "than", "what", "when", "who", "from", "by",
    "up", "out", "into", "over", "down", "off", "about", "like", "just", "one", "all",
}


def _profile(texts: list[str]) -> Counter:
    bag: Counter = Counter()
    for t in texts:
        bag.update(w for w in _WORD.findall(t.lower()) if w not in _STOP and len(w) > 2)
    return bag


def _js_distance(a: Counter, b: Counter) -> float:
    """Jensen-Shannon distance between two word distributions, in [0, 1].

    Chosen over cosine because it is bounded and symmetric, so a number is comparable across
    arms without normalising by vocabulary size — two characters with more to say would
    otherwise look more distinct than two with less.
    """
    na, nb = sum(a.values()), sum(b.values())
    if not na or not nb:
        return 0.0
    keys = set(a) | set(b)
    div = 0.0
    for k in keys:
        p, q = a[k] / na, b[k] / nb
        m = (p + q) / 2
        if p:
            div += 0.5 * p * math.log2(p / m)
        if q:
            div += 0.5 * q * math.log2(q / m)
    return round(math.sqrt(max(0.0, div)), 6)


def voice_distinctness(beats: list[dict], cast: dict[str, str]) -> float | None:
    """Mean pairwise JS distance between the characters' own beats. Higher is more distinct.

    ``None`` when fewer than two characters actually spoke — a single voice has nothing to
    be distinct FROM, and reporting 0.0 there would read as "identical" when the truth is
    "not measurable".
    """
    by_char: dict[str, list[str]] = {}
    for b in beats:
        if b["kind"] in CHARACTER_KINDS and b.get("characterId"):
            by_char.setdefault(b["characterId"], []).append(b["text"])
    ids = [c for c in by_char if len(_profile(by_char[c])) >= 5]
    if len(ids) < 2:
        return None
    profiles = {c: _profile(by_char[c]) for c in ids}
    pairs = [
        _js_distance(profiles[x], profiles[y])
        for i, x in enumerate(ids) for y in ids[i + 1:]
    ]
    return round(sum(pairs) / len(pairs), 6)


def score_turn(frames: list[dict], cast: dict[str, str], seconds: float) -> dict[str, Any]:
    beats = beats_from(frames)
    chars = [b for b in beats if b["kind"] in CHARACTER_KINDS]
    narration = [b for b in beats if b["kind"] == "narration"]

    cross = 0
    for b in chars:
        others = [n for cid, n in cast.items() if cid != b.get("characterId")]
        if prose_guards.cross_speaker_speech(b["text"], others=others):
            cross += 1

    plan = planned_speakers(frames)
    actual = [b.get("characterId") for b in beats]
    mis = sum(1 for p, a in zip(plan, actual) if p and a and p != a)

    paragraphs = [len([p for p in b["text"].split("\n") if p.strip()]) for b in chars]
    sentences = sum(b["text"].count(".") + b["text"].count("!") + b["text"].count("?")
                    for b in chars)
    words = sum(len(b["text"].split()) for b in chars)

    return {
        "beats": len(beats),
        "character_beats": len(chars),
        "narration_beats": len(narration),
        "seconds": round(seconds, 3),
        "discards": discards_in(frames),
        "fallback": 1 if fell_back(frames) else 0,
        # primary
        "cross_speaker_rate": round(cross / len(chars), 6) if chars else None,
        "misattribution_rate": round(mis / len(plan), 6) if plan else None,
        "voice_distinctness": voice_distinctness(beats, cast),
        # point of view — must not regress
        "addresses_the_reader": round(
            sum(1 for b in chars if prose_guards.addresses_the_reader(b["text"])) / len(chars), 6
        ) if chars else None,
        "narrator_first_person": round(
            sum(1 for b in narration
                if prose_guards.narrator_speaks_in_first_person(b["text"])) / len(narration), 6
        ) if narration else None,
        "names_the_player": round(
            sum(1 for b in beats if prose_guards.names_the_player(b["text"])) / len(beats), 6
        ) if beats else None,
        # form
        "has_speech": round(sum(1 for b in chars if '"' in b["text"] or "“" in b["text"])
                            / len(chars), 6) if chars else None,
        "paragraph_breaks": round(sum(paragraphs) / len(paragraphs), 6) if paragraphs else None,
        "sentences_per_100_words": round(sentences / words * 100, 6) if words else None,
        "chars": round(sum(len(b["text"]) for b in chars) / len(chars), 6) if chars else None,
    }


PRIMARY = ["cross_speaker_rate", "misattribution_rate", "voice_distinctness"]
SECONDARY = [
    "addresses_the_reader", "narrator_first_person", "names_the_player",
    "has_speech", "paragraph_breaks", "sentences_per_100_words", "chars",
]
COST = ["seconds", "beats", "character_beats", "discards", "fallback"]


def _mean(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 6) if vals else None


def main() -> int:
    global API

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", required=True, type=Path)
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--api", default=API)
    args = ap.parse_args()
    API = args.api.rstrip("/")

    entrypoint = (
        "uv run python -m utils.scripts.research.run_scene_script "
        f"--experiment {args.experiment} --turns {args.turns}"
    )
    record = RunRecord(entrypoint=entrypoint)
    started = time.time()

    storyline, scenario, cast = build_world()
    record.note(f"world storyline={storyline} scenario={scenario} cast={list(cast.values())}")

    sessions: dict[str, str | None] = {arm: None for arm in ARMS}
    transcript: dict[str, list] = {arm: [] for arm in ARMS}
    failed = False

    try:
        for i in range(min(args.turns, len(PLAYER_LINES))):
            line = PLAYER_LINES[i]
            # INTERLEAVED, turn by turn — see PROTOCOL § 4. The endpoint is then a shared
            # condition rather than something that drifted between two blocks of runs.
            for arm in ARMS:
                body: dict[str, Any] = {
                    "text": line,
                    "trace": True,  # the `plan` frame is what misattribution scores against
                    "overrides": {"sceneFlow": arm},
                }
                if sessions[arm]:
                    body["sessionId"] = sessions[arm]
                t0 = time.time()
                try:
                    frames = _stream(f"/play/{scenario}/turn", body)
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as err:
                    failed = True
                    record.note(f"FAILED arm={arm} turn={i + 1}: {err!r}")
                    continue
                seconds = time.time() - t0
                for f in frames:
                    if f.get("sessionId"):
                        sessions[arm] = sessions[arm] or f["sessionId"]
                if any(f.get("type") == "error" for f in frames):
                    failed = True
                    record.note(f"error frame arm={arm} turn={i + 1}")
                row = score_turn(frames, cast, seconds)
                row.update({"arm": arm, "turn": i + 1, "player_line": line})
                record.add_run(row)
                transcript[arm].append(
                    {"turn": i + 1, "beats": beats_from(frames)}
                )
                print(f"  {arm:<11} turn {i + 1}: {row['beats']} beats, "
                      f"{row['seconds']:.1f}s, cross={row['cross_speaker_rate']}, "
                      f"voice={row['voice_distinctness']}", flush=True)
    finally:
        try:
            _req("DELETE", f"/storylines/{storyline}")
        except Exception:  # noqa: BLE001 - cleanup must never mask a run's result
            record.note("cleanup: the throwaway storyline could not be deleted")

    record.wall_clock_seconds = time.time() - started

    logs = args.experiment / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    # **No aggregate over a partly-failed run.** Survivors are not a random subsample; see
    # PROTOCOL § 8 and EXP-2026-08-001, which is this repository's worked example of getting
    # it wrong. Per-turn rows are always written and are what RESULTS.md then reports.
    values: dict[str, Any] = {}
    if failed:
        record.note(
            "PARTIAL RUN — no aggregate computed. Report per-turn rows only."
        )
    else:
        for arm in ARMS:
            rows = [r for r in record.per_run if r["arm"] == arm]
            values[arm] = {k: _mean(rows, k) for k in PRIMARY + SECONDARY + COST}
            values[arm]["turns"] = len(rows)

    write_metrics(args.experiment, record, values)
    write_environment(args.experiment, record)
    update_manifest(args.experiment, {
        "status": "failed" if failed else "complete",
        "code": git_block(entrypoint),
        "compute": {
            "hardware": hardware(),
            "wall_clock_hours": round(record.wall_clock_seconds / 3600, 4),
            "estimated_cost_usd": 0.0,
        },
        "n_runs": len(record.per_run),
        "metrics": {"values": values},
    })
    print(f"\n{'FAILED' if failed else 'complete'} — "
          f"{len(record.per_run)} turn(s) in {record.wall_clock_seconds / 60:.1f} min")
    for note in record.notes:
        print(f"  note: {note}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
