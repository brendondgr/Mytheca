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
    """How many thinking tokens an operation may spend (low → max)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    MAX = "max"


# Effort → thinking-token budget. Values fixed by product spec.
THINKING_BUDGET: dict[ReasoningEffort, int] = {
    ReasoningEffort.LOW: 256,
    ReasoningEffort.MEDIUM: 512,
    ReasoningEffort.HIGH: 1024,
    ReasoningEffort.VERY_HIGH: 2048,
    ReasoningEffort.MAX: 4096,
}


def budget_for(effort: ReasoningEffort) -> int:
    """Return the thinking-token budget for an effort (defaults to Medium if unknown)."""
    return THINKING_BUDGET.get(effort, THINKING_BUDGET[ReasoningEffort.MEDIUM])
