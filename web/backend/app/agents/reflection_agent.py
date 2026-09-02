"""Reflection agent — a character's private, read-time retrospective (§10 / §P9).

After a beat is delivered, each character reflects: what just happened from *their*
POV, and — more importantly — their **disposition** going into the next turn (a short,
mutable stance that *overrides* the previous one). When the turn offered the player a
fork, the reflection is **branch-keyed**: an anticipated stance per option, so whichever
path the player takes, the character re-enters already leaning into it.

This is structure-light interiority, not prose: the model returns a small JSON object,
parsed into an :class:`~app.memory.interior.InteriorRecord`. It is **best-effort** — a
missing/failed/malformed LLM reply yields ``None`` and the character simply keeps its
last interior state.

The generation takes a **pre-resolved LLM connection** (not a ``Session``) so a whole
cast can reflect concurrently on worker threads without sharing the request's SQLAlchemy
session (see ``services.reflection`` / ``services.concurrency``).
"""

from __future__ import annotations

from app.agents._common import extract_json, gen_params
from app.core.errors import APIError
from app.memory.interior import InteriorRecord
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams

# A reflection is a cheap, structure-light interior step — keep the thinking budget low.
REFLECTION_EFFORT = ReasoningEffort.LOW

# The resolved LLM connection tuple (base_url, api_key, model, params) — passed in so a
# whole cast can reflect on worker threads without touching the request Session.
LlmConn = tuple[str, str, str, LlmParams]

_SYSTEM = """You are the private inner voice of ONE character in a living scene, reflecting the instant AFTER a beat just happened. This is never shown to anyone — it only sets how you re-enter next.

Return ONLY a JSON object, no prose, no commentary:
{"disposition": "<your stance RIGHT NOW — how the moment has left you FEELING and what you want, first person, 2-3 sentences>", "retrospective": "<how the beat just landed, from your POV — one short line>", "branches": {"<option tag>": "<how you'd lean if the player takes that path — one short line>"}, "memory": null or {"gloss": "<the thing you will still be carrying about this months from now, first person, one line>", "quote": "<the exact words someone said, copied character-for-character from the text above, or null>", "quoteSpeaker": "<the name of whoever said that line, or null>", "salience": <0.0-1.0>, "valence": "<wound|warmth|fear|debt|shame|awe|relief>", "subjects": ["<short lowercase tag for what this was about>"]}}

Rules:
- "disposition" is mutable: it OVERRIDES your previous stance. Give it 2-3 sentences, in this order: how the moment has left you FEELING (shaken, grieving, afraid, relieved, emboldened — not a trait label), what you want now, and — if the moment shifted the ground under you — what you can no longer keep up. That last part matters most: say plainly when the joke, the swagger, the composure, or the distance you normally hold is not going to survive into the next beat. This is the one thing that carries an adapted manner forward, so a character who was just badly frightened re-enters frightened rather than snapping back to their default.
- Stay fully in character; first person; never break the fourth wall.
- Include "branches" ONLY if branch options are listed below — key each entry by its exact option tag. Otherwise return "branches": {}.
- Keep "retrospective" and every branch line clipped. No prose outside the JSON object.

About "memory" — this one OUTLASTS the scene, so it is held to a harder standard than the rest:
- Return null unless something happened here that you would still be carrying in a completely different place, weeks later. Most beats are not that. A shrug recorded as a memory crowds out a real one later.
- "quote" must be copied EXACTLY from the text above — the same words, in the same order. Do not tidy it, do not shorten it, do not write what someone meant. If no line was said that you would still hear in your head, use null. A quote you compose is worse than no quote: it will be checked against what was actually said, and a mismatch throws it away.
- "gloss" is YOUR reading of what happened, not a neutral report. You may be unfair. You may be wrong about why someone did something. Another character who was there may remember it differently, and that is allowed.
- "salience": 1.0 is something that changes who you are, 0.5 is worth bringing up again, below 0.3 will be discarded.
- "subjects": what it was ABOUT, as short lowercase tags — creatures, objects, places, dangers, the shape of the thing ("ogres", "drowning", "the north road"). This is how you find the memory again when the person involved is not in the room. Skip the names of people already in the scene; those are recorded for you."""


