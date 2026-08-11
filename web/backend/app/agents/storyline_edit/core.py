"""Shared conversation engine for the storyline editor + creator agents.

One turn: assemble the read-scoped context → build a system prompt whose output
contract lists *only* the writable fields → call the LLM (low temperature for the
editor; ``guided_json`` when the backend is vLLM) → parse ``{message, plan?}`` →
stream the assistant reply (chunked) + an optional structured plan. No writes.

The conversation is **client-session memory**: the full ``messages`` history is
sent with each request and replayed into the chat, so the agent remembers the
discussion so far. ``editor``/``creation`` differ only in persona + starting state.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.agents._common import (
    DEFAULT_AUTHORING_EFFORT,
    docs_block,
    extract_json,
    gen_params,
    rag_block,
    resolve_llm,
    world_context,
)
from app.agents.storyline_edit import scope as sc
from app.core.errors import APIError
from app.events.stream import chunk_text
from app.schemas.reasoning import ReasoningEffort
from app.schemas.storyline_edit import (
    FIELD_CATALOG,
    SPEC_BY_KEY,
    AgentMessage,
    AgentMessageFrame,
    AgentPlanFrame,
    FieldChange,
    ScopeState,
    StatChange,
    StatDefinitionDraft,
    StorylineFieldsSnapshot,
    StoryPlan,
)
from app.services import crud, llm, storyline_apply

# camelCase field key → the snapshot attribute holding its current value.
_SNAPSHOT_ATTR = {
    "title": "title",
    "genre": "genre",
    "tagline": "tagline",
    "premise": "premise",
    "worldPrimer": "world_primer",
}

_JSON_CONTRACT = (
    "Respond with ONLY a JSON object — no prose outside it, no markdown fences — with:\n"
    '- "message": your conversational reply to the author (ALWAYS required; this is what '
    "they read).\n"
    '- "plan": include this ONLY when the author asks you to change something. Put in it '
    "ONLY the writable field keys listed above — never any other field. For a text/primer "
    'field key, the value is an object {"after": "<the full new value>", "rationale": '
    '"<one short line on why>"}. For "statChanges", an array of objects '
    '{"key", "changeType" (one of add|update|remove), "after" (the FULL stat definition — '
    "key, displayName, description, min, max, default, bands — for add or update; omit for "
    'remove), "rationale"}. "bands" is a list of OBJECTS, never bare numbers: each is '
    '{"min": <int>, "max": <int>, "label": "<what that range means>", "description": '
    '"<optional, one line, may use the {Character} placeholder>"}. Send [] if you have no '
    'bands to propose. Omit "plan" entirely when you are only discussing, advising, or '
    "answering a question."
)


def validate_inputs(db: Session, messages: list[AgentMessage]) -> None:
    """Pre-flight before the stream opens: a user message + a configured LLM.

    Runs on the request thread so an unconfigured model / empty message returns a
    normal 400 envelope rather than a mid-stream error frame.
    """
    if not any(m.role == "user" and m.content.strip() for m in messages):
        raise APIError(400, "bad_request", "Send a message to the assistant first.")
    resolve_llm(db)  # 400 if the operator has not configured a model


def converse(
    db: Session,
    *,
    persona: str,
    storyline_id: str | None,
    scope: ScopeState,
    messages: list[AgentMessage],
    fields: StorylineFieldsSnapshot,
    low_temp: bool,
    docs_overview: str | None = None,
    reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
) -> Iterator[AgentMessageFrame | AgentPlanFrame]:
    """Run one conversation turn and yield the assistant reply + optional plan."""
    if not any(m.role == "user" and m.content.strip() for m in messages):
        raise APIError(400, "bad_request", "Send a message to the assistant first.")
    base_url, api_key, model, params = resolve_llm(db)

    grounding = _grounding(db, storyline_id, messages) + docs_block(docs_overview)
    system = _build_system(persona, scope, fields, grounding)
    chat: list[dict[str, str]] = [{"role": "system", "content": system}]
    for m in messages:
        chat.append({"role": m.role, "content": m.content})

    p = gen_params(params)
    if low_temp:
        p = p.model_copy(update={"temperature": min(p.temperature, 0.2)})

    text = llm.chat_complete(
        base_url,
        api_key,
        model,
        chat,
        p,
        reasoning=reasoning,
        extra_body=_guided_json(scope, base_url, api_key),
    )

    message, plan = _parse(text, scope, fields)
    for chunk in chunk_text(message):
        yield AgentMessageFrame(delta=chunk, done=False)
    yield AgentMessageFrame(delta="", done=True)
    if plan is not None and not plan.is_empty():
        # Belt: the plan is already filtered to writable keys by construction; the
        # guard re-asserts it (the load-bearing rejection lives on the apply path).
        sc.diff_guard(plan, scope)
        yield AgentPlanFrame(plan=plan, base_version=_base_version(db, storyline_id, scope))


def _base_version(db: Session, storyline_id: str | None, scope: ScopeState) -> str | None:
    """The writable-fields content hash the client echoes on apply (edit mode only)."""
    if not storyline_id:
        return None
    try:
        sl = crud.get_storyline(db, storyline_id)
        return storyline_apply.storyline_version(db, sl, sc.writable_keys(scope))
    except APIError:  # pragma: no cover - defensive; a missing world just skips reconcile
        return None


# ---- context + prompt -------------------------------------------------------


def _grounding(db: Session, storyline_id: str | None, messages: list[AgentMessage]) -> str:
    """Best-effort world grounding for edit mode (primer/genre + retrieved lore)."""
    if not storyline_id:
        return ""
    query = next((m.content for m in reversed(messages) if m.role == "user"), "")
    return world_context(db, storyline_id) + rag_block(db, storyline_id, query)


def _build_system(
    persona: str, scope: ScopeState, fields: StorylineFieldsSnapshot, grounding: str
) -> str:
    parts = [persona]

    writable = sc.writable_keys(scope)
    if writable:
        labels = ", ".join(
            f"{SPEC_BY_KEY[k].label} ({SPEC_BY_KEY[k].key})"
            for k in (spec.key for spec in FIELD_CATALOG)
            if k in writable
        )
        plan_keys = ", ".join(sorted(sc.plan_property_keys(scope)))
        parts.append(
            "You may propose changes to ONLY these fields: "
            f"{labels}. Do not change, restate, or mention edits to any other field. "
            f"In the plan, use only these keys: {plan_keys}."
        )
    else:
        parts.append(
            "No fields are in your write scope right now — you may discuss and advise, "
            "but do not propose any changes (omit the plan)."
        )

    current = _current_values(scope, fields)
    if current:
        parts.append("Current storyline (read-only context):\n" + current)
    if grounding.strip():
        parts.append(grounding.strip())

    parts.append(_JSON_CONTRACT)
    return "\n\n".join(parts)


def _current_values(scope: ScopeState, fields: StorylineFieldsSnapshot) -> str:
    readable = sc.readable_keys(scope)
    lines: list[str] = []
    for spec in FIELD_CATALOG:
        if spec.key not in readable:
            continue
        if spec.kind == "stats":
            if fields.stats:
                stat_line = "; ".join(
                    f"{s.display_name or s.key} [{s.min}-{s.max}, default {s.default}]"
                    for s in fields.stats
                )
                lines.append(f"- Statistics: {stat_line}")
            else:
                lines.append("- Statistics: (none defined yet)")
            continue
        value = str(getattr(fields, _SNAPSHOT_ATTR[spec.key], "") or "").strip()
        lines.append(f"- {spec.label}: {value or '(empty)'}")
    return "\n".join(lines)


def _guided_json(scope: ScopeState, base_url: str, api_key: str) -> dict | None:
    """Constrain output to the writable-fields schema — vLLM only, best-effort.

    On llama.cpp / OpenAI / unknown endpoints this returns ``None`` and the prompt
    contract carries the constraint (the diff guard is the guarantee either way).
    """
    try:
        from app.services import llm_backend

        if llm_backend.get_backend(base_url, api_key) is llm_backend.InferenceBackend.VLLM:
            return {"guided_json": sc.response_schema_for(scope)}
    except Exception:  # pragma: no cover - detection never blocks the turn
        return None
    return None


# ---- parse ------------------------------------------------------------------


def _parse(text: str, scope: ScopeState, fields: StorylineFieldsSnapshot) -> tuple[str, StoryPlan | None]:
    """Parse ``{message, plan?}`` — degrade to a plain message when it isn't JSON."""
    try:
        data = extract_json(text)
    except APIError:
        return text.strip(), None
    message = str(data.get("message") or "").strip() or text.strip()
    raw_plan = data.get("plan")
    plan = _plan_from_raw(raw_plan, scope, fields) if isinstance(raw_plan, dict) else None
    return message, plan


