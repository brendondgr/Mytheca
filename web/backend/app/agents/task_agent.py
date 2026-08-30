"""The checklist a free-text turn writes for itself, and the grade it gives itself after.

This is the whole quality mechanism of free-text mode, standing where the planner stands in
the structured engine — and it is a fundamentally different kind of thing. The planner decides
**structure**: who speaks, in what order, at what pitch, and the engine dispatches on every
field of its answer. The checklist decides **nothing**. It is a list of outcomes, the engine
executes none of it, and the only thing it is ever compared against is the prose that was
actually written.

That distinction has to be defended in code as well as in prose, because a `who` field is
exactly the shape of a schedule and the temptation to dispatch on it will be real. It is a
note about who is involved. Nothing reads it but the writer.

**Two calls, deliberately.** Writing and grading are separate generations because a model
asked to do both in one pass grades the essay it meant to write. The second call sees the
finished body and the list, and nothing else it needs to be talked out of.

Best-effort throughout. No endpoint or an unparseable reply means an empty checklist, which
means the turn writes a passage and stops — which is exactly the mode's third path (a plain
character turn) and a perfectly good scene.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents import prompt_registry
from app.agents._common import decision_timeout, extract_json, resolve_llm
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import freetext_context, llm
from app.services.assembler import CastMember, TurnContext

logger = logging.getLogger("mytheca.turn")

#: Both calls are structural judgements over material that is already in front of them, so
#: neither needs the budget the structured engine's planner spends inventing a turn shape.
TASKS_EFFORT = ReasoningEffort.LOW
REVIEW_EFFORT = ReasoningEffort.LOW

#: The most a single turn may owe. Past this the model is planning a scene rather than an
#: exchange, and every extra item is another thing the review can send the turn back for.
MAX_TASKS = 4

#: The grades a task may come back with. Anything else reads as ``"partial"`` — the safe
#: direction, because it costs a continuation pass rather than losing what the player asked
#: for. Same one-sided bias the structured engine's delivery check takes.
STATES = ("yes", "partial", "no")

_TASKS_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "maxItems": MAX_TASKS,
            "items": {
                "type": "object",
                "properties": {
                    "must": {"type": "string"},
                    "who": {"type": "array", "items": {"type": ["integer", "null"]}},
                },
                "required": ["must"],
            },
        }
    },
    "required": ["tasks"],
}

_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "integer"},
                    "state": {"type": "string", "enum": list(STATES)},
                    "note": {"type": "string"},
                },
                "required": ["task", "state"],
            },
        }
    },
    "required": ["verdicts"],
}


@dataclass
class Task:
    """One outcome the turn owes, and how the last review judged it."""

    n: int
    must: str
    #: Character names the checklist expects to carry it. **Never dispatched on.**
    who: list[str] = field(default_factory=list)
    #: ``""`` until graded, then one of :data:`STATES`.
    state: str = ""
    note: str = ""

    @property
    def delivered(self) -> bool:
        return self.state == "yes"


def outstanding(tasks: list[Task]) -> list[Task]:
    """Everything not yet graded ``yes``, in the order it was asked for.

    An ungraded task counts as outstanding: a review that failed to return a verdict for an
    item has told us nothing about it, and treating silence as delivery is how a requirement
    disappears without anyone noticing.
    """
    return [t for t in tasks if not t.delivered]


def _ask(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    *,
    instruction: str,
    schema: dict,
    schema_name: str,
    effort: ReasoningEffort,
    lore: str | None,
    pov: CastMember | None,
    extra: list[str] | None = None,
) -> dict | None:
    """One structural call on the shared prefix. ``None`` on any failure."""
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return None
    messages = freetext_context.messages(
        ctx, turn_beats, instruction=instruction, lore=lore, pov=pov, extra=extra
    )
    body = {
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema},
        }
    }
    for extra_body in (body, None):
        try:
            raw = llm.chat_complete(
                base_url, api_key, model, messages, params,
                reasoning=effort, extra_body=extra_body, timeout_s=decision_timeout(),
            )
            return extract_json(raw)
        except APIError:
            # Constrained first, unconstrained once: a server without `response_format`
            # rejects the request outright, and that is a different thing from being down.
            continue
    logger.debug("free-text %s: endpoint unavailable", schema_name)
    return None


def write_checklist(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    *,
    lore: str = "",
    pov: CastMember | None = None,
) -> list[Task]:
    """What this turn owes the player. ``[]`` on any failure — the turn then simply writes.

    Roster numbers in ``who`` are resolved to **names** here rather than carried as ids,
    because the only consumer is a prompt, where a name is what the writer can act on. It is
    also a small structural guarantee: an id could be dispatched on, and a name cannot be
    mistaken for one.
    """
    instruction = ctx.prompts.get(prompt_registry.FREETEXT_TASKS, _TASKS)
    present = [m for m in ctx.cast if m.is_present]
    data = _ask(
        db, ctx, turn_beats,
        instruction=instruction, schema=_TASKS_SCHEMA, schema_name="turn_tasks",
        effort=TASKS_EFFORT, lore=lore, pov=pov,
    )
    if not data:
        return []
    rows = data.get("tasks")
    if not isinstance(rows, list):
        return []

    by_number = {i + 1: m.name for i, m in enumerate(present)}
    tasks: list[Task] = []
    for row in rows[:MAX_TASKS]:
        if not isinstance(row, dict):
            continue
        must = str(row.get("must") or "").strip()
        if not must:
            continue
        raw_who = row.get("who")
        who = [
            name
            for entry in (raw_who if isinstance(raw_who, list) else [])
            if (name := by_number.get(_as_int(entry))) is not None
        ]
        tasks.append(Task(n=len(tasks) + 1, must=must, who=list(dict.fromkeys(who))))
    return tasks


def review(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    tasks: list[Task],
    body: str,
    *,
    lore: str = "",
    pov: CastMember | None = None,
) -> list[Task]:
    """Grade ``body`` against ``tasks``, returning the same tasks with their states filled.

    A review that cannot run leaves every state **empty**, which :func:`outstanding` reads as
    not delivered — so a failed review sends the turn into one continuation pass rather than
    silently declaring the checklist met. That is the wrong-but-cheap direction on purpose: an
    extra passage costs the reader some prose, where a false "yes" costs them the thing they
    asked for.
    """
    if not tasks or not body.strip():
        return tasks
    instruction = ctx.prompts.get(prompt_registry.FREETEXT_REVIEW, _REVIEW)
    listed = "\n".join(f"{t.n}. {t.must}" for t in tasks)
    data = _ask(
        db, ctx, turn_beats,
        instruction=instruction, schema=_REVIEW_SCHEMA, schema_name="turn_review",
        effort=REVIEW_EFFORT, lore=lore, pov=pov,
        extra=[
            f"WHAT THIS TURN OWED:\n{listed}",
            f"THE PASSAGE THAT WAS WRITTEN:\n{body.strip()}",
        ],
    )
    if not data:
        return tasks
    rows = data.get("verdicts")
    if not isinstance(rows, list):
        return tasks

    by_n = {t.n: t for t in tasks}
    for row in rows:
        if not isinstance(row, dict):
            continue
        task = by_n.get(_as_int(row.get("task")))
        if task is None:
            continue
        state = str(row.get("state") or "").strip().lower()
        task.state = state if state in STATES else "partial"
        task.note = str(row.get("note") or "").strip()[:200]
    return tasks


def _as_int(value) -> int:
    """Best-effort int; ``-1`` for anything that is not one (never matches a task or roster)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


_TASKS = prompt_registry.default(prompt_registry.FREETEXT_TASKS)
_REVIEW = prompt_registry.default(prompt_registry.FREETEXT_REVIEW)
