"""Reasoning-effort vocabulary — the backend-controlled thinking budget.

Local reasoning models spend most of their wall-clock on hidden *thinking* tokens
before the visible reply. Mytheca caps that thinking on a **per-operation** basis so
quick classifications (triage) finish fast while richer authoring calls keep a
little more room. The effort is always set on the **backend** at the call-site — it
is never exposed to the user for Storyline / Character / Setting creation.

Each effort maps to a hard token budget for the thinking phase; the engine-specific
request key that carries it is chosen by ``services.llm_backend`` once the engine
(vLLM vs. llama.cpp) is detected.
"""

from __future__ import annotations

from enum import Enum


class ReasoningEffort(str, Enum):
    """How many thinking tokens an operation may spend (none → max)."""

    #: Do not think at all. For an operation that already deliberates *in the output* —
    #: the character turn writes a visible in-voice ``<thinking>`` paragraph — hidden
    #: channel reasoning is a second deliberation nobody reads, paid for in the wait
    #: before the first word of prose. One or the other, not both.
    NONE = "none"
    #: Quick and instinctual — enough to read the room and answer, not to deliberate.
    #: The beat planner runs here: it decides who is up next after EVERY beat, so the
    #: cost is paid once per beat and a slow answer is felt directly by the player.
    QUICK = "quick"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    MAX = "max"


# Effort → thinking-token budget. Values fixed by product spec.
THINKING_BUDGET: dict[ReasoningEffort, int] = {
    ReasoningEffort.NONE: 0,
    ReasoningEffort.QUICK: 128,
    ReasoningEffort.LOW: 256,
    ReasoningEffort.MEDIUM: 512,
    ReasoningEffort.HIGH: 1024,
    ReasoningEffort.VERY_HIGH: 2048,
    ReasoningEffort.MAX: 4096,
}


def budget_for(effort: ReasoningEffort) -> int:
    """Return the thinking-token budget for an effort (defaults to Medium if unknown)."""
    return THINKING_BUDGET.get(effort, THINKING_BUDGET[ReasoningEffort.MEDIUM])


def effort_for_level(level: str | None) -> ReasoningEffort | None:
    """Map a player-facing ``ThinkingLevel`` onto an effort, or ``None`` when unset.

    ``None`` in, ``None`` out, and that round-trip is the point: the turn-level thinking
    control is *optional*, and "the player did not choose" must stay distinguishable from
    "the player chose the lowest level" all the way down to the call site. A call site that
    receives ``None`` keeps its own budget — which for the structured mode's prose call is
    ``NONE``, set after that call was measured spending 91 % of its output on hidden
    reasoning nobody reads.

    An unrecognised string reads as ``None`` for the same reason: a nonsense value is not a
    request, so it must not silently become one.
    """
    if not level:
        return None
    try:
        effort = ReasoningEffort(str(level).strip().lower())
    except ValueError:
        return None
    return None if effort is ReasoningEffort.NONE else effort
