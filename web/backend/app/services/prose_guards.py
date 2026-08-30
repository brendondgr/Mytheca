"""Prose guards — is this passage still a scene, and is it still THIS character's?

Split out of ``emission`` on 2026-08-24, when that module went past the 800-line ceiling. The
two halves were always different jobs: ``emission`` turns a thin-tag emission into ordered
segments, and this decides whether a segment should be shown at all. Nothing here parses and
nothing there judges.

Every guard is a **pure function on text**, which is what lets the streaming gate
(``beat_stream``), the smoke harness (``utils/scripts/scene_smoke.py``) and the research
runners all ask the same question and get the same answer. A harness with its own copy of
"what counts as a violation" measures its own opinion.

Two rules they share:

* **The failure direction is chosen, not accidental.** A missed leak costs a reader's
  eyebrow; a false positive silently discards good writing and spends a regeneration. Every
  rule here errs towards missing one.
* **Each was written from an observed failure**, and each docstring names it. None is a
  general-purpose quality score, and none should become one.
"""

from __future__ import annotations

import re

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


#: The half of :data:`_SCRATCHPAD_TERMS` that is never ordinary prose. "beat", "block",
#: "response", "output" and "format" all have perfectly good English senses — a heart beats,
#: a doorway is blocked, there is no response — and they are only safe in
#: :func:`looks_like_scratchpad` because the first-person test carries most of that rule.
_BRIEFING_TERMS = (
    "the player", "the user", "roster", "cast list", "json", "instruction", "type:",
    "final answer", "voice sample", "checklist", "the passage", "the prompt", "system message",
)
#: Three rather than two, because there is no second signal here. See
#: :func:`looks_like_briefing`.
_BRIEFING_MIN_TERMS = 3


def looks_like_briefing(text: str) -> bool:
    """True when a THIRD-PERSON passage is the model briefing itself rather than writing.

    :func:`looks_like_scratchpad` cannot be reused for free-text prose, and the reason is
    exact: that rule is a conjunction of production vocabulary AND *no first-person pronoun*,
    which works because a character beat is written in the first person, so a real passage
    always has one and exempts itself. A free-text body is third person by contract — it
    never has one — so half the conjunction is always true and the rule collapses to its
    vocabulary test alone, which is too eager to run on prose.

    So this is the stricter standalone rule: only vocabulary that is never ordinary English,
    and three distinct terms rather than two.
    """
    opening = (text or "")[:_SCRATCHPAD_WINDOW].lower()
    if not opening.strip():
        return False
    padded = f" {opening} "
    hits = {term for term in _BRIEFING_TERMS if term in padded}
    return len(hits) >= _BRIEFING_MIN_TERMS


def in_the_scene(text: str) -> bool:
    """True once a passage has proved itself to be a character speaking.

    A first-person pronoun is the thing a leaked scratchpad never has and a passage in the
    required form always has, so its arrival ends any need to keep holding the opening
    back. Most passages clear this within their first sentence, which is what keeps the
    guard in :func:`looks_like_scratchpad` from turning streaming prose into a lump.
    """
    return bool(_FIRST_PERSON_RE.search(text or ""))


#: "the player" / "the user" — a production label for a person, used as if it were a name.
#: ``\s+`` rather than a literal space so a line break between the two words still matches,
#: and the ``the`` must be adjacent: "the lute player" and "the other players" are ordinary
#: prose and must survive.
_NAMES_THE_PLAYER_RE = re.compile(r"\bthe\s+(?:player|user)(?:['’]s)?\b", re.IGNORECASE)


def names_the_player(text: str, *, window: int | None = None) -> bool:
    """True when a passage calls the person in the room "the player".

    The character and narrator transcripts label the human's line, and for a long time that
    label was ``Player:``. The models used it as a name: in the EXP-2026-08-008 verification
    run **13 of 18 character beats and 6 of 10 narration beats** said "the player" — *"The
    player's question feels like a stone dropped into a well"*, *"I feel the player's gaze
    sweep over us"*, *"his eyes lock onto the player"*. The prose was otherwise exactly right,
    which is why nothing caught it: :func:`looks_like_scratchpad` needs production vocabulary
    AND no first-person pronoun, and these say "I" throughout;
    :func:`starts_mid_sentence` needs a lowercase open, and these begin on a capital.

    The fix is at the source — the line is labelled ``You:`` and both prompts ask for the
    second person — so this is a backstop and a measurement, not the primary defence.

    ``window`` limits the check to the opening, which is what the engine's gate wants: it
    judges a passage before releasing it, and a beat that reaches a card table in its fourth
    paragraph is writing a scene, not reading its own prompt. Omit it to measure a whole
    passage, which is what the research runner does.
    """
    body = text or ""
    if window is not None:
        body = body[:window]
    return bool(_NAMES_THE_PLAYER_RE.search(body))


