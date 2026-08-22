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
  data. ``Scenario.max_turns`` has no upper bound in the database and nothing stops a
  hand-edited or imported row holding ``0``, and the assembler already takes the same
  belt-and-braces line with ``context_beats``.

Nothing here is shown to an agent. These values decide how a turn is *run*, never what it is
*about*, and that separation is what keeps a per-turn knob from becoming a back door into the
story's direction.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import Scenario
from app.schemas.base import BEAT_LENGTHS, DEFAULT_BEAT_LENGTH, BeatLength
from app.schemas.play import TurnOverrides

#: The per-turn ceiling on ``max_turns``, mirroring ``TurnOverrides``. A scene row may hold
#: more; an override may not ask for more.
MAX_TURNS_CEILING = 10
#: Follow-up suggestions the director may be asked for. Mirrors ``ScenarioUpdate``.
MAX_SUGGESTIONS = 4


@dataclass(frozen=True)
class TurnSettings:
    """The resolved controls for one turn. Frozen: nothing downstream may edit them."""

    max_turns: int
    suggestions_count: int
    beat_length: BeatLength


def resolve(scenario: Scenario, overrides: TurnOverrides | None = None) -> TurnSettings:
    """The scene's settings with this turn's overrides applied, each value re-clamped.

    An absent envelope, or one with every field unset, resolves identically to the scenario
    alone — that equivalence is what lets the whole feature be additive.
    """
    ov = overrides or TurnOverrides()

    max_turns = ov.max_turns if ov.max_turns is not None else scenario.max_turns
    max_turns = max(1, min(int(max_turns or 1), MAX_TURNS_CEILING))

    suggestions = (
        ov.suggestions_count
        if ov.suggestions_count is not None
        else scenario.suggestions_count
    )
    suggestions = max(0, min(int(suggestions or 0), MAX_SUGGESTIONS))

    beat_length = ov.beat_length or scenario.beat_length
    if beat_length not in BEAT_LENGTHS:
        beat_length = DEFAULT_BEAT_LENGTH

    return TurnSettings(
        max_turns=max_turns, suggestions_count=suggestions, beat_length=beat_length
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
