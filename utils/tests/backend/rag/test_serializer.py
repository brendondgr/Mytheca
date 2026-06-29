"""Prefix-fusion serializer + token guard (brief §2)."""

from __future__ import annotations

from app.rag.const import EMBED_MAX_TOK, QUERY_PREFIX
from app.rag.schema import EntryType, Frontmatter
from app.rag.serializer import build_bm25_text, build_embed_text, build_header
from app.rag.tokens import CHARS_PER_TOKEN, approx_tokens, fit_to_budget


def _fm(**over) -> Frontmatter:
    base = dict(
        id="char-maerin",
        type=EntryType.character,
        name="Maerin",
        aliases=["The Warden"],
        faction="Tidewatch",
        location="The Wharf",
        tags=["ranger", "stoic"],
        summary="An elven warden of the harbor.",
    )
    base.update(over)
    return Frontmatter(**base)


def test_query_prefix_is_the_bge_instruction():
    assert QUERY_PREFIX == "Represent this sentence for searching relevant passages: "


def test_header_is_compact_and_metadata_rich():
    header = build_header(_fm())
    assert header.startswith("character: Maerin")
    assert "also known as The Warden" in header
    assert "faction Tidewatch" in header
    assert "location The Wharf" in header
    assert "tags ranger, stoic" in header


def test_embed_text_fuses_header_summary_body_and_is_deterministic():
    fm = _fm()
    body = "Maerin patrols the fracture zones and leads scouting missions."
    a = build_embed_text(fm, body)
    b = build_embed_text(fm, body)
    assert a == b  # deterministic
    assert a.startswith("character: Maerin")
    assert "An elven warden of the harbor." in a  # summary anchors dense retrieval
    assert "fracture zones" in a  # body detail present when it fits


def test_embed_text_drops_body_tail_over_budget_but_keeps_header_and_summary():
    fm = _fm()
    long_body = "word " * (EMBED_MAX_TOK * CHARS_PER_TOKEN)  # far over budget
    text = build_embed_text(fm, long_body)
    assert text.startswith("character: Maerin")
    assert "An elven warden of the harbor." in text
    assert approx_tokens(text) <= EMBED_MAX_TOK + 2


def test_bm25_text_carries_raw_vocabulary_and_body():
    fm = _fm()
    text = build_bm25_text(fm, "patrols the fracture zones")
    for token in ("Maerin", "The Warden", "ranger", "stoic", "Tidewatch", "The Wharf"):
        assert token in text
    assert "patrols the fracture zones" in text


def test_fit_to_budget_never_drops_the_head():
    head = "header and summary"
    fitted = fit_to_budget(head, "x " * 100000, max_tokens=8)
    assert fitted.startswith(head)
    assert approx_tokens(fitted) <= 8 + 2
