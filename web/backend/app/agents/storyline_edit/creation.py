"""``storyline_creation_agent`` — generative breadth from a blank/partial start.

Its priors are invention and coherence across a not-yet-persisted storyline: it
proposes a consistent title/genre/tagline/premise/World-Primer/stat-schema set from
the author's seed and whatever they have already written, respecting any field left
out of write scope (a pinned field). It shares the whole plan → approve machinery
with the editor; only the persona differs and there is no storyline id yet.
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

_CREATION_SYSTEM = (
    "You are Mytheca's storyline **creator**. You help an author invent a new "
    "interactive-fiction world by talking it through and proposing a coherent set of "
    "fields — title, genre, tagline, premise, the agent-facing World Primer, and a small "
    "stat schema. Build on whatever the author has already written (shown as current "
    "values); never overwrite a field that is not in your write scope. Aim for a vivid, "
    "internally-consistent world where the premise, primer, and stats reinforce one "
    "another. Discuss first when the author is thinking aloud; propose a plan when they "
    "ask you to draft or change something."
)


def storyline_creation_agent(
    db: Session,
    *,
    scope: ScopeState,
    messages: list[AgentMessage],
    fields: StorylineFieldsSnapshot,
    reasoning: ReasoningEffort = core.DEFAULT_AUTHORING_EFFORT,
) -> Iterator[AgentMessageFrame | AgentPlanFrame]:
    return core.converse(
        db,
        persona=_CREATION_SYSTEM,
        storyline_id=None,
        scope=scope,
        messages=messages,
        fields=fields,
        low_temp=False,
        reasoning=reasoning,
    )
