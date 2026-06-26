"""Options routes — the global settings surface for the ``/options`` page.

Uses the ``/options`` prefix (the Setting *entity* already owns ``/settings``).
``GET /options`` returns the global config (LLM + library defaults, key masked);
``PATCH`` endpoints update each namespace; ``POST /options/llm/{models,test}``
proxy an OpenAI-compatible endpoint server-side.
"""

from __future__ import annotations

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
    LlmModelsRequest,
    LlmModelsResponse,
    LlmTestRequest,
    LlmTestResponse,
    SettingsRead,
)
from app.services import comfyui, llm, llm_backend, settings_store
from app.services.llm_backend import InferenceBackend

router = APIRouter(prefix="/options", tags=["options"])


@router.get("", response_model=SettingsRead)
def get_options(db: Session = Depends(get_db)):
    return SettingsRead(
        llm=settings_store.get_llm(db),
        library=settings_store.get_library(db),
        comfy=settings_store.get_comfy(db),
    )


@router.patch("/llm", response_model=LlmConfigRead)
def update_llm(data: LlmConfigUpdate, db: Session = Depends(get_db)):
    return settings_store.update_llm(db, data)


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

    Read-only diagnostics: confirms whether Velora sees vLLM / llama.cpp (and is
    therefore sending the thinking budget) for the configured endpoint. Uses the
    cached detection (the background poller keeps it warm).
    """
    base_url, api_key = settings_store.resolve_llm_credentials(db, None, None)
    backend = (
        llm_backend.get_backend(base_url, api_key)
        if base_url.strip()
        else InferenceBackend.UNKNOWN
    )
    return LlmBackendResponse(
        backend=backend.value,
        budgets={effort.value: budget for effort, budget in THINKING_BUDGET.items()},
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
