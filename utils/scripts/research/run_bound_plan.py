"""EXP-2026-08-017 — two execution arms over one bound plan.

Read ``docs/research/experiments/EXP-2026-08-017-bound-plan-execution/PROTOCOL.md`` first.
The design decisions that matter (interleaving, separate sessions, the decision rule, the
threats) are pre-registered there and are not restated here.

Both arms consume the SAME bound plan — one planning call decides the turn — and differ only
in how the planned beats are written: ``continuous`` (one generation, ``<speaker:N>``
hand-offs) or ``voiced`` (one generation per beat, no planning between them).

Every prose metric is imported from ``app.services.prose_guards``. A harness with its own
copy of "what counts as a violation" measures its own opinion.

    uv run python -m utils.scripts.research.run_bound_plan \\
      --experiment docs/research/experiments/EXP-2026-08-017-bound-plan-execution --turns 2
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
    update_manifest,
    write_environment,
    write_metrics,
)

sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.services import prose_guards  # noqa: E402

API = "http://localhost:3345/api"

#: `voiced` first so the arm expected to be SLOWER per beat runs before any warm-up effect
#: could flatter it.
ARMS = ("voiced", "continuous")

CAST = [
    ("Lily", "a street singer who talks her way out of things"),
    ("Zoe", "a harbour-watch sergeant who does not"),
    ("Aldous", "an archivist who knows what both of them owe"),
]

PLAYER_LINES = [
    "Lily jumps up on the table and starts singing to drown out the argument.",
    "Zoe tries to get her down before anyone outside hears.",
]

CHARACTER_KINDS = {"character_prose", "character_dialogue", "character_action"}
BEAT_KINDS = CHARACTER_KINDS | {"narration"}
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
        "title": "EXP-017 Bound Plan",
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
        "suggestionsCount": 0,
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
        if kind not in BEAT_KINDS:
            continue
        eid = frame.get("id") or ""
        data = frame.get("data") or {}
        if eid not in by_id:
            by_id[eid] = {"kind": kind, "characterId": data.get("characterId"), "text": ""}
            order.append(eid)
        by_id[eid]["text"] += data.get("text") or ""
    return [by_id[i] for i in order if by_id[i]["text"].strip()]


def beats_after_the_plan(frames: list[dict]) -> list[dict]:
    """Only the beats the plan could have been responsible for.

    Split on frame ORDER rather than on beat kind. The scene-opening narration and any beat
    the direction scheduler forces are emitted BEFORE the `plan` frame exists, so counting
    them against the plan measures the engine's other contracts, not the planner's. Anything
    before the plan frame is by construction not something the plan scheduled.
    """
    seen_plan = False
    tail: list[dict] = []
    for frame in frames:
        if frame.get("type") == "plan":
            seen_plan = True
            tail = []  # restart: everything before the plan is not the plan's
            continue
        if seen_plan:
            tail.append(frame)
    return beats_from(tail) if seen_plan else []


def planned_beats(frames: list[dict]) -> list[str | None]:
    """The plan's speaker order, from the `plan` frame."""
    for f in frames:
        if f.get("type") == "plan":
            return [b.get("actorId") for b in f.get("beats", [])
                    if b.get("action") in ("speak", "narrate")]
    return []


def planner_calls(frames: list[dict]) -> int:
    """How many planning calls this turn made. The bound turn's whole point is 1."""
    n = 0
    for f in frames:
        if f.get("type") != "trace":
            continue
        if f.get("step") in ("planning",) and "off" not in str((f.get("data") or {}).get("planner", "")):
            n += 1
    return n


def was_bound(frames: list[dict]) -> bool:
    return any(
        f.get("type") == "trace" and (f.get("data") or {}).get("planner") == "upfront"
        for f in frames
    )


def cache_rate(frames: list[dict]) -> float | None:
    """Prefix-cache hit rate over the turn's prose calls, from the server's own usage.

    ``None`` when the endpoint never reported the field (vLLM omits it) — reported as
    unmeasured rather than as a zero, which would read as "the cache never hit".
    """
    cached = prompt = 0
    seen = False
    for f in frames:
        if f.get("type") != "trace":
            continue
        data = f.get("data") or {}
        if data.get("cachedTokens") is None or not data.get("promptTokens"):
            continue
        seen = True
        cached += int(data["cachedTokens"])
        prompt += int(data["promptTokens"])
    return round(cached / prompt, 6) if seen and prompt else None


def forced_beats(frames: list[dict]) -> int:
    """Beats the DIRECTION scheduler forced, which the plan never named.

    The player's message is parsed into requirements ("Lily is standing on the table",
    "Lily is singing") and the engine schedules beats to deliver them, before and around the
    planned ones. That is a deliberate contract — the player's instruction outranks the
    plan's length — but it means total beats run is NOT comparable to the plan's length.
    Counted separately so `plan_adherence` measures the plan rather than the direction.
    """
    return sum(
        1 for f in frames
        if f.get("type") == "trace" and f.get("step") == "speaker"
        and (f.get("data") or {}).get("puppet") is True
    )


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


# ---- metrics -----------------------------------------------------------------

