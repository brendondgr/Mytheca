"""EXP-2026-08-018 — does a storyline STYLE GUIDE in the cached prefix change the prose?

Two arms differing only in whether a romance narrative-style guide is inserted between the
character output contract and the world primer — the placement the feature design
recommends for prefix-cache reuse. Same scene, same cast, same transcript, same sampler,
interleaved per sample so endpoint drift cannot land on one arm.

The user prompt is built by the ENGINE'S OWN ``character_turn_agent._build_user_prompt``,
so the harness cannot drift from what the app actually sends — the same reason
``utils/scripts/scene_smoke.py`` imports its checks from ``services/emission``.

Local model only. Read ``PROTOCOL.md`` first; it is pre-registered and this implements it.

    uv run python -m utils.scripts.research.run_style_guide \
      --experiment docs/research/experiments/EXP-2026-08-018-narrative-style-romance
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
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

sys.path.insert(0, str(REPO_ROOT / "web" / "backend"))

from app.agents import character_turn_agent, prompt_registry  # noqa: E402
from app.models.scenario import Scenario  # noqa: E402
from app.schemas.reasoning import ReasoningEffort  # noqa: E402
from app.schemas.settings import LlmParams  # noqa: E402
from app.services import assembler, emission, llm  # noqa: E402

CONTRACT = prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT)

#: The world, identical in both arms. This is what ``_build_stable_prefix`` produces today.
STABLE_PREFIX = (
    "WORLD: Harrow Lane (Contemporary).\n\n"
    "WORLD PRIMER\n"
    "A terrace house on a canal street in a northern city, shared by four tenants who "
    "were strangers a year ago. Nothing supernatural, nothing criminal. The kitchen is "
    "the only warm room and everyone ends up in it."
)

#: The romance style guide, as drafted and approved in chat. Four blocks; the fifth
#: (Pacing) targets the planner and is NOT exercised here — see PROTOCOL.md.
STYLE_GUIDE = """HOW THIS STORY IS WRITTEN

Attention. Spend the prose on proximity and on the body's small betrayals: where someone's hands go when they have nothing to hold, who looks away first, the half-second of a decision not to say something. Interiority is the point — a character noticing their own reaction, and mistrusting it, is worth more than any event. Physical detail matters only in relation to another person: a room is warm because of who is in it. Skip logistics; arrive at the moment already begun.

Voice. People say slightly less than they mean, and the gap between the two is where the scene lives. Kindness is done, not announced. Humour is deflection and should arrive exactly when someone is about to be honest. When someone is finally direct, let the sentence be plain and short — no ornament — because the plainness is the event.

Texture. Shared objects carry the history — the same cup, the same walk home, the coat that keeps getting lent. Time of day is late or too early. Other people exist mainly as interruption.

