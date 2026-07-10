"""Write-scope enforcement for the storyline editor — belt-and-suspenders.

Three independent layers keep an unauthorized field from ever being written:

1. **Dynamic response schema** (:func:`response_schema_for`) — the agent's output
   schema is built at request time from the *writable* fields only, so a
   non-scoped field key is not merely discouraged, it is unrepresentable. On a
   vLLM backend this is passed as ``guided_json``; everywhere else it shapes the
   prompt (the local stack is prompt-instructed JSON, so layer 3 is load-bearing).
2. **Prompt** — the system prompt names the writable keys and says leave the rest
   untouched (redundant with 1 by design; improves plan quality).
3. **Diff guard** (:func:`diff_guard`) — after the agent returns *and* again at
   implement time, the set of fields the plan would change must be a subset of the
   approved write scope, or the whole request is rejected. This is the backstop.
"""

from __future__ import annotations

from app.core.errors import APIError
from app.schemas.storyline_edit import (
    FIELD_CATALOG,
    FIELD_KEYS,
    SPEC_BY_KEY,
    ScopeState,
    StoryPlan,
)

# The plan property key statistics changes travel under (not a raw field key).
STAT_CHANGES_KEY = "statChanges"


def writable_keys(scope: ScopeState) -> set[str]:
    """The field keys the agent is permitted to write (∩ the known catalogue)."""
    return {k for k, v in scope.items() if v.writable and k in FIELD_KEYS}


def readable_keys(scope: ScopeState) -> set[str]:
    """The field keys the agent may see as context (∩ the known catalogue)."""
    return {k for k, v in scope.items() if v.readable and k in FIELD_KEYS}


def changed_fields(plan: StoryPlan) -> set[str]:
    """The set of scoped field keys a plan would actually change."""
    changed = {c.field for c in plan.changes if c.field in FIELD_KEYS}
    if plan.stat_changes:
        changed.add("statistics")
    return changed


def diff_guard(plan: StoryPlan, scope: ScopeState) -> None:
    """Reject the whole plan if it would change any field outside the write scope.

    Raises :class:`APIError` (422 ``scope_violation``) — the load-bearing safety
    layer, run both when the agent returns and again at implement time.
    """
    changed = changed_fields(plan)
    allowed = writable_keys(scope)
    outside = changed - allowed
    if outside:
        raise APIError(
            422,
            "scope_violation",
            "The plan would change fields outside the approved write scope.",
            {"outside": sorted(outside), "writable": sorted(allowed)},
        )


def _text_change_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "after": {"type": "string"},
            "rationale": {"type": "string"},
        },
        "required": ["after"],
        "additionalProperties": False,
    }


def _stat_changes_schema() -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "changeType": {"type": "string", "enum": ["add", "update", "remove"]},
                "after": {"type": "object"},
                "schemaAltering": {"type": "boolean"},
                "rationale": {"type": "string"},
            },
            "required": ["key", "changeType"],
            "additionalProperties": True,
        },
    }


def response_schema_for(scope: ScopeState) -> dict:
    """Build the agent's JSON response schema from the writable fields *only*.

    The returned schema always has a ``message`` (the conversational reply) and an
    optional ``plan`` whose properties are exactly the writable fields — a
    non-scoped key is structurally absent. For every subset of the field set this
    omits the out-of-scope keys.
    """
    w = writable_keys(scope)
    plan_props: dict[str, dict] = {}
    for spec in FIELD_CATALOG:
        if spec.key not in w:
            continue
        if spec.kind in ("text", "primer"):
            plan_props[spec.key] = _text_change_schema()
        elif spec.kind == "stats":
            plan_props[STAT_CHANGES_KEY] = _stat_changes_schema()

    plan_schema = {
        "type": "object",
        "properties": {**plan_props, "notes": {"type": "string"}},
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "plan": plan_schema,
        },
        "required": ["message"],
        "additionalProperties": False,
    }


def plan_property_keys(scope: ScopeState) -> set[str]:
    """The writable field keys as they appear in the plan schema (stats → statChanges).

    Handy for tests and for the prompt's explicit key list.
    """
    keys: set[str] = set()
    for key in writable_keys(scope):
        spec = SPEC_BY_KEY[key]
        keys.add(STAT_CHANGES_KEY if spec.kind == "stats" else key)
    return keys
