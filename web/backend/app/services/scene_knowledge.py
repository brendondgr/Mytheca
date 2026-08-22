"""What the scene knows — assembled from what is already recorded.

The Inspector answers *"what did the loop do"*. This answers *"what does the scene know"*, for
a player rather than for whoever is debugging the loop. The app already computes every one of
these facts and shows none of them: which files were attached, whether retrieval fired, how far
back the cast can actually remember, which relationships reached the prompt, what the player
asked for and what of it landed.

**Read from the persisted `TurnTrace` rows, not emitted as a new frame.** Two consequences, and
both are the reason for the choice: it adds nothing to the turn's hot path, and it works on a
**resumed** scene — a panel that could only be populated by a live stream would be blank
exactly when a player returning to a long session most wants to ask what it still remembers.

Every field degrades to empty rather than absent. A session with no turns yet is a legitimate
question, and the honest answer is a set of zeroes, not a 404.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlaySession, TurnTrace
from app.schemas.play import (
    SceneKnowledgeResponse,
    SceneKnowledgeDirection,
    SceneKnowledgeRetrieval,
    SceneKnowledgeSummary,
)


def scene_knowledge(db: Session, session: PlaySession) -> SceneKnowledgeResponse:
    """Everything the scene currently knows, from the most recent turn's trace rows."""
    rows = _latest_turn(db, session.id)
    by_step: dict[str, list[TurnTrace]] = {}
    for row in rows:
        by_step.setdefault(row.step, []).append(row)

    window = _data(by_step, "window")
    assemble = _data(by_step, "assemble")
    lore = _data(by_step, "lore")
    files = _data(by_step, "files")
    context = _data(by_step, "context")

    return SceneKnowledgeResponse(
        window_beats=_int(window.get("windowBeats")),
        window_source=str(window.get("windowSource") or ""),
        dropped_beats=_int(window.get("droppedBeats")),
        budget_tokens=_int(window.get("budgetTokens")),
        # The exact figure the endpoint reported for the last character call — the only
        # non-estimated number on the panel, which is why it is carried separately.
        prompt_tokens=_int(context.get("promptTokens")) or None,
        tagged_names=[str(n) for n in (files.get("names") or []) if str(n).strip()],
        retrieval=SceneKnowledgeRetrieval(
            fired=bool(lore.get("fetched")),
            reason=str(lore.get("reason") or ""),
            matched=bool(lore.get("injected")),
        ),
        # One line per character whose ties reached a prompt this turn. `detail` is already
        # written as plain language by `beat_runner.relationship_note`, so it needs no
        # rewriting here — only attribution.
        relationships=[
            f"{_name(assemble, r.data.get('characterId'))}: {r.detail}".strip(": ")
            for r in by_step.get("relationship", [])
            if r.detail
        ],
        direction=_direction(by_step),
        summary=SceneKnowledgeSummary(
            text=(session.summary_text or "").strip(),
            through_seq=session.summary_through_seq,
            updated_at=session.summary_updated_at,
        ),
    )


def _latest_turn(db: Session, session_id: str) -> list[TurnTrace]:
    """The trace rows of the most recent turn, in order.

    Only the latest turn: "what does the scene know **now**" is a question about the state the
    next beat will be written against, and folding every turn's rows together would answer a
    different question — what it has ever known.
    """
    latest = db.scalar(
        select(TurnTrace.turn)
        .where(TurnTrace.session_id == session_id)
        .order_by(TurnTrace.turn.desc())
        .limit(1)
    )
    if latest is None:
        return []
    return list(
        db.scalars(
            select(TurnTrace)
            .where(TurnTrace.session_id == session_id, TurnTrace.turn == latest)
            .order_by(TurnTrace.n)
        )
    )


def _direction(by_step: dict[str, list[TurnTrace]]) -> SceneKnowledgeDirection:
    """What the player asked for, and what of it the turn confirmed.

    The opening `direction` row lists what was asked; the closing one (the only row carrying a
    `total`) holds the verdict. Reading both rather than accumulating every row in between
    avoids double-counting a requirement that several beats reported partial progress on.
    """
    asked: list[str] = []
    text = ""
    outstanding: list[str] = []
    for row in by_step.get("direction", []):
        data = row.data or {}
        if reqs := data.get("requirements"):
            text = row.detail or text
            asked = [str(r.get("text") if isinstance(r, dict) else r) for r in reqs]
        if "total" in data:
            outstanding = [str(t) for t in (data.get("undelivered") or [])]
    return SceneKnowledgeDirection(
        text=text,
        items=asked,
        outstanding=outstanding,
        delivered=[t for t in asked if t not in set(outstanding)],
    )


def _data(by_step: dict[str, list[TurnTrace]], step: str) -> dict:
    rows = by_step.get(step) or []
    return (rows[-1].data or {}) if rows else {}


def _name(assemble: dict, character_id: object) -> str:
    for member in assemble.get("cast") or []:
        if isinstance(member, dict) and member.get("id") == character_id:
            return str(member.get("name") or "")
    return ""


def _int(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0
