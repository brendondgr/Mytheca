"""Settings store — read/write the global ``app_settings`` rows.

Holds all the masking + key-retention logic so the routes stay thin. The raw API
key lives only in the DB row's JSON (``_apiKey``); it is never placed on a
``*Read`` schema. Defaults seed from the process ``Settings`` so a fresh install
already points at the configured provider.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.app_setting import AppSetting
from app.content import art_styles, style_presets
from app.content.art_styles import ArtStyle
from app.schemas.settings import (
    ArtStyleRead,
    ComfyConfigRead,
    ComfyConfigUpdate,
    ComfyParams,
    LibraryDefaultsRead,
    LibraryDefaultsUpdate,
    LlmConfigRead,
    LlmConfigUpdate,
    LlmParams,
    LlmProviderOption,
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
#: The author's own saved style guides. Built-ins live in ``content/style_presets`` and are
#: never written here — this row holds only what the author saved.
STYLE_PRESETS_KEY = "style_presets"


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


# ---- Per-provider credentials ----------------------------------------------
# The llm row was a FLAT single-endpoint document: one baseUrl, one model, one
# _apiKey. Supporting several providers means holding several credentials at
# once, and there was nowhere to put them — so an operator could not even *test*
# a second endpoint without destroying the first one's settings.
#
# The row now carries a `providers` map alongside the flat fields. The flat
# fields remain the ACTIVE provider's values, so every existing reader —
# `get_llm`, `resolve_llm_credentials`, all ~25 agent call sites — keeps working
# unchanged and no migration is required. `_with_providers` seeds the map from
# the flat fields the first time a pre-existing row is read, which is what makes
# this backward compatible rather than merely additive.


def _provider_slot(doc: dict, provider: str) -> dict:
    return (doc.get("providers") or {}).get(provider) or {}


def _with_providers(doc: dict) -> dict:
    """Ensure the row has a `providers` map, seeded from the flat fields."""
    providers = dict(doc.get("providers") or {})
    active = doc.get("provider") or "openai-compatible"
    if active not in providers:
        providers[active] = {
            "baseUrl": doc.get("baseUrl", ""),
            "model": doc.get("model", ""),
            "_apiKey": doc.get("_apiKey", ""),
        }
    doc["providers"] = providers
    return doc


def _normalize_provider(doc: dict) -> dict:
    """Map a stored provider id onto one the registry actually knows.

    Existing rows hold `openai` or `local` — the two values the pre-adapter
    settings row could take, both meaning "the one OpenAI-compatible endpoint".
    Left as-is they match no adapter, so the operator's working configuration
    would show as *unconfigured* in the new picker and the dropdown would
    preselect nothing. Normalising on READ migrates every existing install with
    no migration step and no data change.
    """
    from app.services import llm_providers

    doc["provider"] = llm_providers.get_adapter(doc.get("provider")).id
    return doc


def _llm_doc(db: Session) -> dict:
    return _with_providers(_normalize_provider({**_llm_defaults(), **_get_row(db, LLM_KEY)}))


def _provider_options(doc: dict) -> list[LlmProviderOption]:
    """The provider dropdown, built from the registry rather than a literal list.

    Pure config — no network. The Options panel therefore renders its picker even
    when every configured endpoint is down, which is exactly when an operator is
    most likely to be looking at it.
    """
    from app.services import llm_providers

    slots = doc.get("providers") or {}
    out: list[LlmProviderOption] = []
    for pid, label, default_base_url, supports_discovery in llm_providers.provider_options():
        slot = slots.get(pid) or {}
        out.append(
            LlmProviderOption(
                id=pid,
                label=label,
                configured=bool(slot.get("_apiKey") or slot.get("baseUrl")),
                default_base_url=default_base_url,
                supports_discovery=supports_discovery,
            )
        )
    return out


def prime_active_provider(db: Session) -> None:
    """Load the stored provider into the process global at startup.

    Without this a fresh process generates against the DEFAULT provider until
    someone happens to save Options — so a restart would silently change which
    backend the app talks to.
    """
    from app.services import llm_providers

    llm_providers.set_active(_llm_doc(db).get("provider"))


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
        providers=_provider_options(doc),
    )


def update_llm(db: Session, data: LlmConfigUpdate) -> LlmConfigRead:
    doc = _llm_doc(db)
    if data.base_url is not None:
        # Store normalized (trailing slash trimmed) to match the proxy's view.
        doc["baseUrl"] = data.base_url.strip().rstrip("/")
    if data.model is not None:
        doc["model"] = data.model
    if data.provider is not None and data.provider != doc.get("provider"):
        # Switching provider parks the outgoing one's credentials in its slot and
        # loads the incoming one's. Without this, changing the dropdown would
        # silently carry an Anthropic key over to an Ollama endpoint — or, worse,
        # overwrite the key the operator spent a minute pasting in.
        outgoing = doc.get("provider") or "openai-compatible"
        doc.setdefault("providers", {})[outgoing] = {
            "baseUrl": doc.get("baseUrl", ""),
            "model": doc.get("model", ""),
            "_apiKey": doc.get("_apiKey", ""),
        }
        doc["provider"] = data.provider
        slot = _provider_slot(doc, data.provider)
        doc["baseUrl"] = slot.get("baseUrl", "")
        doc["model"] = slot.get("model", "")
        doc["_apiKey"] = slot.get("_apiKey", "")
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
    # Mirror the flat fields back into the active provider's slot, so the next
    # switch away and back restores what the operator last had.
    doc.setdefault("providers", {})[doc.get("provider") or "openai-compatible"] = {
        "baseUrl": doc.get("baseUrl", ""),
        "model": doc.get("model", ""),
        "_apiKey": doc.get("_apiKey", ""),
    }
    _set_row(db, LLM_KEY, doc)
    # Generation reads the active provider from a process global (see
    # llm_providers.set_active for why). Updating the row without updating that
    # is the silent failure this whole layer exists to prevent: the operator
    # picks Anthropic, the picker says Anthropic, and every turn keeps going to
    # the old endpoint in the old dialect.
    from app.services import llm_providers

    llm_providers.set_active(doc.get("provider"))
    return get_llm(db)


def resolve_llm_credentials(
    db: Session,
    base_url: str | None,
    api_key: str | None,
    provider: str | None = None,
) -> tuple[str, str]:
    """Fall back to the stored base URL / key when a request omits them.

    `provider` lets Options probe a NON-active provider — listing its models or
    running a test call — without switching to it first. Discovery that requires
    committing to a provider before you can see whether it works is not
    discovery.
    """
    doc = _llm_doc(db)
    slot = _provider_slot(doc, provider) if provider else {}
    fallback_url = slot.get("baseUrl") if provider else doc.get("baseUrl")
    fallback_key = slot.get("_apiKey") if provider else doc.get("_apiKey")
    resolved_url = (base_url or fallback_url or "").strip()
    resolved_key = api_key if api_key is not None else (fallback_key or "")
    return resolved_url, resolved_key


def configured_providers(db: Session) -> dict[str, bool]:
    """Which providers have a credential or a base URL stored.

    Powers the Options dropdown's "configured" marks. Returns booleans, never
    the values — a key never leaves this module.
    """
    doc = _llm_doc(db)
    return {
        pid: bool((slot or {}).get("_apiKey") or (slot or {}).get("baseUrl"))
        for pid, slot in (doc.get("providers") or {}).items()
    }


# ---- ComfyUI config --------------------------------------------------------


def _comfy_defaults() -> dict:
    s = get_settings()
    return {
        "baseUrl": s.comfyui_base_url,
        "workflow": "ZiT-Workflow.json",
        "params": ComfyParams().model_dump(by_alias=True),
        "artStyle": art_styles.DEFAULT_STYLE_ID,
        # Per-style LoRA overrides, keyed by style id. Empty by default: the catalog's own
        # defaults are the fallback, so a fresh install renders exactly as it always did.
        "styleLoras": {},
    }


def _comfy_doc(db: Session) -> dict:
    return {**_comfy_defaults(), **_get_row(db, COMFY_KEY)}


@dataclass(frozen=True)
class ResolvedStyle:
    """A style plus the LoRA it actually renders with, after operator overrides.

    The one answer to "what look, and with which LoRA?" — every render path asks for this
    and passes ``lora_*`` straight through to :func:`app.services.comfyui.generate`.
    """

    style: ArtStyle
    lora_name: str
    lora_strength: float
    lora_enabled: bool


def _style_lora(doc: dict, style: ArtStyle) -> ResolvedStyle:
    """Fold this style's stored override (if any) over its catalog defaults."""
    stored = (doc.get("styleLoras") or {}).get(style.id) or {}
    name = str(stored.get("loraName", style.default_lora or "") or "").strip()
    strength = stored.get("loraStrength", style.default_lora_strength)
    # Enabled defaults to "does the catalog give this style a LoRA at all" — so `anime`
    # and `photoreal` bypass the node until an operator points them at a file.
    enabled = stored.get("loraEnabled", bool(style.default_lora))
    return ResolvedStyle(
        style=style,
        lora_name=name,
        lora_strength=float(strength if strength is not None else style.default_lora_strength),
        # A style cannot be "enabled" with no file to load.
        lora_enabled=bool(enabled) and bool(name),
    )


