"""World population — the create-time phase that fills a new world's cast + places.

The guarantee under test is *persistence*, not prose: whatever the drafting agents
return must end up as real `Character` / `Setting` rows on the storyline, because the
recurring failure mode is generated content that never reaches the world. The agents
and the ComfyUI pipeline are stubbed; the database is the real (in-memory) one.
"""

from __future__ import annotations

import pytest

from app.core.errors import APIError
from app.schemas.character import (
    CharacterDraftResponse,
    PortraitPromptResponse,
    StartingStatProposal,
    StartingStatsResponse,
    VoiceSample,
    VoiceSamplesResponse,
)
from app.schemas.setting import SceneArtPromptResponse, SettingDraftResponse
from app.schemas.storyline import StorylineCreate
from app.schemas.world_populate import (
    PopulateDoneFrame,
    PopulateStatusFrame,
    PopulateEntityFrame,
    PopulateErrorFrame,
    RosterEntry,
    RosterProposal,
)
from app.services import crud, world_populate


@pytest.fixture
def world(db_session):
    return crud.create_storyline(
        db_session, StorylineCreate(id="embergate", title="Embergate", genre="Maritime")
    ).id


def _roster(characters=("Maerin",), settings=("The Wharf",)) -> RosterProposal:
    return RosterProposal(
        characters=[RosterEntry(name=n, seed=f"{n} seed") for n in characters],
        settings=[RosterEntry(name=n, seed=f"{n} seed") for n in settings],
    )


def _character_draft(name: str = "Maerin Voss") -> CharacterDraftResponse:
    return CharacterDraftResponse(
        name=name,
        role="Smuggler",
        traits="wry · watchful",
        speech="Clipped.",
        goal="Clear the debt.",
        secret="Sold the charts.",
        appearance="Salt-bleached coat.",
        background="Raised on the wharf.",
        personality="Guarded.",
        color="#3A5A78",
    )


def _setting_draft(name: str = "The Salt Wharf") -> SettingDraftResponse:
    return SettingDraftResponse(
        name=name,
        type="Social Hub",
        desc="Where cargo changes hands.",
        atmosphere="Tar and cold rope.",
        features="Crane, ledger house.",
        current_state="Dawn, low tide.",
    )


def _stub_agents(monkeypatch, *, roster, character=None, setting=None, voice=None, stats=None):
    """Stub every generation the run makes; persistence stays real.

    Voice + starting stats are stubbed to no-ops by default so the tests that are about
    drafting/artwork stay about that; the tests below that *are* about them override.
    """
    monkeypatch.setattr(
        world_populate.roster_agent, "propose_roster", lambda *a, **k: roster
    )
    monkeypatch.setattr(
        world_populate.character_agent,
        "propose_voice_samples",
        voice or (lambda *a, **k: VoiceSamplesResponse(samples=[])),
    )
    monkeypatch.setattr(
        world_populate.character_agent,
        "propose_starting_stats",
        stats or (lambda *a, **k: StartingStatsResponse(proposals=[])),
    )
    monkeypatch.setattr(
        world_populate.character_agent,
        "draft_character",
        character or (lambda *a, **k: _character_draft()),
    )
    monkeypatch.setattr(
        world_populate.setting_agent,
        "draft_setting",
        setting or (lambda *a, **k: _setting_draft()),
    )


def _run(db, storyline_id, **kwargs):
    return list(world_populate.populate_world(db, storyline_id, **kwargs))


def test_persists_the_roster_as_real_rows(db_session, world, monkeypatch):
    """The whole point: what was generated is readable back off the storyline."""
    _stub_agents(monkeypatch, roster=_roster(("Maerin", "Cael"), ("The Wharf",)))

    frames = _run(db_session, world)

    characters = crud.list_characters(db_session, world)
    settings = crud.list_settings(db_session, world)
    # The second draft returns the same invented name; it is disambiguated (below).
    assert [c.name for c in characters] == ["Maerin Voss", "Cael"]
    assert [s.name for s in settings] == ["The Salt Wharf"]
    assert all(c.appearance and c.background and c.personality for c in characters)
    assert settings[0].atmosphere and settings[0].current_state

    done = frames[-1]
    assert isinstance(done, PopulateDoneFrame)
    assert (done.characters, done.settings) == (2, 1)
    entities = [f for f in frames if isinstance(f, PopulateEntityFrame)]
    assert {f.id for f in entities} == {c.id for c in characters} | {s.id for s in settings}


