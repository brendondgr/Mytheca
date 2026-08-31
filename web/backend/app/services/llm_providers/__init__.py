"""The provider registry.

One place that answers "what backends does this build know about", so nothing
else has to hold that list — not the Options page, not a route, not a settings
default. A build that ships a new adapter gains it in the dropdown by appearing
here and nowhere else.

Unknown ids fall back to the OpenAI-compatible adapter rather than raising. That
is deliberate and matches how `settings_store.resolve_art_style` already treats
an unknown art style: a settings row written by a newer build, or hand-edited,
must not take the app down on the next generation. The fallback is logged.
"""

from __future__ import annotations

import logging

from app.services.llm_providers.base import (
    ChatReply,
    ChatRequest,
    ProviderAdapter,
    normalize_base,
    split_system,
)

logger = logging.getLogger(__name__)

#: The id every unknown value resolves to, and the one every existing install is
#: already on. Changing this changes what a blank settings row means.
DEFAULT_PROVIDER = "openai-compatible"

__all__ = [
    "ChatReply",
    "ChatRequest",
    "ProviderAdapter",
    "DEFAULT_PROVIDER",
    "get_adapter",
    "set_active",
    "active_provider",
    "active_adapter",
    "provider_options",
    "normalize_base",
    "split_system",
]


def _registry() -> dict[str, ProviderAdapter]:
    """Build the registry lazily.

    Imported inside the function, not at module scope, so that a syntax or
    import error in ONE adapter cannot take down the whole LLM layer — which
    would make every turn fail because of a provider nobody is using.
    """
    from app.services.llm_providers.anthropic import AnthropicAdapter
    from app.services.llm_providers.gemini import GeminiAdapter
    from app.services.llm_providers.ollama import OllamaAdapter
    from app.services.llm_providers.openai_compatible import OpenAICompatibleAdapter

    adapters: list[ProviderAdapter] = [
        OpenAICompatibleAdapter(),
        AnthropicAdapter(),
        GeminiAdapter(),
        OllamaAdapter(),
    ]
    return {a.id: a for a in adapters}


_CACHE: dict[str, ProviderAdapter] | None = None


def _adapters() -> dict[str, ProviderAdapter]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _registry()
    return _CACHE


# The active provider, as a process global.
#
# It is global because the thing it mirrors is: there is exactly ONE `llm`
# settings row, so at any moment there is exactly one active provider. The
# alternative — threading it through `LlmConn` — means changing ~25 call sites
# that destructure a four-tuple, for a value that is the same at every one of
# them.
#
# The precedent is `llm_backend`'s engine cache, which is refreshed the same way
# (`refresh_for_config`, called from app/main.py at startup). Kept in sync from
# exactly two places: startup, and `settings_store.update_llm`.
_ACTIVE: str = DEFAULT_PROVIDER


def set_active(provider: str | None) -> None:
    """Record which provider generation should use. Idempotent."""
    global _ACTIVE
    _ACTIVE = (provider or DEFAULT_PROVIDER).strip() or DEFAULT_PROVIDER


def active_provider() -> str:
    return _ACTIVE


def active_adapter() -> ProviderAdapter:
    return get_adapter(_ACTIVE)


def get_adapter(provider: str | None) -> ProviderAdapter:
    """Resolve a stored provider id to its adapter, never raising."""
    key = (provider or DEFAULT_PROVIDER).strip()
    adapters = _adapters()
    if key in adapters:
        return adapters[key]
    # `local` and `openai` were the two values the pre-adapter settings row could
    # hold; both meant "the one OpenAI-compatible endpoint".
    if key in {"local", "openai", ""}:
        return adapters[DEFAULT_PROVIDER]
    logger.warning("unknown LLM provider %r — falling back to %s", key, DEFAULT_PROVIDER)
    return adapters[DEFAULT_PROVIDER]


def provider_options() -> list[tuple[str, str, str, bool, bool]]:
    """`(id, label, default_base_url, supports_discovery, streaming_dispatched)`.

    Pure config; no I/O. The Options panel renders its provider dropdown from
    this without touching the network, which is what keeps the panel usable when
    every configured endpoint happens to be down.
    """
    out: list[tuple[str, str, str, bool, bool]] = []
    for adapter in _adapters().values():
        out.append(
            (
                adapter.id,
                adapter.label,
                getattr(adapter, "default_base_url", ""),
                getattr(adapter, "supports_discovery", True),
                # Defaults to False: a new adapter is not streamed until someone
                # has actually wired and checked it, and claiming otherwise is
                # the silent degradation this flag exists to prevent.
                getattr(adapter, "streaming_dispatched", False),
            )
        )
    return out
