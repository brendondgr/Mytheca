"""The free-text prompt: one cached prefix, one instruction per call.

Free-text mode makes several model calls for a single turn — look up what it does not know,
write the checklist, write the body, grade the body, and sometimes continue it. That is more
calls than the structured engine makes for a whole scene, and it would be an obvious
regression if each of them re-read a fresh prompt.

So they don't. **Every call in a free-text turn is composed here**, and every one of them is
byte-identical up to its final block:

* ``system_message`` — the output contract, the style guide, the world, the place, and the
  **whole cast**. Identical for every call of every turn until the world, the scene or the
  roster changes. Paid once and read from cache after that.
* ``history_block`` — the scene's memory, the block-anchored transcript, this turn so far.
  Append-only, and its start is held still by ``buffer.anchored_turns``.
* ``tail`` — the live stat readings, whatever was looked up, the player's tagged files, and
  **the one instruction for this particular call**. Small, and re-read every time.

The load-bearing decision is where a character's *statistics* go. The owner asked for the
whole cast and their stats in the prompt, and those are two different kinds of fact: identity
(name, role, background, manner, voice) does not change during a scene, while a stat value
changes the first time anyone is hurt or stops trusting someone. Putting the values in the
cached block would invalidate the largest region of the prompt on the most frequently
changing thing in the game. They live in the tail instead — a few hundred tokens, re-read per
call — and the cast block stays still. Both are present; each sits in the region it belongs
to.

There is a second, quieter win. In the structured engine the volatile tail is re-read *per
beat*, so a five-beat turn pays it five times. A free-text turn writes one body however long
it runs, so length is nearly free in prefix terms.
"""

from __future__ import annotations

from app.agents import prompt_registry
from app.services import stat_render
from app.services.assembler import CastMember, TurnContext, format_voice_samples

#: How many of a character's authored voice samples reach the shared cast block.
#:
#: The structured engine gives ONE speaker every sample it has, selected by the beat's
#: register. Free-text puts every character in one prompt, so the same generosity would be a
#: wall of exemplars the model has to attribute for itself — and the samples of whoever is
#: listed last would be read as the voice of whoever speaks first. Two apiece keeps each
#: entry recognisably one person's.
#:
#: This is the cost of one body, stated where it is paid rather than hidden: per-character
#: prompt isolation is the thing this mode sells.
_CAST_SAMPLES = 2


def _cast_entry(member: CastMember, number: int) -> str:
    """One character's stable identity — everything about them that a scene cannot change."""
    lines = [f"[{number}] {member.name} — {member.role}"]
    if member.traits:
        lines.append(f"    Who they are: {member.traits}")
    if member.speech:
        lines.append(f"    How they talk: {member.speech}")
    samples = format_voice_samples(member.voice_sample_rows) or member.voice_samples
    if samples:
        rows = [row for row in samples.strip().splitlines() if row.strip()][: _CAST_SAMPLES * 2]
        if rows:
            lines.append("    Sounds like:")
            lines.extend(f"    {row.strip()}" for row in rows)
    return "\n".join(lines)


def full_cast_block(ctx: TurnContext) -> str:
    """Every character in the scene, in roster order, identity only.

    **Everyone**, not a selection — the owner's call, and it is also the cheaper answer:
    a block that changes depending on who is expected to speak would be rebuilt every turn,
    where this one is written once and read from cache for the rest of the scene.

    Absent characters are included and *marked*. A scene that has written someone out still
    has to be able to refer to them, and dropping them from the roster mid-scene would edit
    the cached prefix for no gain.
    """
    if not ctx.cast:
        return ""
    entries = []
    for index, member in enumerate(ctx.cast):
        entry = _cast_entry(member, index + 1)
        if not member.is_present:
            entry += f"\n    NOT IN THE SCENE ({member.presence}) — do not give them lines."
        entries.append(entry)
    return "THE CAST\n" + "\n\n".join(entries)


def live_state(ctx: TurnContext) -> str:
    """Every present character's current stat readings, in band language, third person.

    Not ``stat_render.render_character_stats``, which addresses one speaker as "you" and is
    right for a prompt that voices exactly one person. A free-text body is written *about*
    the room, so the same values have to read as observations rather than as a briefing to
    the person they describe.
    """
    if not ctx.stat_defs:
        return ""
    blocks: list[str] = []
    for member in ctx.cast:
        if not member.is_present or not member.stats:
            continue
        lines: list[str] = []
        for sd in ctx.stat_defs:
            key = getattr(sd, "key", None)
            if key is None or key not in member.stats:
                continue
            value = int(member.stats[key])
            name = getattr(sd, "display_name", None) or key
            headline = f"{name} {value}/{getattr(sd, 'max', value)}"
            band = stat_render.current_band(getattr(sd, "bands", None), value)
            meaning = ""
            if band:
                label = str(band.get("label") or "").strip()
                if label:
                    headline += f" ({label})"
                meaning = stat_render.substitute_character(
                    band.get("description"), member.name
                )
            lines.append(f"  - {headline}{f' — {meaning}' if meaning else ''}")
        if lines:
            blocks.append(f"{member.name}:\n" + "\n".join(lines))
    if not blocks:
        return ""
    return (
        "WHERE EVERYONE STANDS RIGHT NOW (their live condition — let it show in what they "
        "do and how they speak, and never state a number):\n" + "\n".join(blocks)
    )