def get_comfy(db: Session) -> ComfyConfigRead:
    doc = _comfy_doc(db)
    return ComfyConfigRead(
        base_url=doc.get("baseUrl", ""),
        workflow=doc.get("workflow", "ZiT-Workflow.json"),
        params=ComfyParams.model_validate(doc.get("params") or {}),
        art_style=art_styles.get(doc.get("artStyle")).id,
        styles=[
            ArtStyleRead(
                id=style.id,
                label=style.label,
                blurb=style.blurb,
                lora_name=resolved.lora_name,
                lora_strength=resolved.lora_strength,
                lora_enabled=resolved.lora_enabled,
            )
            for style in art_styles.catalog()
            for resolved in (_style_lora(doc, style),)
        ],
    )


def update_comfy(db: Session, data: ComfyConfigUpdate) -> ComfyConfigRead:
    doc = _comfy_doc(db)
    if data.base_url is not None:
        doc["baseUrl"] = data.base_url.strip().rstrip("/")
    if data.workflow is not None:
        doc["workflow"] = data.workflow
    if data.params is not None:
        doc["params"] = data.params.model_dump(by_alias=True)
    if data.art_style is not None:
        # Coerced, not rejected: a stale client naming a retired style falls back to the
        # default rather than failing the whole settings save.
        doc["artStyle"] = art_styles.get(data.art_style).id
    if data.styles is not None:
        known = set(art_styles.ids())
        loras = dict(doc.get("styleLoras") or {})
        for style_id, override in data.styles.items():
            if style_id not in known:
                continue
            entry = dict(loras.get(style_id) or {})
            patch = override.model_dump(by_alias=True, exclude_none=True)
            if "loraName" in patch:
                patch["loraName"] = str(patch["loraName"]).strip()
            entry.update(patch)
            loras[style_id] = entry
        doc["styleLoras"] = loras
    _set_row(db, COMFY_KEY, doc)
    return get_comfy(db)


