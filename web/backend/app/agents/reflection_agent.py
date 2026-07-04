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
{"disposition": "<your stance RIGHT NOW — how the moment has left you FEELING and what you want, first person, one short line>", "retrospective": "<how the beat just landed, from your POV — one short line>", "branches": {"<option tag>": "<how you'd lean if the player takes that path — one short line>"}}

Rules:
- "disposition" is mutable: it OVERRIDES your previous stance. Say how the moment has left you FEELING (e.g. shaken, grieving, afraid, relieved, emboldened) as well as what you want now — not a trait label. If the situation shifted the emotional ground under you (danger, loss, tenderness), let that show, so you re-enter the next beat genuinely changed by it rather than snapping back to your default manner.
- Stay fully in character; first person; never break the fourth wall.
- Include "branches" ONLY if branch options are listed below — key each entry by its exact option tag. Otherwise return "branches": {}.
- Keep every line clipped. No prose outside the JSON object."""


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

    head = f"You are {name} — {role}."
    body = [head, "", f"What just happened:\n{transcript or '(scene opening)'}"]
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

    if not (disposition or retrospective or branch_dispositions):
        return None  # empty reflection — keep the last interior state
    return InteriorRecord(
        character_id=character_id,
        disposition=disposition,
        retrospective=retrospective,
        branch_dispositions=branch_dispositions,
        seq=seq,
    )
