"""Settings store — read/write the global ``app_settings`` rows.

Holds all the masking + key-retention logic so the routes stay thin. The raw API
key lives only in the DB row's JSON (``_apiKey``); it is never placed on a
``*Read`` schema. Defaults seed from the process ``Settings`` so a fresh install
already points at the configured provider.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.app_setting import AppSetting
from app.schemas.settings import (
    ComfyConfigRead,
    ComfyConfigUpdate,
    ComfyParams,
    LibraryDefaultsRead,
    LibraryDefaultsUpdate,
    LlmConfigRead,
    LlmConfigUpdate,
    LlmParams,
    PromptsConfigRead,
    PromptsConfigUpdate,
    PromptSpecRead,
    ReasoningVisibility,
)

_DEFAULT_MAX_CONTEXT_TOKENS = 16384

LLM_KEY = "llm"
LIBRARY_KEY = "library"
COMFY_KEY = "comfy"
PROMPTS_KEY = "prompts"


def _get_row(db: Session, key: str) -> dict:
    row = db.get(AppSetting, key)
    return dict(row.value) if row and row.value else {}


def _set_row(db: Session, key: str, value: dict) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()


def _mask(api_key: str) -> str | None:
    """A short, non-reversible hint for a stored key (e.g. ``…sk-AB12`` → ``…AB12``)."""
    if not api_key:
        return None
    tail = api_key[-4:]
    return f"…{tail}"


# ---- LLM config ------------------------------------------------------------


#: The product default for how much of a turn's thinking the player sees. ``full`` because
#: the first reasoning token arrives at ~0.4 s against roughly ten seconds before any prose
#: (EXP-2026-08-005), so it is the largest reduction in *perceived* wait available — and
#: because a wait that shows nothing is the complaint this whole line of work started from.
#: One constant, so a stored row missing the key and a stored row holding nonsense both
#: resolve to the same place as a fresh install.
_DEFAULT_REASONING_VISIBILITY: ReasoningVisibility = "full"


def _llm_defaults() -> dict:
    s = get_settings()
    return {
        "baseUrl": s.local_llm_base_url if s.llm_provider == "local" else "",
        "model": "",
        "provider": s.llm_provider or "openai-compatible",
        "params": LlmParams().model_dump(by_alias=True),
        "_apiKey": s.openai_api_key or "",
        "authoringConcurrency": s.build_max_concurrency,
        "maxContextTokens": _DEFAULT_MAX_CONTEXT_TOKENS,
        "reasoningVisibility": _DEFAULT_REASONING_VISIBILITY,
    }


def _reasoning_visibility(value: object) -> ReasoningVisibility:
    """Coerce a stored value to a known visibility, else the product default."""
    if value in ("hidden", "summary", "full"):
        return value  # type: ignore[return-value]
    return _DEFAULT_REASONING_VISIBILITY


def _llm_doc(db: Session) -> dict:
    return {**_llm_defaults(), **_get_row(db, LLM_KEY)}


def get_llm(db: Session) -> LlmConfigRead:
    doc = _llm_doc(db)
    api_key = doc.get("_apiKey") or ""
    return LlmConfigRead(
        base_url=doc.get("baseUrl", ""),
        model=doc.get("model", ""),
        provider=doc.get("provider", "openai-compatible"),
        params=LlmParams.model_validate(doc.get("params") or {}),
        has_api_key=bool(api_key),
        api_key_hint=_mask(api_key),
        authoring_concurrency=max(1, int(doc.get("authoringConcurrency") or 1)),
        max_context_tokens=max(
            1024, int(doc.get("maxContextTokens") or _DEFAULT_MAX_CONTEXT_TOKENS)
        ),
        reasoning_visibility=_reasoning_visibility(doc.get("reasoningVisibility")),
    )


def update_llm(db: Session, data: LlmConfigUpdate) -> LlmConfigRead:
    doc = _llm_doc(db)
    if data.base_url is not None:
        # Store normalized (trailing slash trimmed) to match the proxy's view.
        doc["baseUrl"] = data.base_url.strip().rstrip("/")
    if data.model is not None:
        doc["model"] = data.model
    if data.provider is not None:
        doc["provider"] = data.provider
    if data.params is not None:
        doc["params"] = data.params.model_dump(by_alias=True)
    # api_key: None = keep; "" = clear; otherwise replace.
    if data.api_key is not None:
        doc["_apiKey"] = data.api_key
    if data.authoring_concurrency is not None:
        doc["authoringConcurrency"] = max(1, int(data.authoring_concurrency))
    if data.max_context_tokens is not None:
        doc["maxContextTokens"] = max(1024, int(data.max_context_tokens))
    if data.reasoning_visibility is not None:
        doc["reasoningVisibility"] = data.reasoning_visibility
    _set_row(db, LLM_KEY, doc)
    return get_llm(db)


def resolve_llm_credentials(
    db: Session, base_url: str | None, api_key: str | None
) -> tuple[str, str]:
    """Fall back to the stored base URL / key when a request omits them."""
    doc = _llm_doc(db)
    resolved_url = (base_url or doc.get("baseUrl") or "").strip()
    resolved_key = api_key if api_key is not None else (doc.get("_apiKey") or "")
    return resolved_url, resolved_key


# ---- ComfyUI config --------------------------------------------------------


def _comfy_defaults() -> dict:
    s = get_settings()
    return {
        "baseUrl": s.comfyui_base_url,
        "workflow": "ZiT-Workflow.json",
        "params": ComfyParams().model_dump(by_alias=True),
    }


def _comfy_doc(db: Session) -> dict:
    return {**_comfy_defaults(), **_get_row(db, COMFY_KEY)}


def get_comfy(db: Session) -> ComfyConfigRead:
    doc = _comfy_doc(db)
    return ComfyConfigRead(
        base_url=doc.get("baseUrl", ""),
        workflow=doc.get("workflow", "ZiT-Workflow.json"),
        params=ComfyParams.model_validate(doc.get("params") or {}),
    )


def update_comfy(db: Session, data: ComfyConfigUpdate) -> ComfyConfigRead:
    doc = _comfy_doc(db)
    if data.base_url is not None:
        doc["baseUrl"] = data.base_url.strip().rstrip("/")
    if data.workflow is not None:
        doc["workflow"] = data.workflow
    if data.params is not None:
        doc["params"] = data.params.model_dump(by_alias=True)
    _set_row(db, COMFY_KEY, doc)
    return get_comfy(db)


def resolve_comfy_base_url(db: Session, base_url: str | None) -> str:
    """Fall back to the stored base URL when a request omits one."""
    return (base_url or _comfy_doc(db).get("baseUrl") or "").strip()


# ---- Library defaults ------------------------------------------------------


def _library_defaults() -> dict:
    return LibraryDefaultsRead().model_dump(by_alias=True)


def get_library(db: Session) -> LibraryDefaultsRead:
    doc = {**_library_defaults(), **_get_row(db, LIBRARY_KEY)}
    return LibraryDefaultsRead.model_validate(doc)


def update_library(db: Session, data: LibraryDefaultsUpdate) -> LibraryDefaultsRead:
    doc = {**_library_defaults(), **_get_row(db, LIBRARY_KEY)}
    patch = data.model_dump(by_alias=True, exclude_unset=True)
    doc.update(patch)
    _set_row(db, LIBRARY_KEY, doc)
    return get_library(db)


# ---- Writing-prompt overrides (global defaults for the four writing agents) --


def get_prompts_overrides(db: Session) -> dict[str, str]:
    """The stored global prompt overrides ({registry key -> text}); {} when unset.

    This is the raw override map the assembler folds under the storyline/scenario
    layers via ``prompt_registry.resolve_prompts``. Only string values are kept.
    """
    row = _get_row(db, PROMPTS_KEY)
    return {str(k): str(v) for k, v in row.items() if isinstance(v, str) and v.strip()}


def get_prompts(db: Session) -> PromptsConfigRead:
    """The prompts settings payload: the **visible** registry catalog + stored global overrides.

    Visible, not all: a catalog row for a prompt nothing consumes teaches the author that
    editing prompts does nothing, which costs far more than the missing row. Stored overrides
    are returned unfiltered — a value saved for a since-hidden key must not silently vanish
    from the payload that round-trips it.
    """
    from app.agents import prompt_registry

    catalog = [
        PromptSpecRead(
            key=spec.key,
            agent=spec.agent,
            label=spec.label,
            description=spec.description,
            default=spec.default,
        )
        for spec in prompt_registry.visible_specs()
    ]
    return PromptsConfigRead(catalog=catalog, overrides=get_prompts_overrides(db))


def update_prompts(db: Session, data: PromptsConfigUpdate) -> PromptsConfigRead:
    """Apply a patch of global prompt overrides, then return the full payload."""
    set_prompts_overrides(db, data.overrides)
    return get_prompts(db)


def set_prompts_overrides(db: Session, overrides: dict[str, str]) -> dict[str, str]:
    """Merge a patch of global prompt overrides; a blank value clears that key.

    Only registry-known keys are stored (unknown keys are ignored); an empty/blank
    value deletes the override so the prompt reverts to its registry default.
    """
    from app.agents import prompt_registry

    known = set(prompt_registry.keys())
    doc = _get_row(db, PROMPTS_KEY)
    for key, value in (overrides or {}).items():
        if key not in known:
            continue
        text = str(value or "").strip()
        if text:
            doc[key] = text
        else:
            doc.pop(key, None)
    _set_row(db, PROMPTS_KEY, doc)
    return get_prompts_overrides(db)
