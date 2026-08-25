"""EXP-2026-08-015 — does the cast stop addressing a player who is not in the scene?

Read ``docs/research/experiments/EXP-2026-08-015-pov-and-voice-baseline/PROTOCOL.md`` first.
The design (two commits, why it must be two, the confound that buys, the threats) is
pre-registered there and is not restated here.

Two backends, one per commit, interleaved turn by turn against the same LLM endpoint. Both
arms' transcripts are scored by **this** commit's ``app.services.prose_guards`` — a metric
that differed between arms would be measuring itself rather than the prose.

    uv run python -m utils.scripts.research.run_pov_mode \\
      --experiment docs/research/experiments/EXP-2026-08-015-pov-and-voice-baseline \\
      --pre-api http://localhost:3356/api --post-api http://localhost:3355/api --turns 6
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
    git_block,
    hardware,
    update_manifest,
    write_environment,
    write_metrics,
)

sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.services import prose_guards  # noqa: E402

from .run_scene_script import (  # noqa: E402  (one definition of each, shared deliberately)
    CAST,
    CHARACTER_KINDS,
    DISCARD_FLAGS,
    voice_distinctness,
)

#: The same scripted conversation as EXP-2026-08-016, so the two experiments' transcripts are
#: comparable by eye. The first line names a character on purpose: it is the owner's own
#: example, and the case where the narrator must describe **Lily** rather than address "you".
PLAYER_LINES = [
    "Lily jumps up on the table and starts singing to drown out the argument.",
    "Zoe tries to get her down before anyone outside hears.",
    "Aldous finally says what he has been holding back all evening.",
    "Someone outside starts knocking, slowly, three times.",
    "Lily decides to answer the door herself.",
    "Whatever is on the other side, it is not what any of them expected.",
]


def _req(api: str, method: str, path: str, body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{api}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=1800) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw.strip() else None


def _stream(api: str, path: str, body: dict) -> list[dict]:
    req = urllib.request.Request(
        f"{api}{path}", data=json.dumps(body).encode(), method="POST",
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


def build_world(api: str, title: str) -> tuple[str, str, dict[str, str]]:
    """A world per arm. Separate, so neither arm's beats condition the other's prompts."""
    storyline = _req(api, "POST", "/storylines", {
        "title": title,
        "genre": "noir",
        "premise": "A dockside tavern the night before a debt comes due.",
    })["id"]
    cast: dict[str, str] = {}
    for name, role in CAST:
        row = _req(api, "POST", f"/storylines/{storyline}/characters",
                   {"name": name, "role": role})
        cast[row["id"]] = name
    setting = _req(api, "POST", f"/storylines/{storyline}/settings", {
        "name": "The Smoldering Hearth",
        "desc": "A back room behind a dockside tavern, rain on the shutters.",
    })["id"]
    scenario = _req(api, "POST", f"/storylines/{storyline}/scenarios", {
        "title": "Last Call",
        "castIds": list(cast),
        "settingId": setting,
        "suggestionsCount": 0,
    })["id"]
    return storyline, scenario, cast


def beats_from(frames: list[dict]) -> list[dict]:
    """Accumulate the delta stream into finished beats, in order.

    Both arms are read the same way. The `pre` commit emits the same event shapes — the
    change under test is what the prose SAYS, not how it is transmitted.
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


def score_turn(frames: list[dict], cast: dict[str, str], seconds: float) -> dict[str, Any]:
    beats = beats_from(frames)
    chars = [b for b in beats if b["kind"] in CHARACTER_KINDS]
    narration = [b for b in beats if b["kind"] == "narration"]

    cross = 0
    for b in chars:
        others = [n for cid, n in cast.items() if cid != b.get("characterId")]
        if prose_guards.cross_speaker_speech(b["text"], others=others):
            cross += 1

    texts = [b["text"] for b in chars]
    distinct = len({t.strip()[:200] for t in texts}) / len(texts) if texts else None
    sentences = sum(b["text"].count(".") + b["text"].count("!") + b["text"].count("?")
                    for b in chars)
    words = sum(len(b["text"].split()) for b in chars)
    paragraphs = [len([p for p in b["text"].split("\n") if p.strip()]) for b in chars]

    discards = sum(
        1 for f in frames
        if f.get("type") == "trace" and any((f.get("data") or {}).get(k) for k in DISCARD_FLAGS)
    )

    return {
        "seconds": round(seconds, 3),
        "beats": len(beats),
        "character_beats": len(chars),
        "narration_beats": len(narration),
        "discards": discards,
        # ---- primary ----
        "addresses_the_reader": round(
            sum(1 for b in chars if prose_guards.addresses_the_reader(b["text"])) / len(chars), 6
        ) if chars else None,
        "narrator_addresses_the_reader": round(
            sum(1 for b in narration if prose_guards.addresses_the_reader(b["text"]))
            / len(narration), 6
        ) if narration else None,
        "narrator_first_person": round(
            sum(1 for b in narration
                if prose_guards.narrator_speaks_in_first_person(b["text"])) / len(narration), 6
        ) if narration else None,
        "names_the_player": round(
            sum(1 for b in beats if prose_guards.names_the_player(b["text"])) / len(beats), 6
        ) if beats else None,
        # ---- secondary: must not regress ----
        "cross_speaker_rate": round(cross / len(chars), 6) if chars else None,
        "has_speech": round(sum(1 for b in chars if '"' in b["text"] or "“" in b["text"])
                            / len(chars), 6) if chars else None,
        "is_distinct": round(distinct, 6) if distinct is not None else None,
        "sentences_per_100_words": round(sentences / words * 100, 6) if words else None,
        "voice_distinctness": voice_distinctness(beats, cast),
        # ---- reported, NOT compared across arms (PROTOCOL section 5) ----
        "paragraph_breaks": round(sum(paragraphs) / len(paragraphs), 6) if paragraphs else None,
        "chars": round(sum(len(b["text"]) for b in chars) / len(chars), 6) if chars else None,
    }


