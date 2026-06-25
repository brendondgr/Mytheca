"""Id generation: prefix-free short ids for the URL-facing entities.

Storyline ids are pure 8-hex and scenario ids pure 4-hex (no prefix), so they
read cleanly in ``/{storylineId}/{scenarioId}`` URLs. Every other entity keeps
its prefixed ``new_id`` form. Generated short ids must also be unique and the
client-supplied-id path must still pass through.
"""

from __future__ import annotations

import re

from app.core.ids import new_hex_id, new_id
from app.schemas.scenario import ScenarioCreate
from app.schemas.storyline import StorylineCreate
from app.services import crud

HEX = re.compile(r"^[0-9a-f]+$")


def test_new_hex_id_is_bare_hex_of_requested_length():
    sid = new_hex_id(8)
    assert len(sid) == 8 and HEX.match(sid) and "_" not in sid
    cid = new_hex_id(4)
    assert len(cid) == 4 and HEX.match(cid)


def test_new_id_keeps_prefix_for_other_entities():
    cid = new_id("c")
    assert cid.startswith("c_") and len(cid) == 12


def test_generated_short_ids_are_unique():
    assert len({new_hex_id(8) for _ in range(500)}) == 500


def test_create_storyline_mints_8_hex_id(db_session):
    sl = crud.create_storyline(db_session, StorylineCreate(title="Driftmark"))
    assert len(sl.id) == 8 and HEX.match(sl.id) and "_" not in sl.id


def test_create_scenario_mints_4_hex_id(db_session):
    sl = crud.create_storyline(db_session, StorylineCreate(title="Driftmark"))
    sc = crud.create_scenario(db_session, sl.id, ScenarioCreate(title="Low Tide"))
    assert len(sc.id) == 4 and HEX.match(sc.id) and "_" not in sc.id


def test_client_supplied_ids_still_pass_through(db_session):
    sl = crud.create_storyline(db_session, StorylineCreate(id="embergate", title="Embergate"))
    assert sl.id == "embergate"
    sc = crud.create_scenario(
        db_session, sl.id, ScenarioCreate(id="opening-scene", title="Opening")
    )
    assert sc.id == "opening-scene"
