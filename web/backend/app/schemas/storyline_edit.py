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
# Primer (surfaced with extra scrutiny in the plan), ``stats`` = the stat schema,
# ``style`` = the narrative style guide's six blocks.
#
# ``style`` is its own kind rather than six ``text`` fields for the same reason ``stats``
# is: it is ONE thing the author scopes on or off, and six checkboxes would make the scope
# panel a list of implementation details instead of a list of decisions.
FieldKind = Literal["text", "primer", "stats", "style"]


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
    ScopedFieldSpec("styleBlocks", "Narrative style", "style"),
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


class StyleChange(CamelModel):
    """A proposed change to ONE block of the narrative style guide.

    ``after`` of ``None`` means *remove this block* — a real and reversible edit an author
    may well ask for ("drop the never block"), and distinct from leaving it untouched,
    which the agent expresses by not proposing a change for it at all.
    """

    block: str
    before: str | None = None
    after: str | None = None
    rationale: str = ""


class StoryPlan(CamelModel):
    """The reviewable plan for one agent turn — nothing is written until approval."""

    changes: list[FieldChange] = Field(default_factory=list)
    stat_changes: list[StatChange] = Field(default_factory=list)
    style_changes: list[StyleChange] = Field(default_factory=list)
    notes: str = ""

    def is_empty(self) -> bool:
        return not self.changes and not self.stat_changes and not self.style_changes


# ---- Conversation -----------------------------------------------------------


class AgentMessage(CamelModel):
    """One turn of the client-session conversation, sent back to the agent."""

    role: Literal["user", "assistant"]
    content: str


class StorylineFieldsSnapshot(CamelModel):
    """The author's *current* form values — the agent's read context + plan before-values.

    Sent with every request so each scoped pass re-reads the current (possibly
    unsaved) state of the form, exactly as the design intends.
    """

    title: str = ""
    genre: str = ""
    tagline: str = ""
    premise: str = ""
    world_primer: str = ""
    stats: list[StatDefinitionDraft] = Field(default_factory=list)
    #: The narrative style guide as it stands in the editor ({block id -> text}).
    style_blocks: dict[str, str] = Field(default_factory=dict)


class StorylineAgentRequest(CamelModel):
    """Request body for both converse/plan streams (create + edit)."""

    scope: ScopeState = Field(default_factory=dict)
    messages: list[AgentMessage] = Field(default_factory=list)
    fields: StorylineFieldsSnapshot = Field(default_factory=StorylineFieldsSnapshot)
    # Inline text of the context files the author kept selected for **Draft** in the
    # panel, concatenated client-side. It grounds this turn only — the corpus itself is
    # persisted separately via the context-document CRUD. Optional and bounded server-
    # side by ``_common.DOCS_CAP``; omitting it leaves the agent ungrounded as before.
    docs_overview: str = ""


# ---- Stream frames (NDJSON-from-POST) ---------------------------------------


class AgentStatusFrame(CamelModel):
    type: Literal["status"] = "status"
    message: str


class AgentMessageFrame(CamelModel):
    """A chunk of the assistant's conversational reply (accumulated on the client)."""

    type: Literal["message"] = "message"
    delta: str = ""
    done: bool = False


class AgentPlanFrame(CamelModel):
    """The terminal structured plan (present only when the agent proposes changes).

    ``base_version`` is the server's content hash of the writable fields at plan
    time (edit mode only); the client echoes it on apply so a concurrent manual
    edit is rejected rather than silently overwritten.
    """

    type: Literal["plan"] = "plan"
    plan: StoryPlan
    base_version: str | None = None


class AgentErrorFrame(CamelModel):
    """Terminal in-band error frame (mid-stream failures can't change the HTTP status)."""

    type: Literal["error"] = "error"
    message: str


AgentEditEvent = AgentStatusFrame | AgentMessageFrame | AgentPlanFrame | AgentErrorFrame


# ---- Apply (implement) ------------------------------------------------------


class StorylineApplyRequest(CamelModel):
    """Approve → implement an edit plan against an existing storyline."""

    scope: ScopeState = Field(default_factory=dict)
    plan: StoryPlan
    # The content hash the plan was built against; when present and mismatched the
    # apply is rejected (409 stale). Omit to skip the concurrency check.
    base_version: str | None = None


class StorylineApplyResponse(CamelModel):
    """The refreshed storyline plus a human-readable audit of what was applied."""

    storyline: "StorylineRead"
    applied: list[str] = Field(default_factory=list)


# Imported at the bottom to avoid a cycle (storyline schema is standalone).
from app.schemas.storyline import StorylineRead  # noqa: E402

StorylineApplyResponse.model_rebuild()
