"""Type Registry request/response schemas (§1.4).

``GraphTypeRead`` is the wire shape for a registry entry; ``GraphTypeCreate`` is
how a user registers a new node/edge type (the create-time check that an edge
declares a valence lives here, since §1.3's net-lean computation cannot place an
edge without one).
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from app.models.graph_type import (
    KIND_EDGE,
    KIND_NODE,
    VALENCE_NEGATIVE,
    VALENCE_NEUTRAL,
    VALENCE_POSITIVE,
)
from app.schemas.base import CamelModel

GraphKind = Literal["node", "edge"]
GraphValence = Literal["positive", "negative", "neutral"]
GraphStatus = Literal["built_in", "experimental", "trusted"]
# numeric-with-range / enum / prose / reference-that-should-be-an-edge (§1.4).
FieldKind = Literal["numeric", "enum", "prose", "reference", "scalar"]

_VALENCES = {VALENCE_POSITIVE, VALENCE_NEGATIVE, VALENCE_NEUTRAL}


class GraphFieldSpec(CamelModel):
    """One metadata field declaration in a type's field schema."""

    name: str
    kind: FieldKind = "prose"
    required: bool = False
    default: object | None = None
    # numeric: bounds; enum: allowed values; reference: the edge type it implies.
    min: float | None = None
    max: float | None = None
    options: list[str] | None = None
    edge_type: str | None = None
    description: str = ""


class GraphTypeBase(CamelModel):
    kind: GraphKind = "node"
    type_name: str
    field_schema: list[GraphFieldSpec] = []
    description: str = ""
    valence: GraphValence | None = None
    decay: dict | None = None


class GraphTypeCreate(GraphTypeBase):
    """A user-registered type. Edges must declare a valence (§1.3)."""

    @model_validator(mode="after")
    def _edge_requires_valence(self) -> GraphTypeCreate:
        if self.kind == KIND_EDGE and self.valence not in _VALENCES:
            raise ValueError("An edge type must declare a valence (positive|negative|neutral).")
        if self.kind == KIND_NODE and self.valence is not None:
            raise ValueError("A node type must not declare a valence.")
        return self


class GraphTypeUpdate(CamelModel):
    field_schema: list[GraphFieldSpec] | None = None
    description: str | None = None
    valence: GraphValence | None = None
    decay: dict | None = None
    status: GraphStatus | None = None


class GraphTypeRead(CamelModel):
    id: str
    storyline_id: str | None = None
    kind: GraphKind
    type_name: str
    field_schema: list[GraphFieldSpec] = []
    description: str = ""
    valence: GraphValence | None = None
    decay: dict | None = None
    status: GraphStatus
