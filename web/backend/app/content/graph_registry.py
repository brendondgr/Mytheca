"""The seed Type Registry — the built-in node and edge types every storyline
starts with (§5 of the Story-Graph brief).

This is *data*, not engine logic: ``services/type_registry.seed_builtin_types``
inserts each entry as a global ``GraphTypeDefinition`` (``storyline_id = NULL``,
``status = built_in``). Users extend the catalogue per-storyline the exact same
way — there is no structural difference between built-in and user-defined types
(Principle 3). Edge valence is declared here because §1.3's net-lean computation
cannot place an edge without it.

Field ``kind`` values: ``numeric`` (with min/max), ``enum`` (with options),
``prose`` (free text), ``reference`` (a value that should really be an edge),
``scalar`` (a plain non-traversed value).
"""

from __future__ import annotations

from app.models.graph_type import (
    KIND_EDGE,
    KIND_NODE,
    VALENCE_NEGATIVE,
    VALENCE_NEUTRAL,
    VALENCE_POSITIVE,
)

# The generic edge metadata every relationship carries (§1.2/§1.3). Not part of a
# type's own field schema — the writer attaches these to every edge regardless of
# type, so they live here as the shared convention (and are documented for agents).
SHARED_EDGE_METADATA = ["weight", "contributions", "visibility", "status", "last_updated"]

# A turn-relative decay default for feeling edges (§1.3 — connections fade without
# reinforcement and linger at a low floor rather than being deleted).
_FEELING_DECAY = {"half_life_turns": 40, "floor": 0.05}


def _node(type_name: str, description: str, fields: list[dict]) -> dict:
    return {
        "kind": KIND_NODE,
        "type_name": type_name,
        "description": description,
        "field_schema": fields,
        "valence": None,
        "decay": None,
    }


def _edge(
    type_name: str,
    description: str,
    valence: str,
    *,
    decay: dict | None = None,
    fields: list[dict] | None = None,
) -> dict:
    return {
        "kind": KIND_EDGE,
        "type_name": type_name,
        "description": description,
        "field_schema": fields or [],
        "valence": valence,
        "decay": decay,
    }


# ---- node types (§5.1–§5.5 + the reified consequence record §6.4) -----------

BUILTIN_NODE_TYPES: list[dict] = [
    _node(
        "Character",
        "A person in the storyline — the anchor node (§3/§5.1). Descriptive identity "
        "lives in metadata; feelings toward others are directed edges, not fields.",
        [
            {"name": "appearance", "kind": "prose", "description": "Physical appearance."},
            {"name": "background", "kind": "prose", "description": "Backstory."},
            {"name": "personality", "kind": "prose", "description": "Temperament, values, fears."},
            {"name": "traits", "kind": "prose", "description": "Short trait line."},
            {"name": "speech", "kind": "prose", "description": "Voice / speech style."},
            {"name": "goal", "kind": "prose", "description": "Driving goal."},
            {"name": "secret", "kind": "prose", "description": "What they hide (often also a Secret node)."},
        ],
    ),
    _node(
        "Setting",
        "A place where events occur and to which characters/factions connect (§4). "
        "Description + current state are metadata; presence/control/history are edges.",
        [
            {"name": "desc", "kind": "prose", "description": "Base description."},
            {"name": "atmosphere", "kind": "prose", "description": "Sensory character."},
            {"name": "features", "kind": "prose", "description": "Notable physical features."},
            {"name": "current_state", "kind": "prose", "description": "Mutable here-and-now."},
            {"name": "kind", "kind": "scalar", "description": "Setting type, e.g. Social Hub."},
        ],
    ),
    _node(
        "Event",
        "A thing that happened — the convergence point linking the characters, the "
        "setting, and the consequences involved (§5.3). Home of n-ary facts.",
        [
            {"name": "summary", "kind": "prose", "description": "What happened."},
            {"name": "kind", "kind": "scalar", "description": "Event kind."},
            {"name": "visibility", "kind": "enum", "options": ["public", "private"], "default": "public"},
        ],
    ),
    _node(
        "Secret",
        "A discrete fact some characters know and others don't (§5.4). Its meaning is "
        "who-knows-it; it propagates along trust edges. Some 'secrets' are false.",
        [
            {"name": "severity", "kind": "numeric", "min": 0, "max": 1, "description": "How damaging."},
            {"name": "truth_value", "kind": "enum", "options": ["true", "false", "unknown"], "default": "true"},
            {"name": "visibility", "kind": "enum", "options": ["public", "private"], "default": "private"},
        ],
    ),
    _node(
        "Faction",
        "An organization characters belong to (§5.5). Membership and rivalry are "
        "traversable: 'who's in House Vell?', 'are they enemies?'.",
        [
            {"name": "name", "kind": "scalar", "description": "Faction name."},
            {"name": "desc", "kind": "prose", "description": "What it is and wants."},
        ],
    ),
    _node(
        "Consequence",
        "The reified consequence record (§6.4) — one shared type attached to an edge "
        "contribution, an acquired trait, or a setting timeline entry. Gives every "
        "change uniform decay, audit, and status, and is queryable in aggregate "
        "('every consequence from scenario X').",
        [
            {"name": "reason", "kind": "prose", "description": "Why the change happened."},
            {"name": "origin", "kind": "scalar", "description": "{scenario, turn} it originated from."},
            {"name": "delta", "kind": "numeric", "description": "Signed magnitude this entry moved the target."},
            {"name": "status", "kind": "enum", "options": ["active", "faded", "expired"], "default": "active"},
        ],
    ),
]

