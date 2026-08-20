"""Conversation-scaling runner for EXP-2026-08-005.

Two modes, answering two halves of one question — *does a scene get slower as it gets
longer, and if so is it because the prompt cache is being thrown away?*

``--mode conversation`` drives a real N-turn back-and-forth through
``POST /api/play/{id}/turn`` against a running backend, recording per turn: time to the
first frame, to each trace step, to the first visible prose, the total, how many beats the
turn produced, and the prompt/cached token counts the engine reports. It builds its own
storyline, cast, setting and scenario at the configured settings, so a run does not depend
on what happens to be in the dev database.

``--mode layout`` isolates the mechanism with no app in the loop: the same content, the
same token count, two orderings — volatile-before-transcript (what
``character_turn_agent._build_user_prompt`` does today) and volatile-after-transcript —
measured across a growing transcript.

Usage::

    uv run python -m utils.scripts.research.run_conversation_scaling --mode conversation \\
        --turns 10 --max-turns 5 --context-beats 100 --suggestions 0 \\
        --experiment docs/research/experiments/EXP-2026-08-005-conversation-scaling
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import REPO_ROOT
from .record import (
    RunRecord,
    git_block,
    hardware,
    hash_text,
    update_manifest,
    write_environment,
    write_metrics,
)

API = "http://localhost:3345/api"

# A scripted player side. Fixed, so a rerun drives the identical conversation and the only
# thing that varies between turns is how much history has accumulated.
PLAYER_LINES = [
    "I set my cup down and look around the room.",
    "I ask who else has been here tonight.",
    "I mention the drowned ledger, and watch faces.",
    "I say the harbour watch already knows about the salt.",
    "I offer to trade what I know for what they know.",
    "I press on the name nobody wants to say.",
    "I put a coin on the table and leave my hand on it.",
    "I ask what happens if I walk out that door right now.",
    "I say I will take the risk anyway.",
    "I ask for one honest answer before I go.",
]

# Frames that put something on screen. `internal_thought` counts toward "first visible"
# (it is the first thing a player sees) but NOT as a beat — the scenario's maxTurns caps
# emitted BEATS, and counting a character's thought and their spoken line as two would
# make a 5-beat cap look as though it had been exceeded.
VISIBLE = {"narration", "internal_thought", "character_dialogue", "character_action"}
BEATS = {"narration", "character_dialogue", "character_action"}


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        return json.load(res)


def _patch(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


def build_world(max_turns: int, suggestions: int, context_beats: int) -> tuple[str, str]:
    """Create a throwaway storyline + cast + setting + scenario at the given settings."""
    sl = _post("/storylines", {
        "title": "Scaling Probe",
        "genre": "noir",
        "premise": "A harbour city where a truce between smugglers and the watch is fraying.",
    })["id"]
    cast = [
        _post(f"/storylines/{sl}/characters", {"name": name, "role": role})["id"]
        for name, role in (("Mei", "fence"), ("Kira", "harbour watch"), ("Aldous", "archivist"))
    ]
    setting = _post(f"/storylines/{sl}/settings", {
        "name": "The Smoldering Hearth",
        "desc": "A back room behind a dockside tavern, rain on the shutters.",
    })["id"]
    scenario = _post(f"/storylines/{sl}/scenarios", {
        "title": "Salt and Ledgers",
        "castIds": cast,
        "settingId": setting,
        "maxTurns": max_turns,
        "suggestionsCount": suggestions,
        "contextBeats": context_beats,
    })["id"]
    # Confirm the settings actually landed — a silently-clamped value would invalidate the
    # whole run, and the schema does clamp (context_beats 5..100, suggestions 0..4).
    got = _patch(f"/scenarios/{scenario}", {})
    applied = {
        "maxTurns": got.get("maxTurns"),
        "suggestionsCount": got.get("suggestionsCount"),
        "contextBeats": got.get("contextBeats"),
    }
    if applied != {"maxTurns": max_turns, "suggestionsCount": suggestions,
                   "contextBeats": context_beats}:
        raise SystemExit(f"scenario settings were not applied as requested: {applied}")
    return scenario, sl


def _gaps(marks: dict[str, float]) -> dict[str, float]:
    """Seconds spent between consecutive milestones, in arrival order.

    The offsets alone say when each step landed; the gaps say which step the turn was
    actually stuck in. A step that appears late because everything before it was slow
    looks identical to a slow step until you subtract.
    """
    ordered = sorted(marks.items(), key=lambda kv: kv[1])
    out: dict[str, float] = {}
    previous = 0.0
    for name, at in ordered:
        out[name] = round(at - previous, 3)
        previous = at
    return out


def run_turn(scenario: str, session: str | None, text: str) -> dict[str, Any]:
    """Drive one player turn, timing every frame class as it arrives."""
    payload: dict[str, Any] = {"text": text, "trace": True}
    if session:
        payload["sessionId"] = session
    req = urllib.request.Request(
        f"{API}/play/{scenario}/turn", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    started = time.monotonic()
    marks: dict[str, float] = {}
    steps: list[str] = []
    prompt_tokens: list[int] = []
    cached_tokens: list[int] = []
    # Locally-computed prompt reuse (see api-contract "reusablePrefixChars"): the share of
    # each character prompt that was byte-identical to the previous one in this session.
    # Recorded separately from `cached_tokens` because this endpoint omits its own cache
    # counter when the hit is zero — the case most worth catching.
    reuse_ratios: list[float] = []
    reasoning_frames = 0
    first_reasoning: float | None = None
    beats = 0
    session_id = session
    error: str | None = None

    with urllib.request.urlopen(req, timeout=1800) as res:
        first_byte = None
        for raw in res:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            now = time.monotonic() - started
            if first_byte is None:
                first_byte = now
            try:
                frame = json.loads(line)
            except ValueError:
                continue
            kind = frame.get("type")
            session_id = frame.get("sessionId") or session_id
            if kind == "trace":
                step = frame.get("step", "")
                steps.append(step)
                # Number the repeats: `speaker` and `context` fire once per beat, and a
                # turn's cost is mostly in the later ones, which a first-occurrence-only
                # mark would hide entirely.
                seen = sum(1 for prior in steps if prior == step)
                marks.setdefault(f"step:{step}", now)
                if seen > 1:
                    marks.setdefault(f"step:{step}#{seen}", now)
                data = frame.get("data") or {}
                if step == "context":
                    if isinstance(data.get("promptTokens"), int):
                        prompt_tokens.append(data["promptTokens"])
                    if isinstance(data.get("cachedTokens"), int):
                        cached_tokens.append(data["cachedTokens"])
                    reusable = data.get("reusablePrefixChars")
                    chars = data.get("promptChars")
                    if isinstance(reusable, int) and isinstance(chars, int) and chars:
                        reuse_ratios.append(reusable / chars)
            elif kind == "reasoning":
                # On the wire by default since the visibility change — and the first thing
                # the player actually sees, so it is the honest "time to something".
                reasoning_frames += 1
                if first_reasoning is None:
                    first_reasoning = now
            elif kind == "error":
                error = frame.get("message")
            elif kind in VISIBLE:
                marks.setdefault("first_visible", now)
                marks.setdefault(f"first_{kind}", now)
                if frame.get("data", {}).get("done") and kind in BEATS:
                    beats += 1
    total = time.monotonic() - started

    return {
        "session_id": session_id,
        "error": error,
        "first_byte_s": round(first_byte or total, 3),
        "first_visible_s": round(marks["first_visible"], 3) if "first_visible" in marks else None,
        "reading_s": round(marks["step:reading"], 3) if "step:reading" in marks else None,
        "planning_s": round(marks["step:planning"], 3) if "step:planning" in marks else None,
        "first_speaker_s": round(marks["step:speaker"], 3) if "step:speaker" in marks else None,
        # Every step's first-occurrence offset, and the gap from the previous step — this
        # is what "measure it at every step of the way" actually needs. Without the gaps
        # the row says when things happened but not which one was expensive.
        "step_marks": {k: round(v, 3) for k, v in marks.items()},
        "step_gaps": _gaps(marks),
        "total_s": round(total, 3),
        "beats": beats,
        "llm_calls": len([s for s in steps if s == "context"]),
        # Per-turn context size and reuse. `max` rather than mean: the largest character
        # call is the one that carries the full transcript, so it is the honest measure of
        # how big the prompt has become.
        "prompt_tokens_max": max(prompt_tokens) if prompt_tokens else None,
        "cached_tokens_max": max(cached_tokens) if cached_tokens else None,
        "cache_hit_ratio": (
            round(max(cached_tokens) / max(prompt_tokens), 4)
            if prompt_tokens and cached_tokens and max(prompt_tokens) else None
        ),
        # Mean over the turn's character calls, not max: every call's reuse matters, and a
        # single warm call would not tell you the layout is working.
        "reuse_ratio_mean": (
            round(sum(reuse_ratios) / len(reuse_ratios), 4) if reuse_ratios else None
        ),
        "reuse_ratio_min": round(min(reuse_ratios), 4) if reuse_ratios else None,
        "planner_calls": len([s for s in steps if s == "planning"]),
        "reasoning_frames": reasoning_frames,
        "first_reasoning_s": round(first_reasoning, 3) if first_reasoning is not None else None,
        "trace_steps": len(steps),
    }


def mode_conversation(args, record: RunRecord) -> None:
    scenario, storyline = build_world(args.max_turns, args.suggestions, args.context_beats)
    record.note(f"scenario={scenario} storyline={storyline} "
                f"maxTurns={args.max_turns} suggestions={args.suggestions} "
                f"contextBeats={args.context_beats}")
    session: str | None = None
    for turn in range(1, args.turns + 1):
        text = PLAYER_LINES[(turn - 1) % len(PLAYER_LINES)]
        try:
            row = run_turn(scenario, session, text)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            row = {"error": f"{exc.__class__.__name__}: {exc}"}
            record.note(f"turn {turn} FAILED: {row['error']}")
        session = row.get("session_id") or session
        row["turn"] = turn
        record.add_run(row)
        print(
            f"turn {turn:>2}: first_visible={row.get('first_visible_s')}s "
            f"total={row.get('total_s')}s beats={row.get('beats')} "
            f"prompt={row.get('prompt_tokens_max')} reuse={row.get('reuse_ratio_mean')} "
            f"plan_calls={row.get('planner_calls')} first_reason={row.get('first_reasoning_s')} "
            f"hit={row.get('cache_hit_ratio')}",
            flush=True,
        )
        if row.get("error"):
            record.note(f"turn {turn} reported an error frame: {row['error']}")


# ---- layout mode ------------------------------------------------------------

BACKEND = REPO_ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

SYSTEM = ("OUTPUT CONTRACT: emit thin tags only.\n\nWORLD: Embergate (noir).\n\nWORLD PRIMER\n"
          + "A rain-soaked harbour city where the smuggling families and the harbour watch have "
            "held an uneasy truce for eleven years. Coin talks; names matter more. " * 10)


def _volatile(turn: int) -> str:
    """The block the app puts in the prompt HEAD: identity + CURRENT stat values."""
    return (f"You are [1] Mei — a fence.\nTraits: wary, patient.\n"
            f"Your current state: patience {10 - turn}/10, suspicion {turn}/10, trust {turn}/10.\n")


# A character beat's worth of prose. Real beats are paragraphs, not one-liners, and a
# probe built from one-liners produces a prompt too small for prefill to dominate the
# noise on a shared GPU — which would hide the very effect being measured.
_BEAT = (
    "Mei turns the cup a quarter turn on the wood and does not look up. \"You say that "
    "like the ledger is a thing a person can simply ask after,\" she says. \"Down here a "
    "question like that is a debt, and debts get collected in weather like this. I have "
    "watched three people ask it since the truce. Two of them left by the back door and "
    "one of them did not leave at all.\""
)


def _transcript(turn: int) -> str:
    """An append-only transcript that grows by two realistic beats per turn."""
    lines = []
    for i in range(1, turn + 1):
        lines.append(f"Player: {PLAYER_LINES[(i - 1) % len(PLAYER_LINES)]}")
        lines.append(f"Mei: {_BEAT} (beat {i})")
    return "Recent beats:\n" + "\n".join(lines)


def _time_call(args, system: str, user: str) -> dict[str, Any]:
    """Issue one streamed call; return prefill-proxy timing and whatever usage is reported.

    ``ttft_s`` (time to the first token of any channel) is dominated by prefill, so it is
    the behavioural proxy for prefix-cache reuse. That proxy is not a luxury: the remote
    GPU route reports ``prompt_tokens_details: null``, so on that endpoint there is no
    cached-token counter to read and latency is the only available evidence.
    """
    from app.schemas.settings import LlmParams
    from app.services import llm

    usage: dict = {}
    # Enough headroom that a reasoning model reaches a visible answer; this call's
    # COMPLETION is irrelevant, only how long the prompt took to ingest.
    params = LlmParams(temperature=0.0, max_tokens=2048)
    started = time.monotonic()
    first: float | None = None
    attempts = 0
    last_error = ""
    # The deployed endpoint intermittently returns an empty completion (~30% of turns in
    # the conversation run). Retrying stops a transient upstream failure from deleting a
    # cache measurement; the attempt count is recorded as evidence of the failure rate
    # rather than hidden by the retry.
    for attempt in range(1, args.retries + 2):
        attempts = attempt
        usage.clear()
        started = time.monotonic()
        first = None
        try:
            stream = llm.chat_complete_stream(
                args.base_url, "", args.model,
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                params, usage_out=usage,
            )
            while True:
                try:
                    delta = next(stream)
                except StopIteration:
                    break
                if first is None and (delta.answer or delta.reasoning):
                    first = time.monotonic() - started
            break
        except Exception as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
    else:
        return {"error": last_error, "attempts": attempts}
    total = time.monotonic() - started
    pt, ct = usage.get("prompt_tokens"), usage.get("cached_tokens")
    return {
        "attempts": attempts,
        "ttft_s": round(first, 3) if first is not None else None,
        "wall_clock_s": round(total, 3),
        "prompt_tokens": pt,
        "cached_tokens": ct,
        "cache_hit_ratio": round(ct / pt, 4) if pt and ct is not None else None,
    }


def mode_layout(args, record: RunRecord) -> None:
    """Walk a growing transcript twice — once in each prompt layout — and watch prefill.

    If a turn's prompt reuses the previous turn's prefix, prefill stays roughly flat as the
    transcript grows. If every turn re-reads the whole conversation, prefill climbs with it.
    That is the difference between a scene that stays responsive and one that gets slower
    the longer you play it.

    Passes alternate which layout goes first and carry a pass-specific salt in the system
    preamble, so no pass can inherit a warm cache from an earlier one — the ordering
    confound that made EXP-2026-08-003's cross-arm numbers unusable.
    """
    layouts = ("volatile-first", "volatile-last")
    # Either walk every history length 1..turns (the conversation-shaped default) or sample
    # specific ones. Sampling is what makes a LONG-context question affordable: the effect
    # under test scales with transcript size, and a probe that stops at ~1.5k tokens cannot
    # see something that only matters at 20k.
    sizes = (
        [int(n) for n in args.sizes.split(",") if n.strip()]
        if args.sizes else list(range(1, args.turns + 1))
    )
    for pass_no in range(1, args.passes + 1):
        order = layouts if pass_no % 2 else tuple(reversed(layouts))
        for layout in order:
            salt = f"\n\n[cache-probe pass {pass_no} {layout}]"
            system = SYSTEM + salt
            for turn in sizes:
                # A plain ask: the app's thin-tag output contract is not what is under
                # test, and an instruction the model sometimes answers with nothing costs
                # measurements without telling us anything about the cache.
                ask = "\n\nReply with one short sentence of dialogue for Mei."
                user = (
                    _volatile(turn) + _transcript(turn) + ask
                    if layout == "volatile-first"
                    else _transcript(turn) + "\n" + _volatile(turn) + ask
                )
                row = _time_call(args, system, user)
                if row.get("error"):
                    record.note(f"pass {pass_no} {layout} turn {turn} FAILED: {row['error']}")
                row.update({"pass": pass_no, "turn": turn, "layout": layout})
                record.add_run(row)
                record.llm_calls += 1
                print(
                    f"pass {pass_no} {layout:<15} turn {turn:>2}: "
                    f"ttft={row.get('ttft_s')}s prompt={row.get('prompt_tokens')} "
                    f"cached={row.get('cached_tokens')} hit={row.get('cache_hit_ratio')}",
                    flush=True,
                )


# ---- budget mode ------------------------------------------------------------


def mode_budget(args, record: RunRecord) -> None:
    """Does this endpoint actually honour a thinking-token budget?

    It matters because a model that thinks past its budget produces no prose at all, which
    reaches the player as a failed turn — 3 of 10 in the conversation run. The app detects
    the relay as RELAY and therefore sends BOTH engine keys; this checks whether that has
    any effect, against sending one or none, on a prompt that invites deliberation.
    """
    import httpx

    from app.services import llm

    conditions = {
        "none": {},
        "vllm-key": {"thinking_token_budget": args.budget},
        "llamacpp-key": {"thinking_budget_tokens": args.budget},
        "both-keys": {
            "thinking_token_budget": args.budget,
            "thinking_budget_tokens": args.budget,
        },
    }
    messages = [{"role": "user", "content":
                 "Think carefully about what a fence in a harbour city would say to a "
                 "stranger offering coin, then reply with one short sentence."}]

    for run in range(1, args.turns + 1):
        for name, extra in conditions.items():
            body = {"model": args.model, "messages": messages, "max_tokens": 800,
                    "temperature": 0.0, **extra}
            row: dict[str, Any] = {"run": run, "condition": name}
            try:
                with httpx.Client(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
                    res = client.post(f"{args.base_url}/chat/completions", json=body)
                    payload = res.json()
                choice = (payload.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                reasoning = llm._reasoning_field(message)
                row.update({
                    "reasoning_chars": len(reasoning),
                    "content_chars": len(message.get("content") or ""),
                    "completion_tokens": (payload.get("usage") or {}).get("completion_tokens"),
                    "finish_reason": choice.get("finish_reason"),
                })
            except Exception as exc:
                row["error"] = f"{exc.__class__.__name__}: {exc}"
                record.note(f"run {run} {name} FAILED: {row['error']}")
            record.add_run(row)
            record.llm_calls += 1
            print(f"run {run} {name:<13}: reasoning={row.get('reasoning_chars')} "
                  f"content={row.get('content_chars')} "
                  f"completion_tokens={row.get('completion_tokens')} "
                  f"finish={row.get('finish_reason')}", flush=True)


def mode_decode(args, record: RunRecord) -> None:
    """Is the endpoint itself generating at the same rate as it was on an earlier day?

    A before/after that compares two code versions measured on different days is only
    honest if the thing underneath them has not moved. Prefill is covered by ``layout``
    mode (time to first token); this covers **decode**, which is where a turn's seconds
    actually go — and it also records the ``model`` string the response reports, because
    this relay routes ``skynet`` with ``upstream_model: auto`` and can hot-swap the model
    under a run without anything else changing.

    Fixed prompt, temperature 0, the same budget keys the app sends.
    """
    import httpx

    messages = [{"role": "user", "content":
                 "Think carefully about what a fence in a harbour city would say to a "
                 "stranger offering coin, then reply with one short sentence."}]
    body = {"model": args.model, "messages": messages, "max_tokens": 800,
            "temperature": 0.0,
            "thinking_token_budget": args.budget, "thinking_budget_tokens": args.budget}

    for run in range(1, args.turns + 1):
        row: dict[str, Any] = {"run": run}
        started = time.monotonic()
        try:
            with httpx.Client(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
                res = client.post(f"{args.base_url}/chat/completions", json=body)
                payload = res.json()
            elapsed = time.monotonic() - started
            usage = payload.get("usage") or {}
            completion = usage.get("completion_tokens")
            row.update({
                "elapsed_s": round(elapsed, 3),
                "served_model": payload.get("model"),
                "completion_tokens": completion,
                "prompt_tokens": usage.get("prompt_tokens"),
                "tokens_per_s": round(completion / elapsed, 2) if completion and elapsed else None,
                "finish_reason": ((payload.get("choices") or [{}])[0]).get("finish_reason"),
            })
        except Exception as exc:
            row["error"] = f"{exc.__class__.__name__}: {exc}"
            record.note(f"decode run {run} FAILED: {row['error']}")
        record.add_run(row)
        record.llm_calls += 1
        print(f"run {run}: {row.get('completion_tokens')} tok in {row.get('elapsed_s')}s "
              f"= {row.get('tokens_per_s')} tok/s · served={row.get('served_model')} "
              f"· finish={row.get('finish_reason')}", flush=True)


def mode_plan(args, record: RunRecord) -> None:
    """Does the planner actually return the several beats it is asked for?

    ``TURN_PLANNER_LOOKAHEAD`` only pays if the model honours the multi-beat contract. The
    conversation run suggested it often does not (planner calls barely fell), but that
    inference is confounded: a call can also be "wasted" by a plan going stale. This asks
    the question directly, and the metric — how many beats came back — is a **count**, so
    it is immune to the endpoint's throughput variance.
    """
    import httpx

    from app.agents import planner_agent
    from app.agents._common import extract_json

    system = planner_agent._SYSTEM
    roster = "\n".join(f"[{i}] Character{i} — a role" for i in (1, 2, 3))
    user = (
        f"Roster:\n{roster}\n\n"
        "Player's direction: (freeform).\n"
        "Characters who have ALREADY taken a beat this turn (roster numbers): none\n\n"
        "This turn so far:\nPlayer: I put the pouch on the table and wait.\n\n"
    )
    # Interleaved arms in ONE session — the methodology EXP-2026-08-006's own threats
    # section says any future latency comparison on this app has to use. ``want=1`` is the
    # pre-lookahead request, byte-identical to what ``next_beat`` sends.
    for run in range(1, args.turns + 1):
        for want in (1, args.budget) if run % 2 else (args.budget, 1):
            ask = (
                "What is the next beat?"
                if want == 1
                else (
                    f"Plan the next {want} beats, in order. Return "
                    '{"beats": [<beat>, <beat>, ...]} where each <beat> is the JSON object '
                    "described above. Stop the list early — with an \"end\" beat, or simply "
                    "fewer entries — if the turn should finish sooner. Judge each beat from "
                    "the situation as it will stand after the ones you planned before it."
                )
            )
            row: dict[str, Any] = {"run": run, "asked_for": want}
            started = time.monotonic()
            try:
                with httpx.Client(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
                    res = client.post(f"{args.base_url}/chat/completions", json={
                        "model": args.model,
                        "messages": [{"role": "system", "content": system},
                                     {"role": "user", "content": user + ask}],
                        "max_tokens": 2000, "temperature": 0.0,
                        "thinking_token_budget": 512, "thinking_budget_tokens": 512,
                    })
                    payload = res.json()
                elapsed = time.monotonic() - started
                message = (payload.get("choices") or [{}])[0].get("message") or {}
                data = extract_json(message.get("content") or "")
                beats = data.get("beats")
                returned = len(beats) if isinstance(beats, list) else (1 if data.get("action") else 0)
                row.update({
                    "elapsed_s": round(elapsed, 3),
                    "returned": returned,
                    # Seconds per beat actually planned — the number that decides whether
                    # asking for several is cheaper than asking repeatedly for one.
                    "seconds_per_beat": round(elapsed / returned, 3) if returned else None,
                    "shape": "beats-array" if isinstance(beats, list) else
                             ("single-object" if data.get("action") else "unparseable"),
                    "completion_tokens": (payload.get("usage") or {}).get("completion_tokens"),
                    "served_model": payload.get("model"),
                })
            except Exception as exc:
                row["error"] = f"{exc.__class__.__name__}: {exc}"
                record.note(f"plan run {run} want={want} FAILED: {row['error']}")
            record.add_run(row)
            record.llm_calls += 1
            print(f"run {run} want={want}: got {row.get('returned')} beat(s) in "
                  f"{row.get('elapsed_s')}s = {row.get('seconds_per_beat')}s/beat "
                  f"({row.get('shape')}, {row.get('completion_tokens')} tok)", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("conversation", "layout", "budget", "decode", "plan"), required=True)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--max-turns", type=int, default=5)
    parser.add_argument("--suggestions", type=int, default=0)
    parser.add_argument("--context-beats", type=int, default=100)
    parser.add_argument("--base-url", default="http://localhost:4000/v1")
    parser.add_argument("--model", default="skynet")
    parser.add_argument("--sizes", default="",
                        help="layout mode: comma-separated history lengths to sample "
                             "(e.g. 10,50,100,200,400) instead of walking 1..turns")
    parser.add_argument("--budget", type=int, default=128,
                        help="budget mode: thinking-token budget to request")
    parser.add_argument("--retries", type=int, default=2,
                        help="retries per call; the deployed endpoint intermittently returns empty")
    parser.add_argument("--passes", type=int, default=2,
                        help="layout mode: how many counterbalanced passes to run")
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args()

    exp = args.experiment if args.experiment.is_absolute() else REPO_ROOT / args.experiment
    if not exp.is_dir():
        print(f"no such experiment folder: {exp}", file=sys.stderr)
        return 2

    entrypoint = (
        f"uv run python -m utils.scripts.research.run_conversation_scaling --mode {args.mode} "
        f"--turns {args.turns} --max-turns {args.max_turns} --suggestions {args.suggestions} "
        f"--context-beats {args.context_beats} --experiment {args.experiment}"
    )
    record = RunRecord(entrypoint=entrypoint)
    started = time.monotonic()
    {"conversation": mode_conversation, "layout": mode_layout,
     "budget": mode_budget, "decode": mode_decode,
     "plan": mode_plan}[args.mode](args, record)
    record.wall_clock_seconds = time.monotonic() - started

    failures = sum(1 for r in record.per_run if r.get("error"))
    if failures:
        record.note(
            f"{failures} turn(s) failed — NO aggregate computed. Per-turn rows are the "
            "result; see ISSUES.md."
        )

    # Deliberately no aggregate over turns even on a clean run: the whole question is how
    # the numbers CHANGE from turn to turn, and a mean over a growing series hides exactly
    # that. Every per-turn row is written; the trend is the finding.
    write_environment(exp, record)
    write_metrics(exp, record, {})
    update_manifest(exp, {
        "code": git_block(entrypoint),
        "status": "failed" if failures else "complete",
        "n_runs": args.turns,
        "compute": {
            "hardware": hardware(),
            "wall_clock_hours": round(record.wall_clock_seconds / 3600, 4),
            "estimated_cost_usd": 0.0,
        },
        "llm": {"model": f"relay/{args.model}", "prompt_hash": hash_text(SYSTEM)},
    })
    log = exp / "logs" / f"{args.mode}.log"
    log.write_text(json.dumps({"notes": record.notes, "failures": failures,
                               "rows": record.per_run}, indent=2), encoding="utf-8")
    print(f"\n{'FAILED' if failures else 'complete'} — wrote {log}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
