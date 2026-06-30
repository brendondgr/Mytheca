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


def test_setting_node_metadata_roundtrip(client, storyline_id):
    created = client.post(
        f"/api/storylines/{storyline_id}/settings",
        json={
            "name": "The Drowned Market",
            "type": "Black Market",
            "desc": "Below the tideline.",
            "atmosphere": "Brine and tallow; lantern-light on standing water.",
            "features": "Submerged vault rows and plank walkways.",
            "currentState": "Tide rising; bells counting it down.",
            "image": "/media/scenes/abc123.webp",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["atmosphere"].startswith("Brine and tallow")
    assert body["features"].startswith("Submerged vault")
    assert body["currentState"].startswith("Tide rising")
    assert body["image"] == "/media/scenes/abc123.webp"
    # The event timeline is play-accrued: it ships empty, not null.
    assert body["timeline"] == []
    sid = body["id"]

    patched = client.patch(
        f"/api/settings/{sid}",
        json={"atmosphere": "Now flooded to the knee; the lanterns drowning one by one."},
    )
    assert patched.status_code == 200
    assert patched.json()["atmosphere"].startswith("Now flooded")
    # Untouched fields survive the partial update.
    assert patched.json()["features"].startswith("Submerged vault")


def test_setting_defaults_have_null_node_metadata(client, storyline_id):
    body = client.post(
        f"/api/storylines/{storyline_id}/settings", json={"name": "A bare room"}
    ).json()
    assert body["atmosphere"] is None
    assert body["features"] is None
    assert body["currentState"] is None
    assert body["image"] is None
    # Scene-art prompts default to null until an image is generated + saved.
    assert body["sceneArtPositive"] is None
    assert body["sceneArtNegative"] is None
    assert body["timeline"] == []


def test_setting_scene_art_prompts_roundtrip(client, storyline_id):
    """Create + PATCH persist the establishing-image prompts; GET reflects them."""
    created = client.post(
        f"/api/storylines/{storyline_id}/settings",
        json={
            "name": "The Lantern Bridge",
            "image": "/media/scenes/bridge.webp",
            "sceneArtPositive": "watercolor bridge at dusk, lanterns, mist",
            "sceneArtNegative": "people, text, blurry",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["image"] == "/media/scenes/bridge.webp"
    assert body["sceneArtPositive"] == "watercolor bridge at dusk, lanterns, mist"
    assert body["sceneArtNegative"] == "people, text, blurry"
    sid = body["id"]

    patched = client.patch(
        f"/api/settings/{sid}",
        json={
            "sceneArtPositive": "watercolor bridge at dawn, lanterns dimming",
            "sceneArtNegative": "lowres, watermark",
        },
    )
    assert patched.status_code == 200
    data = patched.json()
    assert data["sceneArtPositive"] == "watercolor bridge at dawn, lanterns dimming"
    assert data["sceneArtNegative"] == "lowres, watermark"
    # Untouched field preserved by the partial update.
    assert data["image"] == "/media/scenes/bridge.webp"

    fetched = client.get(f"/api/settings/{sid}").json()
    assert fetched["sceneArtPositive"] == "watercolor bridge at dawn, lanterns dimming"
    assert fetched["sceneArtNegative"] == "lowres, watermark"
