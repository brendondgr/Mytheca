"""Recap agent — the scene's memory of what fell out of the window.

The transcript window fits itself to the model's context budget (``services/context_budget``),
and once a scene outgrows that window the oldest beats are dropped. Dropping them is honest —
it is what every context-limited system does — but it is also how a scene forgets that someone
already confessed, already left, already promised.

This turns the dropped beats into a **rolling summary**: tight third-person prose, plus a short
list of hard facts (names, debts, injuries, promises, places) that prose is bad at holding onto
under compression. It is incremental — each call folds the newly-dropped beats into the
previous summary rather than re-reading the whole scene — so a long session costs one cheap
call roughly every anchor block, not a growing re-summarisation every turn.

Like ``reflection_agent``, it takes a **pre-resolved connection** rather than a ``Session``: it
runs off the request's SQLAlchemy session, and coupling a summary to a live transaction would
make a slow model able to hold a turn open.

**Best-effort throughout.** A missing endpoint, an ``APIError`` or an empty reply returns
``None``, and the caller keeps the previous summary — a scene that cannot summarise is a scene
that forgets a little more, which is exactly where it was before this existed.
"""

from __future__ import annotations

from app.agents import prompt_registry
from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams

#: Summarising is a compression task, not a creative one — keep the thinking budget low.
RECAP_EFFORT = ReasoningEffort.LOW

#: The resolved LLM connection tuple, passed in so this never touches the request Session.
LlmConn = tuple[str, str, str, LlmParams]

#: Hard cap on the stored summary. A summary that grows without bound would eventually cost
#: more context than the beats it replaced, which would defeat the entire point.
MAX_SUMMARY_CHARS = 2_400


def build_prompt(previous_summary: str, beats: list[str]) -> str:
    """The user message: what is already remembered, and what has just fallen out."""
    parts: list[str] = []
    if previous_summary.strip():
        parts.append(f"What you already remember of this scene:\n{previous_summary.strip()}")
    parts.append(
        "These beats have just passed out of live memory. Fold them in:\n"
        + "\n".join(f"- {b.strip()}" for b in beats if b.strip())
    )
    parts.append("Write the updated memory now.")
    return "\n\n".join(parts)


def summarize_history(
    conn: LlmConn,
    *,
    previous_summary: str = "",
    beats: list[str],
    stable_prefix: str = "",
    system: str | None = None,
    reasoning: ReasoningEffort = RECAP_EFFORT,
) -> str | None:
    """Fold ``beats`` into ``previous_summary``. ``None`` on any failure.

    ``system`` lets the caller pass the resolved (possibly author-overridden) prompt; it falls
    back to the registry default so the agent is usable without a context.
    """
    # Imported lazily so the module imports cleanly with no provider configured, and so worker
    # threads share the module-level client factory.
    from app.services import llm

    usable = [b for b in beats if b and b.strip()]
    if not usable:
        return None
    base_url, api_key, model, params = conn
    if not base_url.strip():
        return None

    prompt = system or prompt_registry.default(prompt_registry.RECAP_SUMMARIZE)
    try:
        raw = llm.chat_complete(
            base_url,
            api_key,
            model,
            [
                {"role": "system", "content": f"{prompt}\n\n{stable_prefix}".strip()},
                {"role": "user", "content": build_prompt(previous_summary, usable)},
            ],
            _gen_params(params),
            reasoning=reasoning,
        )
    except APIError:
        return None

    text = (raw or "").strip()
    if not text:
        return None
    if len(text) > MAX_SUMMARY_CHARS:
        # Trim on a paragraph boundary where possible — a summary cut mid-sentence reads as
        # corruption to whatever model reads it next.
        cut = text.rfind("\n\n", 0, MAX_SUMMARY_CHARS)
        text = text[: cut if cut > MAX_SUMMARY_CHARS // 2 else MAX_SUMMARY_CHARS].rstrip()
    return text


def _gen_params(params: LlmParams) -> LlmParams:
    from app.agents._common import gen_params

    return gen_params(params)
