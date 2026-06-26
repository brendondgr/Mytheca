"""Shared helpers for the creation-time authoring agents (storyline, character).

Both agents resolve the configured LLM the same way, floor ``max_tokens`` for
reasoning-model headroom, fold dropped-reference-doc text into the prompt, and
tolerantly parse a JSON reply. Kept in one place so the two agents cannot drift.

No retrieval here. ``docs_overview`` is inline text read from dropped files in the
browser and passed for a single generation only — never persisted or indexed.
"""

from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.schemas.reasoning import ReasoningEffort
from app.schemas.settings import LlmParams
from app.services import crud, settings_store

# Cap on inline reference text passed to a single generation (the frontend also
# caps via DOCS_CHAR_CAP); keeps the prompt bounded without any storage.
DOCS_CAP = 32000

# Backend-set thinking budget for the authoring generations (storyline / character /
# setting drafts + the world build). The user has no UI lever for this — it is fixed
# here so reasoning models don't over-think interactive authoring. Triage overrides
# this to LOW for its quick classifications. (See app/schemas/reasoning.py.)
DEFAULT_AUTHORING_EFFORT = ReasoningEffort.MEDIUM

# Authoring produces multi-paragraph / structured output, and reasoning models
# spend a large share of the budget on hidden reasoning tokens before the visible
# reply. The Options default (512, tuned for the connection test) starves them;
# too tight a floor truncates mid-JSON. Floor generously per-call without touching
# the operator's saved setting. (See the reasoning-model budget memory.)
GEN_MIN_TOKENS = 8192


def gen_params(params: LlmParams) -> LlmParams:
    """Return params with ``max_tokens`` floored for authoring generations."""
    if params.max_tokens >= GEN_MIN_TOKENS:
        return params
    return params.model_copy(update={"max_tokens": GEN_MIN_TOKENS})


def resolve_llm(db: Session) -> tuple[str, str, str, LlmParams]:
    """Pull the configured endpoint, raw key, model, and params from settings.

    Raises a clear 400 when the operator has not configured a model, so the UI can
    point the user at Options instead of surfacing a raw upstream failure.
    """
    cfg = settings_store.get_llm(db)  # model + params in clear (key masked here)
    base_url, api_key = settings_store.resolve_llm_credentials(db, None, None)
    if not base_url:
        raise APIError(400, "bad_request", "Configure a model endpoint in Options first.")
    if not cfg.model:
        raise APIError(400, "bad_request", "Choose a model in Options first.")
    return base_url, api_key, cfg.model, cfg.params


def world_context(db: Session, storyline_id: str | None) -> str:
    """Best-effort grounding: fold the target world's primer/genre into the prompt.

    Best-effort because drafting should not hard-fail if the world cannot be
    loaded; a missing/unsaved storyline simply means an ungrounded draft. Shared by
    the character and setting authoring agents so they ground identically.
    """
    if not storyline_id:
        return ""
    try:
        sl = crud.get_storyline(db, storyline_id)
    except APIError:
        return ""
    parts = [f"World: {sl.title} ({sl.genre})."]
    if sl.world_primer:
        parts.append(f"World primer:\n{sl.world_primer}")
    elif sl.premise:
        parts.append(f"World premise:\n{sl.premise}")
    return "\n\n" + "\n\n".join(parts)


def docs_block(docs_overview: str | None) -> str:
    """Fold dropped-file reference text into a grounding block (bounded)."""
    text = (docs_overview or "").strip()
    if not text:
        return ""
    return (
        "\n\nReference notes from dropped files (for grounding only — do not quote "
        f"verbatim):\n{text[:DOCS_CAP]}"
    )


def extract_json(raw: str) -> dict:
    """Best-effort parse of a model's JSON reply (tolerant of fences/surrounds)."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise APIError(502, "upstream_error", "The model did not return valid JSON.") from exc
    if not isinstance(data, dict):
        raise APIError(502, "upstream_error", "The model did not return a JSON object.")
    return data
