"""Inference-engine detection + reasoning-budget injection.

Mytheca supports two local engines today — **vLLM** and **llama.cpp** — and each
carries the thinking-token budget under a *different* request key. They also expose
distinct non-OpenAI probe endpoints, so the engine can be auto-detected from its
base URL:

* ``GET /version`` → returns a version object on **vLLM** (llama.cpp 404s).
* ``GET /props``   → returns server props on **llama.cpp** (vLLM 404s).
* ``GET /models``  → the OpenAI-standard listing, used as a **third** probe: a relay
  fronting one of those engines serves neither of the above (both 404) but names its
  upstream in each entry's ``owned_by`` (e.g. ``"relay:llama.cpp · local"``). That
  yields :attr:`InferenceBackend.RELAY` — an OpenAI-protocol front end whose routed
  engine can differ per model, so the budget goes out under **both** keys.

Getting this wrong is expensive rather than merely imprecise: an endpoint classified
``UNKNOWN`` used to receive **no** thinking budget at all, so every per-operation
:class:`ReasoningEffort` in the codebase was silently discarded and reasoning models ran
until they exhausted ``max_tokens`` or the generation timeout. An unrecognised engine now
degrades to *capped* (both keys, each ignored by an engine that does not know it) rather
than to *uncapped*.

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
    """The detected inference engine (or ``unknown`` when nothing matched)."""

    VLLM = "vllm"
    LLAMACPP = "llamacpp"
    #: An OpenAI-protocol relay in front of one or more engines. The routed engine can
    #: differ per model (and may be chosen dynamically), so no single budget key is
    #: correct — :func:`apply_reasoning` sends both.
    RELAY = "relay"
    UNKNOWN = "unknown"


#: ``owned_by`` substrings that name a known engine in an OpenAI models listing.
_ENGINE_MARKERS: tuple[tuple[str, InferenceBackend], ...] = (
    ("llama.cpp", InferenceBackend.LLAMACPP),
    ("llamacpp", InferenceBackend.LLAMACPP),
    ("llama_cpp", InferenceBackend.LLAMACPP),
    ("vllm", InferenceBackend.VLLM),
)


def _api_root(base_url: str) -> str:
    """Strip a trailing ``/v1`` (and slashes) — probes live on the server root."""
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def detect_backend(base_url: str, api_key: str = "") -> InferenceBackend:
    """Probe an OpenAI-compatible endpoint and classify its engine (no caching).

    Probes in order — ``/version`` (vLLM), ``/props`` (llama.cpp), then the OpenAI
    ``/models`` listing (a relay naming its upstream). Best-effort: any network/parse
    error on a probe simply means "not this engine". An endpoint matching nothing is
    ``UNKNOWN``, which still receives a capped budget (see :func:`apply_reasoning`).
    """
    root = _api_root(base_url)
    if not root:
        return InferenceBackend.UNKNOWN
    # ``/version`` and ``/props`` live on the server root; ``/models`` is part of the
    # OpenAI surface and stays under the configured base (usually ``…/v1``).
    base = (base_url or "").strip().rstrip("/")
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
            # Neither native probe answered. An OpenAI-protocol relay fronting one of
            # them serves only the standard surface, but names its upstream per model.
            try:
                res = client.get(f"{base}/models", headers=headers, timeout=_PROBE_TIMEOUT)
                if res.status_code == 200:
                    detected = _classify_models_listing(res.json())
                    if detected is not None:
                        return detected
            except (httpx.HTTPError, ValueError):
                pass
    except httpx.HTTPError:
        return InferenceBackend.UNKNOWN
    return InferenceBackend.UNKNOWN


def _classify_models_listing(payload: object) -> InferenceBackend | None:
    """Classify an OpenAI ``/models`` payload by what its entries say they run on.

    Returns ``RELAY`` when any entry declares itself relayed (the routed engine varies
    per model, so no single budget key fits), the engine when the listing names exactly
    one and never mentions a relay, and ``None`` when nothing is recognisable — which
    keeps a plain OpenAI endpoint ``UNKNOWN`` rather than mislabelling it.
    """
    if not isinstance(payload, dict):
        return None
    entries = payload.get("data")
    if not isinstance(entries, list):
        return None
    relayed = False
    engines: set[InferenceBackend] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        owner = str(entry.get("owned_by") or "").lower()
        if not owner:
            continue
        if "relay" in owner:
            relayed = True
        for marker, backend in _ENGINE_MARKERS:
            if marker in owner:
                engines.add(backend)
    if relayed:
        return InferenceBackend.RELAY
    if len(engines) == 1:
        return next(iter(engines))
    return None


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
    * vLLM / relay — ``GET {base_url}/models`` → first model's ``max_model_len``
      (a relay usually omits it, so this simply returns ``None``).
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
            elif backend in (InferenceBackend.VLLM, InferenceBackend.RELAY):
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


#: The per-engine request key carrying the thinking-token budget.
VLLM_BUDGET_KEY = "thinking_token_budget"
LLAMACPP_BUDGET_KEY = "thinking_budget_tokens"


def budget_keys_for(backend: InferenceBackend) -> tuple[str, ...]:
    """The budget key(s) :func:`apply_reasoning` would use for ``backend``.

    Exposed so the Options diagnostics can report what is actually being sent instead
    of leaving the operator to infer it.
    """
    if backend == InferenceBackend.VLLM:
        return (VLLM_BUDGET_KEY,)
    if backend == InferenceBackend.LLAMACPP:
        return (LLAMACPP_BUDGET_KEY,)
    return (VLLM_BUDGET_KEY, LLAMACPP_BUDGET_KEY)


def apply_reasoning(
    body: dict, backend: InferenceBackend, effort: ReasoningEffort
) -> dict:
    """Add the thinking-budget key(s) to a chat-completion body.

    * vLLM → ``thinking_token_budget``
    * llama.cpp → ``thinking_budget_tokens``
    * relay / unknown → **both** keys

    Sending both to an unidentified endpoint is deliberate. An engine ignores a body
    key it does not recognise, so the cost of an unnecessary key is nothing, while the
    cost of sending none is a reasoning model that never stops thinking — which is what
    the ``UNKNOWN`` no-op used to produce. Verified against the relay in use: both keys
    together are accepted, and the llama.cpp upstream honours its own.

    Mutates and returns ``body`` for convenience.
    """
    budget = budget_for(effort)
    for key in budget_keys_for(backend):
        body[key] = budget
    return body
