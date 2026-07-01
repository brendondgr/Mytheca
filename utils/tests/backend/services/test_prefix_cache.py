"""Prefix-cache observability id: stable, prefix-sensitive, short (§P11)."""

from __future__ import annotations

from app.services import llm


def test_prefix_cache_key_is_stable_for_the_same_prefix():
    prefix = "WORLD: Embergate.\n\nWORLD PRIMER\nA rain-soaked harbor city."
    assert llm.prefix_cache_key(prefix) == llm.prefix_cache_key(prefix)


def test_prefix_cache_key_differs_for_different_prefixes():
    assert llm.prefix_cache_key("world A") != llm.prefix_cache_key("world B")


def test_prefix_cache_key_is_short_and_stable_shape():
    key = llm.prefix_cache_key("anything")
    assert len(key) == 12 and key.isalnum()


def test_empty_prefix_has_a_stable_sentinel():
    assert llm.prefix_cache_key("") == llm.prefix_cache_key("")
    assert len(llm.prefix_cache_key("")) == 12
