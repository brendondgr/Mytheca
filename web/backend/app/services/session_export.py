"""Render a play session's full record as JSON or Markdown for export.

The Export control in the story player downloads the *complete* diagnostic record of a
conversation so it can be reviewed and debugged after the fact: the turn-by-turn flow,
each character's private thinking, and the knowledge-graph + RAG activity captured in
the persisted diagnostic trace. Both formats are built from the same in-memory turn
grouping so they never drift.

Grouping: every turn opens with a ``user_turn`` event whose ``seq`` (``seq0`` in the
turn engine) also tags that turn's trace rows, so events fall into a turn by ``seq``
range and traces by their ``turn`` field.
"""

from __future__ import annotations

import json
from typing import Any

from app.models import Event, PlaySession, Scenario, TurnTrace

# Diagnostic steps whose *provenance* the user most wants when debugging — the graph
# writes and the RAG/lore look-up — get a friendlier heading in the Markdown render.
_STEP_LABELS = {
    "turn": "Turn",
    "intent": "Intent",
    # Both were emitted but unlabelled, so they rendered under a raw step name.
    "direction": "Scene direction",
    "files": "Tagged files",
    "reading": "Reading your message",
    "planning": "Deciding who speaks next",
    "assemble": "Scene assembly",
    "lore": "RAG / lore look-up",
    "plan": "Planner",
    "speaker": "Speaker",
    "prose": "Prose",
    "thinking": "Thinking",
    "consistency": "Consistency check",  # historical — the guard was retired
    "relationship": "Relationship context",
    "action": "Action",
    "dialogue": "Dialogue",
    "stat": "Stat change",
    "relationship_change": "Relationship change",
    "branch": "Branch",
    "relationships": "Graph (relationships)",
    "commit": "Graph (commit)",
    "reflection": "Reflection",
}


def _name(char_id: str | None, names: dict[str, str]) -> str:
    if not char_id:
        return ""
    return names.get(char_id, char_id)


def group_turns(
    events: list[Event], traces: list[TurnTrace], names: dict[str, str]
) -> list[dict[str, Any]]:
    """Fold the flat event + trace rows into ordered per-turn records."""
    user_turns = [e for e in events if e.type == "user_turn"]
    boundaries = [e.seq for e in user_turns]

    def _turn_of(seq: int) -> int:
        turn = boundaries[0] if boundaries else 0
        for b in boundaries:
            if seq >= b:
                turn = b
            else:
                break
        return turn

    traces_by_turn: dict[int, list[TurnTrace]] = {}
    for t in traces:
        traces_by_turn.setdefault(t.turn, []).append(t)

    turns: list[dict[str, Any]] = []
    for idx, ut in enumerate(user_turns):
        start = ut.seq
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else None
        beats: list[dict[str, Any]] = []
        for e in events:
            if e.type == "user_turn" or e.seq <= start:
                continue
            if end is not None and e.seq >= end:
                continue
            beats.append(
                {
                    "type": e.type,
                    "character": _name(e.data.get("characterId"), names),
                    "characterId": e.data.get("characterId"),
                    "data": e.data,
                }
            )
        trace_steps = [
            {"n": t.n, "step": t.step, "title": t.title, "detail": t.detail, "data": t.data}
            for t in traces_by_turn.get(start, [])
        ]
        turns.append(
            {
                "turn": idx + 1,
                "seq": start,
                "player": {
                    "text": str(ut.data.get("text", "")),
                    "directedAt": _name(ut.data.get("directedAt"), names),
                    # What the player asked the scene to do, beside what it did. Without it
                    # an export cannot answer the one question a reader would ask of a
                    # directed turn: did it deliver?
                    "guidance": str(ut.data.get("guidance") or ""),
                    "taggedDocIds": list(ut.data.get("taggedDocIds") or []),
                    # Scene settings this turn alone ran with. Absent on the overwhelming
                    # majority of turns, which is why it is rendered only when present: an
                    # override is spent when the turn ends, so this row is the only place a
                    # reader can find out the turn was played under different rules.
                    "overrides": dict(ut.data.get("overrides") or {}),
                },
                "beats": beats,
                "trace": trace_steps,
                # What the direction actually did on this turn, lifted out of its own trace
                # rows. Without it a reader can see the direction and the prose but not the
                # engine's own verdict on whether the two met — which is the whole question.
                "direction": _direction_of(trace_steps),
            }
        )
    return turns


