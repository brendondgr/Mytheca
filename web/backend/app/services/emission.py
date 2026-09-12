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

import json
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
#: Wrapper tags the contract never asks for and models invent anyway — a whole passage
#: delivered inside ``<response>…</response>`` or opening on a bare ``<passage>``. Both were
#: observed live and both were persisted verbatim into the rendered prose, because nothing
#: recognised them. As a complete tag these four words are never prose, so they are scrubbed
#: like any other emission tag rather than shown.
_WRAPPERS = "response|passage|answer|output|prose"
_TAG_CLEAN = re.compile(
    rf"</?(?:type(?::\s*[a-z_]+)?|thinking|speaker(?::\s*\d+)?|{_WRAPPERS})\s*>",
    re.IGNORECASE,
)

# A character beat is ONE untagged first-person passage. There are no prose tags any more,
# and a ``<type:...>`` naming a prose kind is therefore **ignored** rather than honoured:
# models still emit stray ``</type:character_dialogue>`` from the old contract, and each one
# used to *open a new segment*, so a completion that repeated itself became several
# byte-identical persisted events. One live turn produced four. Ignoring them keeps the
# passage whole — a repeating model then yields one ugly beat instead of four duplicates,
# which is a writing-quality problem rather than a correctness one.
_PROSE = "character_prose"
_PROSE_TYPES = {_PROSE}
#: ``<thinking>`` is no longer requested, but a model that emits it is putting deliberation
#: there — kept as a private ``internal_thought`` so it cannot reach the visible passage.
_THINKING_TYPE = "internal_thought"
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


#: A line-opening ``{`` — where an untagged JSON block can begin.
_LINE_JSON = re.compile(r"(?:\A|(?<=\n))[ \t]*\{")
_DECODER = json.JSONDecoder()


def _classify(obj: object) -> str | None:
    """Which JSON block type ``obj`` is, by its shape — ``None`` if it is not one.

    The three shapes are the ones the validators accept, so a misread is harmless: a block
    typed wrongly fails validation downstream and is dropped, rather than being rendered.
    """
    if not isinstance(obj, dict):
        return None
    if "key" in obj and ("delta" in obj or "value" in obj):
        return _STAT_TYPE
    if "type" in obj and "target" in obj:
        return _REL_TYPE
    if "status" in obj:
        return _PRESENCE_TYPE
    return None


def split_bare_json(chunk: str) -> tuple[str, list[tuple[str, str]]]:
    """Split ``chunk`` into its prose and any UNTAGGED JSON blocks that follow it.

    The contract asks a character to put ``<type:state_update>`` before a proposed change.
    Models routinely write the object and skip the tag, and nothing recognised that: the
    object fell through as prose and was rendered verbatim under the beat, *and* the change
    it proposed was silently dropped. Both halves were observed live, on ten of the twelve
    beats of one turn, with a model that was otherwise following the format exactly.

    A run is lifted only where it begins on a line-opening ``{`` **and** its first value
    parses and matches one of the three shapes the validators accept — which narrative prose
    does not do — so the passage is never cut short on the strength of a stray brace. The run
    then extends over every following value that also parses and classifies. Anything after
    it is **trailing**: returned in neither half, exactly as trailing prose after a *tagged*
    JSON block is already dropped by the one-passage rule.

    Returns ``(prose, [(kind, raw_json), …])``; an empty block list is the common case.
    """
    for match in _LINE_JSON.finditer(chunk):
        start = match.end() - 1
        blocks: list[tuple[str, str]] = []
        cursor = start
        while cursor < len(chunk):
            try:
                obj, end = _DECODER.raw_decode(chunk, cursor)
            except ValueError:
                break
            kind = _classify(obj)
            if kind is None:
                break
            blocks.append((kind, chunk[cursor:end]))
            cursor = end
            while cursor < len(chunk) and chunk[cursor] in " \t\r\n":
                cursor += 1
        if blocks:
            return chunk[:start], blocks
    return chunk, []


@dataclass
class Segment:
    """One parsed unit of a character's emission → one story event."""

    type: str
    text: str
    character_id: str


