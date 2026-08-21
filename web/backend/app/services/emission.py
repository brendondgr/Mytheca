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


#: How much of the tail to inspect for degeneration, and how little variety it takes to
#: call it. A passage is never length-capped — a character may hold the floor for as long
#: as the moment needs — but a generation that has stopped producing language should not be
#: streamed into the story. Live runs produced 29,660 and 48,167-character beats that began
#: as prose, drifted into the model's own notes, and ended in "Rex Rex Rex" and "AT AT AT
#: AAAA". Detecting that is what lets the length stay unbounded.
_DEGENERATE_WINDOW = 400
_DEGENERATE_MIN_DISTINCT_WORDS = 12
#: Prose punctuates. A 400-character stretch — roughly seventy words — with **no** mark of
#: punctuation at all is not a sentence any more. This catches the *second* observed
#: collapse mode, which the variety check above cannot see: a drift into an unrelated word
#: list ("… sediment erosion weathering transport deposition compaction lithification …"),
#: where every word differs so lexical variety stays high while the language is gone.
#:
#: One is the threshold rather than two because a single comma in seventy words is still a
#: sentence — a deliberate run-on is a real style, and an earlier draft of this rule cut it.
_DEGENERATE_MIN_PUNCTUATION = 1
_SENTENCE_MARKS = ".,;:!?\"'“”’—"

#: How much verbatim text has to recur before a passage is called a repeat. A model that
#: has lost the thread restates its whole passage — one live beat contained the same
#: ~2,400 characters five times over. Two hundred characters is roughly thirty words: long
#: enough that no writer produces it twice by accident, short enough to catch the loop on
#: its second pass rather than its fifth.
_REPEAT_WINDOW = 200


def repeats_itself(text: str) -> bool:
    """True when the tail of ``text`` has already appeared verbatim earlier in it.

    Distinct from :func:`looks_degenerate`, which asks whether the text has stopped being
    language: a repeat is perfectly good prose, delivered again. Both were the same defect
    while the parser split a repeating emission into one event per pass — five well-formed
    rows that each looked correct. With the passage kept whole the repetition is visible in
    one body, and this is what sees it.
    """
    body = text or ""
    if len(body) < 2 * _REPEAT_WINDOW:
        return False
    tail = body[-_REPEAT_WINDOW:]
    first = body.find(tail)
    return first != -1 and first < len(body) - _REPEAT_WINDOW


def looks_degenerate(text: str) -> bool:
    """True when the tail of ``text`` has stopped being language.

    Two collapse modes, both observed live and both deliberately conservative:

    * **A token loop** — almost no distinct words ("Rex Rex Rex …", "AT AT AT AAAA").
    * **A word list** — plenty of distinct words but no sentence structure at all.

    The check is on the TAIL rather than the whole passage, because the observed shape is a
    beat that opens as ordinary prose and collapses later. Neither rule fires on real
    writing: an incantatory, deliberately repetitive line still punctuates, and ordinary
    prose never runs seventy words without a comma.
    """
    tail = (text or "")[-_DEGENERATE_WINDOW:]
    words = tail.split()
    if len(words) < 20:
        return False
    if len(set(words)) < _DEGENERATE_MIN_DISTINCT_WORDS:
        return True
    return sum(tail.count(mark) for mark in _SENTENCE_MARKS) < _DEGENERATE_MIN_PUNCTUATION


#: Vocabulary that belongs to the job, not to the story. A passage is written from inside a
#: character; these are the words a model reaches for when it is talking to itself ABOUT
#: writing one.
_SCRATCHPAD_TERMS = (
    "the player", "roster", "beat", "tag", "json", "instruction", "passage", "prose",
    "output", "format", "block", "response", "structured", "final answer", "type:",
)
#: How much of the opening to judge, and how many distinct production terms it takes.
_SCRATCHPAD_WINDOW = 400
_SCRATCHPAD_MIN_TERMS = 2
#: The contract asks for first person, present tense. Four hundred characters of a real
#: passage without a single first-person pronoun does not happen; four hundred characters
#: of a model briefing itself never has one. This is the half of the rule that does the
#: work — the vocabulary alone would catch a character who says "my heart beat".
#:
#: Word-boundary matching is load-bearing: a substring test for ``i'`` matched the ``i’`` in
#: a character's name ("Mei's fence") and exempted a leak that had no first person in it.
_FIRST_PERSON_RE = re.compile(r"\b(?:i|i['’]\w+|my|me|mine|myself)\b", re.IGNORECASE)


