"""Inference-engine detection + reasoning-budget injection.

Velora supports two local engines today — **vLLM** and **llama.cpp** — and each
carries the thinking-token budget under a *different* request key. They also expose
distinct non-OpenAI probe endpoints, so the engine can be auto-detected from its
base URL:

* ``GET /version`` → returns a version object on **vLLM** (llama.cpp 404s).
* ``GET /props``   → returns server props on **llama.cpp** (vLLM 404s).

Detection results are cached per normalized base URL with a short TTL so repeated
authoring calls don't re-probe, and a background poller (see ``app.main``) refreshes
the cache periodically so the server adapts when the operator swaps engines.

Probing reuses ``llm.get_http_client`` (patched in tests to a ``MockTransport``), so
this module never hits the real network under the test suite.
"""

from __future__ import annotations

import time
from enum import Enum

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.schemas.reasoning import ReasoningEffort, budget_for
from app.services import llm, settings_store

# A short probe timeout — detection must never stall an authoring call.
_PROBE_TIMEOUT = httpx.Timeout(4.0, connect=2.0)


class InferenceBackend(str, Enum):
    """The detected local inference engine (or ``unknown`` when neither matched)."""

    VLLM = "vllm"
    LLAMACPP = "llamacpp"
    UNKNOWN = "unknown"


def _api_root(base_url: str) -> str:
    """Strip a trailing ``/v1`` (and slashes) — probes live on the server root."""
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def detect_backend(base_url: str, api_key: str = "") -> InferenceBackend:
    """Probe an OpenAI-compatible endpoint and classify its engine (no caching).

    Best-effort: any network/parse error on a probe simply means "not this engine",
    and an endpoint matching neither probe is ``UNKNOWN`` (callers then inject no
    reasoning budget, preserving today's behaviour).
    """
    root = _api_root(base_url)
    if not root:
        return InferenceBackend.UNKNOWN
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    client = llm.get_http_client()
    try:
        with client:
            # vLLM-exclusive /version.
            try:
                res = client.get(f"{root}/version", headers=headers, timeout=_PROBE_TIMEOUT)
                if res.status_code == 200 and isinstance(res.json(), dict) and "version" in res.json():
                    return InferenceBackend.VLLM
            except (httpx.HTTPError, ValueError):
                pass
            # llama.cpp-exclusive /props.
            try:
                res = client.get(f"{root}/props", headers=headers, timeout=_PROBE_TIMEOUT)
                if res.status_code == 200 and isinstance(res.json(), dict):
                    data = res.json()
                    if "total_slots" in data or "default_generation_settings" in data:
                        return InferenceBackend.LLAMACPP
            except (httpx.HTTPError, ValueError):
                pass
    except httpx.HTTPError:
        return InferenceBackend.UNKNOWN
    return InferenceBackend.UNKNOWN


# ---- TTL cache -------------------------------------------------------------

# normalized base URL -> (detected_at_monotonic, backend)
_CACHE: dict[str, tuple[float, InferenceBackend]] = {}


def _ttl_seconds() -> float:
    return float(get_settings().llm_backend_cache_ttl_seconds)


def get_backend(base_url: str, api_key: str = "", *, force: bool = False) -> InferenceBackend:
    """Return the engine for ``base_url``, using the TTL cache unless ``force``."""
    root = _api_root(base_url)
    if not root:
        return InferenceBackend.UNKNOWN
    now = time.monotonic()
    if not force:
        cached = _CACHE.get(root)
        if cached is not None and (now - cached[0]) < _ttl_seconds():
            return cached[1]
    backend = detect_backend(base_url, api_key)
    _CACHE[root] = (now, backend)
    return backend


def clear_cache() -> None:
    """Drop all cached detections (used by tests)."""
    _CACHE.clear()
    _CTX_CACHE.clear()


# ---- context-window probe --------------------------------------------------

# normalized base URL -> (probed_at_monotonic, window_tokens | None)
_CTX_CACHE: dict[str, tuple[float, int | None]] = {}


def get_context_window(base_url: str, api_key: str = "") -> int | None:
    """Probe the inference engine for its context-window size.

    Uses the already-detected backend to pick the right probe:
    * llama.cpp — ``GET {root}/props`` → ``default_generation_settings.n_ctx``,
      falling back to top-level ``n_ctx``.
    * vLLM      — ``GET {base_url}/models`` → first model's ``max_model_len``.
    * unknown   — returns ``None`` (no probe attempted).

    Results are cached per base URL with the same TTL as ``_CACHE`` and share
    the ``clear_cache`` reset seam for tests.
    """
    root = _api_root(base_url)
    if not root:
        return None
    now = time.monotonic()
    cached = _CTX_CACHE.get(root)
    if cached is not None and (now - cached[0]) < _ttl_seconds():
        return cached[1]

    backend = get_backend(base_url, api_key)
    result: int | None = None
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    client = llm.get_http_client()
    try:
        with client:
            if backend == InferenceBackend.LLAMACPP:
                try:
                    res = client.get(f"{root}/props", headers=headers, timeout=_PROBE_TIMEOUT)
                    if res.status_code == 200:
                        data = res.json()
                        gen = data.get("default_generation_settings") or {}
                        n_ctx = gen.get("n_ctx") if isinstance(gen, dict) else None
                        if n_ctx is None:
                            n_ctx = data.get("n_ctx")
                        if isinstance(n_ctx, int) and n_ctx > 0:
                            result = n_ctx
                except (httpx.HTTPError, ValueError, KeyError):
                    pass
            elif backend == InferenceBackend.VLLM:
                try:
                    res = client.get(f"{base_url}/models", headers=headers, timeout=_PROBE_TIMEOUT)
                    if res.status_code == 200:
                        data = res.json()
                        models_list = data.get("data") if isinstance(data, dict) else None
                        if isinstance(models_list, list) and models_list:
                            max_len = models_list[0].get("max_model_len")
                            if isinstance(max_len, int) and max_len > 0:
                                result = max_len
                except (httpx.HTTPError, ValueError, KeyError):
                    pass
    except httpx.HTTPError:
        pass

    _CTX_CACHE[root] = (now, result)
    return result


def refresh_for_config(db: Session) -> InferenceBackend:
    """Re-probe the *configured* endpoint and refresh its cache entry.

    Called by the background poller. Reads the stored base URL / key via the
    settings store; a blank base URL is a no-op (``UNKNOWN``).
    """
    base_url, api_key = settings_store.resolve_llm_credentials(db, None, None)
    if not base_url.strip():
        return InferenceBackend.UNKNOWN
    return get_backend(base_url, api_key, force=True)


# ---- budget injection ------------------------------------------------------


def apply_reasoning(
    body: dict, backend: InferenceBackend, effort: ReasoningEffort
) -> dict:
    """Add the engine-specific thinking-budget key to a chat-completion body.

    * vLLM → ``thinking_token_budget``
    * llama.cpp → ``thinking_budget_tokens``
    * unknown → unchanged (graceful no-op)

    Mutates and returns ``body`` for convenience.
    """
    budget = budget_for(effort)
    if backend == InferenceBackend.VLLM:
        body["thinking_token_budget"] = budget
    elif backend == InferenceBackend.LLAMACPP:
        body["thinking_budget_tokens"] = budget
    return body