def _speaker_runs(
    text: str, roster: dict[int, str], fallback_speaker_id: str
) -> list[tuple[str, str]]:
    """Split an emission into ``(speaker_id, chunk)`` runs at every change of speaker.

    A ``<speaker:N>`` naming somebody NEW starts a run; one naming the current speaker is a
    no-op, because models re-state the current speaker constantly and treating that as a
    hand-off would fragment one passage into a dozen byte-adjacent beats. An out-of-roster
    number resolves to the current speaker, so it is a no-op too rather than an unattributed
    run.

    Exists so :func:`parse_emission` and :class:`EmissionAccumulator` cannot disagree about
    where one speaker's passage ends — a test asserts they produce identical segments, and
    the batch parser is what a re-roll and an export read.
    """
    runs: list[tuple[str, str]] = []
    speaker = fallback_speaker_id
    cursor = 0
    for match in _SPEAKER_RE.finditer(text):
        resolved = roster.get(int(match.group(1)), speaker)
        if resolved == speaker:
            continue  # not a hand-off; leave the run open and let the tag scrub out
        runs.append((speaker, text[cursor : match.start()]))
        speaker = resolved
        cursor = match.end()
    runs.append((speaker, text[cursor:]))
    return runs


def _segments_for_run(chunk: str, speaker_id: str) -> list[Segment]:
    """The segments one speaker's run of an emission produces."""
    segments: list[Segment] = []
    # Only a JSON block interrupts the passage. A prose-named tag is scrubbed with the rest
    # of the text, so stray closers cannot fragment one beat into several.
    type_marks = [m for m in _TYPE_RE.finditer(chunk) if m.group(1).lower() in _JSON_TYPES]
    if not type_marks:
        # The expected shape: no tags at all, one first-person passage — possibly with an
        # untagged JSON block appended, which :func:`split_bare_json` lifts back out.
        prose, blocks = split_bare_json(chunk)
        body = _clean(prose)
        if body:
            segments.append(Segment(_PROSE, body, speaker_id))
        segments.extend(Segment(kind, raw, speaker_id) for kind, raw in blocks)
        return segments

    # Prose before the first tag is the beat itself, not a preamble to discard: the expected
    # emission is plain prose optionally followed by a JSON block (``<type:state_update>``
    # and friends). Keeping it here is what makes the batch and incremental parsers agree on
    # a hybrid emission.
    lead = _clean(chunk[: type_marks[0].start()])
    if lead:
        segments.append(Segment(_PROSE, lead, speaker_id))

    open_kind: str | None = None
    for i, mark in enumerate(type_marks):
        kind = mark.group(1).lower()
        body_end = type_marks[i + 1].start() if i + 1 < len(type_marks) else len(chunk)
        # The closer for the block that is currently open ends it; anything after it is
        # trailing text, not a new block (see the accumulator for why this matters).
        if mark.group(0).lstrip().startswith("</") and open_kind == kind:
            open_kind = None
            continue
        raw_body = chunk[mark.end() : body_end].strip()
        if kind not in _JSON_TYPES:
            continue
        open_kind = kind
        if raw_body:
            segments.append(Segment(kind, raw_body, speaker_id))
    return segments


def parse_emission(
    raw: str,
    *,
    roster: dict[int, str],
    fallback_speaker_id: str,
) -> list[Segment]:
    """Parse a thin-tag emission into ordered segments.

    Usually one speaker's passage. Under a continuous multi-speaker script
    (``sceneFlow: "continuous"``) a ``<speaker:N>`` hands the floor over mid-emission and
    each run becomes its own segment, attributed to whoever the tag named.
    """
    text = raw or ""

    # EVERY ``<thinking>`` block comes out of the passage, not just the first: a model that
    # repeats its whole emission repeats the scratchpad with it, and leaving the later ones
    # in would land the deliberation in the visible prose once the tags were scrubbed. Only
    # the first becomes a segment — the rest are the same thought again.
    #
    # Lifted out BEFORE the speaker split so a thought is attributed to whoever was speaking
    # when it opened, and so a ``<speaker:N>`` inside a thinking block cannot hand the floor
    # to somebody on the strength of the model's scratchpad.
    thought: Segment | None = None
    first_speaker = fallback_speaker_id
    if (match := _SPEAKER_RE.search(text)) is not None:
        first_speaker = roster.get(int(match.group(1)), fallback_speaker_id)
    blocks = list(_THINKING_RE.finditer(text))
    if blocks:
        # Only a block that arrives BEFORE the passage is a thought. One that arrives after
        # it is a model looping back to the top of its own emission, and keeping it would
        # both invent a second deliberation and disagree with the streaming parser, which
        # cannot un-send a passage it has already begun.
        first = blocks[0]
        if not _clean(text[: first.start()]):
            body = _clean(first.group(1))
            if body:
                thought = Segment("internal_thought", body, first_speaker)
        for block in reversed(blocks):
            text = text[: block.start()] + text[block.end() :]

    segments: list[Segment] = [thought] if thought else []
    for speaker_id, chunk in _speaker_runs(text, roster, fallback_speaker_id):
        segments.extend(_segments_for_run(chunk, speaker_id))
    return segments


