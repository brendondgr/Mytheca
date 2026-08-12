"""Headless moment-image runner for EXP-2026-08-002.

Drives the in-narrative image pipeline (``services.scene_moment`` → ``agents.moment_agent``
→ ComfyUI) without the frontend, over a fixed scripted scene, and records what the
prompt writer actually produced.

The question this answers is narrow and checkable: does the moment prompt describe the
people in the shot **by appearance and action rather than by name**, and does the frame
come out **landscape**? Both are properties of the emitted prompt/image, countable with
no model in the loop and no human judgement.

The world is built in memory here (not read from the dev database) so the run is
reproducible on any machine: a fixed three-character scene with authored appearance
prose and a fixed transcript. The **LLM and ComfyUI are real** — that is the point; the
prompt is written by the configured model and rendered by the configured server, which
must both be reachable. Nothing under ``web/backend/app/`` is modified.

Usage::

    uv run python -m utils.scripts.research.run_moment --runs 3 \\
        --experiment docs/research/experiments/EXP-2026-08-002-moment-prompt-style
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import REPO_ROOT
from .record import RunRecord, aggregate, hardware, write_environment, write_metrics
from .record import update_manifest

BACKEND = REPO_ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# The scene under test. Fixed across runs — the arms (if any are ever added) must differ
# in the prompt policy, never in what they were asked to depict.
CAST = (
    {
        "id": "maerin",
        "name": "Maerin Voss",
        "role": "Harbor-mistress",
        "appearance": "Tall and composed, silver at the temples, salt-faded indigo coat.",
        "portrait_positive": (
            "middle-aged human woman, salt-stained indigo coat, silver-streaked dark hair, "
            "sharp eyes, watercolor portrait"
        ),
    },
    {
        "id": "doran",
        "name": "Captain Doran Hale",
        "role": "Harbor captain",
        "appearance": "Broad-shouldered, weathered, grey at the temples, in a naval coat.",
        "portrait_positive": (
            "broad-shouldered human man, weathered face, grey temples, dark naval coat with "
            "brass buttons, watercolor portrait"
        ),
    },
    {
        "id": "wren",
        "name": "Wren Calloway",
        "role": "Informant",
        "appearance": "Wiry and freckled, in a patched grey cloak.",
        "portrait_positive": (
            "wiry young human, freckled face, patched grey cloak, watercolor portrait"
        ),
    },
)

TRANSCRIPT = (
    ("narration", {"text": "Rain ticks against the shutters of the Saltworn's long room."}),
    ("character_dialogue", {"characterId": "maerin", "text": "Sit down, Captain. Before the whole room wonders why you're standing.", "done": True}),
    ("character_action", {"characterId": "doran", "text": "sets his glass down without drinking"}),
    ("character_dialogue", {"characterId": "doran", "text": "The harbor master's ledger is missing three pages, Voss.", "done": True}),
    ("character_action", {"characterId": "wren", "text": "leans in from the next table, low"}),
)

# Words too generic to prove a character's own look reached the prompt.
_STOP = {
    "watercolor", "portrait", "human", "young", "with", "and", "the", "face", "eyes",
    "coat", "hair", "man", "woman", "middle-aged",
}


def _configure_environment() -> None:
    """Graph + vector store off (both degrade to no-ops); LLM and ComfyUI stay real.

    Recorded as a deviation in the manifest: retrieval and graph context do not reach
    the moment prompt in this run. The prompt writer is not given either today, so the
    measurement is unaffected — but it is stated rather than assumed.
    """
    os.environ["NEO4J_URI"] = ""
    os.environ["QDRANT_URL"] = ""
    os.environ["EMBED_PROVIDER"] = "hash"


@contextmanager
def _world(media_dir: Path) -> Iterator[Any]:
    """An in-memory world with the scripted scene already played."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 — registers every table on Base.metadata
    from app.core.db import Base
    from app.events.stream import build_event
    from app.models import Character, PlaySession, Scenario, Setting, Storyline
    from app.services import events_store

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        db.add(Storyline(id="sl1", title="Embergate", genre="Maritime"))
        db.add(
            Setting(
                id="st1",
                storyline_id="sl1",
                name="The Saltworn",
                type="Social Hub",
                desc="A smoke-dark dockside tavern.",
                atmosphere="Lamplight, rain on the shutters, wet wool and tar.",
                current_state="Night; the shutters are barred.",
            )
        )
        for c in CAST:
            db.add(Character(storyline_id="sl1", **c))
        db.add(
            Scenario(
                id="sc1",
                storyline_id="sl1",
                title="The Missing Pages",
                genre="Maritime",
                tone="Tense",
                setting_id="st1",
                cast_ids=[c["id"] for c in CAST],
            )
        )
        db.add(PlaySession(id="ps1", scenario_id="sc1"))
        db.commit()
        for seq, (type_, data) in enumerate(TRANSCRIPT):
            events_store.persist_story_event(
                db, build_event(type_, data, scenario_id="sc1", session_id="ps1", seq=seq)
            )
        yield db
    finally:
        db.close()
        engine.dispose()


def _leaked_names(prompt: str) -> list[str]:
    """Every cast name form that survived into the positive prompt (should be none)."""
    found: list[str] = []
    for c in CAST:
        forms = {c["name"], *[t for t in c["name"].split() if len(t) >= 4]}
        for form in forms:
            if re.search(rf"\b{re.escape(form)}\b", prompt, re.IGNORECASE):
                found.append(form)
    return sorted(set(found))