def resolve_art_style(db: Session, style_id: str | None = None) -> ResolvedStyle:
    """The style to render in: the request's choice, else the stored global default.

    Unknown ids resolve to the default (see ``art_styles.get``) so an image request never
    fails over a style name.
    """
    doc = _comfy_doc(db)
    chosen = style_id if (style_id or "").strip() else doc.get("artStyle")
    return _style_lora(doc, art_styles.get(chosen))


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


# ---- Style presets — the author's saved narrative style guides ----------------------
#
# A **library, not a layer**: applying a preset copies its text into a storyline's own
# fields (``services.style_guide`` resolves ``storyline → scenario`` and nothing above).
# Nothing stores a preset reference, so editing a preset can never silently rewrite a world
# that already shipped with its text.


def _preset_payload(preset_id: str, name: str, blocks: dict, builtin: bool, blurb: str = "") -> dict:
    return {
        "id": preset_id,
        "name": name,
        "blurb": blurb,
        "blocks": blocks,
        "builtin": builtin,
    }


def get_saved_style_presets(db: Session) -> dict[str, dict]:
    """The author's saved presets, raw ({id -> {name, blocks}}); {} when unset."""
    row = _get_row(db, STYLE_PRESETS_KEY)
    out: dict[str, dict] = {}
    for key, value in row.items():
        if not isinstance(value, dict):
            continue
        blocks = value.get("blocks")
        if not isinstance(blocks, dict):
            continue
        out[str(key)] = {"name": str(value.get("name") or key), "blocks": blocks}
    return out


