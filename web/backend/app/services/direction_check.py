"""Did the beat that was *supposed* to deliver a requirement actually deliver it?

The engine used to mark a requirement satisfied at the moment it put that requirement into
a prompt. That is a promise, not an outcome. A beat can come back empty, be withheld as a
scratchpad leak, fail against the endpoint, or simply talk about something else — and every
one of those cases ticked the requirement off permanently. It is the single largest reason
a direction "gets forgotten": the turn believed it had already done the thing.

Splitting *attempted* from *delivered* fixes the failure cases for free (a beat with no text
is never confirmed). This module supplies the cheap part of the rest: a lexical check of
whether the beat's prose actually covers the words the requirement asked for. It is
deliberately **not** an LLM call — this runs after every beat on the turn's hot path, and a
crude signal that costs nothing beats an accurate one that costs a round-trip per beat.

Being crude, it is used only to *withhold confirmation*, never to punish: an unconfirmed
requirement stays outstanding and is retried, and after ``DIRECTION_MAX_ATTEMPTS`` it is
reported as unconfirmed rather than as failed. A false negative therefore costs one more
attempt; it never silently drops anything.
"""

from __future__ import annotations

import re

#: Words that carry no evidence either way. A requirement and a beat will share these no
#: matter what happens in the scene, so counting them would let any prose "cover" anything.
#:
#: The last group is the one that is easy to miss: **abstract subject placeholders**. A
#: requirement reading "a character loses their temper" is saying *anyone* — and no prose
#: will ever contain the word "character", because prose names people. Left in, they are a
#: guaranteed miss on a whole class of word rather than a random one, and they drag the
#: score down by a fixed amount on exactly the requirements that are phrased most generally.
STOPWORDS = frozenset(
    """
    character characters someone somebody person people anyone everybody
    
    the a an and or but so then than that this these those there here
    is are was were be been being am get gets got have has had having
    do does did doing done can could will would shall should may might must
    of in on at to from by with without into onto for about over under again
    as if it its it's he she they them their his her hers him you your yours
    i me my mine we us our ours who whom whose what which when where why how
    not no nor only just very more most some any all both each other another
    up down out off out over back away still now while during until before after
    one two three four five something someone anything anyone everything everyone
    say says said tell tells told make makes made go goes went come comes came
    """.split()
)

#: Tokens shorter than this carry too little signal to be worth matching.
MIN_TOKEN = 3

#: Crude stemming: compare only this many leading characters, so `storms` / `stormed` /
#: `storming` all collapse onto `storm`. Cheaper and more predictable than a real stemmer,
#: and the failure mode (two unrelated words sharing a 5-char prefix) is a false *positive*
#: on one word out of a set, which the threshold absorbs.
STEM = 5

_WORD = re.compile(r"[a-z0-9']+")


def content_words(text: str) -> set[str]:
    """The stemmed, de-stopworded content words of ``text``."""
    out: set[str] = set()
    for token in _WORD.findall((text or "").lower()):
        word = token.strip("'")
        if len(word) < MIN_TOKEN or word in STOPWORDS:
            continue
        out.add(word[:STEM])
    return out


def coverage(requirement: str, beat: str, *, ignore_names: list[str] | None = None) -> float:
    """What fraction of the requirement's content words the beat's prose contains.

    ``ignore_names`` drops the bound actor's own name from the requirement's word set. A
    requirement reads *"Mei snaps back at him"* while Mei's own beat, written in her voice,
    never says "Mei" — without this every in-voice delivery would under-score, and the
    check would be biased against exactly the beats it most wants to confirm.

    Returns ``0.0`` for an empty requirement (nothing was asked for, so nothing is covered
    — a caller must not read that as "delivered").
    """
    wanted = content_words(requirement)
    for name in ignore_names or []:
        wanted -= content_words(name)
    if not wanted:
        return 0.0
    return len(wanted & content_words(beat)) / len(wanted)


def reached(
    requirement: str,
    beat: str,
    *,
    threshold: float,
    ignore_names: list[str] | None = None,
) -> bool:
    """Did ``beat`` cover enough of ``requirement`` to call it delivered?"""
    return coverage(requirement, beat, ignore_names=ignore_names) >= threshold
