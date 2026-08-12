"""The ``scene_image`` story event — the 8th type on the discriminated union.

A picture of the moment is a persisted narrative beat, not a side channel, so it
must build through the same ``build_event`` path (validated by construction) and
serialize in the camelCase wire shape the frontend mirror expects.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.events.envelope import SceneImageEvent, story_event_adapter
from app.events.stream import build_event, to_ndjson_line


def _event(**data):
    payload = {"url": "/media/moments/abc.webp", **data}
    return build_event(
        "scene_image", payload, scenario_id="sc1", session_id="ps1", seq=7
    )


def test_scene_image_builds_as_a_public_story_event():
    event = _event(
        prompt="rain-slick dock, weathered woman in an oilskin coat, wide landscape composition",
        negative="text, watermark",
        caption="A weathered woman closes her ledger on a rain-slick dock.",
        character_ids=["maerin", "wren"],
    )

    assert isinstance(event, SceneImageEvent)
    assert event.type == "scene_image"
    assert event.visibility == "public"  # a picture is shown, never conditioning-only
    assert event.seq == 7
    assert event.data.character_ids == ["maerin", "wren"]


def test_scene_image_serializes_camel_case_on_the_wire():
    line = to_ndjson_line(_event(caption="A quiet moment.", character_ids=["maerin"]))
    obj = json.loads(line)

    assert obj["type"] == "scene_image"
    assert obj["scenarioId"] == "sc1"
    assert obj["data"]["characterIds"] == ["maerin"]
    assert obj["data"]["url"] == "/media/moments/abc.webp"
    # Optional fields default rather than vanish, so the client never guards on undefined.
    assert obj["data"]["prompt"] == ""
    assert obj["data"]["negative"] == ""


def test_scene_image_round_trips_through_the_union_adapter():
    original = _event(caption="A quiet moment.")
    restored = story_event_adapter.validate_python(json.loads(to_ndjson_line(original)))

    assert isinstance(restored, SceneImageEvent)
    assert restored.data.caption == "A quiet moment."


def test_scene_image_requires_a_url():
    with pytest.raises(ValidationError):
        build_event("scene_image", {"caption": "no image"}, scenario_id="sc1", session_id="ps1", seq=1)
