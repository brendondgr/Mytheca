"""Two-arm runner for EXP-2026-09-002 — does episodic recall cause verbatim callbacks?

Plays a fixed scene through the real engine against the real model, once per arm, and
computes the metrics fixed in ``PROTOCOL.md`` **from the persisted rows** rather than from
the stream — so the numbers are exactly what a reload would show.

The arms differ only in ``MEMORY_RECALL_ENABLED``, which means they must be two backend
processes: the setting is read through a process-global ``get_settings()``. The runner does
not start them; it is pointed at one and told which arm it is talking to.

    # arm off — a backend started with MEMORY_RECALL_ENABLED=false
    uv run python -m utils.scripts.research.run_memory_callback \\
        --arm off --api http://localhost:3357/api --run 1

    # arm on
    uv run python -m utils.scripts.research.run_memory_callback \\
        --arm on --api http://localhost:3355/api --run 1

Each invocation appends one row to ``data/runs.jsonl`` in the experiment folder. Nothing
here computes an aggregate: with two runs per arm an aggregate would imply a distribution
that has not been measured (see ``EXP-2026-08-001``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
sys.path.insert(0, str(REPO_ROOT))

from utils.scripts.scene_smoke import Api, errors_from  # noqa: E402

EXPERIMENT = REPO_ROOT / "docs/research/experiments/EXP-2026-09-002-character-memory-callback-rerun"

#: Held identical across arms and runs, so the only difference is the treatment.
CAST = [
    ("Dell", "a runner who nearly drowned in the tunnels last winter"),
    ("Mara", "a cargo master who has had to choose before"),
    ("Kell", "a quartermaster who keeps everyone's ledger, including the moral one"),
]
TURNS = [
    "The water is rising in the tunnel and the crates are still on the platform. "
    "Mara has to choose between the cargo and helping Dell, who is trapped under a beam.",
    "Dell surfaces. He says nothing at first.",
    "Kell arrives and asks what happened down there.",
    "Mara defends the choice she made.",
]

#: A span shorter than this is a phrase two people could reach independently ("I know",
#: "the water"). Long enough that a match is reuse rather than coincidence.
MIN_SPAN = 20

#: A second, looser threshold recorded alongside the primary — declared before the first
#: run, not chosen after seeing one. A null primary has two very different explanations
#: ("no callbacks happened" vs "callbacks happened and were shorter than 20 characters"),
#: and without this the write-up could not tell them apart.
MIN_SPAN_LOOSE = 12


def build_world(api: Api) -> tuple[str, str]:
    storyline = api.post(
        "/storylines",
        {
            "title": "EXP-2026-09-002",
            "genre": "grim maritime",
            "premise": "A flooded cargo tunnel under a harbour town, and the debts it leaves.",
        },
    )["id"]
    cast = [
        api.post(f"/storylines/{storyline}/characters", {"name": n, "role": r})["id"]
        for n, r in CAST
    ]
    setting = api.post(
        f"/storylines/{storyline}/settings",
        {"name": "The Flooded Tunnel", "desc": "A brick service tunnel under the harbour."},
    )["id"]
    scenario = api.post(
        f"/storylines/{storyline}/scenarios",
        {"title": "The Choice", "castIds": cast, "settingId": setting, "suggestionsCount": 0},
    )["id"]
    return storyline, scenario


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower()


def measure(session_id: str) -> dict:
    """Compute the protocol's metrics from the persisted rows."""
    from app.core.db import SessionLocal
    from app.models import CharacterMemory, Event, TurnTrace
    from app.services.prose_guards import quoted_spans

    db = SessionLocal()
    try:
        events = (
            db.query(Event).filter(Event.session_id == session_id).order_by(Event.seq).all()
        )
        # Turn boundaries: a `user_turn` opens each turn, so a beat's turn is the number of
        # user_turn rows at or before it.
        turn_of: dict[str, int] = {}
        turn = 0
        beats: list[tuple[str, int, str]] = []  # (event_id, turn, text)
        for row in events:
            if row.type == "user_turn":
                turn += 1
            turn_of[row.id] = turn
            if row.type in ("character_prose", "character_dialogue"):
                beats.append((row.id, turn, str((row.data or {}).get("text") or "")))

        callbacks: list[dict] = []
        callbacks_loose: list[dict] = []
        eligible = 0
        for event_id, beat_turn, text in beats:
            if beat_turn <= 1:
                continue  # nothing earlier to call back to
            eligible += 1
            earlier = _norm(" || ".join(t for _i, tn, t in beats if tn < beat_turn))
            hit = loose_hit = None
            for span in quoted_spans(text):
                needle = _norm(span)
                if len(needle) < MIN_SPAN_LOOSE or needle not in earlier:
                    continue
                row = {"eventId": event_id, "turn": beat_turn, "span": span}
                loose_hit = loose_hit or row
                if len(needle) >= MIN_SPAN:
                    hit = hit or row
            if hit:
                callbacks.append(hit)
            if loose_hit:
                callbacks_loose.append(loose_hit)

        traces = (
            db.query(TurnTrace)
            .filter(TurnTrace.session_id == session_id, TurnTrace.step == "memory")
            .all()
        )
        surfaced = [m for t in traces for m in ((t.data or {}).get("memories") or [])]
        with_cues = [m for m in surfaced if m.get("cues")]
        # The mechanism check. A quote cannot be called back if none was offered, so a null
        # primary alongside a low `quote_offer_share` says the write path is the constraint,
        # not the model's willingness to reuse a line.
        with_quote = [m for m in surfaced if m.get("quoted")]
        turns_played = max(0, turn)
        memories = db.query(CharacterMemory).filter(
            CharacterMemory.session_id == session_id
        ).count()

        return {
            "turns": turns_played,
            "character_beats": len(beats),
            "eligible_beats": eligible,
            "callbacks": len(callbacks),
            "verbatim_callback_rate": round(len(callbacks) / eligible, 4) if eligible else None,
            "callbacks_loose": len(callbacks_loose),
            "verbatim_callback_rate_loose": (
                round(len(callbacks_loose) / eligible, 4) if eligible else None
            ),
            "recall_turns": len(traces),
            "recall_fire_rate": round(len(traces) / max(1, turns_played - 1), 4),
            "memories_surfaced": len(surfaced),
            "cue_share": round(len(with_cues) / len(surfaced), 4) if surfaced else None,
            "quote_offer_share": round(len(with_quote) / len(surfaced), 4) if surfaced else None,
            "memories_written": memories,
            "memories_per_turn": round(memories / turns_played, 4) if turns_played else None,
            "callback_examples": callbacks[:5],
            "callback_examples_loose": callbacks_loose[:5],
        }
    finally:
        db.close()


