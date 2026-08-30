"""The free-text engine: look up → list → write → grade → continue.

The alternative to ``turn_engine.run_turn``, selected by ``TurnSettings.scene_mode``. It
shares that engine's *setup* (``turn_setup.prepare_turn`` opens the turn, records the player's
line and assembles the context) and its *tail* (``turn_finalize`` offers suggestions, commits
the graph and dispatches reflection), and replaces everything in between.

What it replaces, and what stands in its place:

===========================  ==========================================================
structured engine            free-text
===========================  ==========================================================
intent classification        nothing — the checklist call reads the player's line direct
direction requirements       the checklist
the plan (who speaks, when)  nothing. Nobody is scheduled.
one prose call per beat      one call for the whole turn
the lexical delivery check   the review call, which reads for meaning
re-plan on divergence        continue the same passage, up to :data:`MAX_CONTINUATIONS`
===========================  ==========================================================

**The turn is one event.** Every pass streams into the same ``scene_prose`` id, so a
continuation extends the passage already on the reader's screen rather than appending a
second block underneath it. The accumulate-by-id delta contract makes that free.

**The checklist is withheld from the writer under Playwright, and sent under POV**, which is
the sharpest decision in the mode and lives in exactly one place: :func:`_write`. A model
handed a checklist writes to the checklist, and prose that visibly works through a list reads
like the minutes of a meeting. Under POV the player wrote those instructions *as direction to
their scene partners*, so there is nothing to gain by hiding them.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.agents import freetext_agent, lookup_agent, task_agent
from app.agents.task_agent import Task
from app.core.errors import APIError
from app.events.envelope import StoryEvent
from app.events.stream import TurnReasoningFrame, TurnTask, TurnTasksFrame, TurnTraceFrame
from app.models import Scenario
from app.schemas.play import TurnRequest
from app.schemas.reasoning import effort_for_level
from app.services import (
    freetext_effects,
    prose_guards,
    turn_finalize,
    turn_settings,
    turn_setup,
)
from app.services.assembler import CastMember, TurnContext
from app.services.turn_emit import Emitter, Tracer

logger = logging.getLogger("mytheca.turn")

#: How many times a turn may be sent back to finish what it started.
#:
#: Three generations for one message is already a long wait, and each pass re-reads a prompt
#: that now contains the passage itself. Past this the turn ends and says what went
#: undelivered — the same answer the structured engine gives when it runs out of beats, and
#: for the same reason: the player can always send another message, and cannot un-wait.
MAX_CONTINUATIONS = 2


class _ProseGate:
    """Keeps the consequence blocks — and a leaked briefing — off the reader's screen.

    A free-text passage ends with optional ``<type:…>`` JSON, and the deltas are going
    straight to the wire as they arrive, so by the time the engine could parse the finished
    text the reader would already have watched the machinery scroll past. Two things are
    therefore held back:

    * **A short tail** (:data:`HOLD` characters), so a tag that arrives split across two
      chunks is still recognised before any of it is shown. Once a tag appears the gate
      closes and nothing further is emitted — everything after it is machinery by definition.
    * **The opening** (:data:`OPENING`), judged once before it is released. This is the only
      place a leaked scratchpad can be caught before the reader sees it, and free-text needs
      it more than the structured engine does: thinking is ON by default here.

    ``raw`` keeps everything for the parser; ``shown`` is only what reached the wire.
    """

    #: Long enough for the longest tag opener (``</type:``) to be recognised whole.
    HOLD = 16
    #: How much of the opening is judged before anything is released. Matches the guard's own
    #: window, so the gate and the rule are looking at the same text.
    OPENING = prose_guards.SCRATCHPAD_WINDOW

    def __init__(self) -> None:
        self.raw = ""
        self.shown = ""
        self.closed = False
        self.blocked = False
        self._pending = ""
        self._opened = False

    def push(self, chunk: str) -> str:
        """Take one delta; return the text that may be streamed now (possibly ``""``)."""
        self.raw += chunk
        if self.closed or self.blocked:
            return ""
        self._pending += chunk

        match = _TAG_RE.search(self._pending)
        if match:
            release, self._pending, self.closed = self._pending[: match.start()], "", True
        elif len(self._pending) > self.HOLD:
            release, self._pending = self._pending[: -self.HOLD], self._pending[-self.HOLD :]
        else:
            release = ""

        if not self._opened:
            # Hold everything until there is enough to judge — or until the generation has
            # finished, whichever comes first (`flush` releases a short passage).
            self.shown += release
            if len(self.shown) < self.OPENING and not self.closed:
                return ""
            self._opened = True
            if prose_guards.looks_like_briefing(self.shown):
                self.blocked = True
                return ""
            return self.shown
        self.shown += release
        return release

    def flush(self) -> str:
        """Release whatever is still held once the generation has ended."""
        if self.closed or self.blocked:
            return ""
        release, self._pending = self._pending, ""
        self.shown += release
        if not self._opened:
            self._opened = True
            if prose_guards.looks_like_briefing(self.shown):
                self.blocked = True
                return ""
            return self.shown
        return release


#: Any consequence tag. Matched with an optional slash for the reason ``services/emission``
#: documents: models emit ``</type:x>`` as a delimiter often enough that treating the two
#: identically is what keeps tags out of the rendered prose.
_TAG_RE = re.compile(r"</?type:\s*[a-z_]+\s*>", re.IGNORECASE)


def run_turn(
    db: Session, scenario: Scenario, req: TurnRequest
) -> Generator[
    StoryEvent | TurnTraceFrame | TurnTasksFrame | TurnReasoningFrame, None, None
]:
    """Run one free-text turn, yielding events and transport frames in order."""
    setup = yield from turn_setup.prepare_turn(db, scenario, req)
    ctx = setup.ctx
    tracer = setup.tracer
    emitter = setup.emitter
    turn_beats = setup.turn_beats
    settings = setup.settings or turn_settings.resolve(scenario, req.overrides)
    effort = effort_for_level(settings.thinking)
    pov = setup.pov

    yield from tracer.emit(
        "mode",
        "Writing this turn as one passage",
        detail=(
            "Free-text mode: nobody is scheduled and nothing is split into beats. The turn "
            "writes a checklist for itself, writes the scene, then grades what it wrote."
        ),
        data={"sceneMode": "freetext", "thinking": settings.thinking or "default"},
    )

    # ---- 1. what does it not know? -----------------------------------------
    lore = yield from _look_up(db, ctx, turn_beats, tracer, pov=pov)

    # ---- 2. what does this turn owe? ---------------------------------------
    # A plain character turn — the player is in POV and gave no direction — gets no
    # checklist, no review and no continuation. One call and one passage, which is the whole
    # of that path. Anything else would put deliberation in front of "you said something, and
    # the room answers".
    # Under POV the checklist exists only when the player actually directed the scene — the
    # guidance box, which is a different string from their character's line. Read from the
    # request rather than from `setup.direction`, which free-text deliberately leaves empty:
    # nothing parses a direction into requirements in this mode.
    wants_checklist = pov is None or bool((req.guidance or "").strip())
    tasks: list[Task] = []
    if wants_checklist:
        tasks = yield from _checklist(db, ctx, turn_beats, tracer, emitter, lore=lore, pov=pov)
    else:
        yield from tracer.emit(
            "tasks",
            "No checklist for this turn",
            detail=(
                "You are playing a character and gave no direction, so the scene simply "
                "answers what you said."
            ),
            data={"tasks": 0, "plain": True},
        )

    # ---- 3. write it, then read it back ------------------------------------
    live = emitter.open_stream("scene_prose", buffer_role="narrator")
    body = ""
    #: Everything the model returned, consequence blocks included. The reader saw ``body``;
    #: this is what ``freetext_effects`` parses.
    raw_body = ""
    written = False
    for attempt in range(MAX_CONTINUATIONS + 1):
        missing = [t.must for t in task_agent.outstanding(tasks)] if attempt else []
        if attempt and not missing:
            break
        try:
            chunk, raw = yield from _write(
                db, ctx, turn_beats, live, tracer,
                tasks=tasks, missing=missing, lore=lore, pov=pov,
                effort=effort, continuing=attempt > 0,
            )
        except APIError:
            # An endpoint that dies mid-turn after prose has streamed must keep what the
            # reader already saw. A first pass that returns nothing at all is a real failure
            # and is raised below, where the turn has nothing to show either way.
            if body:
                break
            raise
        if not chunk:
            break
        body += chunk
        raw_body += raw
        written = True
        if not tasks:
            break  # nothing to grade against, so nothing to go back for
        tasks = yield from _review(
            db, ctx, turn_beats, tracer, emitter, tasks, body,
            lore=lore, pov=pov, attempt=attempt + 1,
        )
        if not task_agent.outstanding(tasks):
            break

    if written:
        yield from live.close()
        turn_beats.append({"role": "narrator", "text": live.text, "characterId": None})
    if not written:
        # Nothing came back at all. The player gets a scene rather than a blank turn — the
        # same guarantee `turn_engine` makes with its silent-turn backstop.
        yield from tracer.emit(
            "prose",
            "The scene came back empty",
            detail="Nothing was generated for this turn.",
            data={"empty": True},
        )
        yield from emitter.emit(
            "narration", {"text": "The scene waits, quiet.", "done": True},
            buffer_role="narrator",
        )

    # ---- 4. consequences, and the report -----------------------------------
    consequences = setup.consequences
    if written:
        yield from freetext_effects.apply(db, ctx, raw_body, emitter, tracer, consequences)
    if tasks:
        yield from _report(tracer, tasks)

    yield from turn_finalize.finalize_turn(
        db,
        scenario=scenario,
        req=req,
        ctx=ctx,
        session=setup.session,
        seq0=setup.seq0,
        emitter=emitter,
        tracer=tracer,
        turn_beats=turn_beats,
        consequences=consequences,
        pov=pov,
        acted=[m.id for m in ctx.cast if m.is_present],
        asked_question=False,
        needs_branch=False,
        suggestions_count=settings.suggestions_count,
    )


# ---- the steps -------------------------------------------------------------


def _look_up(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    tracer: Tracer,
    *,
    pov: CastMember | None,
) -> Generator[TurnTraceFrame, None, str]:
    """Decide what to read, read it, and return the reference block (``""`` on anything)."""
    yield from tracer.emit(
        "lore",
        "Checking what it needs to look up",
        detail="Reading the scene for anything this world defines that the prompt does not.",
    )
    terms = lookup_agent.terms_for(db, ctx, turn_beats, pov=pov)
    if not terms:
        yield from tracer.emit(
            "lore",
            "Nothing to look up",
            detail="Everything this turn touches is already in front of it.",
            data={"terms": []},
        )
        return ""
    block = lookup_agent.lore_block(db, ctx.storyline_id, terms)
    yield from tracer.emit(
        "lore",
        f"Looked up {len(terms)} thing(s)" + ("" if block else " — nothing on file"),
        detail=(
            "Folded the world's own records into the prompt as reference."
            if block
            else "The world has no documents covering these yet, so the scene writes without."
        ),
        data={"terms": terms, "found": bool(block)},
    )
    return block


def _checklist(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    tracer: Tracer,
    emitter: Emitter,
    *,
    lore: str,
    pov: CastMember | None,
) -> Generator[TurnTraceFrame | TurnTasksFrame, None, list[Task]]:
    """Write the checklist and put it on the wire before any prose exists."""
    yield from tracer.emit(
        "tasks",
        "Working out what this turn owes you",
        detail="A short list of what has to be true by the end of the passage.",
    )
    tasks = task_agent.write_checklist(db, ctx, turn_beats, lore=lore, pov=pov)
    if not tasks:
        yield from tracer.emit(
            "tasks",
            "No checklist — the scene just answers",
            detail="Nothing came back to grade against, so the turn writes one passage.",
            data={"tasks": 0},
        )
        return []
    yield from tracer.emit(
        "tasks",
        f"{len(tasks)} thing(s) this turn owes you",
        detail=" · ".join(t.must for t in tasks),
        data={"tasks": [t.must for t in tasks]},
    )
    yield _frame(emitter, tasks, review_pass=0)
    return tasks


def _write(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    live,
    tracer: Tracer,
    *,
    tasks: list[Task],
    missing: list[str],
    lore: str,
    pov: CastMember | None,
    effort,
    continuing: bool,
) -> Generator[StoryEvent | TurnTraceFrame | TurnReasoningFrame, None, tuple[str, str]]:
    """Stream one pass into ``live``; return ``(prose shown, raw text)``.

    **Where the checklist is withheld.** Under Playwright the list never reaches this call —
    it was written, it is on the rail, and it is used only by the review. Under POV with
    instructions it rides in ``extra``, because the player wrote it as direction to their
    scene partners and there is nothing to be gained by hiding it.
    """
    extra: list[str] = []
    if continuing:
        instruction = freetext_agent.continue_instruction(missing)
    else:
        instruction = freetext_agent.WRITE
        if tasks and pov is not None:
            owed = "\n".join(f"- {t.must}" for t in tasks)
            extra.append(
                "This turn has to make these true, in what the characters do and say — "
                f"never by quoting or narrating the instruction itself:\n{owed}"
            )

    yield from tracer.emit(
        "prose",
        "Continuing the passage" if continuing else "Writing the scene",
        detail=(
            "The review found something still off the page, so the turn keeps writing from "
            "where it stopped: " + " · ".join(missing)
            if continuing
            else "One passage, the whole room, no beats."
        ),
        data={"continuation": continuing, "missing": missing},
    )

    limit = freetext_agent.RUNAWAY_CHARS
    gate = _ProseGate()
    cut = False
    if continuing:
        # A continuation is the next PARAGRAPH of the same passage, and it has to be given
        # its break here: the transport strips leading whitespace off a completion, so
        # whatever spacing the model wrote never survives the wire. Without this the two
        # passes arrive glued — "…she lets it sit.Valdar does not move." — which reads as a
        # rendering fault rather than as writing.
        yield from live.delta("\n\n")
    stream = freetext_agent.stream_body(
        db, ctx, turn_beats,
        instruction=instruction, lore=lore, pov=pov, extra=extra or None, effort=effort,
    )
    try:
        while True:
            delta = next(stream)
            if delta.reasoning:
                # The outline the model writes before it starts — what it is about to say and
                # why. The owner's word is that this reads well, so it is streamed on every
                # free-text turn rather than gated on the operator's reasoning-visibility
                # setting the way the structured engine's is: there, the channel is off by
                # default and showing it is a debugging affordance; here it is the feature.
                yield TurnReasoningFrame(text=delta.reasoning)
            if not delta.answer:
                continue
            yield from live.delta(gate.push(delta.answer))
            if len(gate.raw) > limit:
                cut = True
                stream.close()
                break
    except StopIteration:
        pass
    yield from live.delta(gate.flush())
    yield TurnReasoningFrame(done=True)

    if cut:
        yield from tracer.emit(
            "prose",
            "The passage was cut short",
            detail=(
                "The generation ran past the point any honest passage reaches and was "
                "stopped. The turn keeps what it had."
            ),
            data={"runaway": True, "chars": len(gate.raw)},
        )
    if gate.blocked:
        # The opening was the model briefing itself rather than writing. Nothing reached the
        # wire, so there is nothing to retract — the pass simply produced no prose, and the
        # caller treats that the same way it treats an empty generation.
        yield from tracer.emit(
            "prose",
            "The passage was withheld",
            detail=(
                "It opened by talking about the instructions rather than starting in the "
                "scene, so it was not shown."
            ),
            data={"briefing": True},
        )
        return "", gate.raw

    added = gate.shown
    # Whole-passage guards. Deliberately reported rather than retracted: this text has
    # already streamed, and a passage that degenerates in its last paragraph is still a
    # passage the reader watched arrive. The structured engine's continuous path makes the
    # same call for the same reason.
    if added and prose_guards.looks_degenerate(added):
        yield from tracer.emit(
            "prose",
            "The passage stopped being prose",
            detail="Its tail collapsed into repetition or a word list.",
            data={"degenerate": True},
        )
    elif added and prose_guards.repeats_itself(added):
        yield from tracer.emit(
            "prose",
            "The passage repeated itself",
            detail="Its ending had already appeared verbatim earlier in the same passage.",
            data={"repeats": True},
        )
    if added and pov is None and prose_guards.addresses_the_reader(added):
        # Only meaningful while the player is not embodied: under POV every "you" aimed at
        # their character is correct. Under Playwright there is nobody in the room to address.
        yield from tracer.emit(
            "prose",
            "The passage addressed somebody who is not there",
            detail=(
                "You are directing this scene from outside it, so a \"you\" in the narration "
                "has no one to land on."
            ),
            data={"secondPerson": True},
        )
    return added, gate.raw


def _review(
    db: Session,
    ctx: TurnContext,
    turn_beats: list[dict],
    tracer: Tracer,
    emitter: Emitter,
    tasks: list[Task],
    body: str,
    *,
    lore: str,
    pov: CastMember | None,
    attempt: int,
) -> Generator[TurnTraceFrame | TurnTasksFrame, None, list[Task]]:
    """Grade the passage so far and put the verdicts on the wire."""
    yield from tracer.emit(
        "review",
        "Reading it back",
        detail="Checking the passage against what the turn owed, item by item.",
        data={"pass": attempt},
    )
    graded = task_agent.review(db, ctx, turn_beats, tasks, body, lore=lore, pov=pov)
    left = task_agent.outstanding(graded)
    yield from tracer.emit(
        "review",
        "Everything landed" if not left else f"{len(left)} thing(s) still off the page",
        detail=" · ".join(f"{t.must} — {t.state or 'not graded'}" for t in graded),
        data={
            "pass": attempt,
            "verdicts": [{"must": t.must, "state": t.state, "note": t.note} for t in graded],
            "complete": not left,
        },
    )
    yield _frame(emitter, graded, review_pass=attempt)
    return graded


def _report(tracer: Tracer, tasks: list[Task]) -> Generator[TurnTraceFrame, None, None]:
    """The turn's closing account of what it delivered — the free-text answer to the
    structured engine's direction report."""
    left = task_agent.outstanding(tasks)
    yield from tracer.emit(
        "tasks",
        (
            "Everything this turn owed you is on the page"
            if not left
            else f"{len(left)} thing(s) went undelivered"
        ),
        detail=" · ".join(f"{t.must} — {t.state or 'not graded'}" for t in tasks),
        data={
            "delivered": len(tasks) - len(left),
            "total": len(tasks),
            "undelivered": [t.must for t in left],
        },
    )


def _frame(emitter: Emitter, tasks: list[Task], *, review_pass: int) -> TurnTasksFrame:
    """The checklist as the rail sees it."""
    return TurnTasksFrame(
        session_id=emitter.session_id,
        tasks=[
            TurnTask(n=t.n, must=t.must, who=list(t.who), state=t.state, note=t.note)
            for t in tasks
        ],
        review_pass=review_pass,
        complete=not task_agent.outstanding(tasks),
    )