def _direction_of(trace_steps: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Fold a turn's ``direction`` trace rows into asked / delivered / unconfirmed / carried.

    Reads the closing summary for the verdict (it is the one row that has seen the whole
    turn) and the opening row for what was asked, so a turn whose beats each reported
    partial progress does not have its counts double-added.
    """
    rows = [t for t in trace_steps if t["step"] == "direction"]
    out: dict[str, list[str]] = {"asked": [], "delivered": [], "unconfirmed": [], "carried": []}
    for row in rows:
        data = row.get("data") or {}
        if reqs := data.get("requirements"):
            out["asked"] = [
                str(r.get("text") if isinstance(r, dict) else r) for r in reqs
            ]
        if carried := data.get("carried"):
            out["carried"] = [
                str(c.get("text") if isinstance(c, dict) else c) for c in carried
            ]
        # The closing summary is the only row carrying a `total`; its lists are the verdict.
        if "total" in data:
            out["unconfirmed"] = [str(t) for t in (data.get("unconfirmed") or [])]
            undelivered = {str(t) for t in (data.get("undelivered") or [])}
            out["delivered"] = [t for t in out["asked"] if t not in undelivered]
    return out


def _session_meta(session: PlaySession) -> dict[str, Any]:
    return {
        "id": session.id,
        "scenarioId": session.scenario_id,
        "createdAt": session.created_at.isoformat(),
        "updatedAt": session.updated_at.isoformat(),
        "closedAt": session.closed_at.isoformat() if session.closed_at else None,
    }


def render_json(
    scenario: Scenario,
    session: PlaySession,
    events: list[Event],
    traces: list[TurnTrace],
    names: dict[str, str],
) -> str:
    """A structured JSON record — the machine-readable debugging format."""
    payload = {
        "scenario": {"id": scenario.id, "title": scenario.title},
        "session": _session_meta(session),
        "turnCount": sum(1 for e in events if e.type == "user_turn"),
        "turns": group_turns(events, traces, names),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _beat_md(beat: dict[str, Any]) -> str:
    who = beat.get("character") or "Character"
    data = beat.get("data", {})
    text = str(data.get("text", "")).strip()
    kind = beat["type"]
    if kind == "narration":
        return f"> {text}" if text else ""
    if kind == "character_prose":
        # One passage, already first-person with its speech quoted inline. Only the
        # speaker's name is added, so the export reads as prose rather than as a
        # reassembled transcript.
        return f"**{who}**\n\n{text}" if text else ""
    if kind == "internal_thought":
        return f"*{who} thinks:* {text}"
    if kind == "character_action":
        return f"*{who}* — {text}"
    if kind == "character_dialogue":
        return f"**{who}:** {text}"
    if kind == "state_update":
        stat = data.get("stat") or {}
        key = stat.get("key", "")
        value = stat.get("value")
        reason = stat.get("reason", "")
        return f"`{key} → {value}`" + (f" — {reason}" if reason else "")
    if kind == "branch_choices":
        labels = ", ".join(str(c.get("label", "")) for c in data.get("choices", []))
        return f"_Branch offered:_ {labels}"
    if kind == "scene_image":
        # A captured moment — the picture itself, linked by its served media path.
        caption = str(data.get("caption", "")).strip() or "Scene image"
        return f"![{caption}]({data.get('url', '')})"
    return text


def render_markdown(
    scenario: Scenario,
    session: PlaySession,
    events: list[Event],
    traces: list[TurnTrace],
    names: dict[str, str],
) -> str:
    """A human-readable transcript with thoughts + the graph/RAG diagnostics inlined."""
    meta = _session_meta(session)
    lines: list[str] = [
        f"# {scenario.title} — Conversation Export",
        "",
        f"Session `{meta['id']}` · created {meta['createdAt']} · updated {meta['updatedAt']}"
        + (f" · closed {meta['closedAt']}" if meta["closedAt"] else ""),
        "",
    ]
    turns = group_turns(events, traces, names)
    if not turns:
        lines.append("_No turns were played in this session._")
    for turn in turns:
        lines.append(f"## Turn {turn['turn']}")
        player = turn["player"]
        directed = f" (to {player['directedAt']})" if player["directedAt"] else ""
        if player["text"]:
            lines.append(f"**You**{directed}: {player['text']}")
        elif player.get("guidance"):
            # Directed without speaking. The direction itself is rendered just below, so the
            # label only has to say *why* there is no line — not repeat it.
            lines.append("**You**: _(direction only)_")
        else:
            # A text-less, direction-less turn: the player let the scene run.
            lines.append("**You**: _(let the scene continue)_")
        if player.get("guidance"):
            lines.append("")
            lines.append(f"_Direction:_ {player['guidance']}")
        if player.get("overrides"):
            settings = ", ".join(
                f"{key} = {value}" for key, value in sorted(player["overrides"].items())
            )
            lines.append(f"_This turn only:_ {settings}")
        direction = turn.get("direction") or {}
        if any(direction.values()):
            if direction.get("carried"):
                lines.append(
                    "_Carried over from an earlier turn:_ "
                    + "; ".join(direction["carried"])
                )
            if direction.get("delivered"):
                lines.append("_Delivered:_ " + "; ".join(direction["delivered"]))
            if direction.get("unconfirmed"):
                lines.append(
                    "_Not confirmed delivered:_ " + "; ".join(direction["unconfirmed"])
                )
        lines.append("")
        for beat in turn["beats"]:
            rendered = _beat_md(beat)
            if rendered:
                lines.append(rendered)
                lines.append("")
        if turn["trace"]:
            lines.append("### Diagnostics (graph · RAG · reasoning)")
            for step in turn["trace"]:
                label = _STEP_LABELS.get(step["step"], step["step"])
                detail = f" — {step['detail']}" if step["detail"] else ""
                lines.append(f"- **{label}:** {step['title']}{detail}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