# ---- Incremental parsing ---------------------------------------------------
# :func:`parse_emission` runs over a finished string, so nothing can be shown until the
# whole beat exists. The accumulator below makes the same decisions on a growing prefix,
# which is what lets a character's private thought reach the player while their spoken
# line is still being written.

#: Every emission tag, in one pattern, so the scanner can find the next one of any kind.
#: The optional leading slash and optional ``:value`` mirror the tolerances above.
_ANY_TAG_RE = re.compile(
    rf"</?(?:speaker(?::\s*\d+)?|type(?::\s*[a-z_]+)?|thinking|{_WRAPPERS})\s*>",
    re.IGNORECASE,
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
        # Untagged text opens a ``character_prose`` segment and streams from the first
        # character. It used to be *held* until ``finish()`` and released as one spoken
        # line, which meant the ordinary case — a model emitting plain prose — showed the
        # player nothing until the whole beat existed.
        self._saw_type_mark = False
        # One passage per SPEAKER. Once a ``character_prose`` segment has been opened, no tag
        # may split it and no later text may start a second one for the same speaker — see
        # :meth:`_consume_text`. Without this a model that repeated its emission became one
        # persisted event per repetition: a single live beat produced five byte-identical
        # rows, which read as five beats by the same character.
        #
        # **Per speaker, not per emission.** It was the latter until continuous multi-speaker
        # scripts existed; a genuine hand-off (``<speaker:2>`` naming somebody else) now
        # releases it, in :meth:`_handle_tag`. That keeps the five-identical-beats defect this
        # was written for — a repeat is the same speaker again — while making a hand-off
        # representable at all.
        self._prose_seen = False
        # Whether ANY prose has been produced in this emission, ever — never reset, not even
        # by a hand-off. It gates the ``<thinking>`` rule, which is emission-wide rather than
        # per-speaker: a deliberation only counts before the writing starts, and a block
        # arriving after ANY prose is a model looping back to the top of its own emission
        # whoever is nominally speaking. Keeping this separate from `_prose_seen` is what
        # stops a hand-off from re-opening the door that guard exists to hold shut.
        self._any_prose_seen = False
        # True between a ``<thinking>`` and its closer while a passage is already open: the
        # deliberation is swallowed rather than allowed to interrupt the prose.
        self._swallowing = False
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
        """Close the emission; return the final deltas.

        The held tail is split here rather than in :meth:`push`, because whether a
        line-opening ``{`` is a JSON block or the start of a very odd sentence is only
        knowable once the emission ends.
        """
        out: list[SegmentDelta] = []
        blocks: list[tuple[str, str]] = []
        if self._buf:
            prose, blocks = split_bare_json(self._buf)
            self._buf = ""
            if prose:
                out.extend(self._consume_text(prose))
        for kind, raw in blocks:
            out.extend(self._close_open())
            out.extend(self._open(kind))
            out.extend(self._grow(raw))
        out.extend(self._close_open())
        return out

    # -- internals -----------------------------------------------------------

    def _safe_prefix(self, text: str) -> int:
        """How much of ``text`` cannot still turn out to be part of a tag or a JSON block.

        A line-opening ``{`` may be the start of an untagged JSON block (see
        :func:`split_bare_json`), and a passage cannot un-send prose it has already
        streamed — so everything from that brace is held until :meth:`finish` can see
        whether it closes as JSON. If it never does, it is released as prose there.
        """
        start = text.rfind("<")
        tag_safe = len(text) if start == -1 or ">" in text[start:] else start
        brace = _LINE_JSON.search(text)
        return tag_safe if brace is None else min(tag_safe, brace.end() - 1)

    def _handle_tag(self, tag: str) -> list[SegmentDelta]:
        speaker = _SPEAKER_RE.fullmatch(tag)
        if speaker:
            resolved = self._roster.get(int(speaker.group(1)), self._speaker_id)
            # A tag naming a DIFFERENT speaker is a hand-off: close whatever is open and let
            # the next text start a fresh passage attributed to them. This is what makes one
            # continuous multi-speaker script parseable (`sceneFlow: "continuous"`).
            #
            # A tag naming the SAME speaker changes nothing, which is the important half:
            # models re-state the current speaker constantly, and treating that as a hand-off
            # would fragment one passage into a dozen byte-adjacent beats.
            #
            # An out-of-roster number resolves to the current speaker, so it is also a no-op
            # rather than an unattributed segment.
            if resolved == self._speaker_id:
                return []
            out = self._close_open()
            self._speaker_id = resolved
            # The new speaker has not written a passage yet, so the one-passage-per-speaker
            # guard is released for them (see `_prose_seen`).
            self._prose_seen = False
            return out
        lowered = tag.lower()
        if "thinking" in lowered:
            # The contract no longer asks for <thinking>, but a model that emits it anyway
            # is putting DELIBERATION there — which must not land in the visible passage.
            # Before the passage starts it is kept as its own private segment: a safety
            # valve that keeps scratchpad out of the story rather than folding it in.
            #
            # Once the passage has started, the block is SWALLOWED instead. A closing tag
            # used to close the open segment, so the next word began a second
            # ``character_prose`` — which is how one repeating generation became five
            # identical persisted beats. A deliberation arriving mid-passage is a model
            # that has looped back to the top of its own emission; it is not a new beat and
            # it is not part of the prose.
            if self._any_prose_seen:
                self._swallowing = not lowered.startswith("</")
                return []
            if lowered.startswith("</"):
                return self._close_open()
            out = self._close_open()
            out.extend(self._open("internal_thought"))
            return out
        type_match = _TYPE_RE.fullmatch(tag)
        if type_match:
            kind = type_match.group(1).lower()
            if kind not in _JSON_TYPES:
                # A prose-named tag (usually a stray closer left over from the old
                # contract). Scrubbed: the passage continues in the segment already open.
                return []
            # ``<type:X>`` and ``</type:X>`` are deliberately treated alike, because some
            # models use a closer as the delimiter BETWEEN blocks. The exception is the
            # closer for the block that is open right now: that one genuinely ends it, and
            # reading it as another opener made the text after a JSON block into a second
            # ``state_update`` whose body was the model's trailing prose.
            if tag.lstrip().startswith("</") and self._open_type == kind:
                return self._close_open()
            self._saw_type_mark = True
            out = self._close_open()
            out.extend(self._open(kind))
            return out
        # A bare </type> / </speaker>, or an invented wrapper the model put the whole
        # passage inside (``<response>``, ``<passage>``), closes nothing and is scrubbed —
        # the passage carries on in whatever segment is open.
        return []

    def _consume_text(self, text: str) -> list[SegmentDelta]:
        if not text or self._swallowing:
            return []
        if self._open_type is None:
            # Prose arriving outside any tag IS the beat. Open a passage and stream it.
            # Whitespace alone does not open one, so a newline after ``<speaker:1>`` does
            # not start a segment that then holds nothing.
            if not text.strip():
                return []
            # ...but only the FIRST time. Text arriving after the passage has closed — a
            # model still talking after its ``<type:state_update>`` block, or looping back
            # to the top of its own emission — is not a second beat by the same character.
            if self._prose_seen:
                return []
            out = self._open(_PROSE)
            out.extend(self._grow(text))
            return out
        return self._grow(text)

    def _open(self, kind: str) -> list[SegmentDelta]:
        if kind == _PROSE:
            self._prose_seen = True
            self._any_prose_seen = True
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
#: Public so the turn engine can gate on the passage specifically.
PROSE_TYPE = _PROSE

# ---- Prose guards ----------------------------------------------------------
# Moved to ``services.prose_guards`` when this module passed the 800-line ceiling — they judge
# text, they do not parse it. Re-exported because ``emission`` is the name the engine, the
# harness, the research runners and their tests already reach for, and a rename would be
# churn with no reader benefit. The docstrings live with the code.
from app.services.prose_guards import (  # noqa: E402,F401  (re-export)
    SCRATCHPAD_WINDOW,
    addresses_the_reader,
    cross_speaker_speech,
    cross_speaker_speech_span,
    narrates_another_mind,
    narrates_another_mind_span,
    cut_before,
    in_the_scene,
    looks_degenerate,
    looks_like_briefing,
    looks_like_scratchpad,
    names_the_player,
    narration_only,
    narrator_speaks_in_first_person,
    repeats_itself,
    starts_mid_sentence,
)
