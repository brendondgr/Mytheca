"""Setting CRUD over the API."""

from __future__ import annotations


def test_setting_crud(client, storyline_id):
    created = client.post(
        f"/api/storylines/{storyline_id}/settings",
        json={"name": "The Saltworn Tavern", "type": "Social Hub", "desc": "Lamplit."},
    )
    assert created.status_code == 201
    sid = created.json()["id"]

    listed = client.get(f"/api/storylines/{storyline_id}/settings")
    assert [s["id"] for s in listed.json()] == [sid]

    patched = client.patch(f"/api/settings/{sid}", json={"desc": "Low-beamed and lamplit."})
    assert patched.json()["desc"] == "Low-beamed and lamplit."

    assert client.delete(f"/api/settings/{sid}").status_code == 204
    assert client.get(f"/api/settings/{sid}").status_code == 404
