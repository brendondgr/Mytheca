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
from app.schemas.settings import (
    LibraryDefaultsRead,
    LibraryDefaultsUpdate,
    LlmConfigRead,
    LlmConfigUpdate,
    LlmModelsRequest,
    LlmModelsResponse,
    LlmTestRequest,
    LlmTestResponse,
    SettingsRead,
)
from app.services import llm, settings_store

router = APIRouter(prefix="/options", tags=["options"])


@router.get("", response_model=SettingsRead)
def get_options(db: Session = Depends(get_db)):
    return SettingsRead(llm=settings_store.get_llm(db), library=settings_store.get_library(db))


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
