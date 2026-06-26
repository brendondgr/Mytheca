"""Settings schemas — the Options menu contract.

Two namespaces are exposed: ``llm`` (the OpenAI-compatible endpoint config) and
``library`` (non-sensitive UI defaults). The API key is **write-only**: it is
stored server-side and never returned in clear — reads expose only ``hasApiKey``
and a short masked hint.
"""

from __future__ import annotations

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


class LlmConfigUpdate(CamelModel):
    base_url: str | None = None
    model: str | None = None
    provider: str | None = None
    params: LlmParams | None = None
    # Omitted = keep the stored key; "" = clear it; any other value = replace it.
    api_key: str | None = None


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


class SettingsRead(CamelModel):
    llm: LlmConfigRead
    library: LibraryDefaultsRead
    comfy: ComfyConfigRead


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

    ``backend`` is ``vllm`` / ``llamacpp`` / ``unknown`` (the last when the endpoint
    is OpenAI or unreachable — no reasoning budget is sent then). ``budgets`` maps
    each reasoning effort to its thinking-token budget. Backend-controlled: the
    effort itself is fixed per operation and not user-editable.
    """

    backend: str
    budgets: dict[str, int]


# ---- Orphaned-media cleanup -----------------------------------------------


class MediaDirOrphans(CamelModel):
    """Per-directory orphan counts for the scan report."""

    orphan_count: int
    eligible_count: int
    total_bytes: int
    eligible_bytes: int


class MediaOrphansResponse(CamelModel):
    """Response for ``GET /options/media/orphans`` (dry-run scan).

    ``portraits`` and ``scenes`` break down the counts per directory.
    ``orphanCount`` / ``eligibleCount`` are totals across both.
    ``minAgeHours`` echoes the effective grace-period threshold used.
    """

    portraits: MediaDirOrphans
    scenes: MediaDirOrphans
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
