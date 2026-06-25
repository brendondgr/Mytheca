"""The Type Registry service (§1.4) — the semantic type system over the graph.

Three jobs:
  * **seed** the built-in catalogue (§5) as global rows, idempotently;
  * **CRUD** for user-defined, per-storyline types (the extensibility spine);
  * **compile** the registry into the two artifacts the rest of the system reads —
    ``validation_rules`` (what the writer enforces, §6.5) and ``schema_blob`` (the
    schema-plus-descriptions handed to the agentic read path, §7.3).

Built-in types are global (``storyline_id is None``, ``status == built_in``) and
immutable; user types are scoped to one storyline and start ``experimental`` (the
§10 staging gate). ``resolve_type`` is what the writer calls to validate an
instance: a storyline-scoped definition shadows a global one of the same name.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.content.graph_registry import BUILTIN_TYPES
from app.core.errors import APIError
from app.models import GraphTypeDefinition, Storyline
from app.models.graph_type import (
    HOT_PATH_STATUSES,
    STATUS_BUILT_IN,
    STATUS_EXPERIMENTAL,
)
from app.schemas.graph_type import GraphTypeCreate, GraphTypeUpdate

# ---- seed ------------------------------------------------------------------


def seed_builtin_types(db: Session) -> int:
    """Insert any missing built-in (global) types. Idempotent; returns # inserted.

    Built-ins live with ``storyline_id is None``; since SQL treats NULLs as
    distinct, the unique constraint can't dedupe them, so existence is checked in
    code here (safe to call on every startup, like the Embergate seed).
    """
    existing = {
        (t.kind, t.type_name)
        for t in db.scalars(
            select(GraphTypeDefinition).where(GraphTypeDefinition.storyline_id.is_(None))
        )
    }
    inserted = 0
    for entry in BUILTIN_TYPES:
        key = (entry["kind"], entry["type_name"])
        if key in existing:
            continue
        db.add(
            GraphTypeDefinition(
                storyline_id=None,
                kind=entry["kind"],
                type_name=entry["type_name"],
                field_schema=entry.get("field_schema", []),
                description=entry.get("description", ""),
                valence=entry.get("valence"),
                decay=entry.get("decay"),
                status=STATUS_BUILT_IN,
            )
        )
        inserted += 1
    if inserted:
        db.commit()
    return inserted


# ---- reads -----------------------------------------------------------------


def list_types(db: Session, storyline_id: str | None = None) -> list[GraphTypeDefinition]:
    """All types visible to a storyline: the global built-ins + its user types."""
    stmt = select(GraphTypeDefinition).where(
        or_(
            GraphTypeDefinition.storyline_id.is_(None),
            GraphTypeDefinition.storyline_id == storyline_id,
        )
        if storyline_id is not None
        else GraphTypeDefinition.storyline_id.is_(None)
    )
    rows = list(db.scalars(stmt))
    rows.sort(key=lambda t: (t.kind, t.type_name))
    return rows


def resolve_type(
    db: Session, kind: str, type_name: str, storyline_id: str | None = None
) -> GraphTypeDefinition | None:
    """Resolve a type for a storyline; a storyline-scoped def shadows the global one."""
    if storyline_id is not None:
        scoped = db.scalar(
            select(GraphTypeDefinition).where(
                GraphTypeDefinition.storyline_id == storyline_id,
                GraphTypeDefinition.kind == kind,
                GraphTypeDefinition.type_name == type_name,
            )
        )
        if scoped is not None:
            return scoped
    return db.scalar(
        select(GraphTypeDefinition).where(
            GraphTypeDefinition.storyline_id.is_(None),
            GraphTypeDefinition.kind == kind,
            GraphTypeDefinition.type_name == type_name,
        )
    )


def get_type(db: Session, type_id: str) -> GraphTypeDefinition:
    row = db.get(GraphTypeDefinition, type_id)
    if row is None:
        raise APIError(404, "not_found", f"Graph type '{type_id}' not found.")
    return row


def is_hot_path_trusted(t: GraphTypeDefinition) -> bool:
    """True when this type may be queried on the latency-critical hot path (§10)."""
    return t.status in HOT_PATH_STATUSES


# ---- writes (user-defined types only) --------------------------------------


def create_user_type(
    db: Session, storyline_id: str, data: GraphTypeCreate
) -> GraphTypeDefinition:
    if db.get(Storyline, storyline_id) is None:
        raise APIError(404, "not_found", f"Storyline '{storyline_id}' not found.")
    dup = db.scalar(
        select(GraphTypeDefinition).where(
            GraphTypeDefinition.storyline_id == storyline_id,
            GraphTypeDefinition.kind == data.kind,
            GraphTypeDefinition.type_name == data.type_name,
        )
    )
    if dup is not None:
        raise APIError(
            409,
            "conflict",
            f"{data.kind} type '{data.type_name}' already exists for this storyline.",
        )
    row = GraphTypeDefinition(
        storyline_id=storyline_id,
        kind=data.kind,
        type_name=data.type_name,
        field_schema=[f.model_dump() for f in data.field_schema],
        description=data.description,
        valence=data.valence,
        decay=data.decay,
        status=STATUS_EXPERIMENTAL,  # staged until promoted (§10)
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_user_type(db: Session, type_id: str, data: GraphTypeUpdate) -> GraphTypeDefinition:
    row = get_type(db, type_id)
    if row.status == STATUS_BUILT_IN:
        raise APIError(409, "conflict", "Built-in graph types are immutable.")
    patch = data.model_dump(exclude_unset=True)
    if "field_schema" in patch and data.field_schema is not None:
        row.field_schema = [f.model_dump() for f in data.field_schema]
        patch.pop("field_schema")
    for key, value in patch.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_user_type(db: Session, type_id: str) -> None:
    row = get_type(db, type_id)
    if row.status == STATUS_BUILT_IN:
        raise APIError(409, "conflict", "Built-in graph types cannot be deleted.")
    db.delete(row)
    db.commit()


# ---- compiled artifacts (§1.4) ---------------------------------------------


def validation_rules(db: Session, storyline_id: str | None = None) -> dict:
    """Compile the writer's validation artifact (§1.4 #2 / §6.5).

    ``{(kind, type_name): {required: [...], fields: {name: kind}, valence}}`` —
    keyed by a ``"kind:type_name"`` string so it's JSON-serializable.
    """
    rules: dict[str, dict] = {}
    for t in list_types(db, storyline_id):
        required = [f.get("name") for f in t.field_schema if f.get("required")]
        fields = {f.get("name"): f.get("kind", "prose") for f in t.field_schema}
        rules[f"{t.kind}:{t.type_name}"] = {
            "required": required,
            "fields": fields,
            "valence": t.valence,
            "status": t.status,
        }
    return rules


def schema_blob(db: Session, storyline_id: str | None = None) -> dict:
    """Compile the schema-plus-descriptions blob for the read path (§1.4 #1 / §7.3).

    Grounds Text2Cypher in current, meaningful types. Only ``built_in``/``trusted``
    types are hot-path eligible (§10); the blob marks each so the read path can
    filter (schema filtering, §7.3) rather than dumping everything.
    """
    nodes, edges = [], []
    for t in list_types(db, storyline_id):
        entry = {
            "type": t.type_name,
            "description": t.description,
            "fields": t.field_schema,
            "hotPathTrusted": is_hot_path_trusted(t),
        }
        if t.kind == "edge":
            entry["valence"] = t.valence
            edges.append(entry)
        else:
            nodes.append(entry)
    return {"nodes": nodes, "edges": edges}
