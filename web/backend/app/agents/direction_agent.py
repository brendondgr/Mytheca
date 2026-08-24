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
in-character line) is parsed here by :func:`parse`. In Playwright mode the player's line *is*
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

from app.agents._common import decision_timeout, extract_json, resolve_llm
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
    the narrator owns it.

    **Attempted is not delivered.** ``attempted`` says a beat carried this requirement into
    its prompt; ``delivered`` says the prose that came back actually reached it. They used
    to be the same flag, which meant a beat that returned nothing — empty generation,
    withheld scratchpad leak, failed request — still ticked the requirement off for good.
    ``attempts`` bounds the retrying, so a requirement the prose keeps paraphrasing cannot
    eat the whole remaining budget.
    """

    id: str
    text: str
    actor_id: str | None = None
    attempted: bool = False
    delivered: bool = False
    attempts: int = 0
    #: The player named this target themselves (an `@` mention on the direction line), so it
    #: was never a guess and must never be silently re-owned. See :meth:`SceneDirection.rebind`.
    pinned: bool = False
    #: A pinned requirement whose character is not in the scene. It cannot be delivered by
    #: anyone and it must not be handed to the narrator instead — the player asked for *that*
    #: person. It waits, is reported as waiting, and is carried to the next turn.
    blocked: bool = False
    #: The turn this requirement was first asked for, when it survived a turn undelivered.
    #: ``None`` for a requirement asked for on the current turn.
    from_turn: int | None = None

    @property
    def satisfied(self) -> bool:
        """Delivered. Read-only: the old writable flag conflated the two states, and the
        whole point of the split is that nothing outside this module may set it directly."""
        return self.delivered


@dataclass
class SceneDirection:
    """What the player directed this turn, and what of it is still owed."""

    text: str = ""
    requirements: list[DirectionRequirement] = field(default_factory=list)

    @property
    def active(self) -> bool:
        """True when there is any direction at all to honor."""
        return bool(self.text.strip() or self.requirements)

    def outstanding(self, max_attempts: int | None = None) -> list[DirectionRequirement]:
        """The requirements still owed, in the order they were asked for.

        "Still owed" means not confirmed delivered **and** not out of attempts. Passing
        ``max_attempts`` (the engine does, from settings) is what stops a requirement the
        lexical check keeps failing to see from being re-owed to every remaining beat.
        """
        return [
            r
            for r in self.requirements
            if not r.delivered
            and not r.blocked
            and (max_attempts is None or r.attempts < max_attempts)
        ]

    def unconfirmed(self, max_attempts: int) -> list[DirectionRequirement]:
        """Tried, out of attempts, never confirmed.

        Reported separately from "never attempted" because they are a different story to
        tell the player: the turn did aim beats at these, and the check could not see them
        land — which is as likely to be the check's crudeness as the scene's failure.
        """
        return [
            r for r in self.requirements if not r.delivered and r.attempts >= max_attempts
        ]

    def for_actor(
        self, actor_id: str | None, max_attempts: int | None = None
    ) -> list[DirectionRequirement]:
        """The outstanding requirements owned by ``actor_id`` (``None`` → the narrator's)."""
        return [r for r in self.outstanding(max_attempts) if r.actor_id == actor_id]

    def rebind(self, present_ids: set[str], locked_id: str | None = None) -> None:
        """Re-own requirements the cast can no longer perform (in place).

        A requirement bound to someone who is absent can never be satisfied by that
        character's beat. Rebinding it to the narrator (``actor_id = None``) keeps the
        promise: narration can still make the event occur.

        **A pinned target is never re-owned.** The player named that character themselves —
        handing their line to the narrator is not a rescue, it is ignoring the instruction.
        Two cases, and neither is a rebind:

        * the character is **present** (including when they are the POV character): the
          requirement stays theirs. Under POV the AI will not voice them, but that does not
          mean the requirement cannot be met — the narrator can describe what they do, and
          the player can do it themselves on their next turn. Silently re-owning it is what
          made "everything you aim at your own character" vanish;
        * the character is **absent**: the requirement is marked ``blocked`` rather than
          rebound. It waits, is reported as waiting, and is carried to the next turn — and
          it is the hook Phase 9 uses to offer bringing that character in.

        ``blocked`` is recomputed each pass rather than latched, so a character walking back
        into the scene unblocks what was waiting on them.
        """
        for req in self.requirements:
            if req.actor_id is None or req.delivered:
                continue
            absent = req.actor_id not in present_ids
            if req.pinned:
                req.blocked = absent
                continue
            if absent or req.actor_id == locked_id:
                req.actor_id = None

    def attempt(self, requirements: list[DirectionRequirement]) -> None:
        """A beat is about to carry ``requirements`` into its prompt.

        This is the *only* thing that is known before the beat runs. Delivery is decided
        afterwards, by :meth:`satisfy`, from the prose that actually came back.
        """
        for req in requirements:
            req.attempted = True
            req.attempts += 1

    def satisfy(self, requirements: list[DirectionRequirement]) -> None:
        """Confirm ``requirements`` delivered — the emitted prose reached them."""
        for req in requirements:
            req.delivered = True

    def summary(self) -> list[str]:
        """One short line per requirement, for the diagnostic trace.

        Three states, not two: delivered, attempted-but-unconfirmed, and never reached.
        """
        def glyph(r: DirectionRequirement) -> str:
            if r.delivered:
                return "\u2713"
            return "\u25d0" if r.attempted else "\u2022"

        return [f"{glyph(r)} {r.text}" for r in self.requirements]


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


def from_directives(
    items: list[tuple[str, str | None]], cast_ids: set[str], *, limit: int = MAX_REQUIREMENTS
) -> SceneDirection:
    """Build a direction straight from what the player wrote, with no LLM call.

    ``items`` is ``(text, actor_id)`` per directive — one line of the direction box each,
    with the ``actor_id`` of an ``@`` cast mention on that line. The player already said
    *what* and *who*, so spending a round-trip to re-guess it is both slower and worse: the
    parse step exists to infer a target, and there is nothing left to infer.

    An ``actor_id`` outside the cast is dropped to ``None`` rather than guessed at (the same
    rule :func:`resolve_requirements` uses). A directive **with** a resolved actor is
    ``pinned`` — the player named them, so :meth:`SceneDirection.rebind` will never re-own it.
    """
    out: list[DirectionRequirement] = []
    for text, actor in items:
        clean = (text or "").strip()
        if not clean:
            continue
        bound = actor if actor in cast_ids else None
        out.append(
            DirectionRequirement(
                id=f"req{len(out) + 1}",
                text=clean,
                actor_id=bound,
                pinned=bound is not None,
            )
        )
        if len(out) >= limit:
            break
    if not out:
        return SceneDirection()
    return SceneDirection(text="\n".join(r.text for r in out), requirements=out)


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
            timeout_s=decision_timeout(),
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
