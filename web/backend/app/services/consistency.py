"""Line-to-line consistency guard (§P10) — catch a beat that breaks continuity.

In a multi-party turn several characters speak in sequence, each reacting to its
predecessor. The guard is the streaming-safe realization of the design's "post-sequence
line-to-line check": before a later speaker's beat is placed on the wire, it is checked
against the beats already established **this turn**; if it plainly contradicts them
(facts, who-did-what, physical state), the engine regenerates that one line with a
corrective note and keeps the sequence order. Checking *before* emit (rather than
un-emitting after) is what makes it compatible with live delta streaming.

It is **best-effort and conservative**: no prior beat, no candidate, an unconfigured or
failed LLM, or a malformed reply all resolve to *consistent* — the guard never blocks a
turn and defaults to trusting the line. The generation takes a **pre-resolved LLM
connection** (not a ``Session``), matching the reflection agent.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents._common import extract_json, gen_params
from app.agents.reflection_agent import LlmConn
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort

# A continuity check is a cheap structural judgement — keep the thinking budget low.
CONSISTENCY_EFFORT = ReasoningEffort.LOW

_SYSTEM = """You are the continuity auditor for a scene. You are given the beats already established THIS turn and ONE new candidate line by the next character. Decide only whether the candidate CONTRADICTS what is already established — a fact, who did what, or a physical state (e.g. claiming someone left when they are present, or an object is gone when it was just handed over). Differences in tone, mood, or opinion are NOT contradictions.

Return ONLY a JSON object: {"consistent": true|false, "reason": "<short why, only when false>"}

Default to "consistent": true unless the contradiction is clear."""


@dataclass
class ConsistencyVerdict:
    """Whether a candidate line is continuous with the established beats."""

    consistent: bool
    reason: str = ""


def review(
    conn: LlmConn,
    *,
    stable_prefix: str,
    prior: str,
    candidate: str,
    reasoning: ReasoningEffort = CONSISTENCY_EFFORT,
) -> ConsistencyVerdict:
    """Judge a candidate line against the established beats (best-effort → consistent)."""
    if not prior.strip() or not candidate.strip():
        return ConsistencyVerdict(True)
    from app.services import llm

    base_url, api_key, model, params = conn
    user = (
        f"Established beats this turn:\n{prior}\n\n"
        f"Candidate next line:\n{candidate}\n\n"
        "Is the candidate consistent with the established beats?"
    )
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [
                {"role": "system", "content": f"{_SYSTEM}\n\n{stable_prefix}".strip()},
                {"role": "user", "content": user},
            ],
            gen_params(params),
            reasoning=reasoning,
        )
        data = extract_json(raw)
    except APIError:
        return ConsistencyVerdict(True)  # best-effort → never block the turn
    return ConsistencyVerdict(bool(data.get("consistent", True)), str(data.get("reason", "")).strip())
