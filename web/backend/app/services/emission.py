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


# ---- Incremental parsing ---------------------------------------------------
# :func:`parse_emission` runs over a finished string, so nothing can be shown until the
# whole beat exists. The accumulator below makes the same decisions on a growing prefix,
# which is what lets a character's private thought reach the player while their spoken
# line is still being written.

#: Every emission tag, in one pattern, so the scanner can find the next one of any kind.
#: The optional leading slash and optional ``:value`` mirror the tolerances above.
_ANY_TAG_RE = re.compile(
    r"</?(?:speaker(?::\s*\d+)?|type(?::\s*[a-z_]+)?|thinking)\s*>", re.IGNORECASE
)


@dataclass
class SegmentDelta:
    """One increment of a segment being parsed out of a streaming emission.

    ``index`` orders segments within the emission; a consumer keyed on it can open an
    event on the first delta and close it when ``done`` arrives. ``text`` is the
    increment, never the accumulation — joining every delta for one index reproduces the
    corresponding :class:`Segment` body exactly.
    """

    index: int
    type: str
    text: str
    character_id: str
    done: bool = False


class EmissionAccumulator:
    """Parse a thin-tag emission as it arrives, yielding :class:`SegmentDelta`s.

    Fed the same text as :func:`parse_emission` — in any chunking — it produces the same
    ordered segments with the same bodies. Three behaviours are worth knowing:

    * **Prose and thinking stream; JSON does not.** ``character_dialogue``,
      ``character_action`` and ``internal_thought`` emit deltas as they grow.
      ``state_update`` / ``relationship_update`` / ``presence_change`` carry a JSON body
      that is meaningless in fragments, so they are held and emitted whole on close.
    * **Text before the first ``<type:>`` mark is held.** The batch parser discards it
      when marks exist, and treats it as one spoken line when none do — which cannot be
      known until the stream ends. Holding it preserves both outcomes.
    * **Order is arrival order.** The batch parser lifts ``internal_thought`` to the
      front of the list wherever it appeared; a stream cannot reorder what it has already
      sent. For the documented think→speak format the two agree, because the thought
      genuinely comes first. Likewise a ``<speaker:N>`` tag arriving *after* a segment has
      opened cannot retroactively re-attribute it, so that segment keeps the engine's
      intended speaker.
    """

    def __init__(self, *, roster: dict[int, str], fallback_speaker_id: str) -> None:
        self._roster = roster
        self._speaker_id = fallback_speaker_id
        self._buf = ""
        self._index = -1
        self._open_type: str | None = None
        self._open_text = ""
        self._pending_ws = ""
        self._held = ""  # preamble: prose seen before any <type:> mark
        self._saw_type_mark = False
        self._segments: list[Segment] = []

    @property
    def segments(self) -> list[Segment]:
        """Every segment closed so far."""
        return list(self._segments)

    def push(self, chunk: str) -> list[SegmentDelta]:
        """Consume a chunk of the emission; return the deltas it produced."""
        if not chunk:
            return []
        self._buf += chunk
        out: list[SegmentDelta] = []
        while True:
            match = _ANY_TAG_RE.search(self._buf)
            if match is None:
                # No complete tag. Emit everything that cannot still become one.
                safe = self._safe_prefix(self._buf)
                if safe:
                    out.extend(self._consume_text(self._buf[:safe]))
                    self._buf = self._buf[safe:]
                break
            out.extend(self._consume_text(self._buf[: match.start()]))
            self._buf = self._buf[match.end() :]
            out.extend(self._handle_tag(match.group(0)))
        return out

    def finish(self) -> list[SegmentDelta]:
        """Close the emission; return the final deltas."""
        out: list[SegmentDelta] = []
        if self._buf:
            out.extend(self._consume_text(self._buf))
            self._buf = ""
        out.extend(self._close_open())
        if not self._saw_type_mark:
            # The model ignored the tag format — the held prose is one spoken line.
            body = _clean(self._held)
            if body:
                out.extend(self._open(_DIALOGUE))
                out.extend(self._grow(body))
                out.extend(self._close_open())
        self._held = ""
        return out

    # -- internals -----------------------------------------------------------

    def _safe_prefix(self, text: str) -> int:
        """How much of ``text`` cannot still turn out to be part of a tag."""
        start = text.rfind("<")
        return len(text) if start == -1 or ">" in text[start:] else start

    def _handle_tag(self, tag: str) -> list[SegmentDelta]:
        speaker = _SPEAKER_RE.fullmatch(tag)
        if speaker:
            self._speaker_id = self._roster.get(int(speaker.group(1)), self._speaker_id)
            return []
        lowered = tag.lower()
        if "thinking" in lowered:
            if lowered.startswith("</"):
                return self._close_open()
            out = self._close_open()
            out.extend(self._open("internal_thought"))
            return out
        type_match = _TYPE_RE.fullmatch(tag)
        if type_match:
            self._saw_type_mark = True
            self._held = ""  # preamble before the first mark is discarded, as in batch
            kind = type_match.group(1).lower()
            out = self._close_open()
            if kind in _PROSE_TYPES or kind in _JSON_TYPES:
                out.extend(self._open(kind))
            return out
        # A bare </type> / </speaker> closes nothing and is simply scrubbed.
        return []

    def _consume_text(self, text: str) -> list[SegmentDelta]:
        if not text:
            return []
        if self._open_type is None:
            self._held += text
            return []
        return self._grow(text)

    def _open(self, kind: str) -> list[SegmentDelta]:
        self._index += 1
        self._open_type = kind
        self._open_text = ""
        self._pending_ws = ""
        return []

    def _grow(self, text: str) -> list[SegmentDelta]:
        """Add text to the open segment, emitting a delta unless it must be held.

        Leading and trailing whitespace are withheld so the accumulated body matches the
        batch parser's ``.strip()``; held whitespace is released as soon as more prose
        follows it. A JSON body is withheld entirely — half a JSON object is not usable.
        """
        assert self._open_type is not None
        if not self._open_text:
            text = text.lstrip()
            if not text:
                return []
        text = self._pending_ws + text
        stripped = text.rstrip()
        self._pending_ws = text[len(stripped) :]
        if not stripped:
            return []
        self._open_text += stripped
        if self._open_type in _JSON_TYPES:
            return []
        return [
            SegmentDelta(
                index=self._index,
                type=self._open_type,
                text=stripped,
                character_id=self._speaker_id,
            )
        ]

    def _close_open(self) -> list[SegmentDelta]:
        if self._open_type is None:
            return []
        kind, body = self._open_type, self._open_text
        self._open_type = None
        self._open_text = ""
        self._pending_ws = ""
        if kind not in _JSON_TYPES:
            body = _clean(body)
        if not body:
            self._index -= 1  # an empty segment was never really a segment
            return []
        self._segments.append(Segment(kind, body, self._speaker_id))
        return [
            SegmentDelta(
                index=self._index,
                type=kind,
                # A JSON body is delivered here, in one piece, having been withheld.
                text=body if kind in _JSON_TYPES else "",
                character_id=self._speaker_id,
                done=True,
            )
        ]


#: The type a tag-free emission collapses to (see :class:`EmissionAccumulator.finish`).
_DIALOGUE = "character_dialogue"
