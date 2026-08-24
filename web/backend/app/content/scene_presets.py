"""Named scene presets — **empty, and deliberately so.**

There were four (*Fast banter*, *Slow burn*, *Cinematic*, *Interrogation*), and every one of
them was defined **entirely** in terms of `max_turns` and `beat_length`: how many beats a
message produces and how much a character says at once. Both of those controls were removed
on 2026-08-24 — a scene's pacing is the planner's judgement now, not three numbers a player
sets before they have read a word of it — which left a preset with nothing to name.

So the catalogue is empty rather than the module deleted. The route
(`GET /api/options/scene-presets`) still answers, with `[]`, so no client 404s; the composer's
picker already hid itself on an empty list, so the UI needed no special case. `scenePreset`
survives as a column and is no longer written.

**If presets come back, they should not come back as this.** The reason nobody used the old
ones is the reason the underlying controls went: they bundled numbers, and knowing which
combination of numbers you want is not a thing a player can know. A preset worth having would
name a way of *reading* — and would have to be expressed as guidance the planner reads, not as
a ceiling that overrides it.
"""

from __future__ import annotations

#: No built-ins. See the module docstring before adding one.
BUILTIN_SCENE_PRESETS: list[dict] = []

#: The ids, for schema validation. Empty, so `ScenePresetId` admits nothing and a request
#: naming a preset is rejected at the boundary rather than silently ignored.
SCENE_PRESET_IDS: tuple[str, ...] = tuple(p["id"] for p in BUILTIN_SCENE_PRESETS)


def preset(preset_id: str | None) -> dict | None:
    """One preset by id, or ``None``. Always ``None`` while the catalogue is empty."""
    if not preset_id:
        return None
    return next((p for p in BUILTIN_SCENE_PRESETS if p["id"] == preset_id), None)
