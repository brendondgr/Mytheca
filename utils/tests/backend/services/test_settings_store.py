"""Settings-store round-trip tests for the LLM namespace.

Covers the max_context_tokens field added in Phase 1 of chat-ux-additions,
plus the default-value guarantee so a fresh install reads 16 384.
"""

from __future__ import annotations

import pytest

from app.schemas.settings import LlmConfigUpdate
from app.services import settings_store


def test_default_max_context_tokens(db_session):
    llm = settings_store.get_llm(db_session)
    assert llm.max_context_tokens == 16384


def test_update_max_context_tokens(db_session):
    updated = settings_store.update_llm(
        db_session, LlmConfigUpdate(max_context_tokens=32768)
    )
    assert updated.max_context_tokens == 32768
    # Persists across a fresh read.
    assert settings_store.get_llm(db_session).max_context_tokens == 32768


def test_max_context_tokens_clamped_to_floor(db_session):
    """Values below 1024 are silently raised to the floor."""
    updated = settings_store.update_llm(
        db_session, LlmConfigUpdate(max_context_tokens=512)
    )
    assert updated.max_context_tokens == 1024


def test_omitting_max_context_tokens_keeps_stored_value(db_session):
    settings_store.update_llm(db_session, LlmConfigUpdate(max_context_tokens=8192))
    # An unrelated patch must not reset the value.
    settings_store.update_llm(db_session, LlmConfigUpdate(model="llama-3"))
    assert settings_store.get_llm(db_session).max_context_tokens == 8192
