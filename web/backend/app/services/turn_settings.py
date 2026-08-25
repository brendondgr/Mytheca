"""What one turn actually runs with: the scene's settings, with this turn's overrides on top.

A scene carries its play controls on the ``Scenario`` row, and a turn may override any of
them for itself alone (:class:`app.schemas.play.TurnOverrides`). Resolving that in one small
pure function keeps ``run_turn`` from growing a two-branch read per control — every one of
which would be a place the override could be honoured in one code path and forgotten in
another.

Two rules the resolver enforces, and they are not the same rule:

* **The override wins when it is set at all.** ``suggestions_count = 0`` is a real request
  ("no follow-ups this turn"), so the test is ``is not None``, never truthiness.
* **The row is re-clamped anyway.** The request schema guards the boundary; this guards the
  data — nothing stops a hand-edited or imported row holding a nonsense value, and the
  assembler already takes the same belt-and-braces line with ``context_beats``.

``max_turns`` and ``beat_length`` used to resolve here and no longer exist as controls: how
many beats a message makes, and how long a beat is, are decided by the scene now. The
``Scenario`` columns are left in place but unread — dropping them would break any other
process still running against this database, and there is nothing to gain by rushing it.

Nothing here is shown to an agent. These values decide how a turn is *run*, never what it is
*about*, and that separation is what keeps a per-turn knob from becoming a back door into the
story's direction.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import Scenario
from app.schemas.play import PlannerMode, Register, SceneFlow, TieScope, TurnOverrides

#: Follow-up suggestions the director may be asked for. Mirrors ``ScenarioUpdate``.
MAX_SUGGESTIONS = 4

#: How prose is produced when nothing says otherwise (owner decision, 2026-08-24).
#:
#: A named constant rather than a literal in :func:`resolve`, for one reason: the per-speaker
#: writer is still a supported mode with a great deal of machinery of its own — register
#: directives, voice samples, relationship notes, disposition, the owed-requirements tail —
#: none of which exists on the continuous path. The tests for that machinery have to pin the
#: mode they are testing, and pinning it by patching one visible constant is honest, where
#: forty scenario fixtures quietly carrying `sceneFlow: "voiced"` would not be.
DEFAULT_SCENE_FLOW = "continuous"


@dataclass(frozen=True)
class TurnSettings:
    """The resolved controls for one turn. Frozen: nothing downstream may edit them."""

    suggestions_count: int
    #: ``"auto"`` (the default), ``"plan"`` or ``"off"`` — see :data:`PlannerMode`.
    planner: PlannerMode = "auto"
    #: A register the player pinned for this turn, or ``None`` to let the scene decide.
    register: Register | None = None
    #: How much of a speaker's history reaches their beat.
    ties: TieScope = "scene"
    #: How the turn's prose is produced — see ``schemas.play.SceneFlow``.
    scene_flow: SceneFlow = "continuous"


def resolve(scenario: Scenario, overrides: TurnOverrides | None = None) -> TurnSettings:
    """The scene's settings with this turn's overrides applied, each value re-clamped.

    An absent envelope, or one with every field unset, resolves identically to the scenario
    alone — that equivalence is what lets the whole feature be additive.
    """
    ov = overrides or TurnOverrides()

    suggestions = (
        ov.suggestions_count
        if ov.suggestions_count is not None
        else scenario.suggestions_count
    )
    suggestions = max(0, min(int(suggestions or 0), MAX_SUGGESTIONS))

    planner = ov.planner or getattr(scenario, "planner_mode", None) or "auto"
    # ``"planner"`` is the value this control shipped with and is still on scenario rows and
    # in saved clients. It means exactly what ``"auto"`` means, so it is normalised here
    # rather than carried through the engine as a second name for one thing.
    if planner == "planner":
        planner = "auto"
    if planner not in ("auto", "plan", "off"):
        planner = "auto"

    ties = ov.ties or getattr(scenario, "tie_scope", None) or "scene"
    if ties not in ("addressed", "scene", "world"):
        ties = "scene"

    # `continuous` is the DEFAULT (owner decision, 2026-08-24), so `NULL` — every scene
    # written before the column — reads as continuous rather than keeping the old path. A
    # scene that wants per-speaker calls sets `"voiced"` explicitly.
    scene_flow = ov.scene_flow or getattr(scenario, "scene_flow", None) or DEFAULT_SCENE_FLOW
    if scene_flow not in ("voiced", "continuous"):
        # The DEFAULT, not a hardcoded mode. These two drifted apart once already: the default
        # moved to continuous and this line kept sending a nonsense row to the old path, so a
        # hand-edited value silently opted a scene out of the default rather than being
        # ignored. One name for one answer.
        scene_flow = DEFAULT_SCENE_FLOW

    return TurnSettings(
        suggestions_count=suggestions,
        planner=planner,
        register=ov.beat_register,
        ties=ties,
        scene_flow=scene_flow,
    )


def applied(overrides: TurnOverrides | None) -> dict:
    """The non-null override map, for the ``user_turn`` row and the trace.

    Empty when nothing was overridden, so a caller can write it only when it says something
    — an empty ``overrides`` key on every row would be noise in the export and in the
    Inspector alike.
    """
    if overrides is None:
        return {}
    return overrides.model_dump(exclude_none=True, by_alias=True)


def pitch(settings: TurnSettings, decision) -> tuple[str | None, str]:
    """How this beat is pitched, and who decided — ``(register, source)``.

    The precedence lives here and nowhere else, because it has to be applied at **five**
    separate sites in the turn loop (the planner's speak branch, the forced-direction beat,
    the forced-exchange responder, the silent-turn backstop and the puppet loop) and five
    copies of a two-line rule is five chances for one of them to disagree.

    ``source`` is ``"player"`` when the pin decided, ``"planner"`` when the beat's own read
    did, and ``""`` when neither had anything — which is a real third case: with planning off
    nobody reads the moment at all, and that is exactly when a pin is the only source there
    is.
    """
    if settings.register:
        return settings.register, "player"
    register = getattr(decision, "register", None) if decision is not None else None
    return register, "planner" if register else ""
