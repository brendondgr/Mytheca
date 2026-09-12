"""The Embergate lore layer, written straight into the Story Graph.

``core/seed.py`` seeds the world's Postgres rows — characters, settings, scenarios —
and those become ``Character`` and ``Setting`` nodes when a scene is first loaded.
That is the whole graph a fresh install has ever had: people and rooms. The registry
in ``content/graph_registry.py`` declares five other node types, and nothing in the
seed ever wrote one, so a new player's first look at the Story Graph showed the cast
standing in a room and nothing else.

This module writes the rest: the factions the cast belongs to, the secrets they keep
from each other, the events those secrets came out of, and the map of which place
adjoins which. It exists because that layer is **authored**, not play-accrued — who
runs the Drowned Market is a fact about Embergate, not something a turn discovers.

Two node types are deliberately absent. ``Subject`` is created by promotion and never
authored (see its registry entry), so seeding one would be a lie about how it got
there. ``Consequence`` is the reified record of a change that happened in play, and
nothing has happened yet.

Idempotent: every write is a MERGE, so this runs on every boot and converges. Entirely
best-effort — the Story Graph is advisory, and a fresh install with no Neo4j gets the
same world minus this layer, exactly as before.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.core import neo4j
from app.core.seed import SEED_STORYLINE_ID
from app.models import Character, Setting, Storyline
from app.services import graph_writer

logger = logging.getLogger("mytheca.graph")

# Authored structure has no play-session provenance and does not decay: it is the state
# of the world when the first scene opens, not a contribution a turn made to it.
_AUTHORED = {"weight": 1.0, "visibility": "public", "status": "active"}


def _edge(source: str, target: str, type_name: str, reason: str = "", **extra: Any) -> dict:
    meta = dict(_AUTHORED)
    if reason:
        meta["reason"] = reason
    meta.update(extra)
    return {"source": source, "target": target, "type": type_name, "metadata": meta}


# ---- factions (§5.5) --------------------------------------------------------

FACTIONS: list[dict] = [
    {
        "id": "fac-court",
        "label": "The Drowned Court",
        "name": "The Drowned Court",
        "desc": "The smuggling power that runs the salt lanes from the flooded undercroft. "
        "It does not hold office and does not need to: it holds the debt.",
    },
    {
        "id": "fac-tidewatch",
        "label": "The Tidewatch",
        "name": "The Tidewatch",
        "desc": "Harbor law, quartered in Tidewatch Keep. Undermanned, underpaid, and the "
        "last institution in Embergate that still writes things down honestly.",
    },
    {
        "id": "fac-guild",
        "label": "The Salt Guild",
        "name": "The Salt Guild",
        "desc": "The harbor guild that rules through debt rather than law. It licenses the "
        "salt trade, sets the tax, and forgives nothing.",
    },
    {
        "id": "fac-chapel",
        "label": "The Chapel of the Drowned",
        "name": "The Chapel of the Drowned",
        "desc": "A failing faith whose undercroft floods twice a day and whose older bargains "
        "are still being honoured by people who no longer remember making them.",
    },
]

# ---- secrets (§5.4) ---------------------------------------------------------
# Each character's `secret` field, promoted to a node so it can be traversed: who knows
# it, who only suspects it, and who it is about are edges, not prose. Plus the two
# world-level secrets the scenarios are actually about.

SECRETS: list[dict] = [
    {
        "id": "sec-court-patron",
        "label": "Maerin answers to the Drowned Court",
        "severity": 0.8,
        "truth_value": "true",
        "visibility": "private",
    },
    {
        "id": "sec-chapel-fire",
        "label": "Aldous set the chapel fire himself",
        "severity": 0.9,
        "truth_value": "true",
        "visibility": "private",
    },
    {
        "id": "sec-wren-sold",
        "label": "Wren has already sold you out once",
        "severity": 0.5,
        "truth_value": "true",
        "visibility": "private",
    },
    {
        "id": "sec-hale-brother",
        "label": "Hale's own brother runs the Drowned Market",
        "severity": 0.85,
        "truth_value": "true",
        "visibility": "private",
    },
    {
        "id": "sec-oracle-blind",
        "label": "Nyssa is going blind to the future, not the world",
        "severity": 0.4,
        "truth_value": "true",
        "visibility": "private",
    },
    {
        "id": "sec-grimm-water",
        "label": "Grimm is terrified of deep water",
        "severity": 0.3,
        "truth_value": "true",
        "visibility": "private",
    },
    {
        "id": "sec-drowned-ledger",
        "label": "The drowned ledger names every salt buyer in the upper town",
        "severity": 0.95,
        "truth_value": "true",
        "visibility": "private",
    },
    {
        "id": "sec-salt-tax",
        "label": "The salt-tax returns are forged at the customs house",
        "severity": 0.7,
        "truth_value": "true",
        "visibility": "private",
    },
    {
        "id": "sec-tithe-drowning",
        "label": "The chapel's winter tithe is paid in people",
        "severity": 1.0,
        "truth_value": "unknown",
        "visibility": "private",
    },
]

# ---- events (§5.3) ----------------------------------------------------------
# The convergence points: the handful of things that already happened and that every
# scene in Embergate is downstream of.

EVENTS: list[dict] = [
    {
        "id": "ev-chapel-fire",
        "label": "The Chapel Fire",
        "summary": "Fire took the chapel's upper nave two winters ago. Eleven died in the "
        "undercroft because the tide had already sealed the stair.",
        "kind": "disaster",
        "visibility": "public",
    },
    {
        "id": "ev-ledger-lost",
        "label": "The Ledger Goes Under",
        "summary": "The harbor's master ledger went into the water the night of the fire. "
        "Everyone agrees it was an accident and nobody believes it.",
        "kind": "theft",
        "visibility": "public",
    },
    {
        "id": "ev-tidewatch-raid",
        "label": "The Failed Raid on the Drowned Market",
        "summary": "Hale took twelve watchmen below the tideline and found empty vaults and "
        "a warm brazier. Someone had been told the hour.",
        "kind": "betrayal",
        "visibility": "public",
    },
    {
        "id": "ev-salt-writ",
        "label": "The Salt Writ",
        "summary": "The Guild bought the right to set the salt-tax outright. Law in Embergate "
        "has been a line of credit ever since.",
        "kind": "bargain",
        "visibility": "public",
    },
    {
        "id": "ev-oracle-vision",
        "label": "The Oracle's Third Vision",
        "summary": "Nyssa read the basin and stopped mid-sentence. She has not said aloud "
        "what she saw, and she has not been wrong yet.",
        "kind": "omen",
        "visibility": "public",
    },
]

# ---- the edges -------------------------------------------------------------
# Authored in the order a reader would want to check them: who belongs where, who holds
# what, how the places connect, what happened, who knows what, and how the cast feels.

EDGES: list[dict] = [
    # Membership (§5.5).
    _edge("maerin", "fac-guild", "member_of", "Fronts the Guild's salt trade in public."),
    _edge("maerin", "fac-court", "member_of", "And answers to the Court in private."),
    _edge("aldous", "fac-chapel", "member_of", "Ordained, and has not resigned."),
    _edge("nyssa", "fac-chapel", "member_of", "The chapel keeps her, and fears her."),
    _edge("doran", "fac-tidewatch", "member_of", "Captain of the harbor watch."),
    _edge("grimm", "fac-court", "member_of", "Paid by the job, not the season."),
    # Standing between the powers.
    _edge("fac-court", "fac-tidewatch", "at_war_with", "The lanes against the law."),
    _edge("fac-guild", "fac-court", "allied_with", "Quietly, and only while the tax holds."),
    _edge("fac-chapel", "fac-court", "allied_with", "An older bargain than either remembers."),
    # Who holds which ground (§4.3).
    _edge("fac-court", "market", "controls", "The vault rows answer to the Court."),
    _edge("fac-tidewatch", "keep", "controls", "Quartered there since the writ."),
    _edge("fac-tidewatch", "customs", "claims", "On paper. The clerks are Guild men."),
    _edge("fac-guild", "customs", "controls", "Where the returns are written."),
    _edge("fac-guild", "harbor", "claims", "Every mooring, by licence."),
    _edge("fac-chapel", "sanctum", "controls", "The salt-circles are chapel ground."),
    _edge("fac-chapel", "chapel", "controls", "What is left of it."),
    _edge("maerin", "saltworn", "claims", "The back snug is hers on any night she wants it."),
    # The map (§4.3) — what adjoins what, which is how a scene knows where it can go.
    _edge("saltworn", "harbor", "connected_to", "The warped side door onto the quay."),
    _edge("harbor", "keep", "connected_to", "The sea wall walk, in sight of the gate."),
    _edge("harbor", "customs", "connected_to", "The customs house heads the quay."),
    _edge("harbor", "market", "connected_to", "Down the drowned stair, at low tide only."),
    _edge("customs", "keep", "connected_to", "The bonded road, gated at both ends."),
    _edge("market", "chapel", "connected_to", "The undercroft and the vaults share a wall."),
    _edge("chapel", "sanctum", "connected_to", "Behind the burnt nave, still dry."),
    # Origins (§4.3).
    _edge("maerin", "keep", "from", "Raised in the upper town's counting-houses."),
    _edge("aldous", "chapel", "from", "He has never lived anywhere else."),
    _edge("wren", "harbor", "from", "Dock-born, dock-raised."),
    _edge("doran", "keep", "from", "Third generation in the Watch."),
    _edge("nyssa", "sanctum", "from", "Nobody remembers her arriving."),
    _edge("grimm", "market", "from", "Wherever the work is, below the line."),
    # What happened, and where (§4.4).
    _edge("ev-chapel-fire", "chapel", "occurred_at"),
    _edge("ev-ledger-lost", "harbor", "occurred_at"),
    _edge("ev-tidewatch-raid", "market", "occurred_at"),
    _edge("ev-salt-writ", "customs", "occurred_at"),
    _edge("ev-oracle-vision", "sanctum", "occurred_at"),
    _edge("ev-chapel-fire", "aldous", "involved", "He was the one who found the stair sealed."),
    _edge("ev-chapel-fire", "nyssa", "involved", "She had warned the chapel that week."),
    _edge("ev-ledger-lost", "maerin", "involved", "She signed the last page anyone has read."),
    _edge("ev-ledger-lost", "wren", "involved", "She was on the quay and says she saw nothing."),
    _edge("ev-tidewatch-raid", "doran", "involved", "He led it."),
    _edge("ev-tidewatch-raid", "grimm", "involved", "He was paid to be elsewhere that night."),
    _edge("ev-salt-writ", "maerin", "involved", "She drafted the terms."),
    _edge("ev-oracle-vision", "nyssa", "involved", "And has said nothing since."),
    # What each secret is about (§5.4).
    _edge("sec-court-patron", "maerin", "subject"),
    _edge("sec-chapel-fire", "aldous", "subject"),
    _edge("sec-wren-sold", "wren", "subject"),
    _edge("sec-hale-brother", "doran", "subject"),
    _edge("sec-oracle-blind", "nyssa", "subject"),
    _edge("sec-grimm-water", "grimm", "subject"),
    # Who knows what — the layer that makes a scene play differently depending on who is
    # in the room. `knows` is certainty; `suspects` is the far more useful state.
    _edge("maerin", "sec-court-patron", "knows", "It is her own arrangement."),
    _edge("maerin", "sec-drowned-ledger", "knows", "She knows because she wrote in it."),
    _edge("maerin", "sec-salt-tax", "knows", "She has seen both sets of returns."),
    _edge("maerin", "sec-wren-sold", "knows", "She is the one Wren sold to."),
    _edge("maerin", "sec-hale-brother", "suspects", "A name in the wrong column, twice."),
    _edge("aldous", "sec-chapel-fire", "knows", "He has confessed it to nobody."),
    _edge("aldous", "sec-tithe-drowning", "knows", "It is why he lit the fire."),
    _edge("aldous", "sec-drowned-ledger", "suspects", "He heard what went into the water."),
    _edge("wren", "sec-wren-sold", "knows", "And has not decided whether to do it again."),
    _edge("wren", "sec-drowned-ledger", "knows", "She knows where it went in."),
    _edge("wren", "sec-court-patron", "suspects", "Nobody is that calm about a ledger."),
    _edge("wren", "sec-grimm-water", "knows", "She has watched him refuse a boat."),
    _edge("doran", "sec-hale-brother", "knows", "And files the reports anyway."),
    _edge("doran", "sec-salt-tax", "suspects", "The arithmetic is too clean."),
    _edge("doran", "sec-court-patron", "suspects", "He cannot prove a word of it."),
    _edge("nyssa", "sec-chapel-fire", "knows", "She read it in the basin before he did it."),
    _edge("nyssa", "sec-oracle-blind", "knows", "Her own, and the only one she guards."),
    _edge("nyssa", "sec-tithe-drowning", "knows", "She has counted the winters."),
    _edge("nyssa", "sec-drowned-ledger", "suspects", "The tide told her something was owed."),
    _edge("grimm", "sec-grimm-water", "knows", "And would kill to keep it."),
    _edge("grimm", "sec-court-patron", "knows", "He takes the Court's coin from her hand."),
    # How the cast actually stands with each other (§5.1). Directed, because Aldous
    # trusting Wren says nothing about whether Wren trusts Aldous.
    _edge("aldous", "maerin", "fears", "She has never once raised her voice at him.", weight=0.8),
    _edge("aldous", "wren", "trusts", "She carried him home the night of the fire.", weight=0.7),
    _edge("aldous", "nyssa", "fears", "She looked at him and did not ask.", weight=0.6),
    _edge("wren", "maerin", "resents", "The debt, and the courtesy about the debt.", weight=0.7),
    _edge("wren", "aldous", "loves", "Protectively, and would deny it.", weight=0.5),
    _edge("wren", "doran", "resents", "He has arrested her twice and apologised both times.", weight=0.4),
    _edge("maerin", "doran", "suspects", "He is the only one still writing things down.", weight=0.6),
    _edge("maerin", "wren", "trusts", "As far as coin reaches, which she considers far enough.", weight=0.3),
    _edge("doran", "maerin", "suspects", "Everything about her, and nothing he can file.", weight=0.9),
    _edge("doran", "aldous", "trusts", "The only honest man he can name in the lower town.", weight=0.6),
    _edge("doran", "grimm", "fears", "Professionally.", weight=0.5),
    _edge("nyssa", "aldous", "loves", "The way you love someone you have already grieved.", weight=0.6),
    _edge("nyssa", "maerin", "resents", "She sold the tide by the barrel.", weight=0.5),
    _edge("grimm", "maerin", "trusts", "She pays on the day.", weight=0.6),
    _edge("maerin", "grimm", "allied_with", "For as long as the work lasts."),
]


def _nodes() -> list[tuple[str, str, str, dict]]:
    """``(node_id, type_name, label, metadata)`` for every authored lore node."""
    out: list[tuple[str, str, str, dict]] = []
    for f in FACTIONS:
        out.append((f["id"], "Faction", f["label"], {"name": f["name"], "desc": f["desc"]}))
    for s in SECRETS:
        out.append(
            (
                s["id"],
                "Secret",
                s["label"],
                {
                    "severity": s["severity"],
                    "truth_value": s["truth_value"],
                    "visibility": s["visibility"],
                },
            )
        )
    for e in EVENTS:
        out.append(
            (
                e["id"],
                "Event",
                e["label"],
                {"summary": e["summary"], "kind": e["kind"], "visibility": e["visibility"]},
            )
        )
    return out


def write_lore(
    session: Any,
    *,
    characters: Sequence[Character] = (),
    settings: Sequence[Setting] = (),
    storyline_id: str = SEED_STORYLINE_ID,
) -> tuple[int, int]:
    """Write the world's nodes and every authored edge through ``session``.

    Takes the Neo4j session rather than opening one, so it is unit-testable against a
    fake. ``characters``/``settings`` are materialized here rather than left to the
    first scene load, for two reasons: an authored edge is a MATCH on both endpoints
    and silently does nothing if either is missing, and the cast who are *not* in the
    opening scene — the Oracle, the hired knife — would otherwise never reach the graph
    at all, taking the off-scene ties with them.
    """
    count = 0
    for char in characters:
        graph_writer.upsert_node(
            session,
            node_id=char.id,
            type_name="Character",
            label=char.name,
            storyline=char.storyline_id,
            metadata=graph_writer.node_props_from_character(char),
        )
        count += 1
    for place in settings:
        graph_writer.upsert_node(
            session,
            node_id=place.id,
            type_name="Setting",
            label=place.name,
            storyline=place.storyline_id,
            metadata=graph_writer.node_props_from_setting(place),
        )
        count += 1
    for node_id, type_name, label, metadata in _nodes():
        graph_writer.upsert_node(
            session,
            node_id=node_id,
            type_name=type_name,
            label=label,
            storyline=storyline_id,
            metadata=metadata,
        )
        count += 1
    for edge in EDGES:
        graph_writer.upsert_edge(
            session,
            source_id=edge["source"],
            target_id=edge["target"],
            type_name=edge["type"],
            metadata=edge["metadata"],
        )
    return count, len(EDGES)


def seed_embergate_lore(db: Session) -> tuple[int, int]:
    """Best-effort lore seed, called from preflight. ``(0, 0)`` when the graph is off."""
    if not neo4j.is_enabled():
        return (0, 0)
    storyline = db.get(Storyline, SEED_STORYLINE_ID)
    if storyline is None:
        return (0, 0)
    try:
        with neo4j.write_session() as session:
            return write_lore(
                session,
                characters=list(storyline.characters),
                settings=list(storyline.settings),
            )
    except Exception as exc:  # the Story Graph is advisory — never block startup
        logger.warning("Embergate lore seed skipped: %s", exc)
        return (0, 0)
