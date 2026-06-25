"""GraphTypeDefinition — the Story Graph Type Registry (§1.4).

The **semantic source of truth** for the graph's type system: which node and edge
types exist, the metadata field schema each carries, the natural-language meaning
of each (the agent-facing description), and — for edges — the valence the net-lean
computation needs (§1.3). It lives in the application store, deliberately *separate
from Neo4j*: Neo4j holds the **instances** (the actual Meis and Blackwood Taverns);
this registry holds the **type system** that describes them. The two reconcile at
write time (the writer validates a proposed instance against the registry — §6.5).

Built-in types (the §5 seed catalogue) are **global**: ``storyline_id`` is NULL and
``status`` is ``built_in``, so every storyline starts with them. Users *extend* the
catalogue **per-storyline** by adding rows (``status`` ``experimental`` until vetted,
then ``trusted`` — the staging gate of §10). The engine never distinguishes built-in
from user-defined types; only ``status`` gates the hot path.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, JSONColumn
from app.core.ids import new_id

# kind discriminator
KIND_NODE = "node"
KIND_EDGE = "edge"

# status — the §10 staging gate. Only built_in + trusted reach the hot path (§7.2);
# experimental user types are served by the async / non-hot path (Text2Cypher) only.
STATUS_BUILT_IN = "built_in"
STATUS_EXPERIMENTAL = "experimental"
STATUS_TRUSTED = "trusted"
HOT_PATH_STATUSES = frozenset({STATUS_BUILT_IN, STATUS_TRUSTED})

# valence — edges only; what the net "lean toward/away" computation places (§1.3).
VALENCE_POSITIVE = "positive"
VALENCE_NEGATIVE = "negative"
VALENCE_NEUTRAL = "neutral"


class GraphTypeDefinition(Base):
    __tablename__ = "graph_type_definitions"
    # A storyline can't declare the same (kind, type_name) twice. Built-in rows
    # have storyline_id NULL — SQL treats NULLs as distinct, so the catalogue's
    # idempotency is enforced in code (seed_builtin_types), not by this constraint.
    __table_args__ = (
        UniqueConstraint("storyline_id", "kind", "type_name", name="uq_graph_type_scope"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("gt"))
    # NULL = a global, built-in type shared by every storyline. A non-NULL value
    # scopes a user-defined type to one world. Real FK so a storyline delete cleans
    # its user types on Postgres (ondelete CASCADE); built-ins (NULL) are untouched.
    storyline_id: Mapped[str | None] = mapped_column(
        ForeignKey("storylines.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # "node" → a Neo4j label; "edge" → a Neo4j relationship type (§6.1).
    kind: Mapped[str] = mapped_column(String, default=KIND_NODE)
    # The label / relationship type itself, e.g. "Character", "Setting", "LOVES".
    type_name: Mapped[str] = mapped_column(String)
    # The metadata field schema: an ordered list of
    #   {name, kind: numeric|enum|prose|reference, required: bool, default, ...}.
    # This *is* the writer's validation (§6.5).
    field_schema: Mapped[list[dict]] = mapped_column(JSONColumn, default=list)
    # The agent-facing meaning of the type — the same role per-stat guidance plays
    # for a stat. Handed to the read path so Text2Cypher is grounded (§1.4/§7.3).
    description: Mapped[str] = mapped_column(Text, default="")
    # Edges only: positive | negative | neutral. NULL for node types.
    valence: Mapped[str | None] = mapped_column(String, nullable=True)
    # Edges only: default decay behaviour ({half_life, floor, ...}); NULL otherwise.
    decay: Mapped[dict | None] = mapped_column(JSONColumn, nullable=True)
    # built_in | experimental | trusted — the §10 hot-path staging gate.
    status: Mapped[str] = mapped_column(String, default=STATUS_EXPERIMENTAL)
