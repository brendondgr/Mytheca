"""How an image-prompt agent turns a requested style id into a style to write for.

One line, but it belongs in one place: ``None`` must mean *the operator's stored default*
(Options → Image generation), not *the catalog default*. Getting that wrong is invisible —
the prompts still come back, just written for the wrong look — so the four agents share
this rather than each calling ``art_styles.get`` and quietly skipping the stored setting.

The render services resolve the same thing through ``settings_store.resolve_art_style``,
which additionally answers the LoRA question; agents only need the style itself.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.content.art_styles import ArtStyle
from app.services import settings_store


def resolve_style(db: Session, style_id: str | None) -> ArtStyle:
    """The requested style, else the stored global default. Unknown ids fall back."""
    return settings_store.resolve_art_style(db, style_id).style
