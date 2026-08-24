"""Scene smoke test — build a throwaway world, play it, and read the prose back.

**Why this exists.** The suite proves the code does what it was written to do. It cannot
prove the scene reads correctly, because the prose comes from a model and no unit test ever
sees a word of it. Every point-of-view defect this repository has fixed — "the player" in
72 % of beats (`EXP-2026-08-008`), the cast addressing a player who is not in the room — was
invisible to a green suite and obvious the moment somebody read an actual turn.

So this drives the **real** engine, over HTTP, against a **real** model, and checks the
output the way a reader would. It builds its own storyline, cast, setting and scenario, plays
one or two turns, prints every beat with who wrote it, and scores each one against the rules
the prompts are supposed to enforce. Then it deletes the world again, so running it does not
silt up the library.

The checks are imported from ``app.services.emission`` rather than reimplemented here. That
is the whole point: the harness and the engine's own guards cannot disagree about what a
violation is, because there is one definition of each.

    # the fast path — assumes a backend is already up on 3345
    uv run python -m utils.scripts.scene_smoke

    # against a backend you started from a worktree on another port
    uv run python -m utils.scripts.scene_smoke --api http://localhost:3355/api

    # keep the world to look at it in the UI, and play more of it
    uv run python -m utils.scripts.scene_smoke --turns 3 --keep

Exit code is 1 if any check fails, so it works as a gate.

**This is not a research experiment.** It is a pass/fail smoke test with n=1 and no arms,
recorded nowhere. Anything that produces a *number worth quoting* — a rate, a comparison
between two versions — belongs in ``docs/research/experiments/`` under
``docs/research/AGENT_INSTRUCTIONS.md``, and `utils/scripts/research/` is where those runners
live. Do not cite this script's output as a measurement.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.services import emission  # noqa: E402

DEFAULT_API = "http://localhost:3345/api"

#: The cast. Three, because two cannot demonstrate a cross-speaker leak (with one other
#: character in the room, "someone else spoke" and "the wrong person spoke" look the same),
#: and because the second-person defect needs a scene busy enough to tempt the model into
#: addressing somebody.
CAST = [
    ("Lily", "a street singer who talks her way out of things"),
    ("Zoe", "a harbour-watch sergeant who does not"),
    ("Aldous", "an archivist who knows what both of them owe"),
]

#: Player lines, in Playwright mode — instructions about the scene, not a person's dialogue.
#: The first names a character on purpose: it is the owner's own example, and it is the case
#: where the narrator must describe **Lily** doing the thing rather than addressing "you".
TURNS = [
    "Lily jumps up on the table and starts singing, badly, to drown out the argument.",
    "Zoe tries to get her down before anyone outside hears.",
    "Aldous finally says what he has been holding back all evening.",
]


class Api:
    """The smallest possible JSON client. No dependency, so this runs anywhere `uv` does."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def _call(self, method: str, path: str, body: dict | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                raw = resp.read().decode()
        except urllib.error.HTTPError as err:  # surface the API's own message, not a 500
            raise SystemExit(f"{method} {path} → {err.code}: {err.read().decode()[:400]}") from err
        except urllib.error.URLError as err:
            raise SystemExit(
                f"{method} {path} → cannot reach {self.base} ({err.reason}).\n"
                "Start a backend first: uv run python app.py backend"
            ) from err
        return json.loads(raw) if raw.strip() else None

    def get(self, path: str) -> Any:
        return self._call("GET", path)

    def post(self, path: str, body: dict) -> Any:
        return self._call("POST", path, body)

    def delete(self, path: str) -> Any:
        return self._call("DELETE", path)

    def stream(self, path: str, body: dict) -> list[dict]:
        """POST and collect the NDJSON frames.

        Delta frames re-emit the same event ``id`` with an **incremental** ``text`` and
        ``done: false``; the final frame carries ``done: true`` and an **empty** ``text``.
        Reading the text off the done frame alone yields "" for every streamed beat, which is
        the single most common way to misread this stream — so accumulate by id.
        """
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        frames: list[dict] = []
        try:
            with urllib.request.urlopen(req, timeout=1800) as resp:
                for line in resp:
                    text = line.decode().strip()
                    if not text:
                        continue
                    try:
                        frames.append(json.loads(text))
                    except ValueError:
                        pass
        except urllib.error.HTTPError as err:
            raise SystemExit(f"POST {path} → {err.code}: {err.read().decode()[:400]}") from err
        return frames


