"""``POST /storylines/{id}/populate/stream`` — the create-time world-population API.

**This is the regression guard for "the new world comes up empty".** The assertions
deliberately go the long way round: run the endpoint, then read the cast and places
back through `GET /storylines/{id}/characters`, `…/settings`, and the storyline's own
`characterCount` / `settingCount` — the exact endpoints the Library loads on redirect.
Asserting only on the stream frames would pass even if nothing were persisted.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import roster_agent
from app.schemas.character import CharacterDraftResponse
from app.schemas.setting import SettingDraftResponse
from app.schemas.world_populate import RosterEntry, RosterProposal
from app.services import llm, llm_backend, world_populate


@pytest.fixture(autouse=True)
def _clear_detection_cache():
    llm_backend.clear_cache()
    yield
    llm_backend.clear_cache()


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _patch_upstream(monkeypatch, handler):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _stub_drafts(monkeypatch, characters: list[str], settings: list[str]):
    """Stub the roster + the two drafting agents; persistence stays real."""
    monkeypatch.setattr(
        world_populate.roster_agent,
        "propose_roster",
        lambda *a, **k: RosterProposal(
            characters=[RosterEntry(name=n, seed=f"{n} seed") for n in characters],
            settings=[RosterEntry(name=n, seed=f"{n} seed") for n in settings],
        ),
    )
    monkeypatch.setattr(
        world_populate.character_agent,
        "draft_character",
        lambda db, seed, *a, **k: CharacterDraftResponse(
            name=seed.split(" — ")[0],
            role="Smuggler",
            traits="wry · watchful",
            speech="Clipped.",
            goal="Clear the debt.",
            secret="Sold the charts.",
            appearance="Salt-bleached coat.",
            background="Raised on the wharf.",
            personality="Guarded.",
            color="#3A5A78",
        ),
    )
    monkeypatch.setattr(
        world_populate.setting_agent,
        "draft_setting",
        lambda db, seed, *a, **k: SettingDraftResponse(
            name=seed.split(" — ")[0],
            type="Social Hub",
            desc="Where cargo changes hands.",
            atmosphere="Tar and cold rope.",
            features="Crane, ledger house.",
            current_state="Dawn, low tide.",
        ),
    )


def _frames(response) -> list[dict]:
    return [json.loads(line) for line in response.text.strip().splitlines() if line.strip()]


def test_populated_world_is_readable_through_the_library_endpoints(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _stub_drafts(monkeypatch, ["Maerin Voss", "Harbormaster Cael"], ["The Salt Wharf"])

    res = client.post(f"/api/storylines/{storyline_id}/populate/stream", json={})
    assert res.status_code == 200

    frames = _frames(res)
    assert frames[-1] == {"type": "done", "characters": 2, "settings": 1}
    entities = [f for f in frames if f["type"] == "entity"]
    assert [f["name"] for f in entities] == [
        "Maerin Voss",
        "Harbormaster Cael",
        "The Salt Wharf",
    ]

    # The world the author is redirected into: the cast and places must be there.
    characters = client.get(f"/api/storylines/{storyline_id}/characters").json()
    settings = client.get(f"/api/storylines/{storyline_id}/settings").json()
    assert [c["name"] for c in characters] == ["Maerin Voss", "Harbormaster Cael"]
    assert [s["name"] for s in settings] == ["The Salt Wharf"]
    assert characters[0]["appearance"] and characters[0]["background"]
    assert settings[0]["atmosphere"] and settings[0]["currentState"]
    assert {e["id"] for e in entities} == {c["id"] for c in characters} | {
        s["id"] for s in settings
    }

    storyline = client.get(f"/api/storylines/{storyline_id}").json()
    assert storyline["characterCount"] == 2
    assert storyline["settingCount"] == 1


def test_bounds_are_honoured_and_clamped(client, storyline_id, monkeypatch):
    """The request's caps reach the roster agent (and the schema rejects absurd ones)."""
    _configure_llm(client)
    seen: dict[str, int] = {}

    def capture(db, *, storyline_id, docs_overview, max_characters, max_settings, **_k):
        seen.update(characters=max_characters, settings=max_settings)
        return RosterProposal()

    monkeypatch.setattr(world_populate.roster_agent, "propose_roster", capture)

    res = client.post(
        f"/api/storylines/{storyline_id}/populate/stream",
        json={"maxCharacters": 2, "maxSettings": 1},
    )

    assert res.status_code == 200
    assert seen == {"characters": 2, "settings": 1}
    assert _frames(res)[-1] == {"type": "done", "characters": 0, "settings": 0}

    over = client.post(
        f"/api/storylines/{storyline_id}/populate/stream", json={"maxCharacters": 99}
    )
    assert over.status_code == 422


def test_draft_grounding_reaches_the_agents(client, storyline_id, monkeypatch):
    """The author's Draft-selected file text grounds the roster and every draft."""
    _configure_llm(client)
    grounding: list[str | None] = []

    monkeypatch.setattr(
        world_populate.roster_agent,
        "propose_roster",
        lambda db, *, docs_overview, **k: grounding.append(docs_overview)
        or RosterProposal(characters=[RosterEntry(name="Maerin", seed="a smuggler")]),
    )
    monkeypatch.setattr(
        world_populate.character_agent,
        "draft_character",
        lambda db, seed, docs_overview=None, *a, **k: grounding.append(docs_overview)
        or CharacterDraftResponse(name="Maerin", role="Smuggler"),
    )

    client.post(
        f"/api/storylines/{storyline_id}/populate/stream",
        json={"docsOverview": "The tide charts are kept in the ledger house."},
    )

    assert grounding == ["The tide charts are kept in the ledger house."] * 2


def test_a_failed_entity_is_reported_without_losing_the_others(
    client, storyline_id, monkeypatch
):
    _configure_llm(client)
    _stub_drafts(monkeypatch, ["Maerin", "Cael"], [])
    good = world_populate.character_agent.draft_character
    calls = {"n": 0}

    def flaky(db, seed, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("upstream exploded")
        return good(db, seed, *a, **k)

    monkeypatch.setattr(world_populate.character_agent, "draft_character", flaky)

    res = client.post(f"/api/storylines/{storyline_id}/populate/stream", json={})
    frames = _frames(res)

    errors = [f for f in frames if f["type"] == "error"]
    assert len(errors) == 1 and errors[0]["fatal"] is False
    assert frames[-1] == {"type": "done", "characters": 1, "settings": 0}
    assert [c["name"] for c in client.get(
        f"/api/storylines/{storyline_id}/characters"
    ).json()] == ["Cael"]


def test_unknown_storyline_is_404_before_the_stream_opens(client, monkeypatch):
    _configure_llm(client)
    res = client.post("/api/storylines/nope/populate/stream", json={})
    assert res.status_code == 404


def test_unconfigured_llm_is_400_before_the_stream_opens(client, storyline_id):
    res = client.post(f"/api/storylines/{storyline_id}/populate/stream", json={})
    assert res.status_code == 400
    assert "Options" in res.json()["error"]["message"]


def test_mid_stream_failure_is_a_terminal_fatal_error_frame(client, storyline_id, monkeypatch):
    """A failure after the 200 cannot change the status — it must be an in-band frame."""
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion("not json at all"))
    monkeypatch.setattr(world_populate, "roster_agent", roster_agent)

    res = client.post(f"/api/storylines/{storyline_id}/populate/stream", json={})

    assert res.status_code == 200
    last = _frames(res)[-1]
    assert last["type"] == "error" and last["fatal"] is True
