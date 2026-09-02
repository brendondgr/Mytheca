"""Memory smoke test — play a scene, then read back what the cast actually kept.

**Why this exists.** The suite proves a memory that reaches ``memory_store`` is stored,
deduplicated and scoped correctly. It cannot prove the memories are *worth having*, because
they come from a model and no unit test ever reads one. A store full of "the conversation
continued" would pass every test in the repository and make every downstream phase —
recall, cues, disclosure — machinery for retrieving mush.

So this drives the **real** engine over HTTP against a **real** model, plays a few turns,
then reads ``character_memories`` straight out of the database and prints what the cast
came away with: whose memory, how much it mattered, the verbatim line they kept, what they
think it was about. Then it reports the four things worth deciding on.

    # the fast path — assumes a backend is already up on 3345
    uv run python -m utils.scripts.memory_smoke

    # against a backend started from a worktree on another port
    uv run python -m utils.scripts.memory_smoke --api http://localhost:3355/api

    # keep the world to poke at it
    uv run python -m utils.scripts.memory_smoke --turns 4 --keep

**This is the checkpoint gate for `docs/plans/character-memory-graph.md` Phase 3.** Read the
output before building recall on top of it. Continue if memories are specific, differ
between characters, and carry verified quotes; if they are vague, near-identical across the
cast, or quote-less, do Phase 3b (split the memory write into its own agent) first.

**This is not a research experiment.** n=1, no arms, recorded nowhere. Anything that
produces a number worth quoting belongs in ``docs/research/experiments/`` under
``docs/research/AGENT_INSTRUCTIONS.md``. Do not cite this script's output as a measurement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))
sys.path.insert(0, str(REPO_ROOT))

from utils.scripts.scene_smoke import Api, DEFAULT_API, beats_from, errors_from  # noqa: E402

#: A cast built so the turns below can hurt somebody. Memory needs stakes the way the
#: prose harness needs a crowded room — a scene where nothing costs anything produces
#: nothing worth carrying, and would fail this check for the wrong reason.
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


def build_world(api: Api) -> tuple[str, str, dict[str, str]]:
    storyline = api.post(
        "/storylines",
        {
            "title": "Memory Smoke",
            "genre": "grim maritime",
            "premise": "A flooded cargo tunnel under a harbour town, and the debts it leaves.",
        },
    )["id"]
    cast: dict[str, str] = {}
    for name, role in CAST:
        cast[api.post(f"/storylines/{storyline}/characters", {"name": name, "role": role})["id"]] = name
    setting = api.post(
        f"/storylines/{storyline}/settings",
        {
            "name": "The Flooded Tunnel",
            "desc": "A brick service tunnel under the harbour, filling fast with cold water.",
        },
    )["id"]
    scenario = api.post(
        f"/storylines/{storyline}/scenarios",
        {
            "title": "The Choice",
            "castIds": list(cast),
            "settingId": setting,
            "suggestionsCount": 0,
        },
    )["id"]
    return storyline, scenario, cast


def read_memories(storyline_id: str) -> list[dict]:
    """Read the rows straight from Postgres — there is no read endpoint until Phase 7."""
    from app.core.db import SessionLocal
    from app.models import Character, CharacterMemory

    db = SessionLocal()
    try:
        names = {c.id: c.name for c in db.query(Character).filter(
            Character.storyline_id == storyline_id
        ).all()}
        rows = db.query(CharacterMemory).filter(
            CharacterMemory.storyline_id == storyline_id
        ).order_by(CharacterMemory.turn_seq, CharacterMemory.salience.desc()).all()
        return [
            {
                "who": names.get(r.character_id, r.character_id),
                "turn": r.turn_seq,
                "salience": r.salience,
                "valence": r.valence,
                "gloss": r.gloss,
                "quote": r.quote,
                "quoteSpeaker": names.get(r.quote_speaker_id or "", r.quote_speaker_id),
                "subjects": list(r.subjects or []),
                "reinforcements": r.reinforcements,
            }
            for r in rows
        ]
    finally:
        db.close()


def render(mem: dict) -> str:
    head = (
        f"  \033[1m{mem['who'].upper()}\033[0m "
        f"\033[2m(turn {mem['turn']} · salience {mem['salience']:.2f}"
        f"{' · ' + mem['valence'] if mem['valence'] else ''}"
        f"{' · reinforced ×' + str(mem['reinforcements']) if mem['reinforcements'] else ''})\033[0m"
    )
    lines = [head, f"    {mem['gloss']}"]
    if mem["quote"]:
        lines.append(f"    \033[36m“{mem['quote']}”\033[0m — {mem['quoteSpeaker'] or 'someone'}")
    else:
        lines.append("    \033[2m(no verified quote)\033[0m")
    lines.append(f"    \033[2msubjects: {', '.join(mem['subjects']) or '—'}\033[0m")
    return "\n".join(lines)


def sameness(memories: list[dict]) -> float:
    """Highest gloss similarity between two *different* characters. High = samey.

    The failure this checkpoint exists to catch: one model writing the same paragraph three
    times with the pronouns changed. Uses the engine's own comparison so "these are the same
    memory" means here exactly what it means to the deduplicator.
    """
    from app.services.memory_store import _same_moment
    from difflib import SequenceMatcher

    worst = 0.0
    for i, a in enumerate(memories):
        for b in memories[i + 1:]:
            if a["who"] == b["who"]:
                continue
            worst = max(worst, SequenceMatcher(None, a["gloss"].lower(), b["gloss"].lower()).ratio())
            if _same_moment(a["gloss"], b["gloss"]):
                worst = max(worst, 1.0)
    return worst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=DEFAULT_API, help=f"API base (default {DEFAULT_API})")
    ap.add_argument("--turns", type=int, default=3, help="player turns to play (default 3)")
    ap.add_argument("--keep", action="store_true", help="do not delete the world afterwards")
    ap.add_argument("--json", action="store_true", help="emit the findings as JSON too")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    api = Api(args.api)
    storyline, scenario, cast = build_world(api)
    print(f"world: storyline={storyline} scenario={scenario} cast={', '.join(cast.values())}\n")

    session: str | None = None
    beats_seen = 0
    broken: list[str] = []
    try:
        for i, direction in enumerate(TURNS[: max(1, args.turns)], start=1):
            print(f"\033[1m── turn {i} ─ direction:\033[0m {direction}")
            payload: dict = {"text": direction}
            if session:
                payload["sessionId"] = session
            frames = api.stream(f"/play/{scenario}/turn", payload)
            for frame in frames:
                session = session or (frame.get("sessionId") or None)
            for err in errors_from(frames):
                print(f"  \033[31mERROR FRAME\033[0m {err}")
                broken.append(f"turn {i}: {err}")
            beats = beats_from(frames)
            beats_seen += len(beats)
            if not beats:
                broken.append(f"turn {i}: produced no prose at all")
            print(f"  {len(beats)} beat(s)\n")

        # Reflection is dispatched at the turn's tail and may be on a background thread.
        print("\033[2mreading memories…\033[0m\n")
        memories = read_memories(storyline)
    finally:
        if args.keep:
            print(f"kept: {args.api.rsplit('/api', 1)[0]}/{storyline}/{scenario}")
        else:
            api.delete(f"/storylines/{storyline}")

    print("─" * 68)
    for mem in memories:
        print(render(mem))
        print()

    print("─" * 68)
    turns_played = min(len(TURNS), max(1, args.turns))
    quoted = [m for m in memories if m["quote"]]
    subjects = {t for m in memories for t in m["subjects"]}
    overlap = sameness(memories)
    per_character = {m["who"] for m in memories}

    print(f"{beats_seen} beat(s) over {turns_played} turn(s) → {len(memories)} memory(s)")
    print(f"  written per turn      {len(memories) / turns_played:.1f}")
    print(f"  with a verified quote {len(quoted)}/{len(memories)}"
          + ("" if memories else "  (nothing to judge)"))
    print(f"  distinct subjects     {len(subjects)}  {sorted(subjects)}")
    print(f"  characters with any   {len(per_character)}/{len(cast)}")
    print(f"  worst cross-character gloss similarity  {overlap:.2f}")
    print()
    print("\033[1mCheckpoint — decide before building recall (plan Phase 3, step 8):\033[0m")
    print("  · Are the glosses specific enough that you could tell which turn each came from?")
    print("  · Do two characters' memories of the same turn actually differ?")
    print("  · Did the quotes survive verification, or is that column mostly empty?")
    print("  · Is 'written per turn' plausible, or is every shrug being kept?")
    print("  A low quote rate is ambiguous: no quotable line was said, OR quotes were")
    print("  composed and rejected. The engine logs each rejection at DEBUG under")
    print("  'mytheca.memory' — check there before concluding which.")
    if args.json:
        print(json.dumps({"memories": memories, "beats": beats_seen, "broken": broken}, indent=2))

    # The *judgement* is the reader's, so a run that produced real memories always exits 0
    # however thin they look — that call is not this script's to make. A run that produced no
    # prose at all is a different thing entirely, and must not read as "the cast remembered
    # nothing". The first version of this script exited 0 on three turns of
    # "Choose a model in Options first", printing a tidy table of zeroes underneath.
    if broken:
        print()
        print(f"\033[31m{len(broken)} turn(s) never ran — nothing above is about memory:\033[0m")
        for line in broken:
            print(f"  \033[31m✗ {line}\033[0m")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