def build_world(api: Api) -> tuple[str, str, dict[str, str]]:
    """Create the throwaway storyline. Returns ``(storyline_id, scenario_id, {id: name})``."""
    storyline = api.post(
        "/storylines",
        {
            "title": "Scene Smoke",
            "genre": "noir",
            "premise": "A dockside tavern the night before a debt comes due.",
        },
    )["id"]
    cast: dict[str, str] = {}
    for name, role in CAST:
        row = api.post(f"/storylines/{storyline}/characters", {"name": name, "role": role})
        cast[row["id"]] = name
    setting = api.post(
        f"/storylines/{storyline}/settings",
        {
            "name": "The Smoldering Hearth",
            "desc": "A back room behind a dockside tavern, rain on the shutters.",
        },
    )["id"]
    scenario = api.post(
        f"/storylines/{storyline}/scenarios",
        {
            "title": "Last Call",
            "castIds": list(cast),
            "settingId": setting,
            # No follow-up suggestions: they cost a call and say nothing about the prose.
            "suggestionsCount": 0,
        },
    )["id"]
    return storyline, scenario, cast


def beats_from(frames: list[dict]) -> list[dict]:
    """Accumulate the delta stream into finished beats, in order.

    Returns one row per prose event: ``{kind, characterId, text}``. Non-prose events (stat
    changes, branch choices) and transport frames (trace, reasoning, error) are dropped —
    this harness is about what the reader reads.
    """
    order: list[str] = []
    by_id: dict[str, dict] = {}
    for frame in frames:
        kind = frame.get("type")
        if kind not in ("narration", "character_prose", "character_dialogue", "character_action"):
            continue
        event_id = frame.get("id") or ""
        data = frame.get("data") or {}
        if event_id not in by_id:
            by_id[event_id] = {
                "kind": kind,
                # `characterId` rides in `data`, not on the envelope — the envelope carries
                # only id/seq/scenarioId/sessionId/ts/visibility. Reading it off the top
                # level silently yields None for every beat, which shows up as an unnamed
                # speaker and quietly disables every check that needs to know who spoke.
                "characterId": data.get("characterId") or frame.get("characterId"),
                "text": "",
            }
            order.append(event_id)
        by_id[event_id]["text"] += data.get("text") or ""
    return [by_id[i] for i in order if by_id[i]["text"].strip()]


def errors_from(frames: list[dict]) -> list[str]:
    """Any error frame the turn reported, so a failed turn is never read as a clean one."""
    out = []
    for frame in frames:
        if frame.get("type") == "error" or "error" in frame:
            out.append(json.dumps(frame)[:200])
    return out


def check_beat(beat: dict, cast: dict[str, str], *, embodied: bool) -> list[str]:
    """Every rule this beat broke, in plain words. Empty means it reads correctly."""
    text = beat["text"]
    kind = beat["kind"]
    speaker_id = beat.get("characterId")
    problems: list[str] = []

    # Applies to every beat, in every mode: "the player" is a production label, never a name.
    if emission.names_the_player(text):
        problems.append('calls someone "the player" / "the user"')

    if kind == "narration":
        if emission.narrator_speaks_in_first_person(text):
            problems.append("narrator uses first person (I / me / we)")
        if not embodied and emission.addresses_the_reader(text):
            problems.append("narrator addresses the reader in second person")
    else:
        if not embodied and emission.addresses_the_reader(text):
            problems.append("addresses the reader in second person outside dialogue")
        others = [name for cid, name in cast.items() if cid != speaker_id]
        leaked = emission.cross_speaker_speech(text, others=others)
        if leaked:
            problems.append(f"gives {leaked} a spoken line inside this beat")
    return problems


def check_turn(direction: str, beats: list[dict], cast: dict[str, str]) -> list[str]:
    """Rules about the turn as a whole rather than any one beat."""
    problems: list[str] = []
    if not beats:
        problems.append("produced no prose at all")
        return problems
    # The owner's Lily case: a direction that names a character must reach that character —
    # either as their own beat, or as narration that names them.
    named = [name for name in cast.values() if name.lower() in direction.lower()]
    whole = " ".join(b["text"] for b in beats)
    spoke = {cast.get(b.get("characterId") or "", "") for b in beats}
    for name in named:
        if name not in whole and name not in spoke:
            problems.append(f'direction named {name}, but no beat mentions or voices them')
    return problems


