"""Latency runner for EXP-2026-08-003 — live turn visibility.

Measures, against the **real** relay, how long a player waits before seeing anything and
how long a generation takes, across three arms that differ only in the arguments passed
to ``app.services.llm``:

* ``blocking-uncapped``  — no reasoning budget. Reproduces the pre-2026-08-19 behaviour
  exactly: an endpoint classified ``UNKNOWN`` received no budget key at all, which is
  identical to passing ``reasoning=None``.
* ``blocking-capped``    — a MEDIUM budget, still one blocking POST.
* ``streaming-capped``   — a MEDIUM budget over SSE, recording when the first answer
  token actually arrives.

Nothing is mocked. The endpoint must be reachable, and the model is pinned by
``--model`` (see PROTOCOL.md for why the deployed ``skynet`` id is not used).

Usage::

    uv run python -m utils.scripts.research.run_live_turn_visibility --runs 5 \\
        --experiment docs/research/experiments/EXP-2026-08-003-live-turn-visibility
"""

from __future__ import annotations

import argparse
import json
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

BACKEND = REPO_ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.schemas.reasoning import ReasoningEffort  # noqa: E402
from app.schemas.settings import LlmParams  # noqa: E402
from app.services import llm, llm_backend  # noqa: E402

# A real character-turn prompt shape: the output contract plus a world/scene preamble in
# the system message, one in-character ask in the user message. Held byte-identical
# across every arm and run, and hashed into the manifest.
SYSTEM = """You are voicing one character in an interactive story. Emit ONLY the thin-tag format:
<speaker:1>
<thinking>one or two sentences of private thought</thinking>
<type:character_dialogue>
their spoken line

World: Embergate, a rain-soaked harbour city where the smuggling families and the
harbour watch have held an uneasy truce for eleven years. Coin talks; names matter more.

Scene: the back room of the Smoldering Hearth, late, rain on the shutters.
Roster: 1 = Mei, a fence who has survived by never being the first to speak."""

USER = """Recent beats:
Player: I slide a coin pouch across the table toward Mei and say nothing.

Mei has patience 3/10 and suspicion 7/10 tonight. Write Mei's next beat now."""

ARMS = ("blocking-uncapped", "blocking-capped", "streaming-capped")
METRIC_KEYS = ["ttft_s", "wall_clock_s", "completion_tokens", "first_reasoning_s"]


def _params() -> LlmParams:
    # The app's own defaults, with the reasoning-headroom floor the turn loop applies.
    return LlmParams(temperature=0.7, max_tokens=8192, top_p=1.0)


def run_blocking(base_url: str, model: str, effort: ReasoningEffort | None) -> dict[str, Any]:
    """One blocking completion. Nothing is visible until it is whole, so ttft == wall clock."""
    started = time.monotonic()
    text, _prompt_tokens = llm.chat_complete_usage(
        base_url, "", model,
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}],
        _params(), reasoning=effort,
    )
    elapsed = time.monotonic() - started
    return {
        "ttft_s": round(elapsed, 3),
        "wall_clock_s": round(elapsed, 3),
        "completion_tokens": None,  # filled by the caller from the usage probe
        "first_reasoning_s": None,
        "chars": len(text),
    }


def run_streaming(base_url: str, model: str, effort: ReasoningEffort | None) -> dict[str, Any]:
    """One streamed completion, timing the first ANSWER token and the first reasoning token."""
    started = time.monotonic()
    first_answer: float | None = None
    first_reasoning: float | None = None
    stream = llm.chat_complete_stream(
        base_url, "", model,
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}],
        _params(), reasoning=effort,
    )
    text = ""
    try:
        while True:
            delta = next(stream)
            now = time.monotonic() - started
            if delta.reasoning and first_reasoning is None:
                first_reasoning = now
            if delta.answer.strip() and first_answer is None:
                first_answer = now
    except StopIteration as stop:
        text, _prompt_tokens = stop.value
    elapsed = time.monotonic() - started
    return {
        "ttft_s": round(first_answer, 3) if first_answer is not None else None,
        "wall_clock_s": round(elapsed, 3),
        "completion_tokens": None,
        "first_reasoning_s": round(first_reasoning, 3) if first_reasoning is not None else None,
        "chars": len(text),
    }


