"""The style guide over the wire: round-trip, clearing, tolerance, and the catalog.

Every tolerance asserted here has the same reason behind it. The feature is optional and
retrofitted, so a client that has never heard of it, a row written before it existed, and a
guide carrying a block id from a newer build must all be ordinary states rather than errors.
"""

from __future__ import annotations


def _storyline(client, **kw) -> dict:
    body = {"title": "Harrow Lane", "genre": "Contemporary", **kw}
    res = client.post("/api/storylines", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _scenario(client, storyline_id: str, **kw) -> dict:
    body = {"title": "Kitchen", **kw}
    res = client.post(f"/api/storylines/{storyline_id}/scenarios", json=body)
    assert res.status_code == 201, res.text
    return res.json()


# ---- storyline ---------------------------------------------------------------------


def test_style_blocks_round_trip_on_a_storyline(client):
    created = _storyline(client, styleBlocks={"voice": "Plain and short."})
    assert created["styleBlocks"] == {"voice": "Plain and short."}
    fetched = client.get(f"/api/storylines/{created['id']}").json()
    assert fetched["styleBlocks"] == {"voice": "Plain and short."}


def test_a_storyline_created_without_a_guide_reads_as_empty_not_null(client):
    created = _storyline(client)
    assert created["styleBlocks"] == {}
    assert client.get(f"/api/storylines/{created['id']}").json()["styleBlocks"] == {}


def test_patching_a_block_replaces_the_whole_guide(client):
    """The field is wholesale-edited value data, like ``branches`` — not a merge target."""
    created = _storyline(client, styleBlocks={"voice": "Plain.", "never": "No recaps."})
    res = client.patch(
        f"/api/storylines/{created['id']}", json={"styleBlocks": {"voice": "Clipped."}}
    )
    assert res.status_code == 200
    assert res.json()["styleBlocks"] == {"voice": "Clipped."}


def test_clearing_a_block_removes_it(client):
    created = _storyline(client, styleBlocks={"voice": "Plain.", "never": "No recaps."})
    res = client.patch(
        f"/api/storylines/{created['id']}",
        json={"styleBlocks": {"voice": "Plain.", "never": "   "}},
    )
    assert res.json()["styleBlocks"] == {"voice": "Plain."}


def test_clearing_every_block_is_allowed_and_reads_as_empty(client):
    """Removable, not just editable — an author must be able to opt back out entirely."""
    created = _storyline(client, styleBlocks={"voice": "Plain."})
    res = client.patch(f"/api/storylines/{created['id']}", json={"styleBlocks": {}})
    assert res.json()["styleBlocks"] == {}


def test_an_unknown_block_id_is_dropped_rather_than_rejected(client):
    created = _storyline(
        client, styleBlocks={"voice": "Plain.", "cadence": "from a newer build"}
    )
    assert created["styleBlocks"] == {"voice": "Plain."}


def test_stored_text_is_canonicalised_on_write(client):
    """The stored bytes ARE the cached prefix, so they are normalised on the way in."""
    created = _storyline(client, styleBlocks={"voice": "  Plain.  \r\n\r\n\r\nShort.  "})
    assert created["styleBlocks"]["voice"] == "Plain.\n\nShort."


def test_a_client_that_never_sends_the_field_is_unaffected(client):
    created = _storyline(client, styleBlocks={"voice": "Plain."})
    res = client.patch(f"/api/storylines/{created['id']}", json={"title": "Renamed"})
    assert res.status_code == 200
    assert res.json()["styleBlocks"] == {"voice": "Plain."}


# ---- scenario ----------------------------------------------------------------------


def test_style_blocks_round_trip_on_a_scenario(client):
    storyline = _storyline(client, styleBlocks={"voice": "Plain."})
    scenario = _scenario(client, storyline["id"], styleBlocks={"attention": "The cold."})
    assert scenario["styleBlocks"] == {"attention": "The cold."}
    res = client.patch(
        f"/api/scenarios/{scenario['id']}", json={"styleBlocks": {"attention": "The heat."}}
    )
    assert res.json()["styleBlocks"] == {"attention": "The heat."}


def test_a_scenario_without_overrides_reads_as_empty(client):
    storyline = _storyline(client)
    assert _scenario(client, storyline["id"])["styleBlocks"] == {}


# ---- the catalog -------------------------------------------------------------------


def test_style_guide_catalog_lists_six_blocks_and_three_builtins(client):
    body = client.get("/api/options/style-guide").json()
    assert [b["id"] for b in body["blocks"]] == [
        "attention", "voice", "pacing", "texture", "never", "signature"
    ]
    assert [p["id"] for p in body["presets"]] == ["mystery", "romance", "action"]
    assert all(p["builtin"] for p in body["presets"])
    assert body["presets"][1]["blocks"]["signature"].startswith("Close and unsaid")


def test_the_signature_block_is_marked_as_the_one_in_the_tail(client):
    blocks = {b["id"]: b for b in client.get("/api/options/style-guide").json()["blocks"]}
    assert blocks["signature"]["placement"] == "tail"
    assert blocks["pacing"]["reader"] == "planner"
    assert all(blocks[i]["placement"] == "prefix" for i in ("attention", "voice", "texture", "never"))


def test_saving_and_deleting_an_author_preset(client):
    saved = client.post(
        "/api/options/style-presets",
        json={"id": "harrow", "name": "Harrow", "blocks": {"voice": "Plain."}},
    ).json()
    mine = [p for p in saved["presets"] if not p["builtin"]]
    assert [p["id"] for p in mine] == ["harrow"]
    assert mine[0]["blocks"] == {"voice": "Plain."}

    after = client.delete("/api/options/style-presets/harrow").json()
    assert [p["id"] for p in after["presets"]] == ["mystery", "romance", "action"]


def test_a_saved_preset_cannot_shadow_a_builtin(client):
    """Overwriting "Romance" by accident would leave the author no way to get it back."""
    body = client.post(
        "/api/options/style-presets",
        json={"id": "romance", "name": "Mine", "blocks": {"voice": "Plain."}},
    ).json()
    romance = next(p for p in body["presets"] if p["id"] == "romance")
    assert romance["builtin"] and romance["name"] == "Romance"


def test_deleting_a_builtin_does_nothing(client):
    body = client.delete("/api/options/style-presets/romance").json()
    assert [p["id"] for p in body["presets"]] == ["mystery", "romance", "action"]


def test_an_empty_preset_is_not_saved(client):
    body = client.post(
        "/api/options/style-presets", json={"id": "blank", "name": "Blank", "blocks": {}}
    ).json()
    assert [p["id"] for p in body["presets"]] == ["mystery", "romance", "action"]
