"""Embergate seed.

Mirrors ``web/frontend/lib/seed-data.ts`` so a fresh database shows the same world
the frontend used to render from memory. Idempotent: it only writes when the
storyline is absent, so it is safe to call on every startup. Also seeds a handful
of baseline stat definitions to exercise the stat seam (no UI yet — guidance
paths are references; the Markdown files come later).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Character, Scenario, Setting, StatDefinition, Storyline

SEED_STORYLINE_ID = "embergate"

_CHARACTERS: list[dict] = [
    {"id": "maerin", "name": "Maerin Voss", "role": "Antagonist", "color": "#8E2B1C", "mono": "MV", "traits": "Patient · Calculating · Velvet-tongued", "speech": "Measured and courteous; never raises her voice.", "goal": "Keep the salt routes hidden a little longer.", "secret": "She answers to the Drowned Court."},
    {"id": "aldous", "name": "Brother Aldous", "role": "Reluctant Ally", "color": "#A8762A", "mono": "BA", "traits": "Guilt-ridden · Gentle · Stubborn", "speech": "Soft, apologetic, scripture half-remembered.", "goal": "Atone for the fire he failed to stop.", "secret": "He set the fire."},
    {"id": "wren", "name": "Wren Calloway", "role": "Wildcard", "color": "#2F7D6B", "mono": "WC", "traits": "Quick · Wry · Loyal-ish", "speech": "Clipped, sardonic, thick with dock-cant.", "goal": "Earn enough coin to leave Embergate for good.", "secret": "She has sold you out once already."},
    {"id": "doran", "name": "Captain Doran Hale", "role": "Lawful Blocker", "color": "#3A5A78", "mono": "DH", "traits": "Dutiful · Rigid · Honourable", "speech": "Formal and terse — strictly by the book.", "goal": "Restore order to a rotting harbor.", "secret": "His own brother runs the Drowned Market."},
    {"id": "nyssa", "name": "Nyssa, Oracle of Salt", "role": "Guide", "color": "#6B4A8A", "mono": "N", "traits": "Cryptic · Serene · Knowing", "speech": "Slow and layered; she speaks in tides.", "goal": "See the vision through to its bitter end.", "secret": "She is going blind to the future, not the world."},
    {"id": "grimm", "name": "Grimm", "role": "Threat", "color": "#5A534A", "mono": "G", "traits": "Brutal · Brief · Bought", "speech": "Few words, and most of them threats.", "goal": "Get paid and get gone.", "secret": "He is terrified of deep water."},
]

_SETTINGS: list[dict] = [
    {"id": "saltworn", "name": "The Saltworn Tavern", "type": "Social Hub", "desc": "Lamplit and low-beamed — every secret here has a price."},
    {"id": "harbor", "name": "Embergate Harbor", "type": "Exploration", "desc": "Fog, brine, and the groan of a hundred moored hulls."},
    {"id": "keep", "name": "Tidewatch Keep", "type": "Fortress", "desc": "The guard's stone fist clenched over the bay."},
    {"id": "market", "name": "The Drowned Market", "type": "Black Market", "desc": "Below the tideline, where nothing is illegal."},
    {"id": "sanctum", "name": "The Oracle's Sanctum", "type": "Sacred", "desc": "Salt-circles and the hush before a truth."},
]

_SCENARIOS: list[dict] = [
    {
        "id": "embergate",
        "title": "The Embergate Conspiracy",
        "genre": "Intrigue",
        "tone": "Tension · rising",
        "goal": "Uncover who smuggles sorcerer's salt through the harbor — before the Tidewatch does.",
        "cast_ids": ["maerin", "aldous", "wren", "doran"],
        "setting_id": "saltworn",
        "opening": "Lamplight gutters across the Saltworn's long tables. Maerin Voss has not looked up from her ledger once — which is how you know she has already seen you.",
        "branches": [
            {"label": "Confront Maerin at her table", "check": "Insight · DC 15", "outcome": "She lets a name slip — Suspicion +2", "tag": "check_request"},
            {"label": "Bargain — silence for the ledger", "check": "Persuasion · DC 20", "outcome": "Gain the smuggling routes — Trust −1", "tag": "branch_choices"},
            {"label": "Expose her to Captain Hale", "check": "Deception · DC 15", "outcome": "Hale's favour +3 — the room turns on you", "tag": "state_update"},
        ],
    },
    {
        "id": "salt",
        "title": "Salt & Secrets",
        "genre": "Social",
        "tone": "Quiet · charged",
        "goal": "Earn the Oracle's trust so she will read the drowned ledger aloud.",
        "cast_ids": ["nyssa", "aldous", "wren"],
        "setting_id": "sanctum",
        "opening": "Salt-circles ring the cold stone floor. The Oracle's breathing is the only sound — slow as a tide that has all the time in the world.",
        "branches": [
            {"label": "Offer a true confession", "check": "Insight · DC 15", "outcome": "The Oracle softens — Trust +2", "tag": "check_request"},
            {"label": "Read the salt-circles yourself", "check": "Arcana · DC 20", "outcome": "A vision, half-understood", "tag": "narration"},
            {"label": "Lie about why you came", "check": "Deception · DC 20", "outcome": "She knows — Patience −2", "tag": "state_update"},
        ],
    },
    {
        "id": "heist",
        "title": "The Drowned Market Heist",
        "genre": "Exploration · Combat",
        "tone": "Volatile",
        "goal": "Lift the harbor ledger from the vault before the tide returns to flood it.",
        "cast_ids": ["wren", "grimm", "doran"],
        "setting_id": "market",
        "opening": "The Drowned Market reeks of brine and tallow. Somewhere above, the bells begin to count down the turning of the tide.",
        "branches": [
            {"label": "Slip past the tide-wardens", "check": "Stealth · DC 15", "outcome": "Reach the vault unseen", "tag": "check_request"},
            {"label": "Pay Grimm to look away", "check": "Persuasion · DC 10", "outcome": "Coin −50 — a clear path", "tag": "branch_choices"},
            {"label": "Take the ledger by force", "check": "Athletics · DC 20", "outcome": "Alarm raised — roll Initiative", "tag": "character_action"},
        ],
    },
]

# Baseline stat schema for the world. These exercise the stat seam; the guidance
# files they reference are authored in a later phase.
_STATS: list[dict] = [
    {"key": "health", "display_name": "Health", "description": "Physical condition and vitality.", "min": 0, "max": 100, "default": 100, "visibility": "public", "guidance": "stats/health.md"},
    {"key": "suspicion", "display_name": "Suspicion", "description": "How wary others are of you.", "min": 0, "max": 10, "default": 0, "visibility": "public", "guidance": "stats/suspicion.md"},
    {"key": "trust", "display_name": "Trust", "description": "Standing with allies.", "min": -5, "max": 5, "default": 0, "visibility": "public", "guidance": "stats/trust.md"},
    {"key": "patience", "display_name": "Patience", "description": "How much forbearance a character has left.", "min": 0, "max": 10, "default": 5, "visibility": "public", "guidance": "stats/patience.md"},
]


def seed_if_empty(session: Session) -> bool:
    """Seed the Embergate world if absent. Returns True if it wrote, else False."""
    if session.get(Storyline, SEED_STORYLINE_ID) is not None:
        return False

    storyline = Storyline(
        id=SEED_STORYLINE_ID,
        title="Embergate",
        genre="Maritime Intrigue",
        tagline="A rotting harbor town where every secret has a price.",
        premise=(
            "Embergate clings to a drowned coast where the tide reclaims a little "
            "more of the lower town every year. Salt has eaten the foundations, the "
            "lamp oil is rationed, and the harbor guild rules through debt rather "
            "than law.\n\n"
            "Three powers circle the failing port: the Drowned Court that runs the "
            "smuggling lanes, the Tidewatch that polices them, and the chapel whose "
            "flooded undercroft hides older bargains. Everyone owes someone, and the "
            "ledger is always coming due."
        ),
        symbol="◆",
        symbol_color="#C8862A",
        position=0,
    )
    for i, char in enumerate(_CHARACTERS):
        storyline.characters.append(Character(position=i, **char))
    for i, place in enumerate(_SETTINGS):
        storyline.settings.append(Setting(position=i, **place))
    for i, scenario in enumerate(_SCENARIOS):
        storyline.scenarios.append(Scenario(position=i, **scenario))
    for stat in _STATS:
        storyline.stat_definitions.append(StatDefinition(**stat))

    session.add(storyline)
    session.commit()
    return True
