"""Band-1 context assembly (read-only).

Materializes everything the per-character POV loop needs for a turn into a single
``TurnContext``: the ordered cast (each with a full clamped stat block + in-voice
anchors pulled from the recent-turn buffer), the setting, the active stat schema +
loaded guidance, the recent beats, the scenario subgraph (best-effort), and the
cacheable **stable prefix** (World Primer + stat guidance — the stable → volatile
ordering the prompt cache wants). Every read is best-effort: a missing cast id is
skipped, a disabled/down graph yields an empty subgraph, no Redis yields no beats —
the turn still runs.

Reads share the request's SQLAlchemy ``Session`` (not thread-safe), so assembly is
sequential; the parallelism the plan calls for (Director-concurrent-with-assembly,
universal reflection) lives in the later phases where each unit is an independent
LLM call with its own short-lived context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agents import _common
from app.memory import buffer, interior
from app.models import Character, Scenario, Setting
from app.models.stat import StatDefinition
from app.services import crud, graph_reader, retrieval_gate, stat_guidance, stats

logger = logging.getLogger("velora.turn")

# How many of a character's most-recent lines to keep as in-voice anchors.
_ANCHOR_LINES = 2


@dataclass
class CastMember:
    """One active character, resolved with state + voice anchors for generation."""

    id: str
    name: str
    role: str
    traits: str
    speech: str
    color: str
    stats: dict[str, int]
    recent_lines: list[str] = field(default_factory=list)
    # Read-time interior state carried in from the previous turn's reflection (§P9):
    # ``disposition`` is the character's current mutable stance, injected into the HEAD
    # of the generation prompt so it re-enters the scene already leaning where it left.
    disposition: str = ""
    # Authored voice & tone profile, pre-rendered to a compact prompt block (situation
    # → sample-response pairs). Injected into the generation HEAD so both spoken lines
    # and the hidden thinking step stay in voice. Empty string when unauthored.
    voice_samples: str = ""


@dataclass
class TurnContext:
    """The fully-assembled, read-only context a turn generates from."""

    scenario: Scenario
    session_id: str
    storyline_id: str
    directed_at: str | None
    cast: list[CastMember]
    setting: Setting | None
    stat_defs: list[StatDefinition]
    stat_guidance: dict[str, str]
    recent_beats: list[dict]
    subgraph: dict
    world_primer: str | None
    stable_prefix: str
    # Gated durable lore (a fenced RETRIEVED LORE block) — empty on a skip turn.
    retrieved_lore: str = ""
    gate_reason: str = ""
    # Open-ended steer from a selected follow-up suggestion (Scene Dialogue Updates).
    # A general direction the scene should move toward — NOT a script to reproduce.
    # Empty on an ordinary turn. Set by the turn engine from ``TurnRequest.guidance``.
    guidance: str = ""

    def cast_by_id(self, character_id: str) -> CastMember | None:
        return next((c for c in self.cast if c.id == character_id), None)


def assemble_context(
    db: Session,
    scenario: Scenario,
    session_id: str,
    directed_at: str | None = None,
    player_text: str = "",
) -> TurnContext:
    """Assemble the read-only ``TurnContext`` for one turn (best-effort throughout)."""
    storyline_id = scenario.storyline_id
    storyline = crud.get_storyline(db, storyline_id)

    stat_defs = stats.list_stat_definitions(db, storyline_id)
    guidance = {
        sd.key: text for sd in stat_defs if (text := stat_guidance.guidance_for(sd))
    }
    recent_beats = buffer.recent_turns(session_id)
    cast = _build_cast(db, scenario, session_id, stat_defs, recent_beats)
    setting = db.get(Setting, scenario.setting_id) if scenario.setting_id else None
    subgraph = _safe_subgraph(db, scenario.id)
    stable_prefix = _build_stable_prefix(storyline, stat_defs, guidance)
    retrieved_lore, gate_reason = _gated_lore(db, storyline, cast, setting, player_text)

    return TurnContext(
        scenario=scenario,
        session_id=session_id,
        storyline_id=storyline_id,
        directed_at=directed_at,
        cast=cast,
        setting=setting,
        stat_defs=stat_defs,
        stat_guidance=guidance,
        recent_beats=recent_beats,
        subgraph=subgraph,
        world_primer=storyline.world_primer,
        stable_prefix=stable_prefix,
        retrieved_lore=retrieved_lore,
        gate_reason=gate_reason,
    )


def _gated_lore(db, storyline, cast, setting, player_text) -> tuple[str, str]:
    """Run the retrieval gate; fetch + fence durable lore only when it fires (best-effort)."""
    known = [storyline.title, *(m.name for m in cast)]
    if setting is not None:
        known.append(setting.name)
    decision = retrieval_gate.gate(player_text, known_names=known)
    logger.debug("retrieval gate: fetch=%s reason=%s", decision.fetch, decision.reason)
    if not decision.fetch:
        return "", f"skip — {decision.reason}"
    # rag_block retrieves + formats a fenced reference block (best-effort → "" when the
    # store is disabled/empty); the model treats it as reference, never as dialogue.
    return _common.rag_block(db, storyline.id, decision.query), f"fetch — {decision.reason}"


def _build_cast(
    db: Session,
    scenario: Scenario,
    session_id: str,
    stat_defs: list[StatDefinition],
    recent_beats: list[dict],
) -> list[CastMember]:
    """Resolve the scenario's cast in order, skipping dangling soft-refs."""
    members: list[CastMember] = []
    for cid in scenario.cast_ids or []:
        char = db.get(Character, cid)
        if char is None:  # deleted character left a dangling cast id — skip gracefully
            continue
        values = stats.get_character_stats(db, char.id)
        # Full block: every defined stat, falling back to its default when unset.
        block = {sd.key: int(values.get(sd.key, sd.default)) for sd in stat_defs}
        # Read-time interior state from the previous turn's reflection (best-effort).
        record = interior.get_interior(session_id, char.id)
        members.append(
            CastMember(
                id=char.id,
                name=char.name,
                role=char.role,
                traits=char.traits,
                speech=char.speech,
                color=char.color,
                stats=block,
                recent_lines=_anchors_for(char.id, recent_beats),
                disposition=record.disposition if record is not None else "",
                voice_samples=_format_voice_samples(char.voice_samples),
            )
        )
    return members