def archive(session_id: str, arm: str, run: int) -> str:
    """Write the whole play-through to a file, so deleting the world costs the record nothing.

    **A dev database is not a research record.** The first version of this runner kept its
    worlds so the rows behind every number stayed readable, which was the right instinct
    aimed at the wrong place: it left a growing pile of throwaway storylines in the author's
    library, and it was fragile besides — one of `EXP-2026-09-001`'s four worlds had already
    been deleted by the time anyone looked. A file under `data/sessions/` is the artifact
    that actually satisfies the contract.

    Carries the app's own session export (`session_export.render_json`, so a run reads the
    way an exported scene does) plus the `character_memories` rows, which that exporter has
    no reason to know about and which are the whole subject here.
    """
    from app.core.db import SessionLocal
    from app.models import Character, CharacterMemory, Event, PlaySession, Scenario, TurnTrace
    from app.services import session_export

    db = SessionLocal()
    try:
        session = db.get(PlaySession, session_id)
        scenario = db.get(Scenario, session.scenario_id)
        events = db.query(Event).filter(Event.session_id == session_id).order_by(Event.seq).all()
        traces = (
            db.query(TurnTrace)
            .filter(TurnTrace.session_id == session_id)
            .order_by(TurnTrace.turn, TurnTrace.n)
            .all()
        )
        names = {c.id: c.name for c in db.query(Character).all()}
        memories = [
            {
                "id": m.id, "character": names.get(m.character_id, m.character_id),
                "turnSeq": m.turn_seq, "gloss": m.gloss, "quote": m.quote,
                "quoteSpeaker": names.get(m.quote_speaker_id or "", m.quote_speaker_id),
                "salience": m.salience, "valence": m.valence,
                "subjects": list(m.subjects or []), "reinforcements": m.reinforcements,
            }
            for m in db.query(CharacterMemory)
            .filter(CharacterMemory.session_id == session_id)
            .order_by(CharacterMemory.turn_seq)
            .all()
        ]
        payload = json.loads(session_export.render_json(scenario, session, events, traces, names))
        payload["characterMemories"] = memories
    finally:
        db.close()

    out = EXPERIMENT / "data" / "sessions" / f"{arm}-{run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return str(out.relative_to(EXPERIMENT))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=["on", "off"])
    ap.add_argument("--api", required=True)
    ap.add_argument("--run", type=int, required=True)
    ap.add_argument("--turns", type=int, default=len(TURNS))
    ap.add_argument(
        "--keep-world",
        action="store_true",
        help="Leave the throwaway storyline in the library afterwards. Off by default: the "
        "run is archived to data/sessions/ first, so the record survives the teardown and "
        "the author's library does not fill up with scaffolding.",
    )
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    api = Api(args.api)
    storyline, scenario = build_world(api)
    print(f"[{args.arm}#{args.run}] storyline={storyline} scenario={scenario}")

    session: str | None = None
    broken: list[str] = []
    try:
        for i, direction in enumerate(TURNS[: args.turns], start=1):
            payload: dict = {"text": direction}
            if session:
                payload["sessionId"] = session
            frames = api.stream(f"/play/{scenario}/turn", payload)
            for frame in frames:
                session = session or (frame.get("sessionId") or None)
            errs = errors_from(frames)
            broken.extend(f"turn {i}: {e}" for e in errs)
            print(f"[{args.arm}#{args.run}] turn {i} done ({len(errs)} error frame(s))")
        row = measure(session or "")
        # Archive BEFORE the teardown, and let a failure to archive stop the teardown: a
        # world deleted with nothing written out is a run that happened and cannot be read.
        row["archive"] = archive(session or "", args.arm, args.run)
    finally:
        if not args.keep_world:
            api.delete(f"/storylines/{storyline}")

    row.update({
        "arm": args.arm, "run": args.run, "sessionId": session,
        "storylineId": storyline, "scenarioId": scenario, "broken": broken,
    })
    out = EXPERIMENT / "data" / "runs.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    print(json.dumps(row, indent=2))
    # A run whose turns errored is not a measurement; it must not be read as a zero.
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
