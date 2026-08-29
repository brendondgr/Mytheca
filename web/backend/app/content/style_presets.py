"""Built-in style presets — three worked examples of a narrative style guide.

A preset is a **starting point, not a setting**. Applying one copies its text into the
storyline's own fields, where every block stays editable and clearable; nothing stores a
reference to a preset id. That is deliberate: a preset the author later edits must never
silently rewrite a world that already shipped with its text.

The three genres were chosen because they pull in visibly different directions — a mystery
withholds, a romance closes distance, an action beat changes the geometry — which is the
whole claim the feature rests on.

``romance`` is the exact text measured in ``EXP-2026-08-018``
(``docs/research/experiments/EXP-2026-08-018-narrative-style-romance/``). Do not edit it
without either re-running that experiment or recording that the measured text and the
shipped text have diverged. Its ``pacing`` block is present but was **not** exercised by
that run — the planner was never called.

Every block here obeys the two rules from ``content.style_blocks``: **no counts of any
kind**, and **no interpolation**. A test pins the first.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StylePreset:
    """One named, ready-to-apply style guide."""

    id: str
    name: str
    #: One line for the picker — what this preset makes prose *do*, not which genre it names.
    blurb: str
    blocks: dict[str, str] = field(default_factory=dict)


MYSTERY = StylePreset(
    id="mystery",
    name="Mystery",
    blurb="Low and slow. Withholds more than it gives, and ends before it satisfies.",
    blocks={
        "attention": (
            "Dwell on what people do with their hands and their eyes while they are answering "
            "a question about something else. The felt moment is the pause before the answer, "
            "not the answer. Report physical facts flatly, almost administratively — a body, a "
            "broken lock, a wet coat — and let the weight sit in what nobody says about them. "
            "When something is discovered, describe the discovering: the reaching, the light "
            "falling wrong, the smell arriving before the sight. Leave the conclusion for a "
            "character to say out loud, or for no one to say at all."
        ),
        "voice": (
            "People here talk around the thing. Answers arrive one clause short of complete. "
            "Everyone keeps a professional register with strangers and drops it only under "
            "real pressure, and when it drops it should be audible. Nobody explains to another "
            "character what they both already know. A lie is told plainly and at normal volume; "
            "it is the small physical thing accompanying it that gives it away."
        ),
        "pacing": (
            "End a turn slightly before it is satisfying. Prefer narration that changes what is "
            "available — a door now open, a name now spoken — over narration that changes what "
            "is happening. Withhold more than you give, and giving nothing new is often right. "
            "Never resolve a question in the same turn it is asked; let it sit across the "
            "player's next move. The register lives at neutral and tense, and it should get to "
            "tense by staying rather than by escalating."
        ),
        "texture": (
            "Weather and time of day are always present and always slightly wrong for the hour. "
            "Rooms are described by what has been moved in them. People are identified by "
            "profession and posture before name. Paper, keys, coats, ledgers, and the smell of "
            "a building recur."
        ),
        "never": (
            "Never let a character recap the case so far. Never state a suspicion outright when "
            "a character could act on it instead. Never have the narrator confirm that "
            "something is important."
        ),
        "signature": "Low and slow. Withhold more than you give; end before it satisfies.",
    },
)

#: The measured preset — see the module docstring before editing any block below.
ROMANCE = StylePreset(
    id="romance",
    name="Romance",
    blurb="Close and unsaid. One shift in the distance per turn, and only one person is brave.",
    blocks={
        "attention": (
            "Spend the prose on proximity and on the body's small betrayals: where someone's "
            "hands go when they have nothing to hold, who looks away first, the half-second of "
            "a decision not to say something. Interiority is the point — a character noticing "
            "their own reaction, and mistrusting it, is worth more than any event. Physical "
            "detail matters only in relation to another person: a room is warm because of who "
            "is in it. Skip logistics; arrive at the moment already begun."
        ),
        "voice": (
            "People say slightly less than they mean, and the gap between the two is where the "
            "scene lives. Kindness is done, not announced. Humour is deflection and should "
            "arrive exactly when someone is about to be honest. When someone is finally direct, "
            "let the sentence be plain and short — no ornament — because the plainness is the "
            "event."
        ),
        "pacing": (
            "A turn is one shift in the distance between two people, and it should be nameable: "
            "closer, further, held. Prefer letting characters speak over narrating around them "
            "— the narrator's job here is to hold a silence or move a body, not to advance a "
            "plot. Never let both people be brave in the same turn; if one reaches, the other "
            "should flinch, deflect, or accept, and the turn ends there. Register runs light to "
            "tense and rarely grave; tense here means emotional exposure, not danger."
        ),
        "texture": (
            "Shared objects carry the history — the same cup, the same walk home, the coat that "
            "keeps getting lent. Time of day is late or too early. Other people exist mainly as "
            "interruption."
        ),
        "never": (
            "Never narrate a feeling a character could show. Never have someone explain the "
            "relationship to the person they are in it with. Never resolve a confession in the "
            "turn it is made."
        ),
        "signature": (
            "Close and unsaid — one shift in the distance, and only one person is brave."
        ),
    },
)

ACTION = StylePreset(
    id="action",
    name="Action",
    blurb="Fast, physical, consequential. Every beat changes the geometry of the room.",
    blocks={
        "attention": (
            "Write the mechanics: footing, weight, distance, what is in each hand, what is "
            "between the two of them, what breaks. Every blow either lands, misses, or is "
            "turned, and the prose says which before it says anything else. Injury is specific "
            "and immediate — where, how deep, what it stops the person doing — and it persists "
            "into every beat after it. Pain is reported in what a body can no longer do, not in "
            "adjectives. Fear shows as a mistake."
        ),
        "voice": (
            "Short. Clipped under load. People speak in imperatives, warnings and names — "
            "\"left\", \"down\", \"behind you\" — and they do not finish sentences while moving. "
            "Anyone delivering a full speech mid-fight is doing it because control is their "
            "move, and it should read as arrogance. Breath is audible in the punctuation."
        ),
        "pacing": (
            "Lead with narration and follow every move through to its consequence in the same "
            "beat — the swing lands, the table goes over, the door closes on someone. Let a "
            "character speak only when the action opens a gap for them, and end the turn on a "
            "changed position: someone moved, something broke, an exit closed. Never end a turn "
            "on stasis or on deliberation. Register sits at tense and drops to grave the moment "
            "a body is failing."
        ),
        "texture": (
            "The environment is inventory: what can be thrown, climbed, hidden behind, jammed. "
            "Distances are stated in strides and rooms. Equipment is named and runs out."
        ),
        "never": (
            "Never slow into interior monologue mid-exchange. Never state a plan and then "
            "execute it — do it, and let the reader work out that it was a plan. Never let two "
            "exchanges of blows read the same way twice."
        ),
        "signature": "Fast, physical, consequential. Every beat changes the geometry.",
    },
)

#: Picker order — every surface renders them in exactly this order.
STYLE_PRESETS: tuple[StylePreset, ...] = (MYSTERY, ROMANCE, ACTION)

_BY_ID = {preset.id: preset for preset in STYLE_PRESETS}


def ids() -> list[str]:
    """Every built-in preset id, in picker order."""
    return [preset.id for preset in STYLE_PRESETS]


def get(preset_id: str | None) -> StylePreset | None:
    """One built-in preset by id, or ``None``.

    Falls back rather than raising: the drafting agent may name a preset that does not
    exist, and the correct answer there is "write one instead", not a 500.
    """
    return _BY_ID.get((preset_id or "").strip())
