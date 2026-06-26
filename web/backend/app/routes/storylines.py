"""Storyline routes — the world container."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents import build_agent, storyline_agent, triage_agent
from app.core.db import get_db
from app.core.errors import APIError
from app.schemas.build import BuildErrorEvent, BuildWorldRequest, ProposedWorld
from app.schemas.context_document import TriageRequest, TriageResponse
from app.schemas.storyline import (
    StorylineCreate,
    StorylineDraftRequest,
    StorylineDraftResponse,
    StorylineRead,
    StorylineUpdate,
    WorldPrimerRequest,
    WorldPrimerResponse,
)
from app.services import crud

router = APIRouter(prefix="/storylines", tags=["storylines"])


@router.get("", response_model=list[StorylineRead])
def list_storylines(db: Session = Depends(get_db)):
    return crud.list_storylines(db)


@router.post("", response_model=StorylineRead, status_code=201)
def create_storyline(data: StorylineCreate, db: Session = Depends(get_db)):
    return crud.create_storyline(db, data)


# ---- Authoring (the agent process) — fixed sub-paths, no id collision --------


@router.post("/draft", response_model=StorylineDraftResponse)
def draft_storyline(data: StorylineDraftRequest, db: Session = Depends(get_db)):
    """Draft library metadata from a one-sentence seed (the create form prefill)."""
    return storyline_agent.draft_storyline(db, data.seed, data.docs_overview)


@router.post("/primer", response_model=WorldPrimerResponse)
def generate_world_primer(data: WorldPrimerRequest, db: Session = Depends(get_db)):
    """Generate the agent-facing World Primer from the seed + premise."""
    primer = storyline_agent.generate_world_primer(db, data.premise, data.seed, data.docs_overview)
    return WorldPrimerResponse(world_primer=primer)


@router.post("/triage", response_model=TriageResponse)
def triage_documents(data: TriageRequest, db: Session = Depends(get_db)):
    """Classify dropped reference docs → Characters / Settings / Other · Draft/RAG."""
    return triage_agent.triage_documents(db, data.docs, data.storyline_id)


@router.post("/build", response_model=ProposedWorld)
def build_world(data: BuildWorldRequest, db: Session = Depends(get_db)):
    """Draft an entire world (metadata, primer, stats, cast, settings) for review."""
    return build_agent.build_world(
        db,
        data.seed,
        data.docs_overview,
        data.storyline_id,
        max_characters=data.max_characters,
        max_settings=data.max_settings,
    )


# NDJSON streaming headers: keep proxies (nginx) from buffering the live stream.
_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/build/stream")
def build_world_stream(data: BuildWorldRequest, db: Session = Depends(get_db)):
    """Stream the world build live as NDJSON (``application/x-ndjson``).

    One JSON object per line: ``status`` / ``meta`` / ``primer`` / ``plan`` /
    ``character`` / ``setting`` / ``done`` (or a terminal ``error``). Missing
    context or an unconfigured LLM is validated *before* the stream opens, so those
    still return a normal ``400`` envelope.
    """
    # Pre-flight (status can't change once the 200 stream has opened).
    build_agent.validate_build_inputs(db, data.seed, data.docs_overview)

    def _lines() -> Iterator[str]:
        try:
            for event in build_agent.iter_build_world(
                db,
                data.seed,
                data.docs_overview,
                data.storyline_id,
                max_characters=data.max_characters,
                max_settings=data.max_settings,
            ):
                yield event.model_dump_json(by_alias=True) + "\n"
        except APIError as exc:
            yield BuildErrorEvent(message=exc.message).model_dump_json(by_alias=True) + "\n"
        except Exception:  # never leak a stack trace into the stream
            yield BuildErrorEvent(
                message="The build failed unexpectedly."
            ).model_dump_json(by_alias=True) + "\n"

    return StreamingResponse(
        _lines(), media_type="application/x-ndjson", headers=_STREAM_HEADERS
    )


@router.get("/{storyline_id}", response_model=StorylineRead)
def get_storyline(storyline_id: str, db: Session = Depends(get_db)):
    return crud.get_storyline(db, storyline_id)


@router.patch("/{storyline_id}", response_model=StorylineRead)
def update_storyline(storyline_id: str, data: StorylineUpdate, db: Session = Depends(get_db)):
    return crud.update_storyline(db, storyline_id, data)


@router.delete("/{storyline_id}", status_code=204)
def delete_storyline(storyline_id: str, db: Session = Depends(get_db)):
    crud.delete_storyline(db, storyline_id)
