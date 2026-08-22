"""Options routes — the global settings surface for the ``/options`` page.

Uses the ``/options`` prefix (the Setting *entity* already owns ``/settings``).
``GET /options`` returns the global config (LLM + library defaults, key masked);
``PATCH`` endpoints update each namespace; ``POST /options/llm/{models,test}``
proxy an OpenAI-compatible endpoint server-side.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.reasoning import THINKING_BUDGET
from app.schemas.settings import (
    ComfyConfigRead,
    ComfyConfigUpdate,
    ComfyStatusRequest,
    ComfyStatusResponse,
    ComfyWorkflowsResponse,
    LibraryDefaultsRead,
    LibraryDefaultsUpdate,
    LlmBackendResponse,
    LlmConfigRead,
    LlmConfigUpdate,
    LlmContextWindowResponse,
    LlmHealthResponse,
    LlmModelsRequest,
    LlmModelsResponse,
    LlmTestRequest,
    LlmTestResponse,
    MediaCleanupResponse,
    MediaDirOrphans,
    MediaOrphansResponse,
    PromptsConfigRead,
    PromptsConfigUpdate,
    SettingsRead,
)
from app.services import (
    comfyui,
    context_budget,
    llm,
    llm_backend,
    media_cleanup,
    settings_store,
)
from app.services.llm_backend import InferenceBackend

router = APIRouter(prefix="/options", tags=["options"])


@router.get("", response_model=SettingsRead)
def get_options(db: Session = Depends(get_db)):
    return SettingsRead(
        llm=settings_store.get_llm(db),
        library=settings_store.get_library(db),
        comfy=settings_store.get_comfy(db),
        prompts=settings_store.get_prompts(db),
    )


@router.patch("/llm", response_model=LlmConfigRead)
def update_llm(data: LlmConfigUpdate, db: Session = Depends(get_db)):
    return settings_store.update_llm(db, data)


@router.patch("/prompts", response_model=PromptsConfigRead)
def update_prompts(data: PromptsConfigUpdate, db: Session = Depends(get_db)):
    """Patch the global writing-agent prompt overrides (blank value clears a key)."""
    return settings_store.update_prompts(db, data)


@router.patch("/library", response_model=LibraryDefaultsRead)
def update_library(data: LibraryDefaultsUpdate, db: Session = Depends(get_db)):
    return settings_store.update_library(db, data)


@router.post("/llm/models", response_model=LlmModelsResponse)
def list_llm_models(data: LlmModelsRequest, db: Session = Depends(get_db)):
    base_url, api_key = settings_store.resolve_llm_credentials(db, data.base_url, data.api_key)
    return llm.list_models(base_url, api_key)


@router.post("/llm/test", response_model=LlmTestResponse)
def test_llm(data: LlmTestRequest, db: Session = Depends(get_db)):
    base_url, api_key = settings_store.resolve_llm_credentials(db, data.base_url, data.api_key)
    return llm.test_chat(base_url, api_key, data.model, data.params)


@router.get("/llm/backend", response_model=LlmBackendResponse)
def llm_backend_info(db: Session = Depends(get_db)):
    """Report the auto-detected inference engine + the reasoning-budget map.

    Read-only diagnostics: names the engine Mytheca sees for the configured endpoint and
    the request key(s) the thinking budget rides under. Uses the cached detection (the
    background poller keeps it warm).
    """
    base_url, api_key = settings_store.resolve_llm_credentials(db, None, None)
    backend = (
        llm_backend.get_backend(base_url, api_key)
        if base_url.strip()
        else InferenceBackend.UNKNOWN
    )
    keys = llm_backend.budget_keys_for(backend)
    return LlmBackendResponse(
        backend=backend.value,
        budgets={effort.value: budget for effort, budget in THINKING_BUDGET.items()},
        budget_keys=list(keys),
        budget_applied=bool(keys),
    )


@router.get("/llm/context-window", response_model=LlmContextWindowResponse)
def llm_context_window(db: Session = Depends(get_db)):
    """Return the effective context-window size for the configured LLM endpoint.

    Probes the engine if possible (``source="detected"``); falls back to the
    stored ``maxContextTokens`` setting when the probe is unavailable or fails
    (``source="configured"``).
    """
    # Delegated to `services/context_budget` so the number shown to the player and the number
    # the turn engine budgets against are the same value rather than two independent reads.
    window = context_budget.resolve_window(db)
    return LlmContextWindowResponse(
        max_context_tokens=window.max_tokens, source=window.source
    )


@router.get("/llm/health", response_model=LlmHealthResponse)
def llm_health(db: Session = Depends(get_db)):
    """Is the configured model endpoint actually usable right now?

    Surfaced in the scene header, where a hardcoded "Narrator active" dot used to sit. A
    player on a local model otherwise learns their endpoint died by sending a turn and waiting
    out ``LLM_GEN_TIMEOUT_SECONDS`` — five minutes to be told nothing.
    """
    cfg = settings_store.get_llm(db)
    base_url, api_key = settings_store.resolve_llm_credentials(db, None, None)
    state, detail = llm_backend.health(base_url, api_key, cfg.model)
    backend = (
        llm_backend.get_backend(base_url, api_key).value
        if state == "reachable" and base_url.strip()
        else ""
    )
    return LlmHealthResponse(
        state=state,
        backend=backend,
        model=cfg.model,
        checked_at=datetime.now(UTC),
        detail=detail,
    )


# ---- ComfyUI image generation ----------------------------------------------


@router.patch("/comfy", response_model=ComfyConfigRead)
def update_comfy(data: ComfyConfigUpdate, db: Session = Depends(get_db)):
    return settings_store.update_comfy(db, data)


@router.get("/comfy/workflows", response_model=ComfyWorkflowsResponse)
def list_comfy_workflows():
    return ComfyWorkflowsResponse(workflows=comfyui.list_workflows())


@router.post("/comfy/status", response_model=ComfyStatusResponse)
def comfy_status(data: ComfyStatusRequest, db: Session = Depends(get_db)):
    base_url = settings_store.resolve_comfy_base_url(db, data.base_url)
    stats = comfyui.check_connection(base_url)
    system = stats.get("system") if isinstance(stats, dict) else {}
    system = system if isinstance(system, dict) else {}
    devices = stats.get("devices") if isinstance(stats, dict) else None
    device = ""
    if isinstance(devices, list) and devices and isinstance(devices[0], dict):
        device = str(devices[0].get("name", ""))
    return ComfyStatusResponse(
        ok=True,
        comfyui_version=str(system.get("comfyui_version", "")),
        device=device,
        python_version=str(system.get("python_version", "")),
    )


# ---- Orphaned-media cleanup ------------------------------------------------


@router.get("/media/orphans", response_model=MediaOrphansResponse)
def scan_media_orphans(
    min_age_hours: float = 24.0,
    db: Session = Depends(get_db),
):
    """Dry-run scan: report orphaned WebP files without deleting anything.

    A file is an orphan when its basename is not referenced by any
    ``Character.portrait`` / ``Setting.image`` / ``Scenario.image`` DB column, nor
    by a persisted ``scene_image`` event's ``url``.  Only files older than
    ``min_age_hours`` are counted as *eligible* for deletion (the rest are within
    the in-flight-draft grace period).
    """
    report = media_cleanup.scan_orphans(db, min_age_hours=min_age_hours)
    return MediaOrphansResponse(
        portraits=MediaDirOrphans(
            orphan_count=report.portraits.orphan_count,
            eligible_count=report.portraits.eligible_count,
            total_bytes=report.portraits.total_bytes,
            eligible_bytes=report.portraits.eligible_bytes,
        ),
        scenes=MediaDirOrphans(
            orphan_count=report.scenes.orphan_count,
            eligible_count=report.scenes.eligible_count,
            total_bytes=report.scenes.total_bytes,
            eligible_bytes=report.scenes.eligible_bytes,
        ),
        moments=MediaDirOrphans(
            orphan_count=report.moments.orphan_count,
            eligible_count=report.moments.eligible_count,
            total_bytes=report.moments.total_bytes,
            eligible_bytes=report.moments.eligible_bytes,
        ),
        orphan_count=report.orphan_count,
        eligible_count=report.eligible_count,
        total_bytes=report.total_bytes,
        eligible_bytes=report.eligible_bytes,
        min_age_hours=report.min_age_hours,
    )


@router.post("/media/cleanup", response_model=MediaCleanupResponse)
def cleanup_media_orphans(
    min_age_hours: float = 24.0,
    db: Session = Depends(get_db),
):
    """Delete eligible orphaned WebP files.

    Only files that are both unreferenced in the DB *and* older than
    ``min_age_hours`` are deleted.  Files within the grace period are
    skipped and counted in ``skippedRecentCount``.
    """
    result = media_cleanup.delete_orphans(db, min_age_hours=min_age_hours)
    return MediaCleanupResponse(
        deleted_count=result.deleted_count,
        freed_bytes=result.freed_bytes,
        skipped_recent_count=result.skipped_recent_count,
    )