def _plan_from_raw(
    raw: dict, scope: ScopeState, fields: StorylineFieldsSnapshot
) -> StoryPlan | None:
    """Build a StoryPlan from the model's keyed plan — writable keys only (drop the rest)."""
    writable = sc.writable_keys(scope)
    changes: list[FieldChange] = []
    for spec in FIELD_CATALOG:
        if spec.kind == "stats" or spec.key not in writable:
            continue
        entry = raw.get(spec.key)
        if not isinstance(entry, dict) or entry.get("after") is None:
            continue
        before = str(getattr(fields, _SNAPSHOT_ATTR[spec.key], "") or "")
        changes.append(
            FieldChange(
                field=spec.key,
                before=before,
                after=str(entry.get("after")),
                rationale=str(entry.get("rationale") or ""),
            )
        )

    stat_changes: list[StatChange] = []
    raw_stats = _raw_stat_list(raw)
    if "statistics" in writable and raw_stats is not None:
        existing = {s.key: s for s in fields.stats}
        for item in raw_stats:
            change = _stat_change_from_raw(item, existing)
            if change is not None:
                stat_changes.append(change)

    plan = StoryPlan(changes=changes, stat_changes=stat_changes, notes=str(raw.get("notes") or ""))
    return None if plan.is_empty() else plan


