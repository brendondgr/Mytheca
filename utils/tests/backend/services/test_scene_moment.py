"""In-narrative image generation — scene → prompt → landscape WebP → persisted beat.

Fully offline: ``agents.moment_agent.write_moment_prompt`` and
``services.comfyui.generate`` are stubbed, and the moments directory is redirected
to a tmp path (mirroring ``test_scene_art.py``). What is under test is the
*gathering* — which beats and which characters reach the prompt writer — plus the
frame the render is asked for and the beat that ends up in the session.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from app.core.errors import APIError
from app.events.envelope import SceneImageEvent
from app.events.stream import build_event
from app.models import Character, PlaySession, Scenario, Setting, Storyline
from app.schemas.play import MomentPromptResponse, MomentRequest, MomentStageFrame
from app.schemas.settings import ComfyConfigUpdate, LlmConfigUpdate
from app.services import comfyui, events_store, scene_moment, settings_store


def _png_bytes(size: tuple[int, int] = (32, 18)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, "slategray").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def scene(db_session):
    """A storyline + place + two-character scenario + an open play session."""
    storyline = Storyline(id="sl1", title="Embergate", genre="Maritime")
    setting = Setting(
        id="st1",
        storyline_id="sl1",
        name="The Saltworn",
        type="Social Hub",
        desc="A smoke-dark dockside tavern.",
        atmosphere="Lamplight, rain on the shutters, wet wool and tar.",
        current_state="Night; the shutters are barred.",
    )
    maerin = Character(
        id="maerin",
        storyline_id="sl1",
        name="Maerin Voss",
        role="Harbor-mistress",
        appearance="Weathered and sharp-eyed.",
        portrait_positive="middle-aged human woman, salt-stained oilskin coat, watercolor portrait",
    )
    wren = Character(
        id="wren",
        storyline_id="sl1",
        name="Wren",
        role="Informant",
        appearance="Wiry and freckled.",
        portrait_positive="wiry young human, patched grey cloak, watercolor portrait",
    )
    scenario = Scenario(
        id="sc1",
        storyline_id="sl1",
        title="Standoff",
        genre="Maritime",
        tone="Tense",
        setting_id="st1",
        cast_ids=["maerin", "wren"],
    )
    session = PlaySession(id="ps1", scenario_id="sc1")
    db_session.add_all([storyline, setting, maerin, wren, scenario, session])
    db_session.commit()
    return session


def _beat(db_session, type_: str, data: dict, seq: int) -> None:
    events_store.persist_story_event(
        db_session,
        build_event(type_, data, scenario_id="sc1", session_id="ps1", seq=seq),
    )


def _configure(db_session, *, comfy: str = "http://comfy.test:8199") -> None:
    settings_store.update_llm(
        db_session,
        LlmConfigUpdate(base_url="http://llm.test/v1", model="test-model", api_key="sk-test"),
    )
    settings_store.update_comfy(db_session, ComfyConfigUpdate(base_url=comfy))


def _stub_prompt(monkeypatch, seen: dict | None = None):
    def fake_write(db, **kwargs):
        if seen is not None:
            seen.update(kwargs)
        return MomentPromptResponse(
            positive="two figures across a lamplit table, wide landscape composition",
            negative="text, watermark",
            caption="Maerin and Wren face each other across a lamplit table.",
        )

    monkeypatch.setattr(scene_moment.moment_agent, "write_moment_prompt", fake_write)


def _stub_render(monkeypatch, captured: dict):
    def fake_generate(base, workflow, **kwargs):
        captured["base"] = base
        captured["workflow"] = workflow
        captured.update(kwargs)
        return _png_bytes(), {"filename": "out.png", "subfolder": "", "type": "output"}

    monkeypatch.setattr(comfyui, "generate", fake_generate)


def test_generate_moment_renders_landscape_and_persists_the_beat(
    db_session, scene, tmp_path, monkeypatch
):
    _configure(db_session)
    _beat(db_session, "narration", {"text": "Rain ticks against the shutters."}, 0)
    _beat(db_session, "character_dialogue", {"characterId": "maerin", "text": "You're late."}, 1)
    seen: dict = {}
    captured: dict = {}
    _stub_prompt(monkeypatch, seen)
    _stub_render(monkeypatch, captured)
    monkeypatch.setattr(scene_moment, "_moments_dir", lambda: tmp_path)

    ctx = scene_moment.prepare_moment(db_session, "sc1", MomentRequest(session_id="ps1"))
    frames = list(scene_moment.generate_moment(db_session, ctx))

    # Two progress stages, then the story event.
    stages = [f for f in frames if isinstance(f, MomentStageFrame)]
    assert [s.stage for s in stages] == ["prompt", "render"]
    assert stages[1].positive.startswith("two figures")

    event = frames[-1]
    assert isinstance(event, SceneImageEvent)
    assert event.data.url.startswith("/media/moments/") and event.data.url.endswith(".webp")
    assert event.data.caption.startswith("Maerin and Wren")
    assert event.data.character_ids == ["maerin"]  # only who actually appeared in the window
    assert event.seq == 2  # continues the session's monotonic sequence

    # The file is a real WebP on disk, and the frame asked for is landscape.
    written = tmp_path / event.data.url.rsplit("/", 1)[1]
    with Image.open(written) as im:
        assert im.format == "WEBP"
    assert captured["width"] == 1216 and captured["height"] == 832
    assert captured["width"] > captured["height"]
    assert captured["base"] == "http://comfy.test:8199"
    assert isinstance(captured["seed"], int)  # a fresh seed, so a re-render re-executes

    # The beat is persisted, so a reload replays the picture in place.
    history = events_store.session_events(db_session, "ps1")
    assert [e.type for e in history][-1] == "scene_image"

    # The prompt writer saw the scene: the beats, the place, the world, the look.
    assert seen["beats"] == ["Narrator: Rain ticks against the shutters.", "Maerin Voss: You're late."]
    assert "The Saltworn" in seen["place"]
    assert "Embergate" in seen["world"]
    assert [c.id for c in seen["cast"]] == ["maerin"]
    assert "salt-stained oilskin coat" in seen["cast"][0].portrait_positive
    assert seen["cast"][0].doing == 'says "You\'re late."'


def test_only_present_characters_active_in_the_window_are_in_frame(
    db_session, scene, tmp_path, monkeypatch
):
    _configure(db_session)
    _beat(db_session, "narration", {"text": "The room stills."}, 0)
    _beat(db_session, "character_dialogue", {"characterId": "maerin", "text": "Sit."}, 1)
    _beat(db_session, "character_action", {"characterId": "wren", "text": "leans in, low"}, 2)
    # Wren then leaves the scene — she is active in the window but no longer present.
    _beat(
        db_session,
        "character_status_change",
        {"characterId": "wren", "status": "left", "reason": "slipped out", "auto": True},
        3,
    )
    seen: dict = {}
    _stub_prompt(monkeypatch, seen)
    _stub_render(monkeypatch, {})
    monkeypatch.setattr(scene_moment, "_moments_dir", lambda: tmp_path)

    ctx = scene_moment.prepare_moment(db_session, "sc1", MomentRequest(session_id="ps1"))
    list(scene_moment.generate_moment(db_session, ctx))

    assert [c.id for c in seen["cast"]] == ["maerin"]


def test_narration_only_scene_frames_the_present_cast(db_session, scene, tmp_path, monkeypatch):
    """Nobody has spoken yet — the shot still shows who is standing there."""
    _configure(db_session)
    _beat(db_session, "narration", {"text": "Lamplight gutters across the long tables."}, 0)
    seen: dict = {}
    _stub_prompt(monkeypatch, seen)
    _stub_render(monkeypatch, {})
    monkeypatch.setattr(scene_moment, "_moments_dir", lambda: tmp_path)

    ctx = scene_moment.prepare_moment(db_session, "sc1", MomentRequest(session_id="ps1"))
    list(scene_moment.generate_moment(db_session, ctx))

    assert [c.id for c in seen["cast"]] == ["maerin", "wren"]


def test_beat_window_is_clamped(db_session, scene, tmp_path, monkeypatch):
    _configure(db_session)
    for i in range(30):
        _beat(db_session, "narration", {"text": f"Beat {i}."}, i)
    seen: dict = {}
    _stub_prompt(monkeypatch, seen)
    _stub_render(monkeypatch, {})
    monkeypatch.setattr(scene_moment, "_moments_dir", lambda: tmp_path)

    ctx = scene_moment.prepare_moment(db_session, "sc1", MomentRequest(session_id="ps1", beats=999))
    list(scene_moment.generate_moment(db_session, ctx))
    assert len(seen["beats"]) == 30  # clamped to the max window, capped by what exists

    ctx = scene_moment.prepare_moment(db_session, "sc1", MomentRequest(session_id="ps1", beats=0))
    list(scene_moment.generate_moment(db_session, ctx))
    assert len(seen["beats"]) == 8  # 0 → the default window, not "no beats"


def test_unplayed_scene_is_rejected_before_anything_is_rendered(db_session, scene):
    _configure(db_session)
    with pytest.raises(APIError) as exc:
        scene_moment.prepare_moment(db_session, "sc1", MomentRequest(session_id="ps1"))
    assert exc.value.status_code == 400


def test_unconfigured_comfyui_is_rejected_up_front(db_session, scene):
    _configure(db_session, comfy="")
    _beat(db_session, "narration", {"text": "Something happens."}, 0)
    with pytest.raises(APIError) as exc:
        scene_moment.prepare_moment(db_session, "sc1", MomentRequest(session_id="ps1"))
    assert exc.value.status_code == 400
    assert "ComfyUI" in exc.value.message


def test_unknown_session_is_rejected(db_session, scene):
    _configure(db_session)
    with pytest.raises(APIError) as exc:
        scene_moment.prepare_moment(db_session, "sc1", MomentRequest(session_id="ps-nope"))
    assert exc.value.status_code == 404
