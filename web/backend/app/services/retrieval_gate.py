"""Retrieval gate — a cheap, model-free skip-or-fetch decision (turn-loop plan §2/§5).

Most turns are answered by the working set (World Primer, live scene state, the graph
subgraph, the recent buffer), so durable-lore retrieval is **gated**: it fires only when
the player names an entity/place/event **absent from the present roster**, or asks a
who/what/when/where about **world history/lore**. The cheapest search is the one we don't
run, and a bad retrieval is worse than none — so the gate is deliberately conservative
(it skips on doubt; a missed fetch just means an ungrounded-but-still-coherent turn).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# wh-words that, paired with a history cue, mark a lore/history question.
_WH = {"who", "what", "when", "where", "why", "how", "whose", "which"}

# Cues that a question reaches into world history / durable lore (not the live beat).
_HISTORY_CUES = (
    "history", "ago", "year", "war", "fire", "founded", "legend", "ancient", "before",
    "used to", "remember", "once", "past", "happened", "decade", "winter", "summer",
    "back then", "long ago", "story of", "the old",
)

# Capitalized titles / honorifics / function words that are NOT lore entities — kept off
# the off-roster trigger so "the Captain by the door" doesn't spuriously fetch.
_STOP = {
    "the", "a", "an", "i", "captain", "brother", "sister", "lord", "lady", "sir", "madam",
    "mister", "miss", "mistress", "father", "mother", "doctor", "master", "saint", "king",
    "queen", "prince", "princess", "guard", "the captain", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday",
}

# A capitalized run sitting *mid-sentence* (preceded by a lowercase letter or comma), or a
# multi-word capitalized run anywhere — the shapes a proper noun takes in player input.
_MID_PROPER = re.compile(r"(?<=[a-z,]\s)([A-Z][a-z']+(?:\s+[A-Z][a-z']+)*)")
_MULTI_PROPER = re.compile(r"\b([A-Z][a-z']+(?:\s+[A-Z][a-z']+)+)\b")


@dataclass
class GateDecision:
    """Whether to fetch durable lore this turn, plus the reason (logged) + query."""

    fetch: bool
    reason: str
    query: str = ""


def _known_words(names: list[str]) -> set[str]:
    words: set[str] = set(_STOP)
    for name in names:
        for word in re.findall(r"[A-Za-z']+", name or ""):
            words.add(word.lower())
    return words


def off_roster_terms(text: str, known_names: list[str]) -> list[str]:
    """Capitalized terms in ``text`` not accounted for by the roster/setting/stoplist."""
    known = _known_words(known_names)
    found: list[str] = []
    for match in [*_MID_PROPER.finditer(text), *_MULTI_PROPER.finditer(text)]:
        span = match.group(1).strip()
        span_words = [w.lower() for w in re.findall(r"[A-Za-z']+", span)]
        if not span_words or all(w in known for w in span_words):
            continue
        if span not in found:
            found.append(span)
    return found


def gate(text: str, *, known_names: list[str]) -> GateDecision:
    """Decide skip-or-fetch for one player turn (conservative — skip by default)."""
    text = (text or "").strip()
    if not text:
        return GateDecision(False, "empty input")

    off = off_roster_terms(text, known_names)
    if off:
        return GateDecision(True, f"names off-roster term '{off[0]}'", query=text)

    lowered = text.lower()
    words = set(re.findall(r"[a-z']+", lowered))
    if (words & _WH) and any(cue in lowered for cue in _HISTORY_CUES):
        return GateDecision(True, "world-history question", query=text)

    return GateDecision(False, "working set suffices", query=text)
