"""The two features the owner named as must-keep, verified against a free-text turn.

Both read the scene's transcript rather than its beats, so both *should* survive the new
engine — which is exactly why this is a test and not an assumption. One of them did not.
"""

from __future__ import annotations

from app.services import scene_moment


class Row:
    """A persisted event, as `scene_moment` reads them."""

    def __init__(self, type_: str, data: dict):
        self.type = type_
        self.data = data


NAMES = {"c1": "Mei", "c2": "Valdar"}


def test_the_picture_reads_a_free_text_passage():
    beats = scene_moment._recent_beats(
        [Row("scene_prose", {"text": "Mei sets the ledger down. Valdar does not move."})],
        NAMES,
        8,
    )
    assert len(beats) == 1


def test_a_free_text_passage_is_rendered_without_a_speaker():
    """There is no speaker. Prefixing a name would tell the prompt writer one character
    said all of it — including the other characters' dialogue."""
    line = scene_moment._render_beat(
        Row("scene_prose", {"text": "Mei sets the ledger down."}), NAMES
    )
    assert line == "Mei sets the ledger down."
    assert not line.startswith("Someone:")


def test_the_picture_reads_character_prose_too():
    """A pre-existing gap this phase caught: `character_prose` is the form a character beat
    takes today and was absent from the list, so every scene image was being composed from
    the narrator's lines and the player's own with the cast's beats invisible to it.
    """
    beats = scene_moment._recent_beats(
        [Row("character_prose", {"text": "I watch the rain.", "characterId": "c1"})], NAMES, 8
    )
    assert len(beats) == 1
    assert scene_moment._render_beat(beats[0], NAMES) == "Mei: I watch the rain."


def test_a_free_text_scene_falls_back_to_the_present_cast_for_who_is_in_frame():
    """A passage names nobody in its envelope, so nothing can be derived from it — the
    picture shows whoever is present, which is the right answer for a whole-room turn."""

    class Char:
        def __init__(self, cid, name):
            self.id = cid
            self.name = name

    cast = [Char("c1", "Mei"), Char("c2", "Valdar")]
    framed = scene_moment._in_frame(
        [Row("scene_prose", {"text": "The room waits."})], cast, {}
    )
    assert [c.name for c in framed] == ["Mei", "Valdar"]
