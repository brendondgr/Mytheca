"""Front-matter schema + the indexable lore entry (brief §1).

``Frontmatter`` is the validated metadata header carried by every lore entry —
the single source of truth so malformed metadata fails loudly at ingest, not
silently at query time. ``LoreEntry`` bundles that header with the body text and
the Mytheca scoping fields (storyline + owning entity) the store/indexer need.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field


class EntryType(str, Enum):
    """Semantic kind of a lore entry (brief §1.3). Mytheca entities map onto these:
    storyline→lore, character→character, setting→location, scenario→event, and a
    context document inherits the kind implied by its triage category."""

    character = "character"
    location = "location"
    faction = "faction"
    event = "event"
    item = "item"
    lore = "lore"


class Frontmatter(BaseModel):
    """Structured metadata prepended to a chunk before embedding (brief §1.1).

    ``era`` is relaxed from the brief's fixed vocabulary to ``str | None`` because
    Mytheca has no era axis today — left ``None`` for every current entry.
    """

    id: str
    type: EntryType
    name: str
    aliases: list[str] = Field(default_factory=list)
    faction: str | None = None
    location: str | None = None
    era: str | None = None
    status: str | None = None
    tags: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    summary: str = ""


@dataclass(frozen=True)
class LoreEntry:
    """An indexable unit: validated front matter + body + Mytheca scoping.

    ``entity_type`` is the Mytheca source kind (``storyline`` | ``character`` |
    ``setting`` | ``scenario`` | ``context_document``) and ``entity_id`` its row
    id; together they namespace the stable Qdrant point id and let deletes target
    exactly the points an entity owns. ``storyline_id`` is the retrieval scope —
    every search filters on it so a world only sees its own corpus.
    """

    fm: Frontmatter
    body: str
    storyline_id: str | None
    entity_type: str
    entity_id: str
    include_rag: bool = True
    related: list[str] = field(default_factory=list)
