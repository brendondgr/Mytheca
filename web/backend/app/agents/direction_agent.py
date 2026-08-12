"""Scene direction — turn the player's narrative guidance into a schedulable contract.

The player is the scene's **director**: they say what happens next and how the cast
should react, and the turn is expected to deliver it. A free-text direction on its own
cannot promise that — the ReAct planner answers one beat at a time and may simply never
get to the second half of what was asked before the scene's turn cap stops it.

So a direction is parsed into an ordered list of :class:`DirectionRequirement` — each one
an outcome that must be true by the end of some beat this turn, optionally **bound to a
cast member** ("Mei has to snap back"). The turn engine then:

* shows the outstanding requirements (and the remaining beat budget) to the planner,
* **stops asking** and calls :func:`schedule` once the budget is as tight as the number of
  requirements left, so everything lands inside ``scenario.max_turns``,
* hands each speaker its own requirement as an outcome to reach *in their own voice*.

A requirement is a **guide, not a script**: it states what must be true, never the words.
The character prompt keeps every one of its in-character constraints.

Two callers produce requirements. POV-mode guidance (a string separate from the player's
in-character line) is parsed here by :func:`parse`. In narrator mode the player's line *is*
the direction, and ``intent_agent`` already classifies that line — so it extracts the
requirements on its own call using the shared prompt fragment below, and no second
round-trip is spent.

Best-effort throughout: an unconfigured or failing LLM yields a single actor-less
requirement holding the whole direction text, so the narrator still covers it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents._common import extract_json, resolve_llm
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.services import llm
from app.services.assembler import TurnContext

# Parsing a direction is a cheap structural call — keep the thinking budget low.
DIRECTION_EFFORT = ReasoningEffort.LOW

# A ceiling on how many requirements one direction may impose. A direction long enough to
# want more than this is really several turns of story; the extras would be packed into a
# single bundled beat anyway (see :func:`schedule`), which reads worse than dropping them.
MAX_REQUIREMENTS = 6


# ---- The shared prompt fragment --------------------------------------------
# Both this module and ``intent_agent`` ask for the SAME ``requirements`` array, so the
# wording lives here once and is imported rather than restated.

REQUIREMENTS_SCHEMA = (
    '"requirements": [{"actor": <roster number or null>, '
    '"must": "<one outcome that has to be true by the end of a beat>"}]'
)

REQUIREMENTS_RULES = """- "requirements" breaks the direction into the concrete things that MUST happen this turn, in the order they should happen. Each entry is an OUTCOME, never a line of dialogue and never stage wording to be recited.
- Set "actor" to the roster number of the character who has to do/say/feel it ("Mei has to snap back" → Mei's number). Use null when it is an event, a change in the room, or something no single character owns ("the lamp goes over").
- Split a direction that asks for several things into several entries; keep a vague direction as ONE entry restating it plainly. Never invent a requirement the direction did not ask for, and never add one just to fill the list.
- Return [] when the line asks for nothing in particular (ordinary conversation, a question, a reaction to what was just said)."""

_SYSTEM = f"""You read the player's DIRECTION for an interactive story scene. The player is the scene's director: they say what should happen next and how the cast should react. Break that direction into what the turn must deliver — STRUCTURE ONLY, never prose.

Return ONLY a JSON object:
{{{REQUIREMENTS_SCHEMA}}}

Rules:
{REQUIREMENTS_RULES}
- Use ONLY the roster numbers given; never invent one.
- No prose, no commentary — just the JSON object."""


@dataclass
class DirectionRequirement:
    """One outcome the turn owes the player's direction.

    ``actor_id`` binds it to a cast member (they must be the one to do it); ``None`` means
    the narrator owns it. ``satisfied`` is flipped by the turn engine once a beat that
    carried this requirement into its prompt has been emitted.
    """

    id: str
    text: str
    actor_id: str | None = None
    satisfied: bool = False


@dataclass
class SceneDirection:
    """What the player directed this turn, and what of it is still owed."""

    text: str = ""
    requirements: list[DirectionRequirement] = field(default_factory=list)

    @property
    def active(self) -> bool:
        """True when there is any direction at all to honor."""
        return bool(self.text.strip() or self.requirements)

    def outstanding(self) -> list[DirectionRequirement]:
        """The requirements not yet carried into a beat, in the order they were asked for."""
        return [r for r in self.requirements if not r.satisfied]

    def for_actor(self, actor_id: str | None) -> list[DirectionRequirement]:
        """The outstanding requirements owned by ``actor_id`` (``None`` → the narrator's)."""
        return [r for r in self.outstanding() if r.actor_id == actor_id]

    def rebind(self, present_ids: set[str], locked_id: str | None = None) -> None:
        """Re-own requirements the cast can no longer perform (in place).

        A requirement bound to someone who is absent — or to the **POV character**, whom
        the AI never voices — can never be satisfied by that character's beat. Rebinding it
        to the narrator (``actor_id = None``) keeps the promise: narration can still make
        the event occur.
        """
        for req in self.requirements:
            if req.actor_id is None:
                continue
            if req.actor_id == locked_id or req.actor_id not in present_ids:
                req.actor_id = None

    def satisfy(self, requirements: list[DirectionRequirement]) -> None:
        """Mark ``requirements`` as delivered (they were carried into an emitted beat)."""
        for req in requirements:
            req.satisfied = True

    def summary(self) -> list[str]:
        """One short line per requirement, for the diagnostic trace."""
        return [
            f"{'✓' if r.satisfied else '•'} {r.text}" for r in self.requirements
        ]


@dataclass
class ScheduledBeat:
    """A beat the engine runs *without* asking the planner, to fit the budget.

    ``actor_id`` is the character who must take it (``None`` → a narrator beat), and
    ``requirements`` are the ones this beat carries into its prompt.
    """

    actor_id: str | None
    requirements: list[DirectionRequirement]


def resolve_requirements(
    raw: object, roster_ids: dict[int, str], *, limit: int = MAX_REQUIREMENTS
) -> list[DirectionRequirement]:
    """Map a model's ``requirements`` array onto roster-constrained requirements.

    Entries without usable text are dropped; an actor number outside the roster degrades to
    the narrator rather than being guessed at. Order is preserved and the list is capped at
    ``limit``.
    """
    out: list[DirectionRequirement] = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, str):
            text, actor = entry.strip(), None
        elif isinstance(entry, dict):
            text = str(entry.get("must") or entry.get("text") or "").strip()
            actor = roster_ids.get(_as_int(entry.get("actor")) or -1)
        else:
            continue
        if not text:
            continue
        out.append(DirectionRequirement(id=f"req{len(out) + 1}", text=text, actor_id=actor))
        if len(out) >= limit:
            break
    return out


def parse(db: Session, ctx: TurnContext, text: str) -> SceneDirection:
    """Parse standalone narrative guidance into a :class:`SceneDirection`.

    Best-effort (never raises): with no LLM configured, on an API failure, or on a reply
    that yields no usable requirement, the whole guidance becomes ONE actor-less
    requirement — the narrator then carries it, which is exactly the pre-direction behavior
    of a narrator ``lead``.
    """
    guidance = (text or "").strip()
    if not guidance:
        return SceneDirection()
    if not ctx.cast:
        return _whole_text(guidance)
    try:
        base_url, api_key, model, params = resolve_llm(db)
    except APIError:
        return _whole_text(guidance)

    roster = "\n".join(f"[{i + 1}] {m.name} — {m.role}" for i, m in enumerate(ctx.cast))
    user = f"Roster:\n{roster}\n\nThe player's direction:\n{guidance}\n\nBreak it down."
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            params,
            reasoning=DIRECTION_EFFORT,
        )
        data = extract_json(raw)
    except APIError:
        return _whole_text(guidance)

    roster_ids = {i + 1: m.id for i, m in enumerate(ctx.cast)}
    requirements = resolve_requirements(data.get("requirements"), roster_ids)
    if not requirements:
        return _whole_text(guidance)
    return SceneDirection(text=guidance, requirements=requirements)