def _raw_stat_list(raw: dict) -> list | None:
    """The plan's stat-change array — tolerant of the model using camel or snake case."""
    for key in (sc.STAT_CHANGES_KEY, "stat_changes"):
        value = raw.get(key)
        if isinstance(value, list):
            return value
    return None


def _merge_bands(existing: list, proposed: list) -> list:
    """Overlay each proposed band onto its existing counterpart (match by label, else
    index) so a **partial** band edit — e.g. adding a description — keeps each band's
    ``min``/``max``/``label`` instead of replacing the whole list (which would drop the
    required fields and get the entire stat change silently rejected). The proposed list
    stays authoritative for the band *set* (add/remove/reorder); each entry is enriched."""
    by_label: dict[str, dict] = {}
    for band in existing:
        if isinstance(band, dict):
            label = str(band.get("label") or "").strip().lower()
            if label:
                by_label[label] = band
    out: list = []
    for i, pband in enumerate(proposed):
        if not isinstance(pband, dict):
            continue
        base: dict | None = None
        label = str(pband.get("label") or "").strip().lower()
        if label and label in by_label:
            base = by_label[label]
        elif i < len(existing) and isinstance(existing[i], dict):
            base = existing[i]
        out.append({**(base or {}), **pband})
    return out


def _usable_bands(value: object) -> list:
    """Keep only the band entries that could possibly validate (objects).

    Models routinely emit ``"bands": [0, 3, 6, 9]`` — the *thresholds* rather than the
    labelled ``{min, max, label}`` objects the schema wants, because ``bands`` is the
    one sub-field whose shape the plan contract does not spell out. Those entries are
    unsalvageable (there is no label to invent), but they must not be allowed to sink
    the stat definition around them: see :func:`_validated_stat`.
    """
    if not isinstance(value, list):
        return []
    return [band for band in value if isinstance(band, dict)]


def _validated_stat(merged: dict) -> StatDefinitionDraft | None:
    """Validate a merged stat definition, sacrificing ``bands`` before the whole stat.

    Bands are decorative — optional, and re-addable by hand in the Stats editor. The
    key/name/range are what the author actually asked for. Rejecting the entire stat
    (and therefore, once every stat fails the same way, the entire plan) over a
    malformed band list is why a Statistics-only request could come back with a
    friendly reply and no plan at all.
    """
    try:
        return StatDefinitionDraft.model_validate(merged)
    except Exception:
        pass
    if "bands" not in merged:
        return None
    salvaged = {**merged, "bands": _usable_bands(merged["bands"])}
    try:
        return StatDefinitionDraft.model_validate(salvaged)
    except Exception:
        return None


def _stat_change_from_raw(
    item: object, existing: dict[str, StatDefinitionDraft]
) -> StatChange | None:
    if not isinstance(item, dict):
        return None
    key = str(item.get("key") or "").strip()
    if not key:
        return None
    change_type = item.get("changeType") or item.get("change_type") or "update"
    if change_type not in ("add", "update", "remove"):
        change_type = "update"

    before = existing.get(key)
    after: StatDefinitionDraft | None = None
    if change_type in ("add", "update"):
        merged: dict = {}
        if before is not None:
            merged.update(before.model_dump(by_alias=True))
        raw_after = item.get("after")
        if isinstance(raw_after, dict):
            patch = dict(raw_after)
            if isinstance(patch.get("bands"), list) and merged.get("bands"):
                patch["bands"] = _merge_bands(merged["bands"], patch["bands"])
            merged.update(patch)
        merged["key"] = key
        after = _validated_stat(merged)
        if after is None:
            return None
        if change_type == "update" and before is not None and after == before:
            return None  # no-op

    schema_altering = change_type in ("add", "remove") or _range_moved(before, after)
    try:
        return StatChange(
            key=key,
            change_type=change_type,  # type: ignore[arg-type]
            before=before,
            after=after,
            schema_altering=schema_altering,
            rationale=str(item.get("rationale") or ""),
        )
    except Exception:
        return None


def _range_moved(before: StatDefinitionDraft | None, after: StatDefinitionDraft | None) -> bool:
    if before is None or after is None:
        return False
    return (before.min, before.max, before.default) != (after.min, after.max, after.default)
