"""Storyline routes — the world container."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import storyline_agent, triage_agent
from app.agents._common import resolve_llm
from app.agents.storyline_edit import core as storyline_edit_core
from app.agents.storyline_edit import creation as creation_agent
from app.agents.storyline_edit import editor as editor_agent
from app.core.db import get_db
from app.core.errors import APIError
from app.models import Character, Scenario, Setting
from app.schemas.context_document import TriageErrorEvent, TriageRequest, TriageResponse
from app.schemas.storyline import (
    StorylineCreate,
    StorylineDraftRequest,
    StorylineDraftResponse,
    StorylineRead,
    StorylineUpdate,
    WorldPrimerRequest,
    WorldPrimerResponse,
)
from app.events.stream import with_keepalive
from app.schemas.storyline_edit import (
    AgentErrorFrame,
    AgentStatusFrame,
    StorylineAgentRequest,
    StorylineApplyRequest,
    StorylineApplyResponse,
)
from app.schemas.world_populate import (
    PopulateErrorFrame,
    PopulateStatusFrame,
    WorldPopulateRequest,
)
from app.services import crud, storyline_apply, world_populate

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


@router.post("/triage/stream")
def triage_documents_stream(data: TriageRequest, db: Session = Depends(get_db)):
    """Stream triage live (NDJSON): one ``status`` + ``item`` per file, then ``done``.

    One LLM call per document so each row is classified in front of the author. An
    unconfigured LLM (with documents to classify) returns a normal ``400`` before
    the stream opens.
    """
    triage_agent.validate_triage_inputs(db, data.docs)

    def _lines() -> Iterator[str]:
        try:
            for event in triage_agent.iter_triage_documents(db, data.docs, data.storyline_id):
                yield event.model_dump_json(by_alias=True) + "\n"
        except APIError as exc:
            yield TriageErrorEvent(message=exc.message).model_dump_json(by_alias=True) + "\n"
        except Exception:  # never leak a stack trace into the stream
            yield TriageErrorEvent(
                message="Triage failed unexpectedly."
            ).model_dump_json(by_alias=True) + "\n"

    return StreamingResponse(
        _lines(), media_type="application/x-ndjson", headers=_STREAM_HEADERS
    )


# ---- Agentic storyline editor/creator (conversational, plan → implement) -----


def _agent_stream(events: Iterator) -> StreamingResponse:
    """Wrap an agent event generator as an NDJSON stream with a terminal error frame.

    An agent turn produces nothing until the LLM call returns, so the response would
    otherwise hold a silent socket for the whole generation. ``with_keepalive`` fills
    that gap with ``status`` frames — a frame type the client already folds to a no-op.
    """

    def _lines() -> Iterator[str]:
        try:
            for event in with_keepalive(
                events, lambda: AgentStatusFrame(message="Still thinking…")
            ):
                yield event.model_dump_json(by_alias=True) + "\n"
        except APIError as exc:
            yield AgentErrorFrame(message=exc.message).model_dump_json(by_alias=True) + "\n"
        except Exception:  # never leak a stack trace into the stream
            yield AgentErrorFrame(
                message="The assistant failed unexpectedly."
            ).model_dump_json(by_alias=True) + "\n"

    return StreamingResponse(
        _lines(), media_type="application/x-ndjson", headers=_STREAM_HEADERS
    )


@router.post("/agent/create/stream")
def storyline_agent_create_stream(data: StorylineAgentRequest, db: Session = Depends(get_db)):
    """Converse with the storyline **creation** agent (blank/partial start).

    Streams the assistant reply (chunked ``message`` frames) and, when the author asks
    for changes, a terminal ``plan`` frame — scoped to the writable fields only. No
    writes: on approval the client fills the create form and commits via Create World.
    An empty message / unconfigured LLM returns a normal 400 before the stream opens.
    """
    storyline_edit_core.validate_inputs(db, data.messages)
    return _agent_stream(
        creation_agent.storyline_creation_agent(
            db,
            scope=data.scope,
            messages=data.messages,
            fields=data.fields,
            docs_overview=data.docs_overview,
        )
    )


# NDJSON streaming headers: keep proxies (nginx) from buffering the live stream.
_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/{storyline_id}", response_model=StorylineRead)
def get_storyline(storyline_id: str, db: Session = Depends(get_db)):
    sl = crud.get_storyline(db, storyline_id)
    char_count = db.scalar(select(func.count()).where(Character.storyline_id == storyline_id)) or 0
    setting_count = db.scalar(select(func.count()).where(Setting.storyline_id == storyline_id)) or 0
    scenario_count = db.scalar(select(func.count()).where(Scenario.storyline_id == storyline_id)) or 0
    return StorylineRead(
        id=sl.id,
        title=sl.title,
        genre=sl.genre,
        tagline=sl.tagline,
        premise=sl.premise,
        world_primer=sl.world_primer,
        symbol=sl.symbol,
        symbol_color=sl.symbol_color,
        prompt_overrides=sl.prompt_overrides or {},
        character_count=char_count,
        setting_count=setting_count,
        scenario_count=scenario_count,
    )


@router.patch("/{storyline_id}", response_model=StorylineRead)
def update_storyline(storyline_id: str, data: StorylineUpdate, db: Session = Depends(get_db)):
    return crud.update_storyline(db, storyline_id, data)


@router.delete("/{storyline_id}", status_code=204)
def delete_storyline(storyline_id: str, db: Session = Depends(get_db)):
    crud.delete_storyline(db, storyline_id)


@router.post("/{storyline_id}/agent/edit/stream")
def storyline_agent_edit_stream(
    storyline_id: str, data: StorylineAgentRequest, db: Session = Depends(get_db)
):
    """Converse with the storyline **editor** agent for an existing world.

    Streams the assistant reply + an optional ``plan`` frame scoped to the writable
    fields. No writes here — approval is a separate POST to ``…/agent/apply``. A missing
    storyline (404) or unconfigured LLM (400) is validated before the stream opens.
    """
    crud.get_storyline(db, storyline_id)  # 404 pre-flight
    storyline_edit_core.validate_inputs(db, data.messages)
    return _agent_stream(
        editor_agent.storyline_editor_agent(
            db,
            storyline_id=storyline_id,
            scope=data.scope,
            messages=data.messages,
            fields=data.fields,
            docs_overview=data.docs_overview,
        )
    )


@router.post("/{storyline_id}/populate/stream")
def populate_storyline_stream(
    storyline_id: str, data: WorldPopulateRequest, db: Session = Depends(get_db)
):
    """Fill a newly-created world with a generated cast + settings (NDJSON stream).

    The create page runs this straight after committing a world, so the author lands
    in a populated Library rather than an empty one. Frames: ``status`` (per stage +
    item), ``entity`` (one per persisted character/setting), ``error`` (a non-fatal
    per-item failure — the run continues), then ``done`` with the real counts.

    Fatal cases are validated before the stream opens so they surface as a normal
    error envelope: 404 for an unknown storyline, 400 for an unconfigured LLM.
    """
    crud.get_storyline(db, storyline_id)  # 404 pre-flight
    resolve_llm(db)  # 400 when the operator has not configured a model

    events = world_populate.populate_world(
        db,
        storyline_id,
        docs_overview=data.docs_overview,
        source=data.source,
        max_characters=data.max_characters,
        max_settings=data.max_settings,
        with_artwork=data.with_artwork,
    )

    def _lines() -> Iterator[str]:
        try:
            # Drafting one entity is a whole generation; without keep-alive frames the
            # socket would sit silent for minutes between entities.
            for event in with_keepalive(
                events, lambda: PopulateStatusFrame(stage="roster", message="Still writing…")
            ):
                yield event.model_dump_json(by_alias=True) + "\n"
        except APIError as exc:
            yield PopulateErrorFrame(
                message=exc.message, fatal=True
            ).model_dump_json(by_alias=True) + "\n"
        except Exception:  # never leak a stack trace into the stream
            yield PopulateErrorFrame(
                message="Populating the world failed unexpectedly.", fatal=True
            ).model_dump_json(by_alias=True) + "\n"

    return StreamingResponse(
        _lines(), media_type="application/x-ndjson", headers=_STREAM_HEADERS
    )


@router.post("/{storyline_id}/agent/apply", response_model=StorylineApplyResponse)
def storyline_agent_apply(
    storyline_id: str, data: StorylineApplyRequest, db: Session = Depends(get_db)
):
    """Approve → implement an edit plan: diff guard, stale-read reconcile, then the
    same validated writes manual edits use — transactionally (rolls back on failure)."""
    _sl, applied = storyline_apply.apply_plan(
        db, storyline_id, data.scope, data.plan, data.base_version
    )
    return StorylineApplyResponse(storyline=get_storyline(storyline_id, db), applied=applied)
