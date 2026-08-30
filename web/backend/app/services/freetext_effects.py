"""Consequences declared by a passage that belongs to nobody in particular.

The structured engine always knows whose beat it is applying a consequence to — the engine
chose the speaker, so ``<type:state_update>`` needs no subject. A free-text body has no
speaker. Mei moves, the narrator carries the room and Valdar answers, all inside one passage,
so *whose trust fell* is a question the engine genuinely cannot answer from context.

So in this mode every block **names its subject**, and this module resolves that name against
the roster before handing the block to the same appliers the structured engine uses. Nothing
new is trusted: an unresolvable name is dropped exactly as an unknown stat key already is.

Resolution is by name and deliberately forgiving in one direction only — case and surrounding
punctuation are ignored, and a first name matches a character whose full name starts with it.
It never guesses between two candidates: an ambiguous name is dropped, because applying a
wound to the wrong character is worse than applying it to nobody.
"""

from __future__ import annotations

import json
import re
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.events.envelope import StoryEvent
from app.events.stream import TurnTraceFrame
from app.services import turn_effects
from app.services.assembler import TurnContext
from app.services.turn_emit import Emitter, Tracer
from app.services.turn_writer import Consequence

#: A consequence block: the tag, then a JSON object. The optional leading slash mirrors
#: ``services/emission`` — models emit ``</type:x>`` as a delimiter often enough that
#: treating the two identically is what keeps the tags out of the rendered prose.
_BLOCK_RE = re.compile(
    r"</?type:\s*(state_update|relationship_update|presence_change)\s*>", re.IGNORECASE
)

#: Where the prose ends. Everything from the first consequence tag onward is machinery, and
#: the reader must never see it — the streaming gate in ``freetext_turn`` holds the tail back
#: for exactly this reason, and this is the same boundary computed on the finished text.
_FIRST_TAG_RE = re.compile(r"</?type:\s*[a-z_]+\s*>", re.IGNORECASE)


def split_prose(raw: str) -> str:
    """The passage with its consequence blocks removed."""
    match = _FIRST_TAG_RE.search(raw or "")
    return (raw[: match.start()] if match else raw or "").strip()


def parse_blocks(raw: str) -> list[tuple[str, dict]]:
    """Every ``(kind, payload)`` declared at the end of a passage.

    Tolerant of the shapes models actually emit: the JSON may be fenced, may be followed by
    prose the contract did not ask for, and a malformed block is skipped rather than taking
    its siblings with it.
    """
    found: list[tuple[str, dict]] = []
    marks = list(_BLOCK_RE.finditer(raw or ""))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(raw)
        body = raw[mark.end() : end]
        payload = _first_object(body)
        if payload is not None:
            found.append((mark.group(1).lower(), payload))
    return found


def _first_object(text: str) -> dict | None:
    """The first balanced ``{…}`` in ``text``, decoded. ``None`` when there isn't one."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    value = json.loads(text[start : index + 1])
                except ValueError:
                    return None
                return value if isinstance(value, dict) else None
    return None


def resolve_character(ctx: TurnContext, name: str | None) -> str | None:
    """A cast member's id from the name a passage used. ``None`` when it is not unambiguous.

    Present characters are matched first. Someone who has left the scene can still be named
    in a block — a passage may perfectly well record that a departed character is now feared
    — so absent members are a fallback rather than an exclusion.
    """
    wanted = re.sub(r"[^\w' ]+", "", str(name or "")).strip().lower()
    if not wanted:
        return None
    for pool in ([m for m in ctx.cast if m.is_present], list(ctx.cast)):
        exact = [m for m in pool if m.name.strip().lower() == wanted]
        if len(exact) == 1:
            return exact[0].id
        if len(exact) > 1:
            return None  # two characters share a name: refuse rather than pick
        prefix = [
            m
            for m in pool
            if m.name.strip().lower().split(" ")[0] == wanted
            or m.name.strip().lower().startswith(f"{wanted} ")
        ]
        if len(prefix) == 1:
            return prefix[0].id
        if len(prefix) > 1:
            return None
    return None


def apply(
    db: Session,
    ctx: TurnContext,
    raw: str,
    emitter: Emitter,
    tracer: Tracer,
    consequences: list[Consequence],
) -> Generator[StoryEvent | TurnTraceFrame, None, int]:
    """Apply every consequence a passage declared. Returns the total stat impact.

    Each block is routed to the structured engine's own applier, which re-validates it
    against the stat schema, the graph's registered edge types and the character's current
    presence. Nothing here shortcuts that: this module resolves *who*, and the appliers
    decide whether the change is legal at all.
    """
    impact = 0
    for kind, payload in parse_blocks(raw):
        character_id = resolve_character(ctx, payload.get("character"))
        if character_id is None:
            yield from tracer.emit(
                kind,
                "A declared change named nobody the scene knows",
                detail=(
                    f"'{payload.get('character')}' does not resolve to one cast member, so "
                    "the change is dropped rather than applied to a guess."
                ),
                data={"named": payload.get("character"), "kind": kind},
            )
            continue
        # The appliers take the block as raw JSON, so it is re-serialised rather than
        # threaded through as a dict — one parsing path for both engines, and the validators
        # keep owning what a valid block is.
        body = json.dumps(payload)
        if kind == "state_update":
            impact += yield from turn_effects.apply_stat_change(
                db, ctx, character_id, body, emitter, consequences, tracer=tracer
            )
        elif kind == "relationship_update":
            yield from turn_effects.apply_relationship_change(
                ctx, character_id, body, consequences, tracer
            )
        else:
            yield from turn_effects.apply_declared_presence(
                ctx, character_id, body, emitter, tracer
            )
    return impact
