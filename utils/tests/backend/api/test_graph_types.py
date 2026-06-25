"""Type Registry routes — list built-ins, register/patch/delete user types, and
the create-time guardrails (edges need a valence; built-ins are immutable).

The TestClient and ``db_session`` share the same in-memory engine within a test
(conftest StaticPool), so seeding built-ins via ``db_session`` makes them visible
to the routes without running the full preflight.
"""

from __future__ import annotations

from app.services import type_registry


def test_list_includes_builtins_with_valence(client, db_session, storyline_id):
    type_registry.seed_builtin_types(db_session)
    res = client.get(f"/api/storylines/{storyline_id}/graph/types")
    assert res.status_code == 200
    by_name = {t["typeName"]: t for t in res.json()}
    assert "Character" in by_name and by_name["Character"]["kind"] == "node"
    assert by_name["loves"]["kind"] == "edge"
    assert by_name["loves"]["valence"] == "positive"
    assert by_name["Character"]["status"] == "built_in"


def test_create_user_node_type_defaults_experimental(client, db_session, storyline_id):
    type_registry.seed_builtin_types(db_session)
    res = client.post(
        f"/api/storylines/{storyline_id}/graph/types",
        json={
            "kind": "node",
            "typeName": "Ritual",
            "description": "A bound ceremony multiple characters participate in.",
            "fieldSchema": [{"name": "potency", "kind": "numeric", "min": 0, "max": 1}],
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["typeName"] == "Ritual"
    assert body["status"] == "experimental"  # staged until promoted (§10)
    assert body["storylineId"] == storyline_id


def test_create_edge_requires_valence(client, storyline_id):
    res = client.post(
        f"/api/storylines/{storyline_id}/graph/types",
        json={"kind": "edge", "typeName": "sworn_to"},
    )
    assert res.status_code == 422  # validator: an edge must declare a valence


def test_create_edge_with_valence_ok(client, storyline_id):
    res = client.post(
        f"/api/storylines/{storyline_id}/graph/types",
        json={"kind": "edge", "typeName": "sworn_to", "valence": "positive"},
    )
    assert res.status_code == 201
    assert res.json()["valence"] == "positive"


def test_promote_user_type_to_trusted(client, storyline_id):
    created = client.post(
        f"/api/storylines/{storyline_id}/graph/types",
        json={"kind": "node", "typeName": "Ritual"},
    ).json()
    patched = client.patch(f"/api/graph/types/{created['id']}", json={"status": "trusted"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "trusted"


def test_duplicate_user_type_conflicts(client, storyline_id):
    payload = {"kind": "node", "typeName": "Ritual"}
    assert client.post(f"/api/storylines/{storyline_id}/graph/types", json=payload).status_code == 201
    assert client.post(f"/api/storylines/{storyline_id}/graph/types", json=payload).status_code == 409


def test_builtins_are_immutable(client, db_session, storyline_id):
    type_registry.seed_builtin_types(db_session)
    listed = client.get(f"/api/storylines/{storyline_id}/graph/types").json()
    character = next(t for t in listed if t["typeName"] == "Character")
    assert client.patch(f"/api/graph/types/{character['id']}", json={"description": "x"}).status_code == 409
    assert client.delete(f"/api/graph/types/{character['id']}").status_code == 409


def test_delete_user_type(client, storyline_id):
    created = client.post(
        f"/api/storylines/{storyline_id}/graph/types",
        json={"kind": "node", "typeName": "Ritual"},
    ).json()
    assert client.delete(f"/api/graph/types/{created['id']}").status_code == 204
    remaining = {t["typeName"] for t in client.get(f"/api/storylines/{storyline_id}/graph/types").json()}
    assert "Ritual" not in remaining
