"""The Type Registry (§1.4) — seed idempotency, resolution precedence, and the
compiled validation/schema artifacts."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.content.graph_registry import BUILTIN_TYPES
from app.models import GraphTypeDefinition, Storyline
from app.services import type_registry


def test_seed_builtin_types_is_idempotent(db_session):
    added = type_registry.seed_builtin_types(db_session)
    assert added == len(BUILTIN_TYPES)
    # Second call inserts nothing; the catalogue is fully present.
    assert type_registry.seed_builtin_types(db_session) == 0
    total = db_session.query(GraphTypeDefinition).count()
    assert total == len(BUILTIN_TYPES)


def test_builtins_are_global_and_built_in(db_session):
    type_registry.seed_builtin_types(db_session)
    character = type_registry.resolve_type(db_session, "node", "Character")
    assert character is not None
    assert character.storyline_id is None
    assert character.status == "built_in"
    assert type_registry.is_hot_path_trusted(character) is True


def test_loves_edge_has_positive_valence(db_session):
    type_registry.seed_builtin_types(db_session)
    loves = type_registry.resolve_type(db_session, "edge", "loves")
    assert loves is not None and loves.valence == "positive"


def test_user_type_shadows_global_builtin(db_session):
    type_registry.seed_builtin_types(db_session)
    db_session.add(Storyline(id="w1", title="W1"))
    db_session.commit()
    scoped = GraphTypeDefinition(
        storyline_id="w1", kind="node", type_name="Character", description="overridden"
    )
    db_session.add(scoped)
    db_session.commit()

    # Scoped to w1 → the override; with no storyline → the global built-in.
    assert type_registry.resolve_type(db_session, "node", "Character", "w1").description == "overridden"
    assert type_registry.resolve_type(db_session, "node", "Character").status == "built_in"


def test_unique_per_storyline(db_session):
    db_session.add(Storyline(id="w1", title="W1"))
    db_session.commit()
    db_session.add_all(
        [
            GraphTypeDefinition(storyline_id="w1", kind="node", type_name="Ritual"),
            GraphTypeDefinition(storyline_id="w1", kind="node", type_name="Ritual"),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_list_types_scopes_to_storyline(db_session):
    type_registry.seed_builtin_types(db_session)
    db_session.add(Storyline(id="w1", title="W1"))
    db_session.add(Storyline(id="w2", title="W2"))
    db_session.commit()
    db_session.add(GraphTypeDefinition(storyline_id="w1", kind="node", type_name="Ritual"))
    db_session.commit()

    w1_names = {t.type_name for t in type_registry.list_types(db_session, "w1")}
    w2_names = {t.type_name for t in type_registry.list_types(db_session, "w2")}
    assert "Ritual" in w1_names  # its own user type
    assert "Ritual" not in w2_names  # not visible to a different world
    assert "Character" in w1_names and "Character" in w2_names  # built-ins shared


def test_validation_rules_and_schema_blob(db_session):
    type_registry.seed_builtin_types(db_session)
    rules = type_registry.validation_rules(db_session)
    assert "node:Character" in rules
    assert rules["edge:loves"]["valence"] == "positive"

    blob = type_registry.schema_blob(db_session)
    node_types = {n["type"] for n in blob["nodes"]}
    edge_types = {e["type"] for e in blob["edges"]}
    assert {"Character", "Setting", "Event", "Secret", "Faction", "Consequence"} <= node_types
    assert "loves" in edge_types
    assert all(n["hotPathTrusted"] for n in blob["nodes"])  # built-ins are trusted
