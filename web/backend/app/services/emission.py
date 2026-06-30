"""Parse a character agent's thin-tag emission into typed event segments.

The model emits a thin header + free prose (the emission format is intentionally
decoupled from the wire envelope — small models are far more reliable producing
``<speaker:N>`` / ``<type:...>`` tags than hand-writing JSON). The backend owns the
envelope: this resolves the roster number → character id and splits the body into
ordered :class:`Segment`s the turn engine turns into events.

A ``<thinking>…</thinking>`` block (added in the think→speak phase) becomes a hidden
``internal_thought`` segment. If the model ignores the tag format entirely, the whole
reply is treated as one spoken line (resilience), and an out-of-roster speaker number
falls back to the engine's intended speaker (it already knows who is up).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SPEAKER_RE = re.compile(r"<speaker:\s*(\d+)\s*>", re.IGNORECASE)
_TYPE_RE = re.compile(r"<type:\s*([a-z_]+)\s*>", re.IGNORECASE)
_THINKING_RE = re.compile(r"<thinking>(.*?)</thinking>", re.IGNORECASE | re.DOTALL)

# Prose types a character may emit (internal_thought is hidden conditioning).
_PROSE_TYPES = {"character_action", "character_dialogue"}


@dataclass
class Segment:
    """One parsed unit of a character's emission → one story event."""

    type: str
    text: str
    character_id: str


def parse_emission(
    raw: str,
    *,
    roster: dict[int, str],
    fallback_speaker_id: str,
) -> list[Segment]:
    """Parse a thin-tag emission into ordered segments for the resolved speaker."""
    text = raw or ""

    match = _SPEAKER_RE.search(text)
    speaker_id = fallback_speaker_id
    if match:
        speaker_id = roster.get(int(match.group(1)), fallback_speaker_id)

    segments: list[Segment] = []

    thinking = _THINKING_RE.search(text)
    if thinking:
        body = thinking.group(1).strip()
        if body:
            segments.append(Segment("internal_thought", body, speaker_id))
        text = text[: thinking.start()] + text[thinking.end() :]

    type_marks = list(_TYPE_RE.finditer(text))
    if not type_marks:
        # Model ignored the tag format — treat the remaining prose as one spoken line.
        body = _SPEAKER_RE.sub("", text).strip()
        if body:
            segments.append(Segment("character_dialogue", body, speaker_id))
        return segments

    for i, mark in enumerate(type_marks):
        kind = mark.group(1).lower()
        body_end = type_marks[i + 1].start() if i + 1 < len(type_marks) else len(text)
        body = text[mark.end() : body_end].strip()
        if kind in _PROSE_TYPES and body:
            segments.append(Segment(kind, body, speaker_id))
    return segments