def reflect(
    conn: LlmConn,
    *,
    name: str,
    role: str,
    character_id: str,
    stable_prefix: str,
    transcript: str,
    branches: list[dict] | None = None,
    seq: int = 0,
    reasoning: ReasoningEffort = REFLECTION_EFFORT,
) -> InteriorRecord | None:
    """Produce one character's interior record for this beat (best-effort → ``None``)."""
    # Imported lazily so the module imports cleanly without a configured provider and so
    # worker threads share the module-level client factory.
    from app.services import llm

    base_url, api_key, model, params = conn
    branch_tags = [str(b.get("outcome") or b.get("label") or "").strip() for b in (branches or [])]
    branch_tags = [t for t in branch_tags if t]

    # Ordered transcript-first on purpose. Every present character reflects on the SAME
    # transcript at the end of a turn, so leading with it makes one shared prefix that all
    # of those calls hit; leading with "You are <name>" made every one of them a cold
    # prompt. Same reasoning as ``character_turn_agent._build_user_prompt``: whatever
    # changes earliest decides how much of the prompt can be reused.
    body = [
        f"What just happened:\n{transcript or '(scene opening)'}",
        "",
        f"You are {name} — {role}.",
    ]
    if branch_tags:
        body.append("\nThe player faces a fork. Branch options (tags): " + ", ".join(branch_tags))
        body.append("Give a branch stance for each tag.")
    body.append("\nReflect now.")
    user = "\n".join(body)

    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [
                {"role": "system", "content": f"{_SYSTEM}\n\n{stable_prefix}".strip()},
                {"role": "user", "content": user},
            ],
            gen_params(params),
            reasoning=reasoning,
        )
        data = extract_json(raw)
    except APIError:
        return None

    disposition = str(data.get("disposition", "")).strip()
    retrospective = str(data.get("retrospective", "")).strip()
    raw_branches = data.get("branches", {})
    branch_dispositions: dict[str, str] = {}
    if isinstance(raw_branches, dict) and branch_tags:
        allowed = set(branch_tags)
        for key, value in raw_branches.items():
            tag = str(key).strip()
            text = str(value).strip()
            if tag in allowed and text:
                branch_dispositions[tag] = text

    memory = _parse_memory(data.get("memory"))

    if not (disposition or retrospective or branch_dispositions or memory):
        return None  # empty reflection — keep the last interior state
    return InteriorRecord(
        character_id=character_id,
        disposition=disposition,
        retrospective=retrospective,
        branch_dispositions=branch_dispositions,
        memory=memory,
        seq=seq,
    )


def _parse_memory(raw: object) -> dict | None:
    """Normalize the optional ``memory`` object, or ``None`` when there isn't one.

    Tolerant by design: a model that returns ``"null"``, an empty object, or a salience as
    a string should cost this turn its memory, not its whole reflection. The *verification*
    of the quote does not happen here — ``services.memory_store`` checks it against prose
    the turn actually produced, because only the caller knows what that prose was.
    """
    if not isinstance(raw, dict):
        return None
    gloss = str(raw.get("gloss") or "").strip()
    if not gloss:
        return None
    try:
        salience = float(raw.get("salience", 0.0))
    except (TypeError, ValueError):
        salience = 0.0
    quote = str(raw.get("quote") or "").strip() or None
    subjects = [str(t).strip() for t in (raw.get("subjects") or []) if str(t).strip()]
    return {
        "gloss": gloss,
        "quote": quote,
        "quoteSpeaker": (str(raw.get("quoteSpeaker") or "").strip() or None) if quote else None,
        "salience": max(0.0, min(1.0, salience)),
        "valence": str(raw.get("valence") or "").strip().lower(),
        "subjects": subjects,
    }