def test_a_failed_draft_costs_only_that_entity(db_session, world, monkeypatch):
    """One bad draft must not abort the run or roll back what already landed."""
    calls = {"n": 0}

    def flaky(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise APIError(502, "upstream_error", "The model did not return valid JSON.")
        return _character_draft("Cael")

    _stub_agents(monkeypatch, roster=_roster(("Maerin", "Cael"), ()), character=flaky)

    frames = _run(db_session, world)

    assert [c.name for c in crud.list_characters(db_session, world)] == ["Cael"]
    errors = [f for f in frames if isinstance(f, PopulateErrorFrame)]
    assert len(errors) == 1 and "Maerin" in errors[0].message
    assert frames[-1].characters == 1


def test_artwork_is_skipped_when_comfyui_is_unreachable(db_session, world, monkeypatch):
    """Asking for artwork without a live render server is a note, not a failed world.

    The probe runs once — an unreachable server must not cost every entity its own
    render timeout, and must not stop the entity from being written.
    """
    _stub_agents(monkeypatch, roster=_roster(("Maerin",), ()))
    probes: list[str] = []

    def unreachable(base: str):
        probes.append(base)
        raise RuntimeError("connection refused")

    monkeypatch.setattr(world_populate.comfyui, "check_connection", unreachable)
    rendered: list[str] = []
    monkeypatch.setattr(
        world_populate.portraits,
        "generate_portrait",
        lambda *a, **k: rendered.append("portrait") or {"portrait": "/media/x.webp"},
    )

    frames = _run(db_session, world, with_artwork=True)

    assert len(probes) == 1
    assert rendered == []
    assert crud.list_characters(db_session, world)[0].portrait is None
    notes = [f for f in frames if isinstance(f, PopulateErrorFrame)]
    assert len(notes) == 1 and "ComfyUI" in notes[0].message
    assert frames[-1].characters == 1


def test_artwork_is_never_probed_when_not_requested(db_session, world, monkeypatch):
    _stub_agents(monkeypatch, roster=_roster(("Maerin",), ()))

    def fail(*_a, **_k):
        raise AssertionError("ComfyUI must not be touched unless artwork was requested")

    monkeypatch.setattr(world_populate.comfyui, "check_connection", fail)

    frames = _run(db_session, world)

    assert [f for f in frames if isinstance(f, PopulateErrorFrame)] == []
    assert crud.list_characters(db_session, world)[0].portrait is None


def test_artwork_renders_and_persists_when_configured(db_session, world, monkeypatch):
    _stub_agents(monkeypatch, roster=_roster(("Maerin",), ("The Wharf",)))
    monkeypatch.setattr(
        world_populate.settings_store, "resolve_comfy_base_url", lambda *a, **k: "http://comfy"
    )
    monkeypatch.setattr(world_populate.comfyui, "check_connection", lambda base: {"ok": True})
    monkeypatch.setattr(
        world_populate.character_agent,
        "generate_portrait_prompts",
        lambda *a, **k: PortraitPromptResponse(positive="watercolor portrait", negative="blurry"),
    )
    monkeypatch.setattr(
        world_populate.portraits,
        "generate_portrait",
        lambda *a, **k: {"portrait": "/media/portraits/maerin.webp"},
    )
    monkeypatch.setattr(
        world_populate.setting_agent,
        "generate_scene_art_prompts",
        lambda *a, **k: SceneArtPromptResponse(positive="watercolor wharf", negative="people"),
    )
    monkeypatch.setattr(
        world_populate.scene_art,
        "generate_scene_art",
        lambda *a, **k: {"image": "/media/scenes/wharf.webp"},
    )

    frames = _run(db_session, world, with_artwork=True)

    char = crud.list_characters(db_session, world)[0]
    setting = crud.list_settings(db_session, world)[0]
    assert char.portrait == "/media/portraits/maerin.webp"
    assert char.portrait_positive == "watercolor portrait"
    assert setting.image == "/media/scenes/wharf.webp"
    assert setting.scene_art_negative == "people"
    images = {f.stage: f.image for f in frames if isinstance(f, PopulateEntityFrame)}
    assert images == {
        "character": "/media/portraits/maerin.webp",
        "setting": "/media/scenes/wharf.webp",
    }


def test_a_failed_render_keeps_the_entity(db_session, world, monkeypatch):
    _stub_agents(monkeypatch, roster=_roster(("Maerin",), ()))
    monkeypatch.setattr(
        world_populate.settings_store, "resolve_comfy_base_url", lambda *a, **k: "http://comfy"
    )
    monkeypatch.setattr(world_populate.comfyui, "check_connection", lambda base: {"ok": True})
    monkeypatch.setattr(
        world_populate.character_agent,
        "generate_portrait_prompts",
        lambda *a, **k: PortraitPromptResponse(positive="watercolor portrait", negative=""),
    )

    def boom(*_a, **_k):
        raise RuntimeError("ComfyUI timed out")

    monkeypatch.setattr(world_populate.portraits, "generate_portrait", boom)

    frames = _run(db_session, world, with_artwork=True)

    char = crud.list_characters(db_session, world)[0]
    assert char.name == "Maerin Voss" and char.portrait is None
    errors = [f for f in frames if isinstance(f, PopulateErrorFrame)]
    assert len(errors) == 1 and "portrait" in errors[0].message
    assert frames[-1].characters == 1


def test_unknown_storyline_raises_before_any_frame(db_session, monkeypatch):
    _stub_agents(monkeypatch, roster=_roster())

    with pytest.raises(APIError) as exc:
        _run(db_session, "nope")

    assert exc.value.status_code == 404


def test_roster_failure_is_fatal(db_session, world, monkeypatch):
    """No roster means nothing to build — that one propagates."""

    def boom(*_a, **_k):
        raise APIError(400, "bad_request", "Choose a model in Options first.")

    monkeypatch.setattr(world_populate.roster_agent, "propose_roster", boom)

    with pytest.raises(APIError) as exc:
        _run(db_session, world)

    assert exc.value.status_code == 400


# The character build is not just the draft — the retired world build also gave every
# character a voice profile and starting stats, and losing them was the regression.
def test_characters_get_their_voice_and_starting_stats(db_session, world, monkeypatch):
    from app.schemas.stat import StatDefinitionCreate
    from app.services import stats as stat_service

    stat_service.create_stat_definition(
        db_session,
        world,
        StatDefinitionCreate(key="trust", display_name="Trust", min=0, max=10, default=5),
    )
    _stub_agents(
        monkeypatch,
        roster=_roster(("Maerin",), ()),
        voice=lambda *a, **k: VoiceSamplesResponse(
            samples=[VoiceSample(situation="Cornered on the wharf.", sample="Try me.")]
        ),
        stats=lambda *a, **k: StartingStatsResponse(
            proposals=[
                StartingStatProposal(
                    key="trust",
                    display_name="Trust",
                    value=2,
                    min=0,
                    max=10,
                    rationale="Guarded.",
                )
            ]
        ),
    )

    frames = _run(db_session, world)

    char = crud.list_characters(db_session, world)[0]
    assert [s["sample"] for s in char.voice_samples] == ["Try me."]
    assert stat_service.get_character_stats(db_session, char.id) == {"trust": 2}
    assert [f for f in frames if isinstance(f, PopulateErrorFrame)] == []
    # Each sub-step announces itself so the build console can show it happening.
    messages = [f.message for f in frames if isinstance(f, PopulateStatusFrame)]
    assert any("voice" in m for m in messages)
    assert any("starting stats" in m for m in messages)


def test_a_failed_voice_or_stat_proposal_keeps_the_character(db_session, world, monkeypatch):
    def boom(*_a, **_k):
        raise APIError(502, "upstream_error", "The model did not return valid JSON.")

    _stub_agents(monkeypatch, roster=_roster(("Maerin",), ()), voice=boom, stats=boom)

    frames = _run(db_session, world)

    char = crud.list_characters(db_session, world)[0]
    assert char.name == "Maerin Voss" and char.voice_samples == []
    errors = [f.message for f in frames if isinstance(f, PopulateErrorFrame)]
    assert len(errors) == 2
    assert any("voice" in m for m in errors) and any("starting stats" in m for m in errors)
    assert frames[-1].characters == 1


def test_a_world_with_no_stat_schema_proposes_nothing(db_session, world, monkeypatch):
    """No definitions → the proposal is skipped, not failed (and costs no LLM call)."""
    _stub_agents(monkeypatch, roster=_roster(("Maerin",), ()))
    calls: list[int] = []
    monkeypatch.setattr(
        world_populate.character_agent,
        "propose_starting_stats",
        lambda db, sid, **k: calls.append(1)
        or StartingStatsResponse(proposals=[]),
    )

    frames = _run(db_session, world)

    assert len(calls) == 1  # asked once; it returns empty without an LLM call of its own
    assert [f for f in frames if isinstance(f, PopulateErrorFrame)] == []


def test_entity_frames_carry_what_landed(db_session, world, monkeypatch):
    """The console needs the role/type to show what was built without re-fetching."""
    _stub_agents(monkeypatch, roster=_roster(("Maerin",), ("The Wharf",)))

    entities = [f for f in _run(db_session, world) if isinstance(f, PopulateEntityFrame)]

    assert [(e.stage, e.name, e.role) for e in entities] == [
        ("character", "Maerin Voss", "Smuggler"),
        ("setting", "The Salt Wharf", "Social Hub"),
    ]


# Two draft agents can independently invent the same name — a real run produced two
# characters called "Kaelen Thorne". The turn loop resolves speakers BY NAME, so a
# duplicate makes them indistinguishable to the engine.
def test_a_repeated_drafted_name_is_disambiguated(db_session, world, monkeypatch):
    roles = iter(["Silt-Runner", "Chief Inquisitor"])
    _stub_agents(
        monkeypatch,
        roster=_roster(("Kaelen", "Thorne"), ()),
        character=lambda *a, **k: CharacterDraftResponse(
            name="Kaelen Thorne", role=next(roles)
        ),
    )

    _run(db_session, world)

    names = [c.name for c in crud.list_characters(db_session, world)]
    assert names[0] == "Kaelen Thorne"
    assert names[1] != names[0]
    assert len(set(names)) == 2


def test_names_are_unique_against_the_world_that_already_exists(db_session, world, monkeypatch):
    """A run pointed at a non-empty world must not collide with what is already there."""
    from app.schemas.character import CharacterCreate

    crud.create_character(db_session, world, CharacterCreate(name="Maerin Voss"))
    _stub_agents(monkeypatch, roster=_roster(("Maerin",), ()))

    _run(db_session, world)

    names = [c.name for c in crud.list_characters(db_session, world)]
    assert len(names) == 2 and len(set(names)) == 2


def test_settings_are_disambiguated_too(db_session, world, monkeypatch):
    _stub_agents(
        monkeypatch,
        roster=_roster((), ("Wharf", "Docks")),
        setting=lambda *a, **k: _setting_draft("The Salt Wharf"),
    )

    _run(db_session, world)

    names = [s.name for s in crud.list_settings(db_session, world)]
    assert len(names) == 2 and len(set(names)) == 2
