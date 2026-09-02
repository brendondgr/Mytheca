"""Finding a memory when nobody from it is in the room, and deciding what may be said.

Two rules, both deterministic, both set comparisons over data already in hand.

**Cues.** Participant matching cannot reach a memory whose people are dead, absent, or were
never characters. A runner who watched an ogre kill a friend has that friend in no further
scene, so the memory that most defines him is unreachable by "who is here" forever. The
answer is to look for what the memory was *about*: when the narration says *"an ogre steps
out of the treeline"*, ``ogres`` is a subject on that memory and the memory becomes a
candidate — three scenarios later, with nobody from that night present.

The trick that makes this free is not identifying everything in the scene. It is scanning
the scene for **the things we already hold memories about** — a set the recall query has
already loaded — so this is a dictionary intersection, not language understanding. No model
call, no extra query, and the same lexical posture ``services/retrieval_gate.py`` uses to
decide whether to fetch lore.

**Disclosure.** A recalled memory is not automatically something the character may say. If
the friend died in a scene the people here were not in, narrating it hands them knowledge
they were never given — a leak that reaches the next prompt as fact and is invisible in the
transcript. Which class a memory falls into is a comparison between who was at the source
event and who is in the room, so it is computed, never guessed, and it is a property of the
memory **and the room together**: the same memory is quotable to someone who was there and
private with respect to someone who was not.
"""

from __future__ import annotations

import re

#: Everyone here was also there. Safe to say aloud, and safe to quote verbatim.
QUOTABLE = "quotable"
#: Some were, some were not. May be alluded to; must not be narrated as common knowledge.
SHARED = "shared"
#: Nobody here was there. Shapes behaviour; must never be stated as something the room knows.
PRIVATE = "private"

_WORDS = re.compile(r"[^a-z0-9]+")


def _haystack(texts: list[str]) -> str:
    """One normalized, space-padded blob to search — punctuation folded, lowercased."""
    joined = " ".join(t or "" for t in texts).lower()
    return f" {_WORDS.sub(' ', joined).strip()} "


def scan(texts: list[str], tags: set[str]) -> set[str]:
    """Which of ``tags`` the live scene actually names.

    ``tags`` are stored subjects in kebab form (``flooded-tunnel``); the scene says "the
    flooded tunnel". Matching is on whole words, so ``mara`` does not fire on "maratime".

    A single trailing ``s`` is tolerated in either direction — ``ogres`` matches "an ogre",
    ``ogre`` matches "ogres". ``normalize_subject`` folds articles but deliberately not
    plurals (stemming would damage words whose plural is the point), and this is where that
    near-miss is absorbed. It is a one-character allowance, not a stemmer: ``knives`` still
    will not match ``knife``.
    """
    if not tags:
        return set()
    hay = _haystack(texts)
    hits: set[str] = set()
    for tag in tags:
        phrase = tag.replace("-", " ").strip()
        if not phrase:
            continue
        variants = {phrase}
        if phrase.endswith("s"):
            variants.add(phrase[:-1])
        else:
            variants.add(phrase + "s")
        if any(f" {v} " in hay for v in variants):
            hits.add(tag)
    return hits


def disclosure(participants: list[str] | None, *, others_present: set[str]) -> str:
    """Whether this memory may be spoken, hinted at, or only acted on.

    ``others_present`` is everyone in the room **except** the character doing the
    remembering. With the room otherwise empty every class is vacuous and the answer is
    :data:`QUOTABLE` — there is nobody to leak it to, and a character alone with a memory
    should be free to speak it aloud.
    """
    was_there = {p for p in (participants or [])}
    if not others_present:
        return QUOTABLE
    if others_present <= was_there:
        return QUOTABLE
    if others_present & was_there:
        return SHARED
    return PRIVATE


def outsiders(participants: list[str] | None, *, others_present: set[str]) -> set[str]:
    """Who is in the room now and was **not** at the source event.

    These are the people a `private` or `shared` memory must not be narrated in front of,
    and naming them in the prompt is what turns the rule from an abstraction into an
    instruction the model can follow.
    """
    return others_present - {p for p in (participants or [])}


# ---- promotion -----------------------------------------------------------------

#: How many memories must carry a tag, or how many scenarios it must span, before it earns
#: a graph node. Arithmetic, not judgement — and the threshold is the whole point: without
#: it every noun anyone mentions becomes a permanent node and traversal gets slower for
#: nothing. `ogres` becomes a node in a world precisely because ogres kept mattering.
PROMOTE_MENTIONS = 3
PROMOTE_SCENARIOS = 2


def promotable(memories: list) -> dict[str, int]:
    """Subject tags that have recurred enough to deserve a node, with their mention counts.

    Counts **normalized** tags, which is why `normalize_subject` folding matters here twice
    over: a place spelled four ways is four tags that each fall short of the bar, and would
    never promote however central it was to the story.
    """
    mentions: dict[str, int] = {}
    scenarios: dict[str, set[str]] = {}
    for memory in memories:
        for tag in set(memory.subjects or []):
            mentions[tag] = mentions.get(tag, 0) + 1
            scenarios.setdefault(tag, set()).add(memory.scenario_id)
    return {
        tag: count
        for tag, count in mentions.items()
        if count >= PROMOTE_MENTIONS or len(scenarios.get(tag, ())) >= PROMOTE_SCENARIOS
    }
