"""RAG routes — corpus (re-)embedding with live progress + status.

``POST /storylines/{id}/rag/reindex/stream`` embeds the whole world's corpus and
streams one ``embedding`` event per entry then a ``done`` summary (NDJSON, same
shape as triage/build). ``GET /storylines/{id}/rag/status`` reports reachability +
the indexed point count. Both are best-effort: with the vector store disabled the
stream yields a single ``done`` (``available=false``) and status reports unavailable.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.rag import indexer
from app.schemas.rag import RagDoneEvent, RagErrorEvent, RagProgressEvent, RagStatusResponse
from app.services import crud

router = APIRouter(tags=["rag"])

_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/storylines/{storyline_id}/rag/status", response_model=RagStatusResponse)
def rag_status(storyline_id: str, db: Session = Depends(get_db)) -> RagStatusResponse:
    crud.get_storyline(db, storyline_id)  # 404 for an unknown world
    available, indexed = indexer.storyline_status(db, storyline_id)
    return RagStatusResponse(available=available, indexed=indexed)


@router.post("/storylines/{storyline_id}/rag/reindex/stream")
def rag_reindex_stream(storyline_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    crud.get_storyline(db, storyline_id)  # 404 before the stream opens

    def _lines() -> Iterator[str]:
        try:
            for stage, data in indexer.iter_reindex_storyline(db, storyline_id):
                event = RagDoneEvent(**data) if stage == "done" else RagProgressEvent(**data)
                yield event.model_dump_json(by_alias=True) + "\n"
        except Exception:  # never leak a stack trace into the stream
            yield RagErrorEvent(message="Re-embedding failed unexpectedly.").model_dump_json(
                by_alias=True
            ) + "\n"

    return StreamingResponse(_lines(), media_type="application/x-ndjson", headers=_STREAM_HEADERS)