def looks_like_scratchpad(text: str) -> bool:
    """True when a passage is the model briefing itself rather than a character speaking.

    Two live beats were persisted and rendered as prose. One was the output contract read
    back — *"then main passage then optional structured blocks each opening tag own line
    JSON below NO closing tag per instructions…"*. The other was third-person planning about
    the character the model was supposed to BE — *"Kira's condition right now — …; must
    carry that into response to what just happened (… player named drowned ledger). Beat
    direct…"*. Both are well-formed language, so ``looks_degenerate`` passes them, and
    nothing else was looking.

    The rule is a conjunction on the OPENING, because a real passage starts in the scene on
    its first word: production vocabulary AND no first-person pronoun. Either alone would
    be too eager.
    """
    opening = (text or "")[:_SCRATCHPAD_WINDOW].lower()
    if not opening.strip():
        return False
    if _FIRST_PERSON_RE.search(opening):
        return False
    padded = f" {opening} "
    hits = {term for term in _SCRATCHPAD_TERMS if term in padded}
    return len(hits) >= _SCRATCHPAD_MIN_TERMS


def in_the_scene(text: str) -> bool:
    """True once a passage has proved itself to be a character speaking.

    A first-person pronoun is the thing a leaked scratchpad never has and a passage in the
    required form always has, so its arrival ends any need to keep holding the opening
    back. Most passages clear this within their first sentence, which is what keeps the
    guard in :func:`looks_like_scratchpad` from turning streaming prose into a lump.
    """
    return bool(_FIRST_PERSON_RE.search(text or ""))


def starts_mid_sentence(text: str) -> bool:
    """True when a passage opens on a lowercase letter — a fragment, not an opening.

    The contract says to start in the scene on the first word, and a passage that begins
    lowercase has not started: it is the tail of something the model was saying to itself.
    A live beat came through as the 62-character *"flat composure build in my own voice
    rather than restating it."*, which :func:`looks_like_scratchpad` cannot see — it says
    "my", so the first-person test exempts it, and its vocabulary is ordinary.

    Deliberately narrow: only a lowercase LETTER counts, so a passage opening on a quote
    mark, an ellipsis or a dash is untouched. Stylised all-lowercase prose is a real style
    and this would cost it one regeneration; that is the trade, and it is worth it against
    a fragment reaching the page.
    """
    stripped = (text or "").lstrip()
    return bool(stripped) and stripped[0].isalpha() and stripped[0].islower()


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

    # EVERY ``<thinking>`` block comes out of the passage, not just the first: a model
    # that repeats its whole emission repeats the scratchpad with it, and leaving the
    # later ones in would land the deliberation in the visible prose once the tags were
    # scrubbed. Only the first becomes a segment — the rest are the same thought again.
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
                segments.append(Segment("internal_thought", body, speaker_id))
        for block in reversed(blocks):
            text = text[: block.start()] + text[block.end() :]

    # Only a JSON block interrupts the passage. A prose-named tag is scrubbed with the
    # rest of the text, so stray closers cannot fragment one beat into several.
    type_marks = [m for m in _TYPE_RE.finditer(text) if m.group(1).lower() in _JSON_TYPES]
    if not type_marks:
        # The expected shape: no tags at all, one first-person passage.
        body = _clean(text)
        if body:
            segments.append(Segment(_PROSE, body, speaker_id))
        return segments

    # Prose before the first tag is the beat itself, not a preamble to discard: the
    # expected emission is plain prose optionally followed by a JSON block
    # (``<type:state_update>`` and friends). Keeping it here is what makes the batch and
    # incremental parsers agree on a hybrid emission.
    lead = _clean(text[: type_marks[0].start()])
    if lead:
        segments.append(Segment(_PROSE, lead, speaker_id))

    open_kind: str | None = None
    for i, mark in enumerate(type_marks):
        kind = mark.group(1).lower()
        body_end = type_marks[i + 1].start() if i + 1 < len(type_marks) else len(text)
        # The closer for the block that is currently open ends it; anything after it is
        # trailing text, not a new block (see the accumulator for why this matters).
        if mark.group(0).lstrip().startswith("</") and open_kind == kind:
            open_kind = None
            continue
        # state_update / relationship_update carry a JSON body; prose is scrubbed.
        raw_body = text[mark.end() : body_end].strip()
        if kind not in _JSON_TYPES:
            continue
        open_kind = kind
        if raw_body:
            segments.append(Segment(kind, raw_body, speaker_id))
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
        # A beat is ONE passage. Once a ``character_prose`` segment has been opened, no tag
        # may split it and no later text may start a second one — see :meth:`_consume_text`.
        # Without this a model that repeated its emission became one persisted event per
        # repetition: a single live beat produced five byte-identical rows, which read as
        # five beats by the same character. Making the second segment unrepresentable turns
        # that into one ugly passage, which ``repeats_itself`` can then act on.
        self._prose_seen = False
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
        """Close the emission; return the final deltas."""
        out: list[SegmentDelta] = []
        if self._buf:
            out.extend(self._consume_text(self._buf))
            self._buf = ""
        out.extend(self._close_open())
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
            if self._prose_seen:
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
#: How much of a passage's opening the engine holds back before showing any of it, so a
#: leaked scratchpad can be caught before the reader sees a word of it (see
#: :func:`looks_like_scratchpad`).
SCRATCHPAD_WINDOW = _SCRATCHPAD_WINDOW
