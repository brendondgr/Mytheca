"""Settings schemas — the Options menu contract.

Two namespaces are exposed: ``llm`` (the OpenAI-compatible endpoint config) and
``library`` (non-sensitive UI defaults). The API key is **write-only**: it is
stored server-side and never returned in clear — reads expose only ``hasApiKey``
and a short masked hint.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel


class LlmParams(CamelModel):
    """Generation parameters passed through to the model endpoint."""

    temperature: float = 0.7
    max_tokens: int = 512
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0


class LlmConfigRead(CamelModel):
    base_url: str = ""
    model: str = ""
    provider: str = "openai-compatible"
    params: LlmParams = LlmParams()
    has_api_key: bool = False
    api_key_hint: str | None = None
    # How many characters/settings are drafted concurrently in the world build (and
    # how many entities are embedded concurrently during a RAG re-index). Bounded by
    # what the configured backend can serve: single-slot llama.cpp → 1, vLLM → higher.
    # Image generation is always sequential (single-GPU ComfyUI) regardless.
    authoring_concurrency: int = 3
    # Fallback context-window size used when the engine does not report one.
    max_context_tokens: int = 16384


class LlmConfigUpdate(CamelModel):
    base_url: str | None = None
    model: str | None = None
    provider: str | None = None
    params: LlmParams | None = None
    # Omitted = keep the stored key; "" = clear it; any other value = replace it.
    api_key: str | None = None
    authoring_concurrency: int | None = None
    # ge=1024: a window smaller than 1 K is not useful and likely a config error.
    max_context_tokens: int | None = None


class LibraryDefaultsRead(CamelModel):
    default_storyline_id: str | None = None
    open_last_storyline: bool = True


class LibraryDefaultsUpdate(CamelModel):
    default_storyline_id: str | None = None
    open_last_storyline: bool | None = None


# ---- ComfyUI image generation ---------------------------------------------


class ComfyParams(CamelModel):
    """Default generation parameters patched into the chosen workflow."""

    steps: int = 4
    cfg: float = 1.0
    width: int = 1024
    height: int = 1024
    batch_size: int = 1
    negative_prompt: str = ""


class ComfyConfigRead(CamelModel):
    base_url: str = ""
    workflow: str = "ZiT-Workflow.json"
    params: ComfyParams = ComfyParams()


class ComfyConfigUpdate(CamelModel):
    base_url: str | None = None
    workflow: str | None = None
    params: ComfyParams | None = None


class ComfyStatusRequest(CamelModel):
    # When omitted, the stored config's base URL is used.
    base_url: str | None = None


class ComfyStatusResponse(CamelModel):
    ok: bool
    comfyui_version: str = ""
    device: str = ""
    python_version: str = ""


class ComfyWorkflowsResponse(CamelModel):
    workflows: list[str]


# ---- Writing-agent prompts ------------------------------------------------


class PromptSpecRead(CamelModel):
    """One editable writing prompt's catalog entry (metadata + default text)."""

    key: str
    agent: str
    label: str
    description: str
    default: str


class PromptsConfigRead(CamelModel):
    """The prompts settings payload: the full catalog + the stored global overrides.

    ``catalog`` is derived from the backend prompt registry (all editable writing
    prompts, in display order); ``overrides`` maps a prompt key to the operator's
    global override text. A key absent from ``overrides`` uses its catalog default.
    """

    catalog: list[PromptSpecRead] = []
    overrides: dict[str, str] = {}


class PromptsConfigUpdate(CamelModel):
    """Patch the global prompt overrides. A blank value clears a key (reverts to default)."""

    overrides: dict[str, str] = {}


class SettingsRead(CamelModel):
    llm: LlmConfigRead
    library: LibraryDefaultsRead
    comfy: ComfyConfigRead
    prompts: PromptsConfigRead


class LlmModelsRequest(CamelModel):
    # When omitted, the stored config is used.
    base_url: str | None = None
    api_key: str | None = None


class LlmModelsResponse(CamelModel):
    models: list[str]


class LlmTestRequest(CamelModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str
    params: LlmParams | None = None


class LlmTestResponse(CamelModel):
    ok: bool
    model: str
    latency_ms: int
    sample: str


class LlmBackendResponse(CamelModel):
    """Read-only diagnostics for the detected inference engine + budget map.

    ``backend`` is ``vllm`` / ``llamacpp`` / ``relay`` / ``unknown`` — ``relay`` being an
    OpenAI-protocol front end that names its upstream engine in the models listing, and
    ``unknown`` an endpoint that matched no probe. ``budgets`` maps each reasoning effort
    to its thinking-token budget; ``budget_keys`` names the request key(s) that budget is
    actually sent under, and ``budget_applied`` says whether any is sent at all.

    The last two exist because their absence hid a real defect: an unrecognised endpoint
    used to receive no budget, so every per-operation effort was silently discarded and
    generations ran until they timed out. The operator can now see that it is capped.
    Backend-controlled: the effort itself is fixed per operation and not user-editable.
    """

    backend: str
    budgets: dict[str, int]
    budget_keys: list[str] = []
    budget_applied: bool = True


class LlmContextWindowResponse(CamelModel):
    """Context-window size for the configured LLM endpoint.

    ``source`` is ``detected`` when the engine reported the value directly,
    ``configured`` when the engine probe returned nothing and the stored fallback
    is used instead.
    """

    max_context_tokens: int
    source: Literal["detected", "configured"]


# ---- Orphaned-media cleanup -----------------------------------------------


class MediaDirOrphans(CamelModel):
    """Per-directory orphan counts for the scan report."""

    orphan_count: int
    eligible_count: int
    total_bytes: int
    eligible_bytes: int


class MediaOrphansResponse(CamelModel):
    """Response for ``GET /options/media/orphans`` (dry-run scan).

    ``portraits``, ``scenes`` and ``moments`` (in-play scene images) break down the
    counts per directory. ``orphanCount`` / ``eligibleCount`` are totals across all
    three. ``minAgeHours`` echoes the effective grace-period threshold used.
    """

    portraits: MediaDirOrphans
    scenes: MediaDirOrphans
    moments: MediaDirOrphans
    orphan_count: int
    eligible_count: int
    total_bytes: int
    eligible_bytes: int
    min_age_hours: float


class MediaCleanupResponse(CamelModel):
    """Response for ``POST /options/media/cleanup``.

    ``deletedCount`` — number of files successfully unlinked.
    ``freedBytes`` — total bytes reclaimed.
    ``skippedRecentCount`` — orphans that exist but are too new (within the
    grace period) and were therefore left untouched.
    """

    deleted_count: int
    freed_bytes: int
    skipped_recent_count: int