def probe_completion_tokens(base_url: str, model: str, effort: ReasoningEffort | None) -> int | None:
    """Read ``usage.completion_tokens`` for the same call.

    ``chat_complete_usage`` returns only *prompt* tokens, and the metric under test is
    how many tokens the model SPENDS — which is what a thinking budget moves. Rather than
    widen the production signature for a measurement, issue the identical request here and
    read the field directly. It is a second call, so it is counted as one, and its latency
    is deliberately NOT used for any timing metric.
    """
    import httpx

    url, body, _ = llm._completion_request(
        base_url, "", model,
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}],
        _params(), reasoning=effort, extra_body=None,
    )
    try:
        with httpx.Client(timeout=httpx.Timeout(600.0, connect=5.0)) as client:
            res = client.post(url, json=body)
            usage = (res.json() or {}).get("usage") or {}
            value = usage.get("completion_tokens")
            return int(value) if isinstance(value, int) else None
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--base-url", default="http://localhost:4000/v1")
    parser.add_argument("--model", default="local")
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args()

    exp = args.experiment if args.experiment.is_absolute() else REPO_ROOT / args.experiment
    if not exp.is_dir():
        print(f"no such experiment folder: {exp}", file=sys.stderr)
        return 2

    entrypoint = (
        f"uv run python -m utils.scripts.research.run_live_turn_visibility "
        f"--runs {args.runs} --model {args.model} --experiment {args.experiment}"
    )
    record = RunRecord(entrypoint=entrypoint)
    backend = llm_backend.get_backend(args.base_url, "")
    record.note(f"detected engine for {args.base_url}: {backend.value}")
    record.note(f"budget keys sent when capped: {llm_backend.budget_keys_for(backend)}")

    started_all = time.monotonic()
    failures = 0
    for run in range(1, args.runs + 1):
        for arm in ARMS:
            effort = None if arm == "blocking-uncapped" else ReasoningEffort.MEDIUM
            try:
                row = (
                    run_streaming(args.base_url, args.model, effort)
                    if arm.startswith("streaming")
                    else run_blocking(args.base_url, args.model, effort)
                )
                row["completion_tokens"] = probe_completion_tokens(args.base_url, args.model, effort)
                record.llm_calls += 2  # the timed call + the usage probe
            except Exception as exc:  # a failed run is recorded, never dropped
                failures += 1
                row = {k: None for k in METRIC_KEYS}
                row["error"] = f"{exc.__class__.__name__}: {exc}"
                record.note(f"run {run} arm {arm} FAILED: {row['error']}")
            row.update({"run": run, "arm": arm})
            record.add_run(row)
            print(
                f"run {run} {arm:>18}: ttft={row.get('ttft_s')}s "
                f"wall={row.get('wall_clock_s')}s tokens={row.get('completion_tokens')}",
                flush=True,
            )
    record.wall_clock_seconds = time.monotonic() - started_all

    # Contract: never aggregate over the survivors of a partially-failed experiment.
    # Survivors are not a random subsample, so an aggregate over them is not a mean of
    # anything. Per-run rows are always written either way.
    values: dict[str, Any] = {}
    if failures:
        record.note(
            f"{failures} run(s) failed — NO aggregate computed. Per-arm rows in "
            "data/metrics.json are the result; see ISSUES.md."
        )
    else:
        for arm in ARMS:
            rows = [r for r in record.per_run if r["arm"] == arm]
            for metric, stats in aggregate(rows, METRIC_KEYS).items():
                values[f"{arm}.{metric}"] = stats

    write_environment(exp, record)
    write_metrics(exp, record, values)
    update_manifest(exp, {
        "code": git_block(entrypoint),
        "status": "failed" if failures else "complete",
        "n_runs": args.runs,
        "compute": {
            "hardware": hardware(),
            "wall_clock_hours": round(record.wall_clock_seconds / 3600, 4),
            "estimated_cost_usd": 0.0,
        },
        "llm": {
            "model": f"relay/{args.model}",
            "temperature": 0.7,
            "top_p": 1.0,
            "max_tokens": 8192,
            "prompt_hash": hash_text(SYSTEM + "\n\n" + USER),
        },
        "metrics": {"values": values},
    })
    (exp / "logs" / "run.log").write_text(
        json.dumps({"notes": record.notes, "failures": failures}, indent=2), encoding="utf-8"
    )
    print(f"\n{'FAILED' if failures else 'complete'} — wrote {exp}/data/metrics.json")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