def list_style_presets(db: Session) -> list[dict]:
    """Every preset the author can apply: the three built-ins, then their own.

    Built-ins are listed first and cannot be shadowed — a saved preset that reuses a
    built-in id is skipped rather than overriding it, because an author who overwrote
    "Romance" by accident would have no way to get it back.
    """
    from app.services import style_guide

    out = [
        _preset_payload(p.id, p.name, dict(p.blocks), True, p.blurb)
        for p in style_presets.STYLE_PRESETS
    ]
    builtin_ids = {p.id for p in style_presets.STYLE_PRESETS}
    for preset_id, saved in sorted(get_saved_style_presets(db).items()):
        if preset_id in builtin_ids:
            continue
        blocks = style_guide.normalize_blocks(saved["blocks"])
        if blocks:
            out.append(_preset_payload(preset_id, saved["name"], blocks, False))
    return out


def get_style_preset_blocks(db: Session, preset_id: str | None) -> dict[str, str]:
    """One preset's blocks by id (built-in or saved), or ``{}`` for an unknown id.

    Falls back rather than raising: the drafting agent may name a preset that does not
    exist, and the right answer there is "write one instead", not a 500.
    """
    from app.services import style_guide

    builtin = style_presets.get(preset_id)
    if builtin is not None:
        return style_guide.normalize_blocks(builtin.blocks)
    saved = get_saved_style_presets(db).get((preset_id or "").strip())
    return style_guide.normalize_blocks(saved["blocks"]) if saved else {}


def save_style_preset(db: Session, preset_id: str, name: str, blocks: dict) -> list[dict]:
    """Save (or replace) one of the author's presets; returns the full list.

    A built-in id is refused silently — the caller gets the unchanged list rather than an
    error, matching how an unknown prompt-override key is ignored rather than 422'd.
    """
    from app.services import style_guide

    preset_id = (preset_id or "").strip()
    cleaned = style_guide.normalize_blocks(blocks)
    if not preset_id or style_presets.get(preset_id) is not None or not cleaned:
        return list_style_presets(db)
    doc = _get_row(db, STYLE_PRESETS_KEY)
    doc[preset_id] = {"name": (name or preset_id).strip(), "blocks": cleaned}
    _set_row(db, STYLE_PRESETS_KEY, doc)
    return list_style_presets(db)


def delete_style_preset(db: Session, preset_id: str) -> list[dict]:
    """Delete one saved preset; returns the full list. Built-ins are not deletable."""
    doc = _get_row(db, STYLE_PRESETS_KEY)
    if doc.pop((preset_id or "").strip(), None) is not None:
        _set_row(db, STYLE_PRESETS_KEY, doc)
    return list_style_presets(db)
