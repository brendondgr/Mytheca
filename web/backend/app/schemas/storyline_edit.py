"""Schemas for the agentic storyline editor/creator.

A single conversational agent edits a storyline's *own* fields — title, genre,
tagline, premise, World Primer, and the stat *schema* — under an explicit
**write scope** the human sets. The flow is **plan → implement**: the agent
returns a reviewable :class:`StoryPlan` (proposed value + rationale per in-scope
field; add/update/remove per stat definition), and nothing is written until the
human approves. The canonical field set is data-driven off :data:`FIELD_CATALOG`
so it can grow without reworking the mechanism.

Enforcement is belt-and-suspenders (see ``agents/storyline_edit/scope.py``): the
agent's response schema + prompt are built from the *writable* fields only, and a
server-side diff guard rejects any change outside the approved write scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from app.schemas.base import CamelModel, Visibility
from app.schemas.stat import StatBand

# ---- Field catalogue --------------------------------------------------------

# ``text`` = a short free-text field, ``primer`` = the long agent-facing World
# Primer (surfaced with extra scrutiny in the plan), ``stats`` = the stat schema.
FieldKind = Literal["text", "primer", "stats"]


@dataclass(frozen=True)
class ScopedFieldSpec:
    """One editable storyline field the agent's scope can cover."""

    key: str  # canonical camelCase identifier (matches the wire + plan)
    label: str
    kind: FieldKind


# The initial scoped field set. The design is field-agnostic — append here to grow
# it. ``statistics`` stands for the whole stat schema (definitions + bands + guidance).
FIELD_CATALOG: tuple[ScopedFieldSpec, ...] = (
    ScopedFieldSpec("title", "Title", "text"),
    ScopedFieldSpec("genre", "Genre", "text"),
    ScopedFieldSpec("tagline", "Tagline", "text"),
    ScopedFieldSpec("premise", "Premise", "text"),
    ScopedFieldSpec("worldPrimer", "World Primer", "primer"),
    ScopedFieldSpec("statistics", "Statistics", "stats"),
)

FIELD_KEYS: frozenset[str] = frozenset(spec.key for spec in FIELD_CATALOG)
SPEC_BY_KEY: dict[str, ScopedFieldSpec] = {spec.key: spec for spec in FIELD_CATALOG}


# ---- Scope ------------------------------------------------------------------


class FieldScope(CamelModel):
    """Per-field scope: may the agent write it, and may it read it as context.

    ``writable`` is the hard axis (enforced three ways). ``readable`` is the soft
    axis (default wide) — clamping it shrinks the agent's input surface.
    """

    writable: bool = False
    readable: bool = True


# The scope object that travels with every request: ``{field key -> FieldScope}``.
# It is the single source of truth both client and server consult.
ScopeState = dict[str, FieldScope]


# ---- Plan artifacts ---------------------------------------------------------


class FieldChange(CamelModel):
    """A proposed change to one text/primer field (before → after + why)."""

    field: str
    before: str | None = None
    after: str | None = None
    rationale: str = ""


class StatDefinitionDraft(CamelModel):
    """A proposed stat *definition* (the apply-ready shape for add/update)."""

    key: str
    display_name: str = ""
    description: str = ""
    min: int = 0
    max: int = 100
    default: int = 0
    visibility: Visibility = "public"
    guidance: str | None = None
    applies_to: list[str] = Field(default_factory=lambda: ["character"])
    bands: list[StatBand] = Field(default_factory=list)


StatChangeType = Literal["add", "update", "remove"]


class StatChange(CamelModel):
    """A proposed change to one stat definition.

    ``schema_altering`` flags the higher-risk changes — adding/removing a stat or
    moving its range — distinctly from a plain description/band edit, so the human
    sees exactly what is moving before approving.
    """

    key: str
    change_type: StatChangeType
    before: StatDefinitionDraft | None = None
    after: StatDefinitionDraft | None = None
    schema_altering: bool = False
    rationale: str = ""


class StoryPlan(CamelModel):
    """The reviewable plan for one agent turn — nothing is written until approval."""

    changes: list[FieldChange] = Field(default_factory=list)
    stat_changes: list[StatChange] = Field(default_factory=list)
    notes: str = ""

    def is_empty(self) -> bool:
        return not self.changes and not self.stat_changes


# ---- Conversation -----------------------------------------------------------


class AgentMessage(CamelModel):
    """One turn of the client-session conversation, sent back to the agent."""

    role: Literal["user", "assistant"]
    content: str