_WORD = re.compile(r"[a-z']+")
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
    na, nb = sum(a.values()), sum(b.values())
    if not na or not nb:
        return 0.0
    div = 0.0
    for k in set(a) | set(b):
        p, q = a[k] / na, b[k] / nb
        m = (p + q) / 2
        if p:
            div += 0.5 * p * math.log2(p / m)
        if q:
            div += 0.5 * q * math.log2(q / m)
    return round(math.sqrt(max(0.0, div)), 6)


def voice_distinctness(beats: list[dict]) -> float | None:
    """``None`` when fewer than two characters spoke — a single voice has nothing to be
    distinct FROM, and 0.0 there would read as "identical" when the truth is "not
    measurable"."""
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
    plan = planned_beats(frames)
    forced = forced_beats(frames)
    plan_beats_run = len(beats_after_the_plan(frames))

    cross = sum(
        1 for b in chars
        if prose_guards.cross_speaker_speech(
            b["text"], others=[n for cid, n in cast.items() if cid != b.get("characterId")]
        )
    )
    actual = [b.get("characterId") for b in beats]
    mis = sum(1 for p, a in zip(plan, actual) if p and a and p != a)
    paragraphs = [len([p for p in b["text"].split("\n") if p.strip()]) for b in chars]

    return {
        "beats": len(beats),
        "character_beats": len(chars),
        "planned_beats": len(plan),
        # THE primary metric: did the turn run the beats it planned, and only those?
        "forced_beats": forced,
        "plan_beats_run": plan_beats_run,
        # Beats the plan was responsible for, over beats it named. 1.0 means the plan ran as
        # written; above 1.0 means something extended it, which after the direction beats are
        # removed can only be a re-plan.
        "plan_adherence": round(plan_beats_run / len(plan), 6) if plan else None,
        "planner_calls": planner_calls(frames),
        "bound": 1 if was_bound(frames) else 0,
        "cached_token_rate": cache_rate(frames),
        "seconds": round(seconds, 3),
        "seconds_per_beat": round(seconds / len(beats), 3) if beats else None,
        "discards": discards_in(frames),
        "fallback": 1 if fell_back(frames) else 0,
        "cross_speaker_rate": round(cross / len(chars), 6) if chars else None,
        "misattribution_rate": round(mis / len(plan), 6) if plan else None,
        "voice_distinctness": voice_distinctness(beats),
        "addresses_the_reader": round(
            sum(1 for b in chars if prose_guards.addresses_the_reader(b["text"])) / len(chars), 6
        ) if chars else None,
        "names_the_player": round(
            sum(1 for b in beats if prose_guards.names_the_player(b["text"])) / len(beats), 6
        ) if beats else None,
        "has_speech": round(
            sum(1 for b in chars if '"' in b["text"] or "“" in b["text"]) / len(chars), 6
        ) if chars else None,
        "paragraph_breaks": round(sum(paragraphs) / len(paragraphs), 6) if paragraphs else None,
    }


PRIMARY = ["plan_adherence", "planner_calls", "cached_token_rate", "seconds_per_beat"]
SECONDARY = [
    "cross_speaker_rate", "misattribution_rate", "voice_distinctness",
    "addresses_the_reader", "names_the_player", "has_speech", "paragraph_breaks",
]
COST = ["beats", "character_beats", "planned_beats", "plan_beats_run", "forced_beats",
        "seconds", "discards", "fallback", "bound"]


def _mean(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 6) if vals else None


def main() -> int:
    global API

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", required=True, type=Path)
    ap.add_argument("--turns", type=int, default=2)
    ap.add_argument("--api", default=API)
    args = ap.parse_args()
    API = args.api.rstrip("/")

    entrypoint = (
        "uv run python -m utils.scripts.research.run_bound_plan "
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
            for arm in ARMS:  # INTERLEAVED — see PROTOCOL § 4
                body: dict[str, Any] = {
                    "text": line,
                    "trace": True,  # the `plan` frame is what adherence scores against
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
                transcript[arm].append({"turn": i + 1, "beats": beats_from(frames)})
                print(
                    f"  {arm:<11} turn {i + 1}: {row['plan_beats_run']}/{row['planned_beats']} planned "
                    f"(+{row['forced_beats']} forced, adherence {row['plan_adherence']}), "
                    f"{row['planner_calls']} planner call(s), "
                    f"{row['seconds']:.1f}s, cache={row['cached_token_rate']}, "
                    f"voice={row['voice_distinctness']}",
                    flush=True,
                )
    finally:
        try:
            _req("DELETE", f"/storylines/{storyline}")
        except Exception:  # noqa: BLE001 - cleanup must never mask a run's result
            record.note("cleanup: the throwaway storyline could not be deleted")

    record.wall_clock_seconds = time.time() - started

    logs = args.experiment / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    # No aggregate over a partly-failed run: survivors are not a random subsample.
    # PROTOCOL § 8, and EXP-2026-08-001 is the worked example of getting it wrong.
    values: dict[str, Any] = {}
    if failed:
        record.note("PARTIAL RUN — no aggregate computed. Report per-turn rows only.")
    else:
        for arm in ARMS:
            rows = [r for r in record.per_run if r["arm"] == arm]
            values[arm] = {k: _mean(rows, k) for k in PRIMARY + SECONDARY + COST}
            values[arm]["turns"] = len(rows)

    write_metrics(args.experiment, record, values)
    write_environment(args.experiment, record)
    update_manifest(args.experiment, {"status": "failed" if failed else "complete"})
    print(f"\nwrote {args.experiment}/data/metrics.json")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