#: Spoken text, so a check can ask about the NARRATION alone. Straight and curly pairs both
#: appear in live output; a lone opening quote at the end of a truncated stream is treated as
#: running to the end of the passage, which is what a streaming gate needs it to do.
_QUOTED_RE = re.compile(r"[\"\u201c][^\"\u201c\u201d]*(?:[\"\u201d]|$)")


def narration_only(text: str) -> str:
    """``text`` with every span of quoted speech removed.

    The two checks below both need this. A character saying *"You are lying, Zoe"* is
    ordinary, correct writing — the second person there is aimed at another character in the
    room. The same pronoun in the NARRATION around it is aimed at the reader, and under
    Playwright mode the reader is not in the scene. Stripping the quotes is what separates
    the two, and it is why :func:`addresses_the_reader` can afford to be strict.
    """
    return _QUOTED_RE.sub(" ", text or "")


#: Second-person pronouns, contractions included. Word-boundary matched so a name that opens
#: on the same letters ("Yourke") is not a hit.
_SECOND_PERSON_RE = re.compile(
    r"\b(?:you|your|yours|yourself|yourselves|you['\u2019](?:re|ve|ll|d))\b",
    re.IGNORECASE,
)
#: First person, for the narrator. The narrator is a voice, not a character: it has no "I".
_NARRATOR_FIRST_PERSON_RE = re.compile(
    r"\b(?:i|i['\u2019](?:m|ve|ll|d)|me|my|mine|myself|we|us|our|ours|ourselves)\b",
    re.IGNORECASE,
)


def addresses_the_reader(text: str, *, window: int | None = None) -> bool:
    """True when a passage speaks to somebody who is not in the scene.

    **Only meaningful while the player is not embodied.** Under Player POV the player IS a
    character in the room, every "you" aimed at them is correct, and this must never run.
    Under Playwright mode the player is outside the fiction entirely — they write what
    happens, they are not a person anyone can look at — so a second person in the narration
    has no referent at all.

    Judged on :func:`narration_only`, never the raw text, for the reason that function
    documents: dialogue legitimately says "you" to another character.

    The mechanism this backs up is the transcript label. `EXP-2026-08-009` showed the label
    is what the model imitates and a rule alone changes nothing — the player's line reads
    ``Direction:`` under Playwright precisely so there is no person there to address. This is
    the backstop and the metric, exactly as :func:`names_the_player` is.

    ``window`` limits the check to the opening, which is what the streaming gate wants; omit
    it to measure a whole passage, which is what the smoke harness and the research runner do.
    """
    body = text or ""
    if window is not None:
        body = body[:window]
    return bool(_SECOND_PERSON_RE.search(narration_only(body)))


def narrator_speaks_in_first_person(text: str) -> bool:
    """True when a narration beat says "I", "me" or "we".

    The narrator describes the scene from outside it and names the people in it. A first
    person there means it has started playing a character — either inventing one, or drifting
    into the voice of whoever spoke last.

    Quotes are stripped for symmetry with :func:`addresses_the_reader`, but the narrator
    prompt forbids dialogue outright, so a quote in a narration beat is already a separate
    defect and this is not the check that should report it.
    """
    return bool(_NARRATOR_FIRST_PERSON_RE.search(narration_only(text)))


