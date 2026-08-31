"""Settings schemas — the Options menu contract.

Two namespaces are exposed: ``llm`` (the OpenAI-compatible endpoint config) and
``library`` (non-sensitive UI defaults). The API key is **write-only**: it is
stored server-side and never returned in clear — reads expose only ``hasApiKey``
and a short masked hint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import BeatLength, CamelModel


#: How much of a turn's thinking the player sees.
#:  * ``hidden``  — no thinking at all; the muted thought line is suppressed too.
#:  * ``summary`` — the character's own ``internal_thought`` (the default, and the only
#:    behaviour that existed before): in-voice interiority, written for the reader.
#:  * ``full``    — additionally streams the model's raw reasoning channel live.
#: ``full`` is the **default**: on the deployed endpoint the first reasoning token arrives
#: at ~0.4 s against roughly ten seconds before any prose (EXP-2026-08-005), so it is the
#: single largest reduction in *perceived* wait available. The cost is real — raw
#: deliberation can spoil the line it precedes — which is why `summary` and `hidden`
#: remain one click away in Options.
ReasoningVisibility = Literal["hidden", "summary", "full"]


class LlmParams(CamelModel):
    """Generation parameters passed through to the model endpoint."""

    temperature: float = 0.7
    max_tokens: int = 512
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0


class LlmProviderOption(CamelModel):
    """One entry in the provider dropdown — pure config, no I/O to produce."""

    id: str
    label: str
    #: Whether this provider already has a base URL or an API key stored, so the
    #: picker can mark it without ever revealing either.
    configured: bool = False
    #: The base URL to prefill when the operator switches to it and has none.
    default_base_url: str = ""
    #: False for providers that cannot list their models over the wire, so the UI
    #: shows a text field rather than an empty dropdown that looks broken.
    supports_discovery: bool = True
    #: False where the turn loop cannot yet parse this provider's stream, so
    #: every turn would silently arrive as one block instead of typing out. The
    #: picker says so rather than letting an operator find out mid-scene.
    streaming_dispatched: bool = False


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
    # How much of a turn's thinking reaches the player (see ``ReasoningVisibility``).
    reasoning_visibility: ReasoningVisibility = "full"
    # Every provider the build knows about, with whether each is already set up.
    # Sent with the config so the Options panel can render its dropdown without a
    # second request — and so it never has to hardcode the list, which is the
    # thing that goes stale between releases.
    providers: list[LlmProviderOption] = []


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
    reasoning_visibility: ReasoningVisibility | None = None


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


class ArtStyleRead(CamelModel):
    """One selectable art style, as the picker and the Options tab see it.

    ``id``/``label``/``blurb`` come from the authored catalog
    (``app.content.art_styles``); the three LoRA fields are the **effective** values —
    the catalog's defaults with any operator override from the ``comfy`` settings row
    already folded in. ``loraName`` is empty when the style renders with the workflow's
    LoRA node bypassed.
    """

    id: str
    label: str
    blurb: str
    lora_name: str = ""
    lora_strength: float = 0.8
    lora_enabled: bool = False


class ArtStyleOverride(CamelModel):
    """The writable slice of a style: which LoRA it uses, how strongly, and whether at all.

    Only the LoRA is operator-editable. The prompt tags are authored content — an operator
    who wants different wording edits the writing prompts, which have their own contract.
    """

    lora_name: str | None = None
    lora_strength: float | None = None
    lora_enabled: bool | None = None


class ComfyConfigRead(CamelModel):
    base_url: str = ""
    workflow: str = "ZiT-Workflow.json"
    params: ComfyParams = ComfyParams()
    #: The default look for every image the product generates. A per-generation picker on
    #: each image surface overrides it for that render only.
    art_style: str = "painted"
    #: The full style catalog with effective LoRA settings, in display order.
    styles: list[ArtStyleRead] = []


class ComfyConfigUpdate(CamelModel):
    base_url: str | None = None
    workflow: str | None = None
    params: ComfyParams | None = None
    art_style: str | None = None
    #: Patch of per-style LoRA overrides, keyed by style id. Unknown ids are ignored
    #: rather than rejected, mirroring how prompt overrides treat unknown keys.
    styles: dict[str, ArtStyleOverride] | None = None


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


class ComfyLorasResponse(CamelModel):
    """LoRA files the configured ComfyUI server reports, for the per-style LoRA picker.

    Best-effort: an unreachable or unrecognised server yields an empty list and the
    Options field degrades to free text, exactly as the workflow picker already does.
    """

    loras: list[str] = []


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
    # Probe a provider WITHOUT switching to it first. Discovery that requires
    # committing to a provider before you can see whether it works is not
    # discovery — the operator would have to destroy a working config to try a
    # new one. Omitted = the active provider.
    provider: str | None = None


class LlmModelsResponse(CamelModel):
    """The result of a discovery attempt.

    `ok` is False for an endpoint that could not be reached, and the route still
    returns **200**. An unreachable local server is a NORMAL state, not an
    exception: someone's GPU box being off is not an error in Mytheca, and a 500
    here would make the Options page look broken instead of the endpoint.
    """

    models: list[str]
    ok: bool = True
    #: Human-readable reason when `ok` is False. Never a stack trace.
    error: str | None = None
    #: Where the list came from: "endpoint" (asked and answered), "config" (this
    #: provider cannot list, so these are declared), or "none".
    source: str = "endpoint"


class LlmTestRequest(CamelModel):
    base_url: str | None = None
    api_key: str | None = None
    provider: str | None = None
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


class LlmHealthResponse(CamelModel):
    """Whether the configured model endpoint is actually usable right now.

    Four states, not a boolean, because they are four different problems with four different
    fixes: ``reachable`` (the model is served), ``model_missing`` (the endpoint is up but does
    not serve that model — a typo in Options), ``unreachable`` (nothing answered — a dead
    process), ``unconfigured`` (nothing was ever set). An endpoint that is up while the model
    is absent produces exactly the same silence as one that is down, and the player deserves
    to be told which.

    Without this a player on a local model learns their endpoint died by sending a turn and
    waiting out ``LLM_GEN_TIMEOUT_SECONDS`` — five minutes to be told nothing.
    """

    state: Literal["reachable", "model_missing", "unreachable", "unconfigured"]
    backend: str = ""
    model: str = ""
    checked_at: datetime
    detail: str = ""


class LlmContextWindowResponse(CamelModel):
    """Context-window size for the configured LLM endpoint.

    ``source`` is ``detected`` when the engine reported the value directly,
    ``configured`` when the engine probe returned nothing and the stored fallback
    is used instead.
    """

    max_context_tokens: int
    source: Literal["detected", "configured", "fallback"]


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


class ScenePresetValues(CamelModel):
    """The play controls one preset sets. Mirrors the bounds ``ScenarioUpdate`` enforces —
    the test that every preset validates against ``ScenarioUpdate`` is what keeps the two
    honest, rather than a second copy of the numbers."""

    max_turns: int
    suggestions_count: int
    beat_length: BeatLength


class ScenePresetRead(CamelModel):
    """One entry of ``GET /options/scene-presets``.

    ``blurb`` names the **trade**, not the numbers: the numbers are visible in the controls
    directly beneath it in the popover, and repeating them in prose tells the reader only
    what they can already see.
    """

    id: str
    label: str
    blurb: str
    values: ScenePresetValues


# ---- Narrative style guide ---------------------------------------------------------


class StyleBlockRead(CamelModel):
    """One field of a style guide, for the editor to render.

    ``reader`` and ``placement`` are shown to nobody, but they are what lets the editor say
    *where* a block lands without hardcoding the answer — and they are the reason
    ``signature`` gets a "kept short" hint the other fields do not.
    """

    id: str
    label: str
    helper: str
    placeholder: str
    reader: str
    placement: str


class StylePresetRead(CamelModel):
    """One applicable preset: the three built-ins, then the author's own.

    ``builtin`` presets cannot be edited or deleted; applying either kind COPIES its blocks
    into the storyline's own fields, so nothing here is a live reference.
    """

    id: str
    name: str
    blurb: str = ""
    blocks: dict[str, str] = Field(default_factory=dict)
    builtin: bool = False


class StyleCatalogRead(CamelModel):
    """``GET /options/style-guide`` — everything the editor needs to render itself."""

    blocks: list[StyleBlockRead] = Field(default_factory=list)
    presets: list[StylePresetRead] = Field(default_factory=list)


class StylePresetSave(CamelModel):
    """``POST /options/style-presets`` — save one of the author's own guides."""

    id: str
    name: str
    blocks: dict[str, str] = Field(default_factory=dict)