def paragraphs(text: str) -> int:
    """How many paragraphs a beat is. Blank-line separated, blank lines not counted."""
    return len([p for p in (text or "").split("\n") if p.strip()])


def render(beat: dict, cast: dict[str, str]) -> str:
    who = "NARRATOR" if beat["kind"] == "narration" else cast.get(
        beat.get("characterId") or "", "?"
    ).upper()
    body = beat["text"].strip()
    # The paragraph count is printed on every beat because length is a thing the prompt can
    # silently dictate. A scene where every beat lands in the same narrow band is a scene
    # being told how long to be, whatever the prose reads like — and that is invisible unless
    # somebody counts.
    return f"  \033[1m{who}\033[0m \033[2m({paragraphs(body)}¶)\033[0m\n" + "\n".join(
        f"    {line}" for line in body.splitlines() if line.strip()
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default=DEFAULT_API, help=f"API base (default {DEFAULT_API})")
    ap.add_argument("--turns", type=int, default=2, help="player turns to play (default 2)")
    ap.add_argument("--keep", action="store_true", help="do not delete the world afterwards")
    ap.add_argument("--json", action="store_true", help="emit the findings as JSON too")
    args = ap.parse_args()

    # Line-buffered, always. A turn against a local model takes minutes, so this is watched
    # through `tail -f` as often as it is read afterwards — and when a run is killed for
    # taking too long, a block-buffered stdout means the file is EMPTY and the very run that
    # most needed diagnosing left nothing behind. That happened once; it does not need to
    # happen twice.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    api = Api(args.api)
    storyline, scenario, cast = build_world(api)
    print(f"world: storyline={storyline} scenario={scenario} cast={', '.join(cast.values())}\n")

    session: str | None = None
    failures: list[dict] = []
    total_beats = 0
    lengths: list[int] = []
    try:
        for i, direction in enumerate(TURNS[: max(1, args.turns)], start=1):
            print(f"\033[1m── turn {i} ─ direction:\033[0m {direction}")
            payload: dict[str, Any] = {"text": direction}
            if session:
                payload["sessionId"] = session
            frames = api.stream(f"/play/{scenario}/turn", payload)
            for frame in frames:
                session = session or (frame.get("sessionId") or None)
            errs = errors_from(frames)
            for err in errs:
                print(f"  \033[31mERROR FRAME\033[0m {err}")
                failures.append({"turn": i, "problem": f"error frame: {err}"})

            beats = beats_from(frames)
            total_beats += len(beats)
            for beat in beats:
                if beat["kind"] != "narration":
                    lengths.append(paragraphs(beat["text"]))
                print(render(beat, cast))
                # Playwright mode throughout: the player never picked a POV character, so
                # they are not embodied and nobody in the scene may address them.
                for problem in check_beat(beat, cast, embodied=False):
                    who = "narrator" if beat["kind"] == "narration" else cast.get(
                        beat.get("characterId") or "", "?"
                    )
                    print(f"    \033[31m✗ {problem}\033[0m")
                    failures.append({"turn": i, "who": who, "problem": problem})
                print()
            for problem in check_turn(direction, beats, cast):
                print(f"  \033[31m✗ {problem}\033[0m")
                failures.append({"turn": i, "who": "(turn)", "problem": problem})
            print()
    finally:
        if args.keep:
            print(f"kept: {args.api.rsplit('/api', 1)[0]}/{storyline}/{scenario}")
        else:
            api.delete(f"/storylines/{storyline}")

    print("─" * 68)
    if lengths:
        spread = sorted(lengths)
        print(
            f"paragraphs per character beat: min {spread[0]} · max {spread[-1]} · "
            f"{', '.join(str(n) for n in lengths)}"
        )
    print(f"{total_beats} beat(s) read, {len(failures)} problem(s) found")
    for f in failures:
        print(f"  turn {f['turn']} · {f.get('who', '')}: {f['problem']}")
    if args.json:
        print(json.dumps({"beats": total_beats, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
