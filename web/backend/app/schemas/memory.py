"""Wire shapes for episodic memory — the per-beat provenance read.

Player-facing, deliberately. This answers *"where did that line come from?"* in the
language of the fiction: the moment, the words that were said, and where to find it in the
record. Scores, fade multipliers and cue hits stay out of it — those belong to the Turn
Inspector, which is where engine internals are already shown.

The `contradicted_by` field is the one that earns its place. A cast that remembers
subjectively will produce characters who flatly disagree about what happened, and without
somewhere to see that, every such moment reads as the app losing track rather than as two
people remembering differently.
"""

from __future__ import annotations

from app.schemas.base import CamelModel


class MemoryContradiction(CamelModel):
    """Someone else's version of the same moment."""

    character_id: str
    character_name: str
    gloss: str


class RecalledMemory(CamelModel):
    """One memory a beat was written with."""

    id: str
    character_id: str
    character_name: str
    #: What this character took from the moment, in their own words.
    gloss: str
    #: The verbatim line they kept, and who said it. Absent when the moment produced no
    #: quotable speech, or when the model's proposed quote failed verification.
    quote: str | None = None
    quote_speaker_name: str | None = None
    #: Where it happened, for the jump-back link.
    scenario_id: str
    scenario_title: str
    session_id: str
    turn_seq: int
    #: The story event to scroll to — resolved from ``(session_id, turn_seq)`` rather than
    #: stored, so an edited or re-rolled beat still lands the reader in the right turn.
    event_id: str | None = None
    #: Whether this play-through can actually scroll to it: a memory from an earlier
    #: scenario is real history, but it is not in this transcript.
    in_this_session: bool = False
    #: Others who were there and remember it differently.
    contradicted_by: list[MemoryContradiction] = []


class BeatMemoryResponse(CamelModel):
    """Everything behind one beat. Empty list rather than 404 for a beat with no memory."""

    event_id: str
    memories: list[RecalledMemory] = []
