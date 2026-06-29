"""Prefix-fusion serializer (brief §2).

Turns front matter + body into the single strings we embed. The dense channel
gets a compact metadata header + summary + body ("prefix-fusion": the metadata is
*embedded*, not merely filtered); the BM25 channel gets the raw vocabulary —
name, aliases, tags, and the filter fields — so exact terms players type still
hit. Deterministic and side-effect free.
"""

from __future__ import annotations

from app.rag.schema import Frontmatter
from app.rag.tokens import fit_to_budget


def build_header(fm: Frontmatter) -> str:
    """Compact metadata header (~10% of chunk length; brief keeps it small)."""
    parts = [f"{fm.type.value}: {fm.name}"]
    if fm.aliases:
        parts.append("also known as " + ", ".join(fm.aliases))
    if fm.faction:
        parts.append(f"faction {fm.faction}")
    if fm.location:
        parts.append(f"location {fm.location}")
    if fm.tags:
        parts.append("tags " + ", ".join(fm.tags))
    return ". ".join(parts)


def build_embed_text(fm: Frontmatter, body: str) -> str:
    """Dense-channel text: header + summary anchor retrieval; body adds detail.

    The body is trimmed to the 512-token budget (header + summary always survive)
    so a long entry never silently loses its metadata anchor.
    """
    header = build_header(fm)
    head = f"{header}.\n\n{fm.summary}".strip() if fm.summary else f"{header}."
    return fit_to_budget(head, body or "")


def build_bm25_text(fm: Frontmatter, body: str) -> str:
    """Sparse-channel text: the raw vocabulary (all aliases + filter fields) + body."""
    tokens: list[str] = [fm.name, *fm.aliases, *(fm.tags or [])]
    for f in (fm.faction, fm.location, fm.era, fm.status):
        if f:
            tokens.append(f)
    head = " ".join(t for t in tokens if t)
    return f"{head}\n{body}".strip()