def _format_voice_samples(samples: list[dict] | None) -> str:
    """Render a character's situation → single-response pairs as a compact block.

    Each pair gets a two-line bullet — the prompting situation, then the character's
    single in-voice response to it. Empty when unauthored so the generation prompt
    simply omits the section.
    """
    if not samples:
        return ""
    lines: list[str] = []
    for s in samples:
        situation = str((s or {}).get("situation", "")).strip()
        sample = str((s or {}).get("sample", "")).strip()
        if not sample:
            continue
        if situation:
            lines.append(f'- Prompt: "{situation}"\n  You: {sample}')
        else:
            lines.append(f"- You: {sample}")
    return "\n".join(lines)


def _anchors_for(character_id: str, recent_beats: list[dict]) -> list[str]:
    """The character's own most-recent lines from the buffer (in-voice anchors)."""
    lines = [
        str(b.get("text", ""))
        for b in recent_beats
        if b.get("role") == "character" and b.get("characterId") == character_id
    ]
    return [t for t in lines if t][-_ANCHOR_LINES:]


def _safe_subgraph(db: Session, scenario_id: str) -> dict:
    """Best-effort scenario subgraph; an empty, unavailable graph on any failure."""
    try:
        return graph_reader.scenario_graph(db, scenario_id)
    except Exception:  # pragma: no cover - defensive; the graph never blocks a turn
        return {"available": False, "scenarioId": scenario_id, "nodes": [], "edges": []}


def _build_stable_prefix(
    storyline,
    stat_defs: list[StatDefinition],
    guidance: dict[str, str],
) -> str:
    """The cacheable stable region: World Primer + stat guidance.

    Ordered stable → volatile so the provider's prompt cache / precomputed KV keeps
    it warm across characters and turns (the volatile per-character block is built
    per call by the character agent). Falls back to the premise when no primer.
    """
    parts: list[str] = [f"WORLD: {storyline.title} ({storyline.genre})."]
    primer = storyline.world_primer or storyline.premise
    if primer:
        parts.append(f"WORLD PRIMER\n{primer}")
    if guidance:
        guide_lines: list[str] = []
        for sd in stat_defs:
            text = guidance.get(sd.key)
            if not text:
                continue
            guide_lines.append(f"## {sd.display_name} ({sd.key}, {sd.min}–{sd.max})\n{text}")
        if guide_lines:
            parts.append("STAT GUIDANCE\n" + "\n\n".join(guide_lines))
    return "\n\n".join(parts)