def system_message(ctx: TurnContext) -> str:
    """The cached prefix. Identical for every call of every turn in a scene.

    Ordered widest scope first, which is what a prefix cache rewards: the output contract is
    the same bytes in every world, the style guide is shared by every world running the same
    preset, the world primer by every scene of one world, and the cast by every call of one
    scene. Nothing below this line may vary per call — that is what the tail is for.
    """
    parts = [ctx.prompts.get(FREETEXT_CONTRACT, _CONTRACT)]

    style = ctx.style.render_prefix()
    if style:
        parts.append(style)

    scenario = ctx.scenario
    title = getattr(scenario, "title", "")
    parts.append(f"WORLD: {title}" if title else "WORLD")
    if ctx.world_primer:
        parts.append(f"WORLD PRIMER\n{ctx.world_primer}")

    if ctx.stat_guidance:
        guide = [
            f"## {sd.display_name} ({sd.key}, {sd.min}–{sd.max})\n{text}"
            for sd in ctx.stat_defs
            if (text := ctx.stat_guidance.get(sd.key))
        ]
        if guide:
            parts.append("WHAT THE STATS MEAN\n" + "\n\n".join(guide))

    if ctx.setting is not None:
        flavor = (
            ctx.setting.atmosphere or ctx.setting.current_state or ctx.setting.desc or ""
        )
        parts.append(
            f"WHERE THIS HAPPENS: {ctx.setting.name}"
            + (
                f" — {flavor} (the place as authored; how it feels right now is whatever "
                "the beats show)"
                if flavor
                else ""
            )
        )

    cast = full_cast_block(ctx)
    if cast:
        parts.append(cast)
    return "\n\n".join(part for part in parts if part)


def history_block(ctx: TurnContext, turn_beats: list[dict]) -> str:
    """The scene so far — append-only, and rendered by the one transcript renderer.

    Imported at call time rather than at module scope: ``character_turn_agent`` imports the
    assembler, which imports this module's siblings, and a top-level import here closes that
    ring. Sharing the renderer matters more than the tidier import — two renderings of one
    transcript is how the two engines end up disagreeing about what the player said.
    """
    from app.agents.character_turn_agent import _transcript

    parts: list[str] = []
    if ctx.history_summary:
        parts.append(f"EARLIER IN THIS SCENE (summary):\n{ctx.history_summary}")
    transcript = _transcript(ctx, turn_beats)
    if transcript:
        parts.append(f"THE SCENE SO FAR:\n{transcript}")
    return "\n\n".join(parts)


def tail(
    ctx: TurnContext,
    *,
    instruction: str,
    lore: str | None = None,
    pov: CastMember | None = None,
    extra: list[str] | None = None,
) -> str:
    """Everything that changes, ending on what this call is being asked to do.

    ``instruction`` is last on purpose, and the reason is not only cache: it is the strongest
    attention position in the prompt, so the composition that keeps the prefix stable is also
    the one that keeps the model on task.
    """
    parts: list[str] = []

    state = live_state(ctx)
    if state:
        parts.append(state)

    fetched = ctx.retrieved_lore if lore is None else lore
    if fetched and fetched.strip():
        parts.append(fetched.strip())
    if ctx.tagged_notes:
        parts.append(ctx.tagged_notes.strip())

    if pov is not None:
        # The one rule that has to survive every call: the player's character is theirs.
        # In the structured engine this is enforced structurally — the POV character is
        # dropped from the selectable roster — but a free-text body has no roster to drop
        # them from, so it is a prompt rule or it is nothing.
        parts.append(
            f"{pov.name} is played by the person you are writing for. What {pov.name} just "
            f"said and did is above, and it is the only thing {pov.name} does in this "
            f"passage. Show how the room answers it. Never write new dialogue or a new "
            f"decision for {pov.name}; you may describe how others see them."
        )
    else:
        parts.append(
            'Lines labelled "Direction:" come from outside the story. Nobody in the scene '
            "said them and there is nobody to address — no \"you\" anywhere outside a "
            "character's own quoted speech. Do what they ask without quoting them, "
            "answering them, or acknowledging that they were said."
        )

    if ctx.directed_at:
        target = ctx.cast_by_id(ctx.directed_at)
        if target is not None:
            parts.append(f"The player aimed this turn at {target.name}.")

    parts.extend(line for line in (extra or []) if line and line.strip())
    parts.append(instruction.strip())
    return "\n\n".join(part for part in parts if part)


def messages(
    ctx: TurnContext,
    turn_beats: list[dict],
    *,
    instruction: str,
    lore: str | None = None,
    pov: CastMember | None = None,
    extra: list[str] | None = None,
) -> list[dict[str, str]]:
    """The full message list for ONE free-text call.

    Every call in the turn goes through here, which is the only way the shared prefix is
    actually shared: two call sites assembling "the same" prompt independently would drift on
    the first edit, and the drift would be invisible — a cache miss is slower, never wrong.
    """
    history = history_block(ctx, turn_beats)
    user = tail(ctx, instruction=instruction, lore=lore, pov=pov, extra=extra)
    return [
        {"role": "system", "content": system_message(ctx)},
        {"role": "user", "content": f"{history}\n\n{user}" if history else user},
    ]


FREETEXT_CONTRACT = prompt_registry.FREETEXT_CONTRACT
_CONTRACT = prompt_registry.default(FREETEXT_CONTRACT)
