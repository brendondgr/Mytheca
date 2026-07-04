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

# Tags are matched with an OPTIONAL leading slash: some models emit XML-style
# closing tags (``</type:character_dialogue>``) or even use ``</type:next>`` as the
# delimiter between blocks. Treating ``<type:X>`` and ``</type:X>`` identically (both
# as "a block of type X starts here") makes every style parse cleanly instead of
# leaking raw tags into the rendered prose.
_SPEAKER_RE = re.compile(r"</?speaker:\s*(\d+)\s*>", re.IGNORECASE)
_TYPE_RE = re.compile(r"</?type:\s*([a-z_]+)\s*>", re.IGNORECASE)
_THINKING_RE = re.compile(r"<thinking>(.*?)</thinking>", re.IGNORECASE | re.DOTALL)
# Belt-and-suspenders scrub for any residual emission tag left inside a body. The type/
# speaker name is OPTIONAL so a **bare** closing tag the model sometimes appends
# (``</type>``, ``</speaker>``) is scrubbed too, not just the named form (``</type:…>``).
_TAG_CLEAN = re.compile(
    r"</?(?:type(?::\s*[a-z_]+)?|thinking|speaker(?::\s*\d+)?)\s*>", re.IGNORECASE
)

# Prose types a character may emit (internal_thought is hidden conditioning).
_PROSE_TYPES = {"character_action", "character_dialogue"}
# A character may also propose a stat change, a relationship change, or a presence change
# (leaving/collapsing) as a JSON body (validated downstream); their ``text`` is the raw
# JSON block, kept verbatim.
_STAT_TYPE = "state_update"
_REL_TYPE = "relationship_update"
_PRESENCE_TYPE = "presence_change"
_JSON_TYPES = {_STAT_TYPE, _REL_TYPE, _PRESENCE_TYPE}


def _clean(body: str) -> str:
    """Strip any residual emission tags from a body and trim."""
    return _TAG_CLEAN.sub("", body).strip()


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
        body = _clean(thinking.group(1))
        if body:
            segments.append(Segment("internal_thought", body, speaker_id))
        text = text[: thinking.start()] + text[thinking.end() :]

    type_marks = list(_TYPE_RE.finditer(text))
    if not type_marks:
        # Model ignored the tag format — treat the remaining prose as one spoken line.
        body = _clean(text)
        if body:
            segments.append(Segment("character_dialogue", body, speaker_id))
        return segments

    for i, mark in enumerate(type_marks):
        kind = mark.group(1).lower()
        body_end = type_marks[i + 1].start() if i + 1 < len(type_marks) else len(text)
        # state_update / relationship_update carry a JSON body; prose is scrubbed.
        raw_body = text[mark.end() : body_end].strip()
        body = raw_body if kind in _JSON_TYPES else _clean(raw_body)
        if not body:
            continue
        if kind in _PROSE_TYPES or kind in _JSON_TYPES:
            segments.append(Segment(kind, body, speaker_id))
    return segments