def _appearance_coverage(prompt: str, character_ids: list[str]) -> float:
    """Fraction of in-frame characters whose OWN look reached the prompt.

    A character counts as covered when at least one distinctive token (>=5 characters,
    not a generic art word) from their authored appearance or portrait prompt appears in
    the positive prompt. Higher is better; 1.0 means every figure in the shot was
    described from their own record rather than invented.
    """
    if not character_ids:
        return 0.0
    low = prompt.lower()
    covered = 0
    for cid in character_ids:
        record = next((c for c in CAST if c["id"] == cid), None)
        if record is None:
            continue
        source = f"{record['appearance']} {record['portrait_positive']}".lower()
        tokens = {t for t in re.findall(r"[a-z-]{5,}", source) if t not in _STOP}
        if any(t in low for t in tokens):
            covered += 1
    return covered / len(character_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the in-narrative moment pipeline.")
    parser.add_argument("--runs", type=int, default=3, help="how many images to generate")
    parser.add_argument("--experiment", type=Path, default=None, help="experiment folder")
    parser.add_argument(
        "--comfy-url", default=None, help="ComfyUI base URL (default: the configured one)"
    )
    parser.add_argument("--llm-url", default=None, help="LLM base URL")
    parser.add_argument("--llm-model", default=None, help="LLM model id")
    args = parser.parse_args()

    _configure_environment()

    from PIL import Image

    from app.schemas.play import MomentRequest
    from app.schemas.settings import ComfyConfigUpdate, LlmConfigUpdate
    from app.services import scene_moment, settings_store

    media_dir = (
        args.experiment.resolve() / "data" / "images"
        if args.experiment
        else REPO_ROOT / "media" / "moments"
    )
    media_dir.mkdir(parents=True, exist_ok=True)
    scene_moment._moments_dir = lambda: media_dir  # noqa: SLF001 — the documented seam

    record = RunRecord(
        entrypoint=(
            f"uv run python -m utils.scripts.research.run_moment --runs {args.runs}"
            + (f" --experiment {args.experiment}" if args.experiment else "")
        )
    )
    rows: list[dict[str, Any]] = []
    started = time.monotonic()

    with _world(media_dir) as db:
        settings_store.update_llm(
            db,
            LlmConfigUpdate(
                base_url=args.llm_url or os.environ.get("MOMENT_LLM_URL", "http://localhost:4000/v1"),
                model=args.llm_model or os.environ.get("MOMENT_LLM_MODEL", "skynet"),
                api_key="",
            ),
        )
        settings_store.update_comfy(
            db,
            ComfyConfigUpdate(
                base_url=args.comfy_url
                or os.environ.get("COMFYUI_BASE_URL", "http://localhost:8199")
            ),
        )

        for index in range(args.runs):
            run_started = time.monotonic()
            row: dict[str, Any] = {"run": index, "error": ""}
            try:
                ctx = scene_moment.prepare_moment(db, "sc1", MomentRequest(session_id="ps1"))
                event = None
                for frame in scene_moment.generate_moment(db, ctx):
                    if getattr(frame, "type", "") == "scene_image":
                        event = frame
                if event is None:
                    raise RuntimeError("the stream ended with no scene_image event")

                prompt = event.data.prompt
                leaked = _leaked_names(prompt)
                path = media_dir / event.data.url.rsplit("/", 1)[1]
                with Image.open(path) as im:
                    width, height = im.size

                record.llm_calls += 1
                row.update(
                    {
                        "name_leak": int(bool(leaked)),
                        "leaked_forms": "|".join(leaked),
                        "landscape": int(width > height),
                        "width": width,
                        "height": height,
                        "appearance_coverage": round(
                            _appearance_coverage(prompt, list(event.data.character_ids)), 4
                        ),
                        "figures_in_frame": len(event.data.character_ids),
                        "phrases": len([p for p in prompt.split(",") if p.strip()]),
                        "image": path.name,
                        "prompt": prompt,
                        "caption": event.data.caption,
                    }
                )
            except Exception as exc:  # recorded, never swallowed
                row["error"] = f"{type(exc).__name__}: {exc}"
                record.note(f"run={index}: {row['error']}")
            row["wall_clock_seconds"] = round(time.monotonic() - run_started, 3)
            rows.append(row)
            print(
                f"run {index}: "
                + (row["error"] or f"{row['width']}x{row['height']} leak={row['name_leak']} "
                   f"coverage={row['appearance_coverage']}")
            )

    record.wall_clock_seconds = time.monotonic() - started
    record.per_run = rows
    failures = [r for r in rows if r["error"]]
    print(f"\n{len(rows)} run(s), {len(failures)} failed, {record.wall_clock_seconds:.1f}s")

    if args.experiment is None:
        print(json.dumps(rows, indent=2))
        return 1 if failures else 0

    experiment = args.experiment.resolve()
    # A survivorship-biased aggregate is worse than no number (see EXP-2026-08-001).
    if failures:
        values: dict[str, Any] = {}
        record.note(
            f"{len(failures)}/{len(rows)} runs failed; metrics.values left empty rather than "
            "aggregated over the surviving rows, which are not a random subsample"
        )
    else:
        values = aggregate(
            rows, ["name_leak", "landscape", "appearance_coverage", "phrases", "wall_clock_seconds"]
        )

    write_metrics(experiment, record, values)
    write_environment(experiment, record)
    update_manifest(
        experiment,
        {
            "status": "complete" if rows and not failures else "failed",
            "n_runs": len(rows),
            "compute": {
                "hardware": hardware(),
                "wall_clock_hours": round(record.wall_clock_seconds / 3600, 4),
                "estimated_cost_usd": 0.0,
            },
            "metrics": {"primary": "name_leak" if values else None, "values": values},
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
