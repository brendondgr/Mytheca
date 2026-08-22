"""Named scene presets — a kind of scene, instead of three numbers.

The scene-config popover asks a player to set `max_turns`, `suggestions_count` and
`beat_length` individually. Each is honestly labelled, and the combination is still a thing
nobody picks: knowing what each control does is not the same as knowing which *combination*
produces the scene you want. A preset answers the question the player actually has.

Every preset writes through the ordinary pinned path — it is a statement about the scene, not
about one turn — and nothing here is a new setting. A preset is a **named point in the space
the existing controls already describe**, which is why it can be abandoned at any moment by
moving one control (the UI then reads *modified*) or by choosing Custom.

Two things are deliberately absent:

* ``context_beats`` — the transcript window fits itself to the model's real context budget
  (``services/context_budget``); asking the player for a depth is asking a question only the
  app can answer, and bundling one into a preset would reintroduce that question sideways.
* ``planner_mode`` — turning the planner off changes what the app *is*, not how fast a scene
  reads, and hiding that inside a mood label would be the wrong kind of convenience.

The values are chosen to be recognisably different from each other *and* from the defaults
(``max_turns`` 5, ``suggestions_count`` 4, ``beat_length`` "medium"): a preset that lands
within one step of the default teaches the player nothing.
"""

from __future__ import annotations

#: The built-in presets. ``blurb`` is rendered at the point of use and names the **trade**,
#: not the numbers — the numbers are visible in the controls directly underneath it, and
#: restating them in prose would only tell the reader what they can already see.
BUILTIN_SCENE_PRESETS: list[dict] = [
    {
        "id": "fast_banter",
        "label": "Fast banter",
        "blurb": (
            "Short beats, quick exchanges, plenty of follow-ups. Scenes move; nobody "
            "monologues."
        ),
        "values": {"maxTurns": 3, "beatLength": "short", "suggestionsCount": 4},
    },
    {
        "id": "slow_burn",
        "label": "Slow burn",
        "blurb": (
            "Long beats, fewer of them. Each message takes noticeably longer to play out."
        ),
        "values": {"maxTurns": 6, "beatLength": "long", "suggestionsCount": 2},
    },
    {
        "id": "cinematic",
        "label": "Cinematic",
        "blurb": (
            "The most beats per message and no follow-ups — the scene carries itself. The "
            "longest turns in the app."
        ),
        "values": {"maxTurns": 8, "beatLength": "medium", "suggestionsCount": 0},
    },
    {
        "id": "interrogation",
        "label": "Interrogation",
        "blurb": (
            "Two beats a message: you ask, someone answers. Nothing runs away from you."
        ),
        "values": {"maxTurns": 2, "beatLength": "medium", "suggestionsCount": 3},
    },
]

#: The ids, for schema validation. Derived rather than retyped so a fifth preset only has to
#: be added in one place.
SCENE_PRESET_IDS: tuple[str, ...] = tuple(p["id"] for p in BUILTIN_SCENE_PRESETS)


def preset(preset_id: str | None) -> dict | None:
    """One preset by id, or ``None`` — including for ``None``, which means *Custom*."""
    if not preset_id:
        return None
    return next((p for p in BUILTIN_SCENE_PRESETS if p["id"] == preset_id), None)