# ---- edge types (§5.1 feelings, §4.3 structure, §5.4/§5.5 relations) --------

BUILTIN_EDGE_TYPES: list[dict] = [
    # Directed character→character feelings (§5.1) — these decay without reinforcement.
    _edge("loves", "A character's love toward another (§5.1).", VALENCE_POSITIVE, decay=_FEELING_DECAY),
    _edge("trusts", "A character's trust toward another.", VALENCE_POSITIVE, decay=_FEELING_DECAY),
    _edge("fears", "A character's fear of another.", VALENCE_NEGATIVE, decay=_FEELING_DECAY),
    _edge("resents", "A character's resentment of another.", VALENCE_NEGATIVE, decay=_FEELING_DECAY),
    # Inter-faction / inter-character standing.
    _edge("allied_with", "An alliance between two parties (§5.5).", VALENCE_POSITIVE),
    _edge("at_war_with", "Open hostility between two parties (§5.5).", VALENCE_NEGATIVE),
    # Knowledge (§5.4) — who knows / suspects what; secrets propagate along these.
    _edge("knows", "A character knows a secret/fact (§5.4).", VALENCE_NEUTRAL),
    _edge("suspects", "A character suspects a secret/fact (§5.4).", VALENCE_NEUTRAL),
    # Membership (§5.5).
    _edge("member_of", "A character belongs to a faction (§5.5).", VALENCE_NEUTRAL),
    # Character/faction ↔ setting (§4.3).
    _edge("from", "A character's origin/home setting (§4.3).", VALENCE_NEUTRAL),
    _edge("present_at", "A character is currently at a setting (§4.3 live casting).", VALENCE_NEUTRAL),
    _edge("controls", "A character or faction holds power over a setting (§4.3).", VALENCE_NEUTRAL),
    _edge("claims", "A character or faction claims a setting (§4.3).", VALENCE_NEUTRAL),
    _edge("connected_to", "Spatial adjacency between two settings (§4.3).", VALENCE_NEUTRAL),
    # Event links (§4.4) — the Setting–Event–Character convergence.
    _edge("occurred_at", "An event happened at a setting (§4.3/§4.4).", VALENCE_NEUTRAL),
    _edge("involved", "An event involved a character (§4.4).", VALENCE_NEUTRAL),
    # Subject pointer for a Secret (§5.4 'subject' — who it's about).
    _edge("subject", "A secret is about a character (§5.4).", VALENCE_NEUTRAL),
    # Episodic memory. The edge is a graph *mirror* of a `character_memories` row, which
    # is canonical in Postgres — so unlike the feeling edges it carries no decay here:
    # fade and reinforcement are computed by `services.memory_recall` over the row.
    _edge("remembers", "A character carries a memory of an event.", VALENCE_NEUTRAL),
]

BUILTIN_TYPES: list[dict] = BUILTIN_NODE_TYPES + BUILTIN_EDGE_TYPES
