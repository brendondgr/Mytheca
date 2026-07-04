"""Render a character's live stats into prompt text.

At play time the character turn agent no longer shows a bare ``stamina=45`` — it
resolves the **current band** for each stat value and substitutes the
``{Character}`` placeholder in the stat/band descriptions with the acting
character's name, so the model reads, in words, what a value *means* for this
character right now (e.g. "Stamina 45/100 (Capable) — {name} still has the fight
to continue forward.").

Kept as a standalone helper so the agent stays lean and the band-resolution +
templating logic has one tested implementation.
"""

from __future__ import annotations

import re
from typing import Any

# Matches the authoring placeholder in both the documented ``{Character}`` form
# and a defensive lowercase ``{character}``.
_TOKEN = re.compile(r"\{[Cc]haracter\}")


def substitute_character(text: str | None, name: str) -> str:
    """Replace ``{Character}`` / ``{character}`` in ``text`` with ``name``.

    Returns "" for falsy text; leaves text without the token unchanged.
    """
    if not text:
        return ""
    return _TOKEN.sub(name, text)


def current_band(bands: list[dict] | None, value: int) -> dict | None:
    """The first band whose ``[min, max]`` contains ``value`` (or None).

    Mirrors the frontend ``bandLabelFor`` — bands need not tile or be contiguous;
    the first match wins. Malformed rows (non-int bounds) are skipped.
    """
    for b in bands or []:
        try:
            lo = int(b.get("min"))
            hi = int(b.get("max"))
        except (TypeError, ValueError):
            continue
        if lo <= value <= hi:
            return b
    return None


def render_character_stats(
    stat_defs: list[Any],
    values: dict[str, int],
    character_name: str,
) -> str:
    """A compact block naming each of the character's stats + current-band meaning.

    One line per stat present in ``values``: ``- Display value/max (BandLabel) —
    <stat description> <current band description>``, both descriptions
    name-substituted. Bands/descriptions are optional — a stat with none renders
    just ``- Display value/max``. Returns "" when nothing renders.
    """
    lines: list[str] = []
    for sd in stat_defs:
        key = getattr(sd, "key", None)
        if key is None or key not in values:
            continue
        value = int(values[key])
        name = getattr(sd, "display_name", None) or key
        headline = f"{name} {value}/{getattr(sd, 'max', value)}"

        band = current_band(getattr(sd, "bands", None), value)
        band_desc = ""
        if band:
            label = str(band.get("label") or "").strip()
            if label:
                headline += f" ({label})"
            band_desc = substitute_character(band.get("description"), character_name)

        stat_desc = substitute_character(getattr(sd, "description", ""), character_name)
        tail = " ".join(part for part in (stat_desc, band_desc) if part)
        lines.append(f"- {headline} — {tail}" if tail else f"- {headline}")

    if not lines:
        return ""
    return "Your current condition (what your stats mean right now):\n" + "\n".join(lines)