Never. Never narrate a feeling a character could show. Never have someone explain the relationship to the person they are in it with. Never resolve a confession in the turn it is made."""

#: The one line that rides in the volatile recency tail.
SIGNATURE = (
    "The style of this story, in one line: close and unsaid — one shift in the distance, "
    "and only one person is brave."
)


def _cast() -> list[assembler.CastMember]:
    return [
        assembler.CastMember(
            id="c_nadia",
            name="Nadia",
            role="a night-shift radiographer, three years in the house",
            traits="observant, deflects with jokes, slow to admit anything",
            speech="dry, unfinished sentences, changes the subject",
            color="#8A5A78",
            stats={"trust": 54},
            recent_lines=["You are not as subtle as you think you are."],
        ),
        assembler.CastMember(
            id="c_emile",
            name="Emile",
            role="a joiner who moved in last spring",
            traits="steady, literal, says the true thing a beat too late",
            speech="plain, short, no hedging",
            color="#3A5A78",
            stats={"trust": 61},
            recent_lines=["I said I would fix the door and I fixed the door."],
        ),
    ]


#: Two scenes, both two-handers at a charged-but-not-dangerous moment. Identical across
#: arms; only the system message and the tail signature differ.
SCENES: list[dict[str, Any]] = [
    {
        "id": "kitchen",
        "speaker": "c_nadia",
        "register": "neutral",
        "stakes": "whether either of them says the thing out loud",
        "purpose": "let Nadia almost answer, and not",
        "recent": [
            {
                "role": "narrator",
                "text": (
                    "The others went to bed an hour ago. Emile has washed the same pan "
                    "twice and Nadia has not moved from the doorway."
                ),
                "characterId": None,
            },
        ],
        "turn": [
            {
                "role": "character",
                "text": (
                    "\"You could just say it,\" I tell her, and put the pan down. \"Whatever "
                    "it is. I'm not going anywhere.\""
                ),
                "characterId": "c_emile",
            },
        ],
    },
    {
        "id": "doorway",
        "speaker": "c_emile",
        "register": "neutral",
        "stakes": "he leaves without it being resolved",
        "purpose": "let Emile offer something small instead of the large thing",
        "recent": [
            {
                "role": "narrator",
                "text": "Nadia's shift starts in forty minutes. Her coat is already on.",
                "characterId": None,
            },
        ],
        "turn": [
            {
                "role": "character",
                "text": (
                    "\"Don't wait up,\" I say, and then, because that came out wrong, \"I mean "
                    "— you don't have to.\""
                ),
                "characterId": "c_nadia",
            },
        ],
    },
]


def _context(scene: dict[str, Any], *, style: bool) -> assembler.TurnContext:
    cast = _cast()
    scenario = Scenario(
        storyline_id="harrow", title="Harrow Lane", cast_ids=[m.id for m in cast], setting_id=""
    )
    prefix = f"{STYLE_GUIDE}\n\n{STABLE_PREFIX}" if style else STABLE_PREFIX
    return assembler.TurnContext(
        scenario=scenario,
        session_id=f"exp018-{scene['id']}",
        storyline_id="harrow",
        directed_at=None,
        cast=cast,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=list(scene["recent"]),
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer=STABLE_PREFIX,
        stable_prefix=prefix,
        player_embodied=False,
    )


def build_messages(scene: dict[str, Any], *, style: bool) -> list[dict[str, str]]:
    """The exact two messages the character agent would send, for one arm."""
    ctx = _context(scene, style=style)
    speaker = next(m for m in ctx.cast if m.id == scene["speaker"])
    system = f"{CONTRACT}\n\n{ctx.stable_prefix}".strip()
    user = character_turn_agent._build_user_prompt(
        ctx,
        speaker,
        list(scene["turn"]),
        register=scene["register"],
        stakes=scene["stakes"],
        purpose=scene["purpose"],
    )
    if style:
        # The Signature — the only part of the design that rides in the recency tail.
        # Appended after the act-now cue; the shipped feature would fuse it into that cue.
        user = f"{user}\n\n{SIGNATURE}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ---- Measures. Crude by construction; the passages in data/ are the real evidence. ----

TERMINATORS = re.compile(r"[.!?]")
SPOKEN = re.compile(r'"[^"]+"|“[^”]+”')

#: Pre-registered lexicons. Not edited after seeing output.
PROXIMITY = re.compile(
    r"\b(hand|hands|wrist|shoulder|elbow|knee|arm|fingers|touch|touches|touching|close|closer|"
    r"between us|beside|next to|lean|leans|leaning|reach|reaches|reaching|breath|breathes|"
    r"breathing|look|looks|looking|looked|away|eyes|gaze|doorway|step|steps|inches|space)\b",
    re.I,
)
INTERIORITY = re.compile(
    r"\b(I notice|I know|I don't know|I do not know|I want|I wanted|I can't|I cannot|I should|"
    r"I could|I think|I thought|I mean|my chest|my throat|my hands|my own|I let|I don't|"
    r"I do not|I almost|I nearly|I decide|I decided)\b",
    re.I,
)
NAMED_EMOTION = re.compile(
    r"\b(love|loving|affection|longing|desire|yearning|happiness|happy|sadness|sad|anger|angry|"
    r"fear|afraid|joy|tenderness|tender|passion|passionate|heartache|adore|romance|romantic|"
    r"emotion|emotions|feelings)\b",
    re.I,
)

METRIC_KEYS = [
    "proximity_per_1k",
    "interiority_per_1k",
    "named_emotion_per_1k",
    "dialogue_share",
    "chars",
    "paragraph_breaks",
    "has_speech",
]


def _per_1k(pattern: re.Pattern[str], text: str) -> float:
    if not text:
        return 0.0
    return round(1000 * len(pattern.findall(text)) / len(text), 3)


def measure(passage: str) -> dict[str, Any]:
    quoted = sum(len(m.group(0)) for m in SPOKEN.finditer(passage))
    words = len(passage.split())
    return {
        "chars": len(passage),
        "words": words,
        "sentences_per_100_words": (
            round(100 * len(TERMINATORS.findall(passage)) / words, 3) if words else 0.0
        ),
        "paragraph_breaks": passage.count("\n\n"),
        "has_speech": 1 if SPOKEN.search(passage) else 0,
        "dialogue_share": round(quoted / len(passage), 4) if passage else 0.0,
        "proximity_per_1k": _per_1k(PROXIMITY, passage),
        "interiority_per_1k": _per_1k(INTERIORITY, passage),
        "named_emotion_per_1k": _per_1k(NAMED_EMOTION, passage),
        "is_scratchpad": 1 if emission.looks_like_scratchpad(passage) else 0,
    }


def passage_of(raw: str) -> str:
    segments = emission.parse_emission(raw, roster={}, fallback_speaker_id="x")
    prose = [s.text for s in segments if s.type == emission.PROSE_TYPE]
    return prose[0] if prose else ""


def call(base_url: str, model: str, messages: list[dict[str, str]], timeout: float) -> dict:
    """One beat, through the ENGINE'S OWN llm layer.

    Not a hand-rolled POST: the local route is a reasoning model (it answers with
    ``reasoning_content``), and a character beat ships with the channel explicitly OFF
    (``character_turn_agent.TURN_EFFORT`` is ``ReasoningEffort.NONE``). A raw request omits
    that, so the model spends the passage's budget thinking and can return empty content —
    observed on this endpoint before this function was rewritten. Going through
    ``llm.chat_complete_usage`` applies the same backend-specific reasoning-off the app
    applies, so the arms differ by the style text and nothing else.
    """
    params = character_turn_agent._voice_params(
        LlmParams(temperature=0.8, max_tokens=512), "neutral", ReasoningEffort.NONE, None
    )
    usage: dict = {}
    text, prompt_tokens = llm.chat_complete_usage(
        base_url,
        "",
        model,
        messages,
        params,
        reasoning=ReasoningEffort.NONE,
        usage_out=usage,
        timeout_s=timeout,
    )
    return {"text": text, "prompt_tokens": prompt_tokens, "usage": usage, "params": params}


ARMS = ("baseline", "romance")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:4000/v1")
    parser.add_argument("--model", default="local", help="LOCAL route only (llama.cpp)")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    exp = args.experiment if args.experiment.is_absolute() else REPO_ROOT / args.experiment
    entrypoint = (
        "uv run python -m utils.scripts.research.run_style_guide "
        f"--experiment {args.experiment} --model {args.model} --samples {args.samples}"
    )
    record = RunRecord(entrypoint=entrypoint)
    record.note(
        f"arms={list(ARMS)} scenes={[s['id'] for s in SCENES]} samples={args.samples} "
        f"model={args.model} (local route only)"
    )

    raw_log: list[dict[str, Any]] = []
    started_all = time.monotonic()
    for sample in range(1, args.samples + 1):
        for scene in SCENES:
            for arm in ARMS:
                messages = build_messages(scene, style=(arm == "romance"))
                row: dict[str, Any] = {"arm": arm, "scene": scene["id"], "sample": sample}
                started = time.monotonic()
                try:
                    payload = call(args.base_url, args.model, messages, args.timeout)
                    raw = payload["text"]
                    passage = passage_of(raw)
                    row.update(measure(passage))
                    row["elapsed_s"] = round(time.monotonic() - started, 3)
                    row["prompt_tokens"] = payload["prompt_tokens"]
                    row["cached_tokens"] = (payload["usage"] or {}).get("cached_tokens")
                    record.input_tokens += payload["prompt_tokens"] or 0
                    raw_log.append({**row, "passage": passage, "raw": raw})
                except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                    row["error"] = f"{exc.__class__.__name__}: {exc}"
                    record.note(f"{arm}/{scene['id']}/sample{sample} FAILED: {row['error']}")
                    raw_log.append({**row})
                record.add_run(row)
                record.llm_calls += 1
                print(
                    f"{arm:<9} {scene['id']:<8} s{sample} "
                    f"prox={row.get('proximity_per_1k')} "
                    f"inter={row.get('interiority_per_1k')} "
                    f"emo={row.get('named_emotion_per_1k')} "
                    f"chars={row.get('chars')} {row.get('error', '')}",
                    flush=True,
                )
    record.wall_clock_seconds = time.monotonic() - started_all

    # An arm that lost a run gets NO aggregate — survivors are not a random subsample
    # (the EXP-2026-08-001 rule).
    values: dict[str, Any] = {}
    for arm in ARMS:
        rows = [r for r in record.per_run if r["arm"] == arm]
        failed = [r for r in rows if r.get("error")]
        if failed:
            record.note(
                f"arm {arm}: {len(failed)}/{len(rows)} run(s) failed — NO aggregate computed. "
                "Per-run rows are the result; see ISSUES.md."
            )
            continue
        for key, cell in aggregate(rows, METRIC_KEYS).items():
            values[f"{arm}.{key}"] = cell

    failures = sum(1 for r in record.per_run if r.get("error"))
    write_environment(exp, record)
    write_metrics(exp, record, values)
    update_manifest(
        exp,
        {
            "code": git_block(entrypoint),
            "status": "failed" if failures else "complete",
            "n_runs": len(record.per_run),
            "compute": {
                "hardware": hardware(),
                "wall_clock_hours": round(record.wall_clock_seconds / 3600, 4),
                "estimated_cost_usd": 0.0,
            },
            "metrics": {"values": values},
            "llm": {
                "model": f"relay/{args.model}",
                "temperature": 0.8,
                "top_p": 0.92,
                "max_tokens": 2048,
                "prompt_hash": hash_text(CONTRACT + STYLE_GUIDE + SIGNATURE),
                "total_input_tokens": record.input_tokens,
                "total_output_tokens": record.output_tokens,
            },
        },
    )
    log = exp / "logs" / "passages.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps({"notes": record.notes, "failures": failures, "rows": raw_log}, indent=2),
        encoding="utf-8",
    )
    print(f"\n{'FAILED' if failures else 'complete'} — wrote {log}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
