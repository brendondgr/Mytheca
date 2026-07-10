"""Entity-extraction agent — split one document into its distinct subjects.

No real network: ``app.services.llm.get_http_client`` is patched to an
``httpx.MockTransport``. The LLM is configured through the Options API on the same
in-memory engine the ``db_session`` fixture binds to, so ``extract_entities`` can be
called directly with that session.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agents import extract_agent
from app.core.errors import APIError
from app.services import llm


def _patch_upstream(monkeypatch, handler):
    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(llm, "get_http_client", factory)


def _configure_llm(client):
    client.patch(
        "/api/options/llm",
        json={"baseUrl": "http://localhost:7070/v1", "model": "test-model", "apiKey": "sk-test"},
    )


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


_ROSTER = json.dumps(
    {
        "characters": [
            {"name": "Maerin Voss", "source": "A wary harbor smuggler with sharp eyes."},
            {"name": "Inquisitor Kestrel", "source": "A cold heretic-hunter of the port."},
            {"name": "Maerin Voss", "source": "duplicate that should be dropped"},
        ],
        "settings": [
            {"name": "The Drowned Chapel", "source": "A sunken shrine beneath the tide."},
        ],
    }
)


def test_extract_entities_splits_a_multi_subject_doc(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion(_ROSTER))
    result = extract_agent.extract_entities(
        db_session,
        "Two smugglers and a cold inquisitor circle a drowned chapel...",
        doc_name="cast.md",
    )
    # Two distinct characters (the duplicate name is de-duped) + one setting.
    assert [c.name for c in result.characters] == ["Maerin Voss", "Inquisitor Kestrel"]
    assert result.characters[0].source.startswith("A wary harbor smuggler")
    assert [s.name for s in result.settings] == ["The Drowned Chapel"]


def test_extract_entities_stamps_source_doc_name(client, db_session, monkeypatch):
    """Every extracted subject records the document it was mined from (build lineage)."""
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion(_ROSTER))
    result = extract_agent.extract_entities(
        db_session,
        "Two smugglers and a cold inquisitor circle a drowned chapel...",
        doc_name="cast.md",
    )
    assert all(c.source_doc_names == ["cast.md"] for c in result.characters)
    assert all(s.source_doc_names == ["cast.md"] for s in result.settings)


def test_extract_entities_no_doc_name_leaves_lineage_empty(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion(_ROSTER))
    result = extract_agent.extract_entities(db_session, "A crew and a chapel.")
    assert all(c.source_doc_names == [] for c in result.characters)


def test_extract_entities_blank_doc_short_circuits(client, db_session, monkeypatch):
    _configure_llm(client)

    def _boom(req):  # must never be called for blank input
        raise AssertionError("LLM should not be hit for blank input")

    _patch_upstream(monkeypatch, _boom)
    result = extract_agent.extract_entities(db_session, "   ")
    assert result.characters == []
    assert result.settings == []


def test_extract_entities_lore_doc_returns_empty(client, db_session, monkeypatch):
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion(json.dumps({})))
    result = extract_agent.extract_entities(db_session, "A timeline of the founding wars.")
    assert result.characters == []
    assert result.settings == []


def test_extract_entities_drops_nameless_rows(client, db_session, monkeypatch):
    _configure_llm(client)
    payload = json.dumps(
        {"characters": [{"source": "no name here"}, {"name": "Vell", "source": ""}]}
    )
    _patch_upstream(monkeypatch, lambda req: _completion(payload))
    result = extract_agent.extract_entities(db_session, "Some people.")
    # Nameless row dropped; the named row keeps its name as a fallback source.
    assert [c.name for c in result.characters] == ["Vell"]
    assert result.characters[0].source == "Vell"


def test_extract_entities_sends_extraction_marker_and_grounding(client, db_session, monkeypatch):
    _configure_llm(client)
    seen: dict = {}

    def handler(req):
        body = json.loads(req.content.decode())
        seen["system"] = body["messages"][0]["content"]
        seen["user"] = body["messages"][1]["content"]
        return _completion(_ROSTER)

    _patch_upstream(monkeypatch, handler)
    extract_agent.extract_entities(
        db_session, "Doc body text.", "World: Embergate (Maritime).", doc_name="cast.md"
    )
    assert "entity-extraction assistant" in seen["system"]
    assert "Doc body text." in seen["user"]
    assert "Embergate" in seen["user"]
    assert "cast.md" in seen["user"]


def test_extract_entities_requires_configured_llm(db_session, monkeypatch):
    # No _configure_llm → resolve_llm raises a 400 before any network call.
    with pytest.raises(APIError) as exc:
        extract_agent.extract_entities(db_session, "Some characters.")
    assert exc.value.status_code == 400


def test_extract_kind_character_drops_any_settings(client, db_session, monkeypatch):
    """A character-bucket doc yields only characters — a phantom setting is cleared."""
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion(_ROSTER))  # _ROSTER has a setting
    result = extract_agent.extract_entities(db_session, "Cast notes.", kind="character")
    assert [c.name for c in result.characters] == ["Maerin Voss", "Inquisitor Kestrel"]
    assert result.settings == []  # the model's setting is scoped out


def test_extract_kind_setting_drops_any_characters(client, db_session, monkeypatch):
    """A setting-bucket doc yields only settings — phantom characters are cleared."""
    _configure_llm(client)
    _patch_upstream(monkeypatch, lambda req: _completion(_ROSTER))
    result = extract_agent.extract_entities(db_session, "Place notes.", kind="setting")
    assert result.characters == []
    assert [s.name for s in result.settings] == ["The Drowned Chapel"]


def test_extract_kind_injects_the_bucket_instruction(client, db_session, monkeypatch):
    """Each bucket's instruction reaches the prompt so extraction is scoped + strict."""
    _configure_llm(client)
    seen: dict = {}

    def handler(req):
        seen["user"] = json.loads(req.content.decode())["messages"][1]["content"]
        seen["system"] = json.loads(req.content.decode())["messages"][0]["content"]
        return _completion(_ROSTER)

    _patch_upstream(monkeypatch, handler)
    extract_agent.extract_entities(db_session, "A doc.", kind="character")
    assert "classified as a CHARACTER" in seen["user"]
    # The system prompt forbids inventing subjects out of lore.
    assert "Do NOT invent" in seen["system"]
    assert "explicitly NAMED" in seen["system"]