PRIMARY = [
    "addresses_the_reader", "narrator_addresses_the_reader",
    "narrator_first_person", "names_the_player",
]
SECONDARY = [
    "cross_speaker_rate", "has_speech", "is_distinct",
    "sentences_per_100_words", "voice_distinctness",
]
REPORTED_ONLY = ["paragraph_breaks", "chars", "beats", "character_beats", "seconds", "discards"]


def _mean(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 6) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--experiment", required=True, type=Path)
    ap.add_argument("--pre-api", required=True, help="backend running the PRE commit")
    ap.add_argument("--post-api", required=True, help="backend running the POST commit")
    ap.add_argument("--turns", type=int, default=6)
    args = ap.parse_args()

    apis = {"pre": args.pre_api.rstrip("/"), "post": args.post_api.rstrip("/")}
    entrypoint = (
        "uv run python -m utils.scripts.research.run_pov_mode "
        f"--experiment {args.experiment} --pre-api {apis['pre']} --post-api {apis['post']} "
        f"--turns {args.turns}"
    )
    record = RunRecord(entrypoint=entrypoint)
    started = time.time()

    worlds: dict[str, tuple[str, str, dict[str, str]]] = {}
    for arm, api in apis.items():
        worlds[arm] = build_world(api, f"EXP-015 {arm}")
        record.note(f"{arm}: storyline={worlds[arm][0]} scenario={worlds[arm][1]} @ {api}")

    sessions: dict[str, str | None] = {"pre": None, "post": None}
    transcript: dict[str, list] = {"pre": [], "post": []}
    failed = False

    try:
        for i in range(min(args.turns, len(PLAYER_LINES))):
            line = PLAYER_LINES[i]
            # Interleaved, arm by arm, so the endpoint is a shared condition — PROTOCOL § 4.
            for arm in ("pre", "post"):
                _sl, scenario, cast = worlds[arm]
                body: dict[str, Any] = {"text": line, "trace": True}
                if sessions[arm]:
                    body["sessionId"] = sessions[arm]
                t0 = time.time()
                try:
                    frames = _stream(apis[arm], f"/play/{scenario}/turn", body)
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
                print(f"  {arm:<5} turn {i + 1}: {row['beats']} beats, {row['seconds']:.1f}s, "
                      f"reader={row['addresses_the_reader']}, "
                      f"narrator_reader={row['narrator_addresses_the_reader']}", flush=True)
    finally:
        for arm, (storyline, _sc, _c) in worlds.items():
            try:
                _req(apis[arm], "DELETE", f"/storylines/{storyline}")
            except Exception:  # noqa: BLE001 — cleanup must not mask a result
                record.note(f"cleanup: {arm} storyline could not be deleted")

    record.wall_clock_seconds = time.time() - started

    logs = args.experiment / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    # No aggregate over a partly-failed run — PROTOCOL § 7, and EXP-2026-08-001 is why.
    values: dict[str, Any] = {}
    if failed:
        record.note("PARTIAL RUN — no aggregate computed. Report per-turn rows only.")
    else:
        for arm in ("pre", "post"):
            rows = [r for r in record.per_run if r["arm"] == arm]
            values[arm] = {k: _mean(rows, k) for k in PRIMARY + SECONDARY + REPORTED_ONLY}
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
    print(f"\n{'FAILED' if failed else 'complete'} — {len(record.per_run)} turn(s) in "
          f"{record.wall_clock_seconds / 60:.1f} min")
    for note in record.notes:
        print(f"  note: {note}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
