"""Headless two-arm scene runner for EXP-2026-08-001.

Drives Mytheca's turn loop without the frontend, under one of two beat-selection
policies, and records turn-structure metrics.

**Arm A — `planner`**  the shipped ReAct per-beat planner (`planner_agent.next_beat`).
**Arm B — `director`** the superseded one-shot speaker-set decision
(`director_agent.who_is_up`), which is still in the repository, still tested, and has
never been compared against its replacement.

Why this is the cheapest real experiment available: both arms already exist. Arm B is
not a strawman written for the occasion — it is the design that actually shipped
first, replaced deliberately, with no measurement taken either way.

**No file under ``web/backend/app/`` is modified.** Arm B is installed by substituting
``planner_agent.next_beat`` with a shim that replays a one-shot ``who_is_up`` decision
as a sequence of beats. Everything downstream — emission parsing, the validator, the
presence fold, the consistency guard, the narrator — is byte-identical between arms,
so the measured difference is attributable to beat selection and nothing else.

Usage::

    uv run python -m utils.scripts.research.run_scene --arm planner --seeds 0,1,2
    uv run python -m utils.scripts.research.run_scene --arm both --seeds 0,1,2 \\
        --experiment docs/research/experiments/EXP-2026-08-001-planner-vs-oneshot-director
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from . import REPO_ROOT

# The backend package lives under web/backend and is not installed; mirror what
# `[tool.pytest.ini_options] pythonpath` does for the test suite.
BACKEND = REPO_ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

ARMS = ("planner", "director")

# The player turns driving each scene. Fixed and identical across arms — the arms must
# differ only in beat selection, never in what they were asked. Chosen to exercise the
# structural properties under test: an open address to the group, a directed question,
# and a follow-up that a bystander could plausibly hijack.
SCRIPT: tuple[dict[str, Any], ...] = (
    {"text": "I need to know who moved the cargo last night. All of you.", "directed_at": None},
    {"text": "Wren — you were on the quay. What did you see?", "directed_at": "wren"},
    {"text": "That doesn't add up. Someone else was there.", "directed_at": None},
)


@dataclass
class TurnMetrics:
    """Structural properties of one turn. Every field is countable from the emitted
    event stream plus the request — no judgement, no model in the loop."""

    beats: int = 0
    character_beats: int = 0
    narrator_beats: int = 0
    speakers: list[str] = field(default_factory=list)
    directed_at: str | None = None
    addressed_responded: bool | None = None
    bystander_first: bool | None = None
    wall_clock_seconds: float = 0.0
    error: str | None = None


def _configure_environment() -> None:
    """Run against in-memory SQLite with the graph and vector store disabled.

    This mirrors the test harness (`utils/tests/backend/conftest.py`) rather than
    production. **That is a deviation and it is recorded in the manifest**: Neo4j and
    Qdrant degrade to no-ops by design, so the turn loop runs, but any measurement
    that depends on graph relationship context or retrieved lore is not comparable to
    a production run. The metrics here are turn-structure only, which the loop
    produces identically either way.
    """
    os.environ["NEO4J_URI"] = ""
    os.environ["QDRANT_URL"] = ""
    os.environ["EMBED_PROVIDER"] = "hash"


@contextmanager
def _database() -> Iterator[Any]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 — registers every table on Base.metadata
    from app.core.db import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@contextmanager
def _director_arm() -> Iterator[None]:
    """Install the one-shot director as the beat-selection policy.

    The shim asks ``who_is_up`` once per turn (on the first call, when nothing has
    acted yet), then hands back its ordered speaker list one beat at a time and ends
    the turn. That is precisely the superseded behaviour: a speaker *set* decided up
    front, capped at 3, with no re-decision after each beat and no narrator
    interstitials chosen mid-turn.
    """
    from app.agents import director_agent, planner_agent
    from app.agents.planner_agent import BeatDecision

    original = planner_agent.next_beat
    plan: dict[str, list[str]] = {}

    def one_shot_next_beat(db, ctx, intent, turn_beats, acted, **kwargs):
        locked_id = kwargs.get("locked_id")
        key = id(ctx)

        if key not in plan:
            decision = director_agent.who_is_up(db, ctx)
            plan[key] = [s for s in decision.speakers if s != locked_id]

        remaining = [s for s in plan[key] if s not in set(acted)]
        if not remaining:
            return BeatDecision("end", reason="one-shot plan exhausted")
        return BeatDecision(
            "speak",
            actor_id=remaining[0],
            addressing_id=ctx.directed_at,
            reason="one-shot director plan",
        )

    planner_agent.next_beat = one_shot_next_beat
    try:
        yield
    finally:
        planner_agent.next_beat = original


def _seed_world(db) -> Any:
    from app.core import seed
    from app.services import crud

    seed.seed_if_empty(db)
    db.commit()
    scenarios = crud.list_scenarios(db, seed.SEED_STORYLINE_ID)
    if not scenarios:
        raise RuntimeError("seed produced no scenario — cannot run a scene")
    return scenarios[0]


def _run_one_turn(db, scenario, session_id: str | None, step: dict[str, Any]) -> tuple[TurnMetrics, str | None]:
    from app.schemas.play import TurnRequest
    from app.services import turn_engine

    metrics = TurnMetrics(directed_at=step["directed_at"])
    req = TurnRequest(
        session_id=session_id,
        text=step["text"],
        directed_at=step["directed_at"],
    )

    started = time.monotonic()
    seen_ids: set[tuple[str, int]] = set()
    try:
        scenario = turn_engine.validate_turn_inputs(db, scenario.id, req)
        for event in turn_engine.run_turn(db, scenario, req):
            payload = event.model_dump() if hasattr(event, "model_dump") else dict(event)
            etype = payload.get("type")
            # Delta streaming re-emits the same (id, seq) with growing text, so a beat
            # must be counted once, on first sight, not once per frame.
            key = (str(payload.get("id")), int(payload.get("seq", -1)))
            if key in seen_ids:
                continue
            seen_ids.add(key)

            if etype in ("character_dialogue", "character_action"):
                metrics.character_beats += 1
                metrics.beats += 1
                speaker = payload.get("characterId") or payload.get("character_id")
                if speaker:
                    metrics.speakers.append(str(speaker))
            elif etype == "narration":
                metrics.narrator_beats += 1
                metrics.beats += 1
    except Exception as exc:  # noqa: BLE001 — a failed turn is data, not a crash
        metrics.error = f"{type(exc).__name__}: {exc}"
    metrics.wall_clock_seconds = time.monotonic() - started

    if metrics.directed_at:
        metrics.addressed_responded = metrics.directed_at in metrics.speakers
        # Did an unaddressed character take the first beat? This is the failure the
        # per-beat planner is supposed to avoid and the one-shot director's
        # "addressed" fast path also avoids — so agreement here would itself be a
        # finding.
        metrics.bystander_first = bool(
            metrics.speakers and metrics.speakers[0] != metrics.directed_at
        )

    return metrics, session_id


def run_arm(arm: str, seed_value: int) -> list[TurnMetrics]:
    """Run the full scripted scene once, under one arm, at one seed."""
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}, got {arm!r}")

    random.seed(seed_value)
    results: list[TurnMetrics] = []

    with _database() as db:
        scenario = _seed_world(db)
        session_id: str | None = None

        arm_context = _director_arm() if arm == "director" else _null_context()
        with arm_context:
            for step in SCRIPT:
                metrics, session_id = _run_one_turn(db, scenario, session_id, step)
                results.append(metrics)
                if session_id is None:
                    # The first turn opens the session; pick it up for the rest so the
                    # scene is continuous rather than three disconnected turns.
                    from app.services import events_store

                    sessions = events_store.list_sessions(db, scenario.id)
                    if sessions:
                        session_id = sessions[0].id

    return results


@contextmanager
def _null_context() -> Iterator[None]:
    yield


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=(*ARMS, "both"), default="both")
    parser.add_argument("--seeds", default="0,1,2", help="comma-separated seeds")
    parser.add_argument(
        "--experiment",
        type=Path,
        default=None,
        help="experiment folder to write manifest/metrics into (omit for a dry run)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="one seed, one turn — checks the harness wires up without spending a run",
    )
    args = parser.parse_args(argv)

    _configure_environment()

    seeds = [0] if args.smoke else [int(s) for s in args.seeds.split(",") if s.strip()]
    arms = list(ARMS) if args.arm == "both" else [args.arm]

    from .record import RunRecord, aggregate, update_manifest, write_environment, write_metrics

    record = RunRecord(
        entrypoint=f"uv run python -m utils.scripts.research.run_scene "
        f"--arm {args.arm} --seeds {args.seeds}"
    )

    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    for arm in arms:
        for seed_value in seeds:
            print(f"running arm={arm} seed={seed_value} ...", flush=True)
            turns = run_arm(arm, seed_value)
            if args.smoke:
                turns = turns[:1]
            for index, turn in enumerate(turns):
                if turn.error:
                    record.note(f"arm={arm} seed={seed_value} turn={index}: {turn.error}")
                rows.append(
                    {
                        "arm": arm,
                        "seed": seed_value,
                        "turn": index,
                        "beats": turn.beats,
                        "character_beats": turn.character_beats,
                        "narrator_beats": turn.narrator_beats,
                        "distinct_speakers": len(set(turn.speakers)),
                        "addressed_responded": (
                            "" if turn.addressed_responded is None
                            else int(turn.addressed_responded)
                        ),
                        "bystander_first": (
                            "" if turn.bystander_first is None else int(turn.bystander_first)
                        ),
                        "wall_clock_seconds": round(turn.wall_clock_seconds, 3),
                        "error": turn.error or "",
                    }
                )
    record.wall_clock_seconds = time.monotonic() - started
    record.per_run = rows

    failures = [r for r in rows if r["error"]]
    print()
    print(f"{len(rows)} turn(s), {len(failures)} failed, {record.wall_clock_seconds:.1f}s")
    if failures:
        print("first failure:", failures[0]["error"], file=sys.stderr)

    if args.experiment is None:
        print(json.dumps(rows, indent=2))
        return 1 if failures else 0

    experiment = args.experiment.resolve()
    usable = [r for r in rows if not r["error"]]

    # A survivorship-biased aggregate is worse than no number. If ANY turn failed, the
    # surviving rows are not a random subsample — here, a missing LLM endpoint kills
    # every director-arm turn while leaving the planner arm's non-LLM fallback beat
    # intact, so aggregating the survivors yields a clean-looking mean over one arm's
    # heuristic. Publish per-run rows and totals, publish no aggregate.
    if failures:
        values: dict[str, Any] = {}
        record.note(
            f"{len(failures)}/{len(rows)} turns failed; metrics.values left empty rather than "
            "aggregated over the surviving rows, which are not a random subsample"
        )
    else:
        values = aggregate(usable, ["beats", "character_beats", "distinct_speakers"])

    write_metrics(experiment, record, values)
    write_environment(experiment, record)
    update_manifest(
        experiment,
        {
            "status": "complete" if usable and not failures else "failed",
            "seeds": seeds,
            "n_runs": len(rows),
            "compute": {
                "hardware": __import__(
                    "utils.scripts.research.record", fromlist=["hardware"]
                ).hardware(),
                "wall_clock_hours": round(record.wall_clock_seconds / 3600, 4),
                "estimated_cost_usd": 0.0,
            },
            "metrics": {"primary": "beats" if values else None, "values": values},
        },
    )
    if record.notes:
        print("\nnotes for ISSUES.md:")
        for note in record.notes:
            print(f"  - {note}")
    print(f"wrote metrics into {experiment}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
