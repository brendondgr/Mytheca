"""EXP-2026-08-007 — are the in-voice sampler penalties what breaks the prose?

The character passage form ships and does not read like a scene: run-ons with no
punctuation, no spoken dialogue, one unbroken block. ``character_turn_agent._voice_params``
applies ``frequency_penalty`` 0.4 and ``presence_penalty`` 0.3 to every character
generation, and those penalties fall on every token — including the ones prose is made of.

This calls the relay directly, so the sampler is the only thing that varies: same contract,
same scene prompts, same temperature/top_p/budgets, three penalty arms, interleaved per
prompt so a drift in endpoint state cannot land on one arm.

Read ``docs/research/experiments/EXP-2026-08-007-prose-form/PROTOCOL.md`` first — it is
pre-registered and this script implements it.

    uv run python -m utils.scripts.research.run_prose_form \
      --experiment docs/research/experiments/EXP-2026-08-007-prose-form
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

from app.agents import prompt_registry  # noqa: E402
from app.services import emission  # noqa: E402

CONTRACT = prompt_registry.default(prompt_registry.CHARACTER_OUTPUT_CONTRACT)

#: Five scenes covering the registers the planner assigns, plus a two-hander whose
#: transcript ends on a direct question — the case where a reply *should* contain speech.
#: They ship here, so they are contaminated for any held-out use (PROTOCOL.md § Data).
PROMPTS: list[dict[str, str]] = [
    {
        "id": "question",
        "register": "neutral",
        "user": (
            "You are Aldous — a dockside factor. Dry, watchful, slow to commit.\n\n"
            "This turn so far:\n"
            'Mei: "The harbour watch already knows about the salt. Did you tell them?"\n\n'
            "Aldous, respond now."
        ),
    },
    {
        "id": "banter",
        "register": "light",
        "user": (
            "You are Fennel — a hedge-witch's apprentice. Quick, teasing, warm.\n\n"
            "This turn so far:\n"
            "Narrator: The two of them end up on the same bench outside the bakehouse, "
            "and neither gets up.\n\n"
            "Fennel, respond now."
        ),
    },
    {
        "id": "standoff",
        "register": "tense",
        "user": (
            "You are Valdar — a caravan guard with a bad debt. Blunt, proud, cornered.\n\n"
            "This turn so far:\n"
            "Narrator: The door is blocked. Kira has not drawn, but her hand has not left "
            "the strap either.\n"
            'Kira: "Sit down, Valdar."\n\n'
            "Valdar, respond now."
        ),
    },
    {
        "id": "grief",
        "register": "grave",
        "user": (
            "You are Lyriel — a healer who has run out of things to try. Precise, tired.\n\n"
            "This turn so far:\n"
            "Narrator: The boy on the table stops breathing between one word and the next.\n\n"
            "Lyriel, respond now."
        ),
    },
    {
        "id": "alone",
        "register": "neutral",
        "user": (
            "You are Mei — a broker who trades in other people's secrets. Careful, dry.\n\n"
            "This turn so far:\n"
            "Narrator: The room empties. Mei is left with the ledger and the rain.\n\n"
            "Mei, respond now."
        ),
    },
]

ARMS: dict[str, dict[str, float]] = {
    "shipped": {"frequency_penalty": 0.4, "presence_penalty": 0.3},
    "half": {"frequency_penalty": 0.2, "presence_penalty": 0.15},
    "off": {"frequency_penalty": 0.0, "presence_penalty": 0.0},
}

#: Fixed for every call — only the two penalty fields move between arms. ``max_tokens`` is
#: what the app sends: budget_for(HIGH) 1024 + _VOICE_PROSE_TOKENS 1200.
FIXED = {
    "temperature": 0.8,
    "top_p": 0.92,
    "max_tokens": 2224,
    "thinking_token_budget": 1024,
}

TERMINATORS = re.compile(r"[.!?]")
#: A *paired* run of double quotes — one stray quote mark is not a spoken line. Straight
#: and curly pairs both count, because the model produces either.
SPOKEN = re.compile(r'"[^"]+"|“[^”]+”')

METRIC_KEYS = [
    "sentences_per_100_words",
    "has_speech",
    "paragraph_breaks",
    "is_scratchpad",
    "chars",
]


def measure(passage: str) -> dict[str, Any]:
    """The four countable shadows of "reads like a scene", plus length for context."""
    words = len(passage.split())
    return {
        "chars": len(passage),
        "words": words,
        "sentences_per_100_words": (
            round(100 * len(TERMINATORS.findall(passage)) / words, 3) if words else 0.0
        ),
        "has_speech": 1 if SPOKEN.search(passage) else 0,
        "paragraph_breaks": passage.count("\n\n"),
        "is_scratchpad": 1 if emission.looks_like_scratchpad(passage) else 0,
    }


def passage_of(raw: str) -> str:
    """The text the turn engine would render, parsed the way the engine parses it."""
    segments = emission.parse_emission(raw, roster={}, fallback_speaker_id="x")
    prose = [s.text for s in segments if s.type == emission.PROSE_TYPE]
    return prose[0] if prose else ""


def call(base_url: str, model: str, user: str, arm: dict[str, float], timeout: float) -> dict:
    import httpx

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": CONTRACT},
            {"role": "user", "content": user},
        ],
        **FIXED,
        **arm,
    }
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0)) as client:
        res = client.post(f"{base_url}/chat/completions", json=body)
        res.raise_for_status()
        return res.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:4000/v1")
    parser.add_argument("--model", default="skynet")
    parser.add_argument("--samples", type=int, default=2, help="samples per prompt per arm")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    exp = args.experiment if args.experiment.is_absolute() else REPO_ROOT / args.experiment
    entrypoint = (
        "uv run python -m utils.scripts.research.run_prose_form "
        f"--experiment {args.experiment} --samples {args.samples}"
    )
    record = RunRecord(entrypoint=entrypoint)
    record.note(
        f"arms={list(ARMS)} prompts={[p['id'] for p in PROMPTS]} samples={args.samples} "
        f"model={args.model}"
    )

    raw_log: list[dict[str, Any]] = []
    started_all = time.monotonic()
    # Interleaved: every arm sees each prompt back to back, so a drift in endpoint state
    # spreads across the arms instead of landing on whichever ran last.
    for sample in range(1, args.samples + 1):
        for prompt in PROMPTS:
            for arm_name, arm in ARMS.items():
                row: dict[str, Any] = {
                    "arm": arm_name,
                    "prompt": prompt["id"],
                    "register": prompt["register"],
                    "sample": sample,
                }
                started = time.monotonic()
                try:
                    payload = call(
                        args.base_url, args.model, prompt["user"], arm, args.timeout
                    )
                    message = (payload.get("choices") or [{}])[0].get("message") or {}
                    raw = message.get("content") or ""
                    passage = passage_of(raw)
                    row.update(measure(passage))
                    row["elapsed_s"] = round(time.monotonic() - started, 3)
                    row["served_model"] = payload.get("model")
                    usage = payload.get("usage") or {}
                    record.input_tokens += usage.get("prompt_tokens") or 0
                    record.output_tokens += usage.get("completion_tokens") or 0
                    raw_log.append({**row, "passage": passage, "raw": raw})
                except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                    row["error"] = f"{exc.__class__.__name__}: {exc}"
                    record.note(
                        f"{arm_name}/{prompt['id']}/sample{sample} FAILED: {row['error']}"
                    )
                    raw_log.append({**row})
                record.add_run(row)
                record.llm_calls += 1
                print(
                    f"{arm_name:<8} {prompt['id']:<9} s{sample} "
                    f"sent/100w={row.get('sentences_per_100_words')} "
                    f"speech={row.get('has_speech')} breaks={row.get('paragraph_breaks')} "
                    f"chars={row.get('chars')} {row.get('error', '')}",
                    flush=True,
                )
    record.wall_clock_seconds = time.monotonic() - started_all

    # Per-arm aggregate. An arm that lost a run gets NO aggregate: survivors are not a
    # random subsample of the arm, and reporting a mean over them would be reporting a
    # different experiment (the EXP-2026-08-001 rule).
    values: dict[str, Any] = {}
    for arm_name in ARMS:
        rows = [r for r in record.per_run if r["arm"] == arm_name]
        failed = [r for r in rows if r.get("error")]
        if failed:
            record.note(
                f"arm {arm_name}: {len(failed)}/{len(rows)} run(s) failed — NO aggregate "
                "computed for it. Per-run rows are the result; see ISSUES.md."
            )
            continue
        for key, cell in aggregate(rows, METRIC_KEYS).items():
            values[f"{arm_name}.{key}"] = cell

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
            # The aggregate goes in the manifest as well as data/metrics.json: a status of
            # `complete` with an empty `metrics.values` fails validation, and deliberately
            # so — a finished experiment that records no number is not a finished experiment.
            "metrics": {"values": values},
            "llm": {
                "model": f"relay/{args.model}",
                "temperature": FIXED["temperature"],
                "top_p": FIXED["top_p"],
                "max_tokens": FIXED["max_tokens"],
                "prompt_hash": hash_text(CONTRACT),
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