def schedule(outstanding: list[DirectionRequirement], remaining: int) -> ScheduledBeat | None:
    """Pick the next beat directly, packing what is left into the beats that are left.

    Called only when the budget has run as tight as the direction is long, so the planner's
    judgement can no longer be afforded. Two rules:

    * **Last beat, several owed** (``remaining <= 1`` and more than one requirement) — a
      single **narrator** beat carries all of them. Narration is the only voice that can
      make several characters' worth of direction land at once, and the scene's turn cap is
      hard: overrunning it is not an option.
    * **Otherwise** — the oldest outstanding requirement drives the beat, bundled with the
      next ones that share its owner, enough of them that what is left fits the beats left.

    Returns ``None`` when there is nothing outstanding.
    """
    if not outstanding:
        return None
    if remaining <= 1 and len(outstanding) > 1:
        return ScheduledBeat(actor_id=None, requirements=list(outstanding))

    driver = outstanding[0]
    # How many must ride on THIS beat for the rest to fit one-per-beat afterwards.
    bundle = max(1, len(outstanding) - max(remaining, 1) + 1)
    carried = [driver]
    for req in outstanding[1:]:
        if len(carried) >= bundle:
            break
        if req.actor_id == driver.actor_id:
            carried.append(req)
    return ScheduledBeat(actor_id=driver.actor_id, requirements=carried)


def _whole_text(guidance: str) -> SceneDirection:
    """The fallback direction: the guidance verbatim, owned by the narrator."""
    return SceneDirection(
        text=guidance,
        requirements=[DirectionRequirement(id="req1", text=guidance, actor_id=None)],
    )


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = re.search(r"\d+", value)
        return int(m.group()) if m else None
    return None