#: Verbs that turn a name beside a quotation into an attribution. Deliberately a closed list:
#: an open "any verb" rule would call *"He read the note aloud"* dialogue.
_SPEECH_VERBS = (
    "say|says|said|ask|asks|asked|reply|replies|replied|answer|answers|answered|"
    "mutter|mutters|muttered|murmur|murmurs|murmured|whisper|whispers|whispered|"
    "shout|shouts|shouted|call|calls|called|add|adds|added|offer|offers|offered|"
    "snap|snaps|snapped|growl|growls|growled|breathe|breathes|breathed|"
    "laugh|laughs|laughed|tell|tells|told|demand|demands|demanded|"
    "insist|insists|insisted|warn|warns|warned|admit|admits|admitted|"
    "repeat|repeats|repeated|continue|continues|continued|declare|declares|declared|"
    "cut in|cuts in|put in|puts in|breaks in|broke in"
)


def cross_speaker_speech_span(text: str, *, others: list[str]) -> tuple[str, int] | None:
    """:func:`cross_speaker_speech`, plus WHERE the leak starts.

    The offset is what lets the streaming gate cut a passage back to before the intrusion
    instead of throwing the whole beat away. A leak arrives mid-passage — the opening is
    usually fine — so "discard and re-roll" would spend a generation to rewrite three good
    paragraphs for the sake of a fourth.
    """
    body = text or ""
    if not body.strip():
        return None
    best: tuple[str, int] | None = None
    for name in others:
        bare = (name or "").strip()
        if not bare:
            continue
        # First word only: the cast is addressed by first name in prose, and a full name
        # would never match "Zoe says" for a character stored as "Zoe Marchetti".
        first = re.escape(bare.split()[0])
        verbs = _SPEECH_VERBS
        patterns = (
            rf"\b{first}\b[^.!?\n\"\u201c]{{0,40}}?\b(?:{verbs})\b[^\"\u201c\n]{{0,20}}[\"\u201c]",
            rf"[\"\u201d][,.!?]?\s+\b{first}\b\s+(?:\w+\s+){{0,2}}?(?:{verbs})\b",
            rf"(?:^|\n)\s*{first}\s*:\s*[\"\u201c]",
        )
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match and (best is None or match.start() < best[1]):
                best = (bare, match.start())
    return best


def cut_before(text: str, offset: int) -> str:
    """``text`` trimmed to a clean boundary at or before ``offset``.

    Prefers the last paragraph break, then the last sentence end, then the offset itself —
    so a cut beat still ends on something a reader can finish, rather than mid-clause.
    """
    head = (text or "")[:offset]
    for boundary in ("\n\n", "\n"):
        cut = head.rfind(boundary)
        if cut > 0:
            return head[:cut].rstrip()
    cut = max(head.rfind(mark) for mark in (".", "!", "?", "\u201d", '"'))
    return head[: cut + 1].rstrip() if cut > 0 else head.rstrip()


def cross_speaker_speech(text: str, *, others: list[str]) -> str | None:
    """The name of another character given a spoken line inside this beat, or ``None``.

    The contract has said *"Only your character. Never write anyone else's words"* since
    before any of the prose experiments, and nothing has ever checked it — `emission` guards
    degeneration, repetition, scratchpad leakage, a mid-sentence opening and the phrase "the
    player", and not this. The owner's report is the shape it takes in practice: Lily is
    speaking, and Zoe starts talking inside Lily's beat.

    **Deliberately narrow, in the safe direction.** Only three shapes count, all of them an
    attribution rather than a mention:

    * ``Zoe says, "..."`` — name, speech verb, quote.
    * ``"...," Zoe says`` — quote, name, speech verb.
    * ``Zoe: "..."`` — a script-style label the contract already forbids.

    Reported speech (*"He told me the gate was shut"*), a character being described,
    addressed, or answered, and the speaker quoting **themself** all survive untouched. A
    missed leak costs a reader's eyebrow; a false positive silently discards good writing and
    spends a regeneration, so the rule errs towards missing one.

    Returns the offending name rather than a bool so the caller can say **who** leaked, which
    is the difference between a trace a reader can act on and one that only says "something".
    """
    found = cross_speaker_speech_span(text, others=others)
    return found[0] if found else None


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


#: How much of a passage's opening the engine holds back before showing any of it, so a
#: leaked scratchpad can be caught before the reader sees a word of it (see
#: :func:`looks_like_scratchpad`). Public because the gate in ``beat_stream`` and the
#: research runners both size their window from it — two independently chosen windows for
#: one question is how the guard and the metric come to disagree.
SCRATCHPAD_WINDOW = _SCRATCHPAD_WINDOW
