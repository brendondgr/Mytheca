"""EXP-2026-08-019 — is the tail Signature doing anything the cached prefix isn't?

``EXP-2026-08-018``'s style arm carried the four prose blocks in the cached system prefix
AND the one-clause ``signature`` in the volatile recency tail, so it could not say which did
the work. Three arms here separate them.

**This harness drives the shipped code.** ``style_guide.resolve`` →
``assembler._build_stable_prefix`` → ``character_turn_agent._build_user_prompt``, with the
signature fused into the act-now cue by the engine rather than appended by the harness. The
arms differ by ONE argument — which blocks the resolver is handed — which closes the fidelity
gap recorded in EXP-2026-08-018's ISSUES.md.

Local model only. Read ``PROTOCOL.md`` first; it is pre-registered and this implements it.

    uv run python -m utils.scripts.research.run_style_signature \
      --experiment docs/research/experiments/EXP-2026-08-019-style-signature-separation
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
from app.content import style_blocks, style_presets  # noqa: E402
from app.models.scenario import Scenario  # noqa: E402
from app.schemas.reasoning import ReasoningEffort  # noqa: E402
from app.schemas.settings import LlmParams  # noqa: E402
from app.services import assembler, emission, llm, style_guide  # noqa: E402

CONTRACT = prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT)

#: The measured guide, taken from the SHIPPED preset rather than re-typed here — so this
#: experiment cannot silently drift from the text the product actually offers.
ROMANCE = dict(style_presets.ROMANCE.blocks)
WITHOUT_SIGNATURE = {k: v for k, v in ROMANCE.items() if k != style_blocks.SIGNATURE.id}

ARMS: dict[str, dict[str, str] | None] = {
    "baseline": None,
    "prefix": WITHOUT_SIGNATURE,
    "prefix_signature": ROMANCE,
}


class _Storyline:
    """The minimum ``_build_stable_prefix`` reads. Identical across arms."""

    title = "Harrow Lane"
    genre = "Contemporary"
    world_primer = (
        "A terrace house on a canal street in a northern city, shared by four tenants who "
        "were strangers a year ago. Nothing supernatural, nothing criminal. The kitchen is "
        "the only warm room and everyone ends up in it."
    )
    premise = None


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


#: The same two scenes as EXP-2026-08-018, so its baseline and full-style arms stay
#: comparable to this experiment's `baseline` and `prefix_signature`.
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


def build_messages(scene: dict[str, Any], blocks: dict[str, str] | None) -> list[dict[str, str]]:
    """The exact two messages the engine would send, for one arm.

    Everything below this line is the shipped code path: the resolver decides what the arm
    is, ``_build_stable_prefix`` places the prose blocks, and ``_build_user_prompt`` fuses
    the signature into the act-now cue if there is one.
    """
    style = style_guide.resolve(blocks)
    cast = _cast()
    scenario = Scenario(
        storyline_id="harrow", title="Harrow Lane", cast_ids=[m.id for m in cast], setting_id=""
    )
    ctx = assembler.TurnContext(
        scenario=scenario,
        session_id=f"exp019-{scene['id']}",
        storyline_id="harrow",
        directed_at=None,
        cast=cast,
        setting=None,
        stat_defs=[],
        stat_guidance={},
        recent_beats=list(scene["recent"]),
        subgraph={"available": False, "nodes": [], "edges": []},
        world_primer=_Storyline.world_primer,
        stable_prefix=assembler._build_stable_prefix(_Storyline(), [], {}, style),
        style=style,
        player_embodied=False,
    )
    speaker = next(m for m in ctx.cast if m.id == scene["speaker"])
    system = f"{CONTRACT}\n\n{ctx.stable_prefix}".strip()
    user = character_turn_agent._build_user_prompt(
        ctx, speaker, list(scene["turn"]),
        register=scene["register"], stakes=scene["stakes"], purpose=scene["purpose"],
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ---- Measures. Same as EXP-2026-08-018, minus the one it found measured nothing. ----

TERMINATORS = re.compile(r"[.!?]")
SPOKEN = re.compile(r'"[^"]+"|“[^”]+”')

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

METRIC_KEYS = [
    "proximity_per_1k",
    "interiority_per_1k",
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
        "is_scratchpad": 1 if emission.looks_like_scratchpad(passage) else 0,
    }


def passage_of(raw: str) -> str:
    segments = emission.parse_emission(raw, roster={}, fallback_speaker_id="x")
    prose = [s.text for s in segments if s.type == emission.PROSE_TYPE]
    return prose[0] if prose else ""


def call(base_url: str, model: str, messages: list[dict[str, str]], timeout: float) -> dict:
    """One beat through the engine's own llm layer, with the reasoning channel OFF.

    Not a hand-rolled POST — see EXP-2026-08-018's ISSUES §1: the local route is a reasoning
    model, and a raw request lets it spend the passage's budget thinking and return nothing.
    """
    params = character_turn_agent._voice_params(
        LlmParams(temperature=0.8, max_tokens=512), "neutral", ReasoningEffort.NONE, None
    )
    usage: dict = {}
    text, prompt_tokens = llm.chat_complete_usage(
        base_url, "", model, messages, params,
        reasoning=ReasoningEffort.NONE, usage_out=usage, timeout_s=timeout,
    )
    return {"text": text, "prompt_tokens": prompt_tokens, "usage": usage}


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
        "uv run python -m utils.scripts.research.run_style_signature "
        f"--experiment {args.experiment} --model {args.model} --samples {args.samples}"
    )
    record = RunRecord(entrypoint=entrypoint)
    record.note(
        f"arms={list(ARMS)} scenes={[s['id'] for s in SCENES]} samples={args.samples} "
        f"model={args.model} (local route only; shipped code path)"
    )

    # Assert the arms actually differ where the protocol says they do, before spending any
    # model time. A harness whose arms silently collapse is worse than no harness.
    probe = {
        name: {m["role"]: m["content"] for m in build_messages(SCENES[0], blocks)}
        for name, blocks in ARMS.items()
    }
    signature = style_guide.resolve(ROMANCE).render_signature()
    assert probe["prefix"]["system"] != probe["baseline"]["system"], (
        "the prefix arm did not change the system message"
    )
    assert probe["prefix"]["system"] == probe["prefix_signature"]["system"], (
        "the two style arms must share a byte-identical system message"
    )
    assert probe["baseline"]["user"] == probe["prefix"]["user"], (
        "the prefix arm must not touch the user prompt"
    )
    assert probe["prefix_signature"]["user"].replace(f" {signature}", "") == probe["prefix"]["user"], (
        "the signature is not the only difference in the user prompt"
    )
    record.note("arm-difference preflight passed: prefix differs in system, signature only in user")

    raw_log: list[dict[str, Any]] = []
    started_all = time.monotonic()
    for sample in range(1, args.samples + 1):
        for scene in SCENES:
            for arm, blocks in ARMS.items():
                messages = build_messages(scene, blocks)
                row: dict[str, Any] = {"arm": arm, "scene": scene["id"], "sample": sample}
                started = time.monotonic()
                try:
                    payload = call(args.base_url, args.model, messages, args.timeout)
                    passage = passage_of(payload["text"])
                    row.update(measure(passage))
                    row["elapsed_s"] = round(time.monotonic() - started, 3)
                    row["prompt_tokens"] = payload["prompt_tokens"]
                    row["cached_tokens"] = (payload["usage"] or {}).get("cached_tokens")
                    record.input_tokens += payload["prompt_tokens"] or 0
                    raw_log.append({**row, "passage": passage, "raw": payload["text"]})
                except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                    row["error"] = f"{exc.__class__.__name__}: {exc}"
                    record.note(f"{arm}/{scene['id']}/sample{sample} FAILED: {row['error']}")
                    raw_log.append({**row})
                record.add_run(row)
                record.llm_calls += 1
                print(
                    f"{arm:<17} {scene['id']:<8} s{sample} "
                    f"prox={row.get('proximity_per_1k')} "
                    f"inter={row.get('interiority_per_1k')} "
                    f"chars={row.get('chars')} {row.get('error', '')}",
                    flush=True,
                )
    record.wall_clock_seconds = time.monotonic() - started_all

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
                "prompt_hash": hash_text(CONTRACT + json.dumps(ROMANCE, sort_keys=True)),
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
