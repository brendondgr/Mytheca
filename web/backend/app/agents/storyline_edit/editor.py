"""``storyline_editor_agent`` — surgical edits to an existing, persisted storyline.

Its priors are minimal, faithful, in-scope change: alter exactly what the author
asks and preserve everything else. Low temperature for repeatability. Shares the
plan schema, dynamic-schema builder, diff guard, and conversation engine with the
creation agent; only the persona + starting state differ.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.agents.storyline_edit import core
from app.schemas.reasoning import ReasoningEffort
from app.schemas.storyline_edit import (
    AgentMessage,
    AgentMessageFrame,
    AgentPlanFrame,
    ScopeState,
    StorylineFieldsSnapshot,
)

_EDITOR_SYSTEM = (
    "You are Mytheca's storyline **editor**. You help an author refine an existing "
    "interactive-fiction storyline by discussing it plainly and proposing precise, "
    "minimal edits. Prefer the smallest change that satisfies the request; preserve the "
    "author's voice, the premise's continuity, and every field you were not asked to "
    "touch. When you propose a change, say briefly why. Never invent facts about the "
    "world that contradict the context you were given. The World Primer is agent-facing "
    "runtime context injected into every scene — treat edits to it with extra care and "
    "always surface the full before/after."
)


def storyline_editor_agent(
    db: Session,
    *,
    storyline_id: str,
    scope: ScopeState,
    messages: list[AgentMessage],
    fields: StorylineFieldsSnapshot,
    docs_overview: str | None = None,
    reasoning: ReasoningEffort = core.DEFAULT_AUTHORING_EFFORT,
) -> Iterator[AgentMessageFrame | AgentPlanFrame]:
    return core.converse(
        db,
        persona=_EDITOR_SYSTEM,
        storyline_id=storyline_id,
        scope=scope,
        messages=messages,
        fields=fields,
        low_temp=True,
        docs_overview=docs_overview,
        reasoning=reasoning,
    )
