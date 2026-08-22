"""Live record-controls harness for EXP-2026-08-014.

Five probes, one per record operation, each against the **running** dev backend and the
local relay on ``:4000``. The question from ``PROTOCOL.md``: the five operations all
change the transcript visibly — do they change everything the transcript is derived from?

Two things make this a live harness rather than a unit test. Three of the five suspected
defects live in the route layer or in what Redis holds afterwards, and neither is
reachable from an in-process fixture; and the recall probe is a question about what a
real model does with a real prompt, which no fake can answer.

Each probe builds its **own** throwaway world and play-through, so a probe that fails
cannot contaminate the next, and nothing is aggregated across probes — they measure
different mechanisms, and a mean over them would be a number about nothing. Worlds are
left in the dev database rather than deleted: a deleted world cannot be inspected when a
number looks wrong.

Usage::

    uv run python -m utils.scripts.research.run_record_controls \\
        --arm baseline \\
        --experiment docs/research/experiments/EXP-2026-08-014-record-controls
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from . import REPO_ROOT
from .record import RunRecord, git_block, hardware, update_manifest, write_environment, write_metrics
from .run_conversation_scaling import API, _post, build_world

#: The relay, read for the model id actually served. "skynet" is a route, not a model —
#: the relay hot-swaps its upstream, so the run has to record what answered it.
RELAY = "http://localhost:4000/v1/models"

# ---------------------------------------------------------------------------
# The scripted player side. Fixed before the run; identical in both arms.
# ---------------------------------------------------------------------------

#: Asked BEFORE anything is planted, to establish the recall floor. Whatever the cast
#: invents here is the score a scene that genuinely forgot should return to.
CONTROL = "I ask them what they already know about me."

#: The planted fact, reused verbatim from EXP-2026-08-011 so the two experiments' recall
#: numbers are on the same scale. Deliberately concrete: a fact scored by word overlap has
#: to be made of words that cannot arrive by accident.
PLANT = (
    "I tell them my name is Rensal Vey, that I owe the harbourmaster four hundred crowns, "
    "and that I keep a brass key sewn into my collar."
)
#: Attached to the planting turn as scene direction. Chosen to be something a single turn
#: is unlikely to deliver, so it survives as `standing_direction` and the rewind has a debt
#: to cancel. The probe asserts the setup rather than assuming it.
PLANT_DIRECTION = (
    "Before the scene ends, have every one of them separately name the drowned lighthouse "
    "keeper and say what they owe him."
)
#: A turn that REACTS to the plant, so the cut turns have produced interior state, graph
#: edges and a summary of their own.
REACT = "I ask which of them is going to tell the harbourmaster where I am."
#: Asked AFTER the rewind. If the scene forgot, this scores near the floor.
PROBE = "I ask them to repeat back what I told them about my debt and my collar."
#: The content the probe's answer must reach for the fact to count as remembered.
PROBE_FACT = (
    "Rensal Vey owes the harbourmaster four hundred crowns and keeps a brass key sewn "
    "into his collar"
)

#: Turns for the probes that only need a scene to exist.
FILLER = [
    "I set my cup down and look around the room.",
    "I ask who else has been here tonight.",
    "I put a coin on the table and leave my hand on it.",
]

#: Event types whose prose the recent-turn buffer holds. Mirrors
#: ``services.session_state._BUFFER_ROLES`` — kept here as a literal on purpose: if the
#: engine's idea of a buffered row ever changes, this harness should disagree loudly rather
#: than silently follow it.
BUFFERED = {"narration", "character_prose", "character_dialogue", "character_action"}
#: Types that carry visible prose in the transcript.
PROSE = BUFFERED | {"internal_thought", "user_turn"}


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


def _request(method: str, path: str, payload: dict | None = None, timeout: int = 300) -> Any:
    req = urllib.request.Request(
        f"{API}{path}",
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = res.read().decode()
    return json.loads(body) if body.strip() else None


def _get(path: str) -> Any:
    return _request("GET", path)


def _patch(path: str, payload: dict) -> Any:
    return _request("PATCH", path, payload)


def _stream(path: str, payload: dict, timeout: int = 900) -> list[dict]:
    """Drive an NDJSON endpoint to completion and return every frame.

    The turn and re-roll endpoints both answer this way, so one reader serves both. Delta
    frames re-emit the same id with an incremental chunk; the callers below accumulate by
    id rather than reading the final (empty) ``done`` frame, which is the trap
    ``CLAUDE.md`` warns about.
    """
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    frames: list[dict] = []
    with urllib.request.urlopen(req, timeout=timeout) as res:
        for raw in res:
            line = raw.decode().strip()
            if not line:
                continue
            try:
                frames.append(json.loads(line))
            except json.JSONDecodeError:  # a truncated line is a finding, not a crash
                frames.append({"type": "unparseable", "raw": line[:200]})
    return frames


def turn(scenario: str, session: str | None, text: str, **extra: Any) -> tuple[str, list[dict]]:
    """One player turn. Returns the session id and every frame the stream carried."""
    payload: dict[str, Any] = {"text": text, "trace": True, **extra}
    if session:
        payload["sessionId"] = session
    frames = _stream(f"/play/{scenario}/turn", payload)
    for frame in frames:
        if frame.get("type") == "error":
            raise SystemExit(f"turn failed: {frame.get('message')}")
        if not session and frame.get("sessionId"):
            session = str(frame["sessionId"])
    if session is None:
        raise SystemExit("the turn stream never named a session")
    return session, frames


def prose_of(frames: list[dict]) -> str:
    """Every visible word the stream produced, accumulated by event id.

    Delta frames re-emit one id with an incremental chunk, so the last chunk per id is the
    tail and not the whole line. Concatenating chunks per id in arrival order is the only
    reading that recovers the text.
    """
    by_id: dict[str, str] = {}
    order: list[str] = []
    for frame in frames:
        if frame.get("type") not in ("narration", "character_prose", "character_dialogue", "character_action"):
            continue
        eid = str(frame.get("id") or "")
        text = str((frame.get("data") or {}).get("text") or "")
        if eid not in by_id:
            by_id[eid] = ""
            order.append(eid)
        by_id[eid] += text
    return "\n".join(by_id[i] for i in order)


# ---------------------------------------------------------------------------
# Inspection — what the record actually holds, behind the API
# ---------------------------------------------------------------------------


def _backend_path() -> pathlib.Path:
    return REPO_ROOT / "web" / "backend"


def _app():
    """Import the backend package for direct store inspection.

    The harness drives the app over HTTP — that is the point — but three of the metrics
    are about state the API deliberately does not expose: Redis keys, a session column,
    and the graph. Reading them through the app's own clients is more honest than
    re-deriving connection strings here.
    """
    path = str(_backend_path())
    if path not in sys.path:
        sys.path.insert(0, path)


def coverage(fact: str, text: str, ignore: list[str] | None = None) -> float:
    """The engine's own lexical coverage check. A floor on recall, never a measurement
    of it — see PROTOCOL.md."""
    _app()
    from app.services import direction_check  # noqa: PLC0415 — path set above

    return round(direction_check.coverage(fact, text, ignore_names=ignore or []), 4)


def recall(answer: str) -> tuple[float, float]:
    """Two readings of the same answer: plain coverage, and coverage with the probe's own
    vocabulary discounted.

    Added after the baseline rewind probe ran (recorded in ISSUES.md). The probe asks about
    "my debt and my collar", so *collar* is in the question — a model that merely echoes the
    question scores for it. Discounting the question's own content words leaves only the
    tokens an answer can reach by remembering. The undiscounted figure is kept because the
    first baseline row has only that, and dropping it would hide the amendment.
    """
    _app()
    from app.services import direction_check  # noqa: PLC0415 — path set above

    plain = direction_check.coverage(PROBE_FACT, answer, ignore_names=["Rensal Vey"])
    wanted = direction_check.content_words(PROBE_FACT) - direction_check.content_words(
        "Rensal Vey"
    )
    wanted -= direction_check.content_words(PROBE)
    if not wanted:  # pragma: no cover - the probe would have to quote the whole fact
        return round(plain, 4), 0.0
    hit = len(wanted & direction_check.content_words(answer)) / len(wanted)
    return round(plain, 4), round(hit, 4)


def redis_client():
    _app()
    from app.core.redis import get_redis  # noqa: PLC0415

    return get_redis()


def interior_keys(session_id: str) -> list[str]:
    """Every ``interior:{session}:*`` key. The disposition a character re-enters with."""
    try:
        return sorted(redis_client().scan_iter(match=f"interior:{session_id}:*"))
    except Exception as exc:  # pragma: no cover - a dead Redis is a finding, not a crash
        return [f"<redis unavailable: {exc}>"]


def buffer_entries(session_id: str) -> list[dict]:
    """The recent-turn buffer, oldest first (it is stored newest-first)."""
    try:
        raw = redis_client().lrange(f"buffer:{session_id}", 0, -1)
    except Exception:  # pragma: no cover
        return []
    return [json.loads(r) for r in reversed(raw)]


def session_row(session_id: str) -> dict[str, Any]:
    """``standing_direction`` and the rolling summary, straight off the row."""
    _app()
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.models import PlaySession  # noqa: PLC0415

    with SessionLocal() as db:
        row = db.get(PlaySession, session_id)
        if row is None:
            return {}
        return {
            "standingDirection": row.standing_direction or [],
            "summaryText": row.summary_text,
            "summaryThroughSeq": row.summary_through_seq,
        }


def graph_edges(scenario_id: str) -> int:
    """How many character↔character ties the story graph holds for this scenario."""
    try:
        rels = _get(f"/play/{scenario_id}/relationships")
    except urllib.error.HTTPError:  # pragma: no cover
        return -1
    return len(rels.get("relationships") or [])


def replay_window_holds(scenario_id: str, session_id: str, event_id: str) -> dict[str, Any]:
    """Does the context a re-roll is generated against still contain the beat it replaces?

    A **direct** read of H3, in process, with no model involved: build the same
    ``TurnContext`` ``beat_rerun.rerun_beat`` builds and look for the target's own text in
    its transcript window and in the speaker's voice anchors. Added after the baseline arm
    (ISSUES.md A-3) because ``self_overlap`` — how much wording a re-take reuses — cannot
    separate "the model was shown the line" from "two versions of one beat share nouns".
    """
    _app()
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.models import Event, Scenario  # noqa: PLC0415
    from app.services import turn_setup  # noqa: PLC0415

    with SessionLocal() as db:
        scenario = db.get(Scenario, scenario_id)
        row = db.get(Event, event_id)
        if scenario is None or row is None:
            return {"error": "unknown scenario or beat"}
        data = row.data if isinstance(row.data, dict) else {}
        target = str(data.get("text") or "").strip()
        ctx, turn_beats = turn_setup.context_for_replay(
            db, scenario, session_id, through_seq=row.seq - 1
        )
        window = [str(b.get("text") or "") for b in ctx.recent_beats]
        speaker = ctx.cast_by_id(str(data.get("characterId") or ""))
        anchors = list(speaker.recent_lines) if speaker is not None else []
        return {
            "target_in_replay_window": int(any(target and target in t for t in window)),
            "target_in_voice_anchors": int(any(target and target in a for a in anchors)),
            "target_in_turn_beats": int(
                any(target and target in str(b.get("text") or "") for b in turn_beats)
            ),
            "replay_window_beats": len(window),
        }


def history(scenario: str, session: str) -> dict[str, Any]:
    return _get(f"/play/{scenario}/sessions/{session}")


def events(scenario: str, session: str) -> list[dict]:
    return history(scenario, session)["events"]


def counts_by_type(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        out[row["type"]] = out.get(row["type"], 0) + 1
    return out


def text_of(row: dict) -> str:
    return str((row.get("data") or {}).get("text") or "")


# ---------------------------------------------------------------------------
# Probe 1 — does a rewind make the scene forget?
# ---------------------------------------------------------------------------


def probe_rewind(record: RunRecord) -> dict[str, Any]:
    scenario, storyline = build_world(max_turns=4, suggestions=0, context_beats=14)
    row: dict[str, Any] = {"probe": "rewind", "scenario": scenario, "storyline": storyline}

    session, control_frames = turn(scenario, None, CONTROL)
    row["recall_floor"] = coverage(PROBE_FACT, prose_of(control_frames), ignore=["Rensal Vey"])

    plant_seq_before = len(events(scenario, session))
    session, plant_frames = turn(scenario, session, PLANT, guidance=PLANT_DIRECTION)
    row["plant_coverage"] = coverage(PROBE_FACT, prose_of(plant_frames), ignore=["Rensal Vey"])
    # The beat the rewind will point at: the player's own line that planted the fact.
    rows_after_plant = events(scenario, session)
    plant_turn = next(
        e for e in rows_after_plant[plant_seq_before:] if e["type"] == "user_turn"
    )
    cut_seq = plant_turn["seq"] - 1

    turn(scenario, session, REACT)

    before = events(scenario, session)
    state_before = session_row(session)
    row["events_before"] = len(before)
    row["interior_before"] = len(interior_keys(session))
    row["standing_before"] = len(state_before.get("standingDirection") or [])
    row["graph_edges_before"] = graph_edges(scenario)
    # The prose the rewind is about to delete — the strings a leaked buffer would still
    # be holding afterwards.
    doomed = [text_of(e) for e in before if e["seq"] > cut_seq and e["type"] in PROSE]
    doomed = [t for t in doomed if t.strip()]

    # A direction that was never owed cannot be a rewind's fault. Recorded rather than
    # asserted, so the metric reads as inconclusive instead of as a pass.
    row["standing_setup_ok"] = int(row["standing_before"] > 0)

    result = _request(
        "POST",
        f"/play/{scenario}/sessions/{session}/rewind",
        {"atEventId": plant_turn["id"], "keepSnapshot": True},
    )
    row["removed_events"] = result["removedEvents"]
    row["cut_seq"] = result["cutSeq"]
    row["restored_text_matches"] = int((result.get("restoredTurn") or {}).get("text") == PLANT)
    row["restored_guidance_matches"] = int(
        (result.get("restoredTurn") or {}).get("guidance") == PLANT_DIRECTION
    )
    row["snapshot_kept"] = int(bool(result.get("snapshotSessionId")))

    after = events(scenario, session)
    state_after = session_row(session)
    standing_after = state_after.get("standingDirection") or []
    row["events_after"] = len(after)
    row["events_above_cut"] = sum(1 for e in after if e["seq"] > cut_seq)
    row["interior_keys_after"] = len(interior_keys(session))
    row["standing_after"] = len(standing_after)
    row["standing_after_from_cut_turns"] = sum(
        1
        for s in standing_after
        if isinstance(s, dict) and isinstance(s.get("fromTurn"), int) and s["fromTurn"] > cut_seq
    )
    row["summary_after"] = int(bool(state_after.get("summaryText")))
    row["graph_edges_after"] = graph_edges(scenario)

    buffered = [str(b.get("text") or "") for b in buffer_entries(session)]
    row["buffer_leak_beats"] = sum(1 for t in doomed if t in buffered)
    row["buffer_beats_after"] = len(buffered)

    # The question the owner actually asked: does the scene still know?
    _, probe_frames = turn(scenario, session, PROBE)
    answer = prose_of(probe_frames)
    row["recall_coverage"], row["recall_coverage_discounted"] = recall(answer)
    row["recall_above_floor"] = round(row["recall_coverage"] - row["recall_floor"], 4)
    # Stored so the number can be re-scored without re-running a fifteen-minute probe —
    # which is exactly what the missing discount cost the first time.
    row["probe_answer"] = answer

    record.note(
        f"rewind probe: session={session} scenario={scenario} cut_seq={cut_seq} "
        f"interior_after={row['interior_keys_after']} standing_after={row['standing_after']}"
    )
    return row


# ---------------------------------------------------------------------------
# Probe 2 — does a re-roll replace the beat, or continue it?
# ---------------------------------------------------------------------------


def probe_reroll_beat(record: RunRecord) -> dict[str, Any]:
    scenario, storyline = build_world(max_turns=3, suggestions=0, context_beats=14)
    row: dict[str, Any] = {"probe": "reroll_beat", "scenario": scenario, "storyline": storyline}

    session, _ = turn(scenario, None, FILLER[0])
    session, _ = turn(scenario, session, FILLER[1])

    before = events(scenario, session)
    counts_before = counts_by_type(before)
    target = next(
        (e for e in reversed(before) if e["type"] in ("character_prose", "character_dialogue")),
        None,
    )
    if target is None:
        row["status"] = "inconclusive: the scene produced no character beat to re-roll"
        return row
    row["status"] = "ok"
    row["target_type"] = target["type"]
    # Measured BEFORE the first re-roll, against the record as it stands: this is the
    # question `self_overlap` can only guess at.
    row.update(replay_window_holds(scenario, session, target["id"]))

    previous = text_of(target)
    overlaps: list[float] = []
    ids: set[str] = set()
    seqs: set[int] = set()
    for _ in range(3):
        frames = _stream(
            f"/play/{scenario}/sessions/{session}/beats/{target['id']}/reroll", {"scope": "beat"}
        )
        errors = [f for f in frames if f.get("type") == "error"]
        if errors:
            row["status"] = f"failed: {errors[0].get('message')}"
            record.note(f"reroll probe: stream error — {errors[0].get('message')}")
            return row
        row.setdefault("leads_with_beat_reroll", int(frames[0].get("type") == "beat_reroll"))
        fresh = next(e for e in events(scenario, session) if e["id"] == target["id"])
        ids.add(fresh["id"])
        seqs.add(fresh["seq"])
        new_text = text_of(fresh)
        # How much of the wording it was asked to replace the replacement reuses. A model
        # shown the beat it is replacing tends to continue from it.
        overlaps.append(coverage(previous, new_text))
        previous = new_text

    final = next(e for e in events(scenario, session) if e["id"] == target["id"])
    data = final.get("data") or {}
    counts_after = counts_by_type(events(scenario, session))

    row["id_stable"] = int(ids == {target["id"]})
    row["seq_stable"] = int(seqs == {target["seq"]})
    row["takes"] = len(data.get("takes") or [])
    row["active_take"] = data.get("activeTake")
    row["active_take_is_last"] = int(data.get("activeTake") == len(data.get("takes") or []) - 1)
    row["takes_distinct"] = len({t.get("text") for t in (data.get("takes") or [])})
    row["state_update_delta"] = counts_after.get("state_update", 0) - counts_before.get("state_update", 0)
    row["thought_delta"] = counts_after.get("internal_thought", 0) - counts_before.get("internal_thought", 0)
    row["total_rows_delta"] = sum(counts_after.values()) - sum(counts_before.values())
    row["self_overlap_mean"] = round(sum(overlaps) / len(overlaps), 4)
    row["self_overlap_max"] = round(max(overlaps), 4)

    # The take pager has to actually show a kept version.
    if row["takes"] >= 2:
        restored = _patch(
            f"/play/{scenario}/sessions/{session}/beats/{target['id']}/take", {"take": 0}
        )
        row["take_select_ok"] = int(
            (restored.get("data") or {}).get("text") == (data.get("takes") or [{}])[0].get("text")
        )
        buffered = [str(b.get("text") or "") for b in buffer_entries(session)]
        row["take_select_reaches_buffer"] = int(
            (restored.get("data") or {}).get("text") in buffered
        )

    record.note(f"reroll probe: session={session} beat={target['id']} takes={row['takes']}")
    return row


# ---------------------------------------------------------------------------
# Probe 3 — does re-running a turn replace it cleanly?
# ---------------------------------------------------------------------------


def probe_rerun_turn(record: RunRecord) -> dict[str, Any]:
    scenario, storyline = build_world(max_turns=3, suggestions=0, context_beats=14)
    row: dict[str, Any] = {"probe": "rerun_turn", "scenario": scenario, "storyline": storyline}

    session, _ = turn(scenario, None, FILLER[0])
    session, _ = turn(scenario, session, FILLER[2])

    before = events(scenario, session)
    opening = [e for e in before if e["type"] == "user_turn"][-1]
    row["rows_before"] = len(before)
    row["opening_seq"] = opening["seq"]
    target = next(e for e in reversed(before) if e["type"] in BUFFERED)

    frames = _stream(
        f"/play/{scenario}/sessions/{session}/beats/{target['id']}/reroll", {"scope": "turn"}
    )
    errors = [f for f in frames if f.get("type") == "error"]
    if errors:
        row["status"] = f"failed: {errors[0].get('message')}"
        record.note(f"rerun_turn probe: stream error — {errors[0].get('message')}")
        return row
    row["status"] = "ok"

    after = events(scenario, session)
    same_turn = [e for e in after if e["seq"] >= opening["seq"]]
    row["rows_after"] = len(after)
    row["user_turn_rows"] = sum(1 for e in same_turn if e["type"] == "user_turn")
    row["player_text_preserved"] = int(
        any(e["type"] == "user_turn" and text_of(e) == FILLER[2] for e in same_turn)
    )
    row["first_new_seq"] = min((e["seq"] for e in same_turn if e["type"] != "user_turn"), default=-1)
    row["first_new_seq_is_opening_plus_one"] = int(row["first_new_seq"] == opening["seq"] + 1)
    row["beats_after_rerun"] = sum(1 for e in same_turn if e["type"] in BUFFERED)
    # The seqs of a replayed turn must be contiguous — a gap means rows were cut and the
    # replacement started counting somewhere else.
    seqs = sorted(e["seq"] for e in after)
    row["seqs_contiguous"] = int(seqs == list(range(seqs[0], seqs[0] + len(seqs))))
    row["seqs_unique"] = int(len(seqs) == len(set(seqs)))

    record.note(f"rerun_turn probe: session={session} rows {row['rows_before']} → {row['rows_after']}")
    return row


# ---------------------------------------------------------------------------
# Probe 4 — is a branch a copy that leaves the original alone?
# ---------------------------------------------------------------------------


def probe_branch(record: RunRecord) -> dict[str, Any]:
    scenario, storyline = build_world(max_turns=3, suggestions=0, context_beats=14)
    row: dict[str, Any] = {"probe": "branch", "scenario": scenario, "storyline": storyline}

    session, _ = turn(scenario, None, FILLER[0])
    session, _ = turn(scenario, session, PLANT, guidance=PLANT_DIRECTION)

    source_before = events(scenario, session)
    parent_state = session_row(session)
    row["source_rows_before"] = len(source_before)
    row["parent_standing"] = len(parent_state.get("standingDirection") or [])

    fork_at = [e for e in source_before if e["type"] == "user_turn"][-1]
    fork = _request(
        "POST",
        f"/play/{scenario}/sessions/{session}/branch",
        {"atEventId": fork_at["id"], "name": "Probe fork"},
    )
    fork_id = fork["id"]

    source_after = events(scenario, session)
    fork_rows = events(scenario, fork_id)
    fork_state = session_row(fork_id)

    row["source_rows_delta"] = len(source_after) - len(source_before)
    row["fork_rows"] = len(fork_rows)
    row["seqs_identical"] = int(
        [e["seq"] for e in fork_rows] == [e["seq"] for e in source_before[: len(fork_rows)]]
    )
    row["ids_fresh"] = int(
        not ({e["id"] for e in fork_rows} & {e["id"] for e in source_before})
    )
    row["text_identical"] = int(
        [text_of(e) for e in fork_rows] == [text_of(e) for e in source_before[: len(fork_rows)]]
    )
    row["fork_standing"] = len(fork_state.get("standingDirection") or [])
    row["standing_inherited"] = int(row["fork_standing"] == row["parent_standing"])
    row["fork_summary_cleared"] = int(not fork_state.get("summaryText"))
    row["parent_recorded"] = int(fork.get("parentSessionId") == session)

    # The fork has to be playable, and playing it must not touch the parent.
    turn(scenario, fork_id, REACT)
    row["source_rows_after_fork_played"] = len(events(scenario, session))
    row["source_untouched_by_fork_play"] = int(
        row["source_rows_after_fork_played"] == len(source_before)
    )

    record.note(f"branch probe: source={session} fork={fork_id}")
    return row


# ---------------------------------------------------------------------------
# Probe 5 — does an edit reach the model, and whose lines can be edited?
# ---------------------------------------------------------------------------


def probe_edit(record: RunRecord) -> dict[str, Any]:
    scenario, storyline = build_world(max_turns=3, suggestions=0, context_beats=14)
    row: dict[str, Any] = {"probe": "edit", "scenario": scenario, "storyline": storyline}

    session, _ = turn(scenario, None, FILLER[0])
    rows = events(scenario, session)

    player_row = next(e for e in rows if e["type"] == "user_turn")
    new_player = "I set my cup down and say the name Corvin Ashgate out loud."
    edited = _patch(
        f"/play/{scenario}/sessions/{session}/beats/{player_row['id']}", {"text": new_player}
    )
    buffered = [str(b.get("text") or "") for b in buffer_entries(session)]
    row["player_row_text_matches"] = int((edited.get("data") or {}).get("text") == new_player)
    row["player_edited_flag"] = int(bool((edited.get("data") or {}).get("editedByPlayer")))
    row["player_buffer_text_matches"] = int(new_player in buffered)

    ai_row = next((e for e in rows if e["type"] in BUFFERED), None)
    if ai_row is None:
        row["ai_status"] = "inconclusive: the scene produced no AI prose beat"
    else:
        new_ai = "The lamp gutters, and nobody answers the name Corvin Ashgate."
        edited_ai = _patch(
            f"/play/{scenario}/sessions/{session}/beats/{ai_row['id']}", {"text": new_ai}
        )
        buffered = [str(b.get("text") or "") for b in buffer_entries(session)]
        row["ai_status"] = "ok"
        row["ai_row_type"] = ai_row["type"]
        row["ai_row_text_matches"] = int((edited_ai.get("data") or {}).get("text") == new_ai)
        row["ai_buffer_text_matches"] = int(new_ai in buffered)

    # The thought row is the one the frontend can mis-target (H4). Its behaviour behind the
    # API is recorded so the frontend finding is not the only evidence.
    thought = next((e for e in rows if e["type"] == "internal_thought"), None)
    row["thought_row_present"] = int(thought is not None)
    if thought is not None:
        try:
            frames = _stream(
                f"/play/{scenario}/sessions/{session}/beats/{thought['id']}/reroll",
                {"scope": "beat"},
            )
            row["thought_reroll_refused"] = int(
                any(f.get("type") == "error" for f in frames)
            )
        except urllib.error.HTTPError:
            row["thought_reroll_refused"] = 1
        edited_thought = _patch(
            f"/play/{scenario}/sessions/{session}/beats/{thought['id']}", {"text": "…"}
        )
        # The API accepts it — which is exactly why the frontend must not point Edit here.
        row["thought_edit_accepted"] = int(
            (edited_thought.get("data") or {}).get("text") == "…"
        )

    # A machinery beat has nothing to rewrite and must be refused, not silently ignored.
    machinery = next((e for e in rows if e["type"] == "state_update"), None)
    if machinery is not None:
        try:
            _patch(f"/play/{scenario}/sessions/{session}/beats/{machinery['id']}", {"text": "x"})
            row["machinery_edit_refused"] = 0
        except urllib.error.HTTPError as exc:
            row["machinery_edit_refused"] = int(exc.code == 422)

    record.note(f"edit probe: session={session}")
    return row


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

PROBES = {
    "rewind": probe_rewind,
    "reroll_beat": probe_reroll_beat,
    "rerun_turn": probe_rerun_turn,
    "branch": probe_branch,
    "edit": probe_edit,
}


def relay_models() -> dict[str, Any]:
    """What the relay is actually serving. Recorded because "skynet" is a route."""
    try:
        with urllib.request.urlopen(RELAY, timeout=10) as res:
            return json.load(res)
    except Exception as exc:  # pragma: no cover
        return {"error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=["baseline", "fixed"])
    parser.add_argument("--experiment", required=True, type=pathlib.Path)
    parser.add_argument(
        "--probes",
        default=",".join(PROBES),
        help="Comma-separated subset to run (default: all).",
    )
    parser.add_argument(
        "--replay-window",
        metavar="SCENARIO",
        help=(
            "Measure the replay window of an ALREADY-RUN scene's last character beat and "
            "exit. Costs no model calls, so a scene recorded by an earlier run can be "
            "re-read on the code as it stands now (ISSUES.md A-3)."
        ),
    )
    args = parser.parse_args()

    if args.replay_window:
        sessions = _get(f"/play/{args.replay_window}/sessions")["sessions"]
        session = sessions[0]["id"]
        rows = events(args.replay_window, session)
        target = next(
            e for e in reversed(rows)
            if e["type"] in ("character_prose", "character_dialogue")
        )
        out = {
            "scenario": args.replay_window, "session": session, "beat": target["id"],
            **replay_window_holds(args.replay_window, session, target["id"]),
        }
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    experiment = args.experiment
    if not experiment.exists():
        raise SystemExit(f"no such experiment folder: {experiment}")

    entrypoint = (
        "uv run python -m utils.scripts.research.run_record_controls "
        f"--arm {args.arm} --experiment {experiment}"
    )
    record = RunRecord(entrypoint=entrypoint)
    started = time.monotonic()

    models = relay_models()
    (experiment / "env").mkdir(parents=True, exist_ok=True)
    (experiment / "env" / f"relay-models-{args.arm}.json").write_text(
        json.dumps(models, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    selected = [p.strip() for p in args.probes.split(",") if p.strip()]
    for name in selected:
        probe = PROBES.get(name)
        if probe is None:
            raise SystemExit(f"unknown probe: {name}")
        print(f"[{args.arm}] {name} …", flush=True)
        try:
            row = probe(record)
        except Exception as exc:  # a crashed probe is recorded, never dropped
            row = {"probe": name, "status": f"crashed: {type(exc).__name__}: {exc}"}
            record.note(f"{name}: CRASHED — {type(exc).__name__}: {exc}")
        row["arm"] = args.arm
        record.add_run(row)
        print(json.dumps(row, indent=2, sort_keys=True), flush=True)

    record.wall_clock_seconds = time.monotonic() - started

    # Per-probe rows only. These measure five different mechanisms; a mean over them
    # would be a number about nothing, and the repository's rule about partially-failed
    # experiments forbids aggregating over survivors anyway.
    # Merge by probe rather than overwrite: a probe is often re-run on its own, and a
    # whole-file write would silently delete the four that were not asked for. A row that
    # is replaced moves to `superseded` — the contract is append-only, and a number that
    # was measured and then improved on is part of the record, not an embarrassment.
    out = experiment / "data" / f"metrics-{args.arm}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    previous: dict[str, Any] = {}
    if out.exists():
        previous = json.loads(out.read_text(encoding="utf-8"))
    kept = {r.get("probe"): r for r in previous.get("rows", [])}
    superseded = list(previous.get("superseded", []))
    for fresh in record.per_run:
        stale = kept.get(fresh.get("probe"))
        if stale is not None:
            superseded.append(stale)
        kept[fresh.get("probe")] = fresh
    out.write_text(
        json.dumps(
            {
                "arm": args.arm,
                "rows": [kept[k] for k in sorted(kept, key=str)],
                "superseded": superseded,
                "notes": [*previous.get("notes", []), *record.notes],
                "relay": models,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    existing = out
    write_metrics(experiment, record, {})
    write_environment(experiment, record)
    update_manifest(
        experiment,
        {
            "status": "running",
            "code": git_block(entrypoint),
            "compute": {
                "hardware": hardware(),
                "wall_clock_hours": round(record.wall_clock_seconds / 3600, 4),
                "estimated_cost_usd": 0.0,
            },
        },
    )
    print(f"\n[{args.arm}] wrote {existing}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
